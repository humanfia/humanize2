"""Tests for the minimal agent library.

The shared process plumbing is exercised with `sh`-backed fake sessions, which take their script
as the prompt. The concrete backends are driven through `run()` against fake CLIs on PATH, so what
is checked is the command they build and the session they resume, not how they build it.
"""

from __future__ import annotations

import errno
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.agents import (
    AgentBase,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CommandSessionBase,
    Question,
    Stopped,
)
from hmz.machines import AnchoredConfig
from tests.stubs import HereAnchor, ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CODEX_ID = "019fa62b-d9e1-7b73-be84-bd70260e1cf6"

CONFIG = AgentConfig(model="m", effort="high")


class _EchoSession(CommandSessionBase):
    """Runs `cat`, echoing the prompt back on stdout -- the only fake on the stdin path."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["cat"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        return "echo"


class _EchoAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> _EchoSession:
        return _EchoSession(self, cwd)


class _StubbornSession(CommandSessionBase):
    """Fills its own stdout before reading a byte of the prompt, which a pipe cannot hold."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", "yes answer | head -c 150000; cat > /dev/null"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        return "stubborn"


class _StubbornAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> _StubbornSession:
        return _StubbornSession(self, cwd)


class _QuitterSession(CommandSessionBase):
    """Rejects the call and exits before reading a byte of the prompt still being written."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", "echo 'bad flag' >&2; exit 4"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        raise AssertionError("a failed turn must never be asked for a session id")


class _QuitterAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> _QuitterSession:
        return _QuitterSession(self, cwd)


@dataclass(frozen=True)
class _Call:
    """One invocation of a fake CLI: what it was asked for, and what it was fed."""

    argv: list[str]
    stdin: str


@dataclass(frozen=True)
class _FakeCLIs:
    """A fake `claude` on PATH, recording the calls it was made with."""

    log: Path

    def calls(self) -> list[_Call]:
        return [_Call(**json.loads(line)) for line in self.log.read_text().splitlines()]


@pytest.fixture
def clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeCLIs:
    """Installs a fake CLI per backend, printing the transcript that backend really prints."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    # Claude is held open and spoken to in JSON, so its fake answers a line at a time and
    # records the launch and each thing said as calls of their own.
    claude = (
        "import json, pathlib, sys\n"
        f"log = pathlib.Path({str(log)!r})\n"
        "def note(argv, said):\n"
        "    with log.open('a') as stream:\n"
        "        json.dump({'argv': argv, 'stdin': said}, stream)\n"
        "        stream.write('\\n')\n"
        "note(sys.argv[1:], '')\n"
        "flags = dict(zip(sys.argv, sys.argv[1:]))\n"
        "pinned = flags.get('--session-id') or flags['--resume']\n"
        "print(json.dumps({'type': 'system', 'session_id': pinned}), flush=True)\n"
        "for line in sys.stdin:\n"
        "    said = json.loads(line)['message']['content'][0]['text']\n"
        "    note([], said)\n"
        "    answer = (pathlib.Path('PROJECT_FACT').read_text() "
        "if said == 'read project fact' else said)\n"
        "    print(json.dumps({'type': 'assistant', 'message': {'content': "
        "[{'type': 'text', 'text': 'working'}]}}), flush=True)\n"
        # One answer per thing said, which is what the real one does.
        "    print(json.dumps({'type': 'result', 'result': answer}), flush=True)\n"
    )
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{claude}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _FakeCLIs(log)


def test_run_returns_agent_text() -> None:
    assert _EchoAgent(CONFIG).new()("hello world") == "hello world"


def test_both_streams_are_teed_and_captured(capsys: pytest.CaptureFixture[str]) -> None:
    session = ShellAgent(CONFIG).new()
    assert (
        session("echo progress >&2; echo answer") == "answer"
    )  # only stdout is the response
    assert (
        session.id == "answer\n\nprogress"
    )  # but the id parser sees both streams, kept apart

    streams = capsys.readouterr()
    assert streams.out == "answer\n"
    assert streams.err == "progress\n"


def test_failed_turn_raises_and_leaves_the_session_unopened() -> None:
    session = ShellAgent(CONFIG).new()
    with pytest.raises(subprocess.CalledProcessError) as exc:
        session("echo boom >&2; exit 3")
    assert exc.value.returncode == 3
    assert exc.value.stderr == "boom\n"  # stderr reaches the caller as a diagnostic
    assert session.reads == 0  # a failed turn is never asked for a session id
    with pytest.raises(
        RuntimeError
    ):  # so the next turn opens the session instead of resuming
        _ = session.id


def test_a_session_spans_its_turns() -> None:
    session = ShellAgent(CONFIG).new()
    with pytest.raises(RuntimeError):  # not opened until a turn lands
        _ = session.id
    session("echo one")
    session("echo two")
    assert session.id == "one"
    assert (
        session.reads == 1
    )  # the id names the session, so it is read only as it opens


def test_every_driven_agent_names_the_backend_it_is_registered_under() -> None:
    """What an agent calls its backend is what its account, its skills and its cost are under.

    Read off the class name, so a class whose name spells its product rather than its backend
    -- `GrokBuildAgent` for `grok` -- would name a backend nothing answers to, and every one
    of those lookups would quietly answer with nothing.
    """
    from hmz.agents import DRIVEN
    from hmz.backends import named

    for backend, (driver, config) in DRIVEN.items():
        agent = driver(config(model="m", effort="high"))
        assert agent.backend == backend, driver.__name__
        assert named(agent.backend) is not None


def test_an_agent_is_one_agent_apart_from_its_configuration() -> None:
    # The rlar shape: an actor and the reviewer reading its work, at one model and one effort.
    actor, reviewer = _EchoAgent(CONFIG), _EchoAgent(CONFIG)
    assert actor.id != reviewer.id
    assert actor.config == reviewer.config
    # A flow that names its agents keeps those names across restarts; one left unnamed is
    # named after its class, so a trace of two of them still reads as two.
    assert _EchoAgent(CONFIG, name="actor").id == "actor"
    assert actor.id.startswith("_EchoAgent#")


def test_an_agent_remembers_every_session_it_opened() -> None:
    agent = ShellAgent(CONFIG)
    assert agent.opened == []  # nothing has been opened yet
    kept = agent.new()
    kept("echo one")
    kept("echo two")  # the same session: noted as it opened, and only then
    for turn in range(3):  # a Ralph loop, whose sessions nobody holds on to
        agent.new()(f"echo loop-{turn}")

    assert agent.opened == ["one", "loop-0", "loop-1", "loop-2"]
    assert agent.sessions == [
        kept
    ]  # what the weak list cannot say, this one still does
    agent.opened.clear()  # a copy, so a reader cannot lose the agent its history
    assert len(agent.opened) == 4


def test_a_failed_turn_leaves_nothing_behind_to_remember() -> None:
    agent = ShellAgent(CONFIG)
    with pytest.raises(subprocess.CalledProcessError):
        agent.new()("exit 3")

    assert agent.opened == []


def test_an_agent_keeps_the_sessions_it_launched() -> None:
    agent = _EchoAgent(CONFIG)
    first, second = agent.new(), agent.new()
    assert agent.sessions == [first, second]  # oldest first
    assert agent.config is CONFIG

    agent.sessions.clear()  # the list is a copy, so a caller cannot lose the agent its sessions
    assert agent.sessions == [first, second]


def test_an_agent_does_not_grow_by_the_sessions_a_flow_dropped() -> None:
    agent = _EchoAgent(CONFIG)
    kept = agent.new()
    for _ in range(100):  # a Ralph loop: a session per turn, none of them kept
        agent.new()("x")
    assert agent.sessions == [kept]
    assert len(agent._sessions) == 1  # not even the bookkeeping is left behind


def test_launching_while_another_thread_reads_loses_no_session() -> None:
    agent = _EchoAgent(CONFIG)
    stop = threading.Event()

    def read() -> None:
        while not stop.is_set():
            len(agent.sessions)

    with ThreadPoolExecutor(max_workers=1) as pool:
        reader = pool.submit(read)
        held = [agent.new() for _ in range(2000)]
        stop.set()
        reader.result()
    assert agent.sessions == held


def test_turns_of_one_session_do_not_overlap(tmp_path: Path) -> None:
    session = ShellAgent(CONFIG).new()
    # `set -C` makes the redirection fail rather than truncate, so a turn that overlapped another
    # would exit nonzero instead of quietly sharing the marker.
    script = f'set -Ce; : > "{tmp_path}/turn"; sleep 0.05; rm "{tmp_path}/turn"'
    with ThreadPoolExecutor(max_workers=4) as pool:
        turns = [pool.submit(session, script) for _ in range(4)]
    for turn in turns:
        turn.result()  # one conversation, so its turns are a sequence


def test_a_turn_that_takes_no_prompt_on_stdin_cannot_read_ours(tmp_path: Path) -> None:
    """A backend taking its prompt in argv must not be handed the terminal we are watched from."""
    typed = tmp_path / "typed"
    typed.write_text("what the user is typing\n")
    ours = os.dup(0)
    try:
        with typed.open() as stdin:
            os.dup2(stdin.fileno(), 0)
        assert (
            ShellAgent(CONFIG).new()("cat") == ""
        )  # nothing to read, rather than ours
    finally:
        os.dup2(ours, 0)
        os.close(ours)


@pytest.mark.timeout(
    60, method="thread"
)  # a regression hangs rather than fails: bound it
def test_a_turn_outlives_our_own_output_going_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A flow piped into something that has exited must not leave its agent blocked on a write."""

    class _Closed(io.StringIO):
        def write(self, text: str) -> int:
            raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(sys, "stdout", _Closed())
    session = ShellAgent(CONFIG).new()
    turn = session(
        "yes answer | head -c 150000"
    )  # more than a pipe holds, nowhere to tee it
    assert (
        len(turn) == 150_000
    )  # nothing can be shown, but the flow still gets its answer
    assert session("echo again") == "again"


@pytest.mark.timeout(
    60, method="thread"
)  # a regression hangs rather than fails: bound it
def test_output_the_encoding_cannot_decode_is_kept_and_does_not_wedge_the_session() -> (
    None
):
    session = ShellAgent(CONFIG).new()
    # A byte the encoding cannot decode used to kill the reader; with the pipe then unread the
    # agent blocked on its next write and the turn hung, holding the session's lock forever.
    script = "printf 'thinking \\377\\n' >&2; yes noise | head -c 150000 >&2; exit 3"
    with pytest.raises(subprocess.CalledProcessError) as exc:
        session(script)
    assert exc.value.stderr.startswith("thinking")  # replaced, rather than fatal
    assert (
        len(exc.value.stderr) > 150_000
    )  # and the rest of the diagnostic still arrived
    assert session("echo again") == "again"  # the session is still usable


def test_an_agent_that_exits_mid_prompt_is_reported_by_its_exit_status() -> None:
    # The prompt is larger than a pipe holds, so the write breaks; what the caller needs is the
    # agent's own complaint, not our broken pipe -- which the flows do not catch.
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _QuitterAgent(CONFIG).new()("P" * 300_000)
    assert exc.value.returncode == 4
    assert exc.value.stderr == "bad flag\n"


def test_a_prompt_larger_than_the_pipe_buffer_does_not_deadlock() -> None:
    # Deadlocks unless every pipe drains while the prompt is being written, which is the shape of
    # a long task file sent to an agent that reports progress before it has read all of it.
    assert len(_StubbornAgent(CONFIG).new()("P" * 300_000)) == 150_000


def test_claude_holds_one_process_for_the_whole_session(clis: _FakeCLIs) -> None:
    """Two turns are two lines written to one Claude, rather than two runs of it.

    That is what leaves the agent there to be talked to while a turn is still running.
    """
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    assert session("hi") == "hi"
    assert session("again") == "again"

    launch, first, second = clis.calls()
    assert launch.argv[:2] == ["--print", "--input-format"]
    assert launch.argv[launch.argv.index("--session-id") + 1] == session.id
    assert "--dangerously-skip-permissions" in launch.argv
    assert launch.argv[-4:] == ["--model", "claude-opus-4-8", "--effort", "high"]
    assert "--resume" not in launch.argv  # nothing to resume: it never went away
    assert [first.stdin, second.stdin] == ["hi", "again"]


def test_a_shape_is_asked_for_by_the_process_the_turn_runs_in(clis: _FakeCLIs) -> None:
    """`--json-schema` is an argument of the process, so asking for one restarts it.

    The conversation is not restarted with it: the new process resumes the session, which is
    what an anchored session does between every pair of turns anyway.
    """
    from pydantic import BaseModel

    class Greeting(BaseModel):
        model_config = {"extra": "forbid"}

        greeting: str

    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    assert session("hi") == "hi"
    # The stand-in answers with what it was told, so a prompt that is the object is a turn
    # that answered in the shape.
    assert session('{"greeting": "hello"}', schema=Greeting) == Greeting(
        greeting="hello"
    )
    assert session("back to words") == "back to words"

    launches = [call.argv for call in clis.calls() if call.argv]
    assert (
        len(launches) == 3
    )  # one apiece: without the shape, with it, and without again
    assert "--json-schema" not in launches[0]
    assert "--json-schema" in launches[1]
    assert "--json-schema" not in launches[2]
    # Which is the same conversation throughout: every process after the first resumes it.
    assert [argv[argv.index("--resume") + 1] for argv in launches[1:]] == [
        session.id
    ] * 2


def test_claude_can_be_talked_to_while_a_turn_is_running(clis: _FakeCLIs) -> None:
    """The point of holding the process open: a word put in reaches the turn under way."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    said: list[str] = []
    for event in session.stream("start"):
        if (
            event.kind == "text" and not said
        ):  # the turn is running, and Claude is listening
            session.interject("actually, stop")
        said.append(event.kind)

    # One turn, however many things were said in it: what came back from the word put in is
    # part of it, and only the last answer closes it.
    assert said[-1] == "result"
    assert said.count("result") == 1
    assert [call.stdin for call in clis.calls() if call.stdin] == [
        "start",
        "actually, stop",
    ]
    assert session("after") == "after"  # the stream is still in step for the next turn


def test_a_session_that_never_opened_cannot_be_talked_to() -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    with pytest.raises(RuntimeError, match="no turn is running"):
        session.interject("hello?")


def test_claude_pursues_through_its_own_goal_command(clis: _FakeCLIs) -> None:
    """`/goal` is Claude's, and print mode expands it: what a goal must not be is a prompt."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    session.pursue("the suite passes")

    assert [call.stdin for call in clis.calls() if call.stdin] == [
        "/goal the suite passes"
    ]


def test_claude_can_receive_large_goal_context_before_its_short_objective(
    clis: _FakeCLIs,
) -> None:
    """Task material is a remembered turn, not part of Claude's `/goal` command."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    context = "complete task material " * 250
    session.pursue("return the final answer", context=context)

    assert [call.stdin for call in clis.calls() if call.stdin] == [
        context,
        "/goal return the final answer",
    ]


def test_disabled_goals_never_reach_claude(clis: _FakeCLIs, tmp_path: Path) -> None:
    """A goals-off ordinary turn cannot leave HMZ through continuation tools."""
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    )
    (tmp_path / "PROJECT_FACT").write_text("the frozen source fact")
    session = agent.new(tmp_path)
    agent.disable_goals()

    assert not agent.goals_enabled
    with pytest.raises(RuntimeError, match="goals are disabled"):
        session.pursue("the suite passes", suppress=True)
    assert not clis.log.exists()
    assert session("read project fact") == "the frozen source fact"
    launched = clis.calls()[0].argv
    assert launched.count("--disallowedTools") == 1
    assert launched[launched.index("--disallowedTools") + 1] == (
        "Agent,ScheduleWakeup,CronCreate,CronDelete,CronList"
    )


def test_an_anchored_agent_hands_its_whole_turn_to_the_anchor(clis: _FakeCLIs) -> None:
    """The agent still runs here, so the session it opens is still ours to resume."""
    anchor = HereAnchor(target="ssh://build-box", workspace="/srv/project")
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-4-8",
            effort="high",
            machine=AnchoredConfig(anchor=anchor),
        )
    ).new()
    session("hi")
    session("again")

    # What coganchor is given is the backend's own call, resumed session id and all. An
    # anchored turn ends with its process, so that what the agent wrote reaches the target
    # before the turn says it landed -- which is what leaves the next turn a session to rejoin.
    opened, resumed = anchor.seen
    assert opened[opened.index("--session-id") + 1] == session.id
    assert resumed[resumed.index("--resume") + 1] == session.id
    assert opened[-4:] == ["--model", "claude-opus-4-8", "--effort", "high"]
    assert [call.stdin for call in clis.calls() if call.stdin] == ["hi", "again"]


def test_a_backend_without_a_goal_feature_says_so() -> None:
    agent = _EchoAgent(CONFIG)
    with pytest.raises(NotImplementedError):
        agent.new().pursue("the suite passes", context="must not be sent")
    assert agent.opened == []


#: A `claude` that answers with the error it is: `subtype` still reads "success", so the
#: What a turn held to a shape answers with, which is the object and nothing else.
SHAPED = '{"capital":"Bern","landlocked":true}'

#: `is_error` flag is the whole of what says a turn did not land.
REFUSING = (
    "import json, sys\n"
    "flags = dict(zip(sys.argv, sys.argv[1:]))\n"
    "pinned = flags.get('--session-id') or flags['--resume']\n"
    "print(json.dumps({'type': 'system', 'session_id': pinned}), flush=True)\n"
    "sys.stderr.write('the model is not available\\n')\n"
    "for line in sys.stdin:\n"
    "    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': True,\n"
    "        'result': \"There's an issue with the selected model\"}), flush=True)\n"
    "    break\n"
    "raise SystemExit(1)\n"
)


@pytest.fixture
def refusing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts a `claude` on PATH that answers every turn by saying it could not run it."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{REFUSING}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")


def test_a_turn_the_backend_refuses_fails_rather_than_answering(
    refusing: None,
) -> None:
    """Otherwise a loop feeds the sentence explaining the failure forward as the work."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="nonesuch", effort="high"))
    session = agent.new()

    with pytest.raises(subprocess.CalledProcessError) as failed:
        session("do the task")

    assert "issue with the selected model" in str(failed.value.output)
    assert (
        "the model is not available" in failed.value.stderr
    )  # what it said on its way out
    # A turn that failed opened nothing: the session is still unopened, so the next attempt
    # is a fresh one rather than a resume of a conversation that never started.
    assert agent.opened == []
    with pytest.raises(RuntimeError):
        _ = session.id


@pytest.mark.parametrize(
    ("result", "because"),
    [
        (
            {
                "subtype": "error_max_turns",
                "is_error": False,
                "terminal_reason": "max_turns",
                "stop_reason": "tool_use",
                "errors": ["turn limit reached"],
            },
            "turn limit reached",
        ),
        (
            {
                "subtype": "success",
                "is_error": False,
                "terminal_reason": "aborted_streaming",
                "stop_reason": "end_turn",
            },
            "aborted_streaming",
        ),
        (
            {
                "subtype": "success",
                "is_error": False,
                "terminal_reason": "completed",
                "stop_reason": "tool_use",
            },
            "tool_use",
        ),
    ],
)
def test_claude_does_not_accept_an_unfinished_result(
    result: dict[str, object], because: str
) -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()

    events = list(session._read(json.dumps({"type": "result", **result})))

    assert len(events) == 1
    assert events[0].kind == "failed"
    assert because in events[0].text


def test_a_turn_held_to_a_shape_ends_on_the_tool_that_answered_it() -> None:
    """Which reads as an unfinished turn everywhere else, and is how a shaped turn ends.

    The last thing the model does is call `StructuredOutput`, so the result says
    `stop_reason: tool_use` -- and says the object beside it, which is the answer.
    """
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()

    events = list(
        session._read(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "terminal_reason": "completed",
                    "stop_reason": "tool_use",
                    "result": SHAPED,
                    "structured_output": {"capital": "Bern", "landlocked": True},
                }
            )
        )
    )

    assert [one.kind for one in events] == ["result"]
    assert events[0].text == SHAPED


def test_claude_accepts_a_completed_result() -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()

    events = list(
        session._read(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "terminal_reason": "completed",
                    "stop_reason": "end_turn",
                    "result": "done",
                }
            )
        )
    )

    assert len(events) == 1
    assert events[0].kind == "result"
    assert events[0].text == "done"


def test_a_loop_that_swallows_a_failed_turn_does_not_swallow_being_stopped() -> None:
    """What `/stop` rests on: being stopped must not arrive as a failed turn.

    A flow is a loop, and a loop that catches a failed turn goes round again.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    session = agent.new()

    agent.stop()

    with pytest.raises(Stopped):
        session("anything")
    # And it is not what a ralph loop suppresses, or the loop would never end.
    assert not issubclass(Stopped, subprocess.CalledProcessError)


def test_stopping_an_agent_ends_the_turn_it_is_taking(clis: _FakeCLIs) -> None:
    """A model can think for minutes, so a stop that waited for the turn is not a stop.

    This is what makes leaving the interface leave rather than hang: the flow's loop is in a
    turn, and closing the screen without ending it would leave the work going behind it.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    session = agent.new()
    session("hi")  # so that there is a process holding the conversation
    assert session._proc is not None

    agent.stop()

    assert session._proc is None  # nothing left of it to wait on


def test_something_said_while_no_turn_was_open_goes_into_the_next_one(
    clis: _FakeCLIs,
) -> None:
    """A line to a running flow lands even when nobody is mid-turn.

    Between two turns there is no turn to steer, and writing to the session anyway would
    have it answer on its own. So it is held, and asked for as the next turn starts: the
    flow's own prompt is the only way into a turn that has not begun.
    """
    held = ["and also this"]
    agent = ClaudeCodeAgent(CONFIG)
    agent.waiting = lambda: [held.pop()] if held else []

    said = agent.new()("do the thing")

    # The turn was asked for, and answered, with both -- the flow's prompt and what was held.
    assert said == "do the thing\n\nand also this"
    assert agent.new()("next") == "next"  # taken once, not again


def test_a_suppressed_turn_answers_with_nothing_rather_than_raising(
    refusing: None,
) -> None:
    """`|| true` as a word on the call, so a flow is a loop and not a `try` around one."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="nonesuch", effort="high"))

    assert agent("do the task", suppress=True) == ""
    assert agent.new()("do the task", suppress=True) == ""
    # And what it catches is a turn that failed and nothing else: an agent that was stopped
    # is not one, or a loop that suppresses its turns would never end.
    agent.stop()
    with pytest.raises(Stopped):
        agent("do the task", suppress=True)


def test_calling_the_agent_is_a_session_it_keeps_nothing_of(clis: _FakeCLIs) -> None:
    """Which is the shape a ralph loop is made of, said without reaching through a session."""
    agent = ClaudeCodeAgent(CONFIG)

    assert agent("hi") == "hi"
    assert agent("again") == "again"

    assert len(agent.opened) == 2  # two sessions, neither resuming the other
    assert len(set(agent.opened)) == 2


def test_an_agent_takes_the_name_a_flow_calls_it_unless_it_has_one() -> None:
    """`builder` says what a hex tail does not, and a trace groups the sessions under it."""
    named = ClaudeCodeAgent(CONFIG, name="actor")
    unnamed = ClaudeCodeAgent(CONFIG)

    named.rename("builder")
    unnamed.rename("reviewer")

    assert named.id == "actor"  # a name given where the agent was made is the name
    assert unnamed.id == "reviewer"


def test_a_question_reaches_whoever_is_driving_the_agent_and_nobody_otherwise() -> None:
    """A turn that stopped to ask must be answerable, and must not wait when it cannot be."""
    agent = ClaudeCodeAgent(CONFIG)
    heard: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            heard.append(event.kind) if event.kind == "asks" else None
        )
    )
    question = Question(text="Which way?", options=("left", "right"))

    assert agent.asked(question) is None  # nobody is driving it, so nobody answers

    agent.ask = lambda asked: asked.options[0]
    assert agent.asked(question) == "left"

    # Whatever is watching the agent is told what was asked, since the turns going past are
    # the one place a run is visible.
    assert heard == ["asks", "asks"]

    def raises(asked: Question) -> str:
        raise RuntimeError("the interface has gone")

    agent.ask = raises
    assert agent.asked(question) is None  # and a turn does not fail because asking did


def test_a_flow_waits_at_the_prompt_only_where_there_is_one() -> None:
    """A conversation needs somewhere to be told the next thing; a command line has nowhere."""
    agent = ClaudeCodeAgent(CONFIG)

    # Nobody is at a prompt, so a flow that is a conversation has had its conversation.
    assert agent.prompted() is None

    said = ["and then this", "this first"]
    agent.prompting = said.pop
    assert agent.prompted() == "this first"
    assert agent.prompted() == "and then this"

    def raises() -> str:
        raise RuntimeError("the interface has gone")

    agent.prompting = raises
    assert agent.prompted() is None  # and a flow ends rather than failing


def test_being_stopped_at_the_prompt_is_being_stopped() -> None:
    """A run ended by hand is written down as one, and `None` would write it down as done."""
    agent = ClaudeCodeAgent(CONFIG)

    def stops() -> str | None:
        agent.stop()  # as esc does, while the flow is waiting to be told something
        return None

    agent.prompting = stops
    with pytest.raises(Stopped):
        agent.prompted()
