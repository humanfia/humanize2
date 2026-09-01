"""The moment a backend waits on, which is the one a refusal actually stops.

Every other moment of a turn is read off the turn itself, and a `PreToolUse` read there says a
tool was reached for after the CLI has already reached for it -- so a flow refusing one is
watching a tool run rather than stopping it. What is checked here is the other route: each
CLI's own hook table, pointed for the length of one run at a relay that carries the moment back
to the hooks hung on the agent, so that the CLI is waiting for the answer when it arrives.

Driven against the protocol and the command lines rather than against live CLIs, for the reason
`tests/test_tools_command.py` is written that way: what is owed to the two ends is exact, and
a backend that is not installed is not a reason to leave it unchecked.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz import backends
from hmz.agents import (
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Moment,
    Occasion,
    QwenCodeAgent,
    Verdict,
)
from hmz.agents import hooks as hooked
from hmz.agents.hooks import EVERYWHERE, WAITING, Gate, Hooks, answers
from hmz.agents.qwen import _SETTINGS
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from collections.abc import Iterator


def _profile(backend: str) -> backends.Profile:
    """One backend's profile, by a name it answers to."""
    found = backends.named(backend)
    assert found is not None
    return found


def _hooks() -> Hooks:
    """One agent's moments, with nothing hung on any of them yet."""
    return Hooks(EVERYWHERE, "worker")


def _called(tool: str = "Bash", **given: Any) -> str:
    """One `PreToolUse`, written as the CLI writes it on its hook's standard input."""
    return json.dumps(
        {
            "session_id": "a-session",
            "transcript_path": "/dev/null",
            "cwd": "/tmp",
            "permission_mode": "acceptEdits",
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": given or {"command": "ls"},
            "tool_use_id": "toolu_1",
        }
    )


@pytest.fixture
def serving() -> Iterator[Hooks]:
    """One agent's moments, with a gate serving them, taken down however the test ended.

    The hooks and not the gate: a gate holds what it serves weakly, so a test that kept only
    the gate would be one whose agent had already gone.
    """
    held = _hooks()
    held.gate().address()
    try:
        yield held
    finally:
        held.gate().close()


def test_a_refusal_is_answered_in_the_words_the_backend_reads_it_in() -> None:
    """A deny with a reason, which is what stops the tool and what the agent is told."""
    hooks = _hooks()
    hooks.on(
        Moment.PRE_TOOL_USE, lambda _: Verdict(refused=True, because="not that one")
    )

    said = json.loads(answers(_called(), hooks))

    assert said["hookSpecificOutput"] == {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "not that one",
    }


def test_a_refusal_with_nothing_to_say_still_says_which_tool_it_was() -> None:
    """A line the agent can act on: `Bash was refused` beats a reason that is empty."""
    hooks = _hooks()
    hooks.on(Moment.PRE_TOOL_USE, lambda _: Verdict(refused=True))

    said = json.loads(answers(_called(), hooks))

    assert said["hookSpecificOutput"]["permissionDecisionReason"] == "Bash was refused"


def test_a_moment_nobody_refused_is_answered_with_nothing_at_all() -> None:
    """Which every one of these CLIs reads as the tool going ahead as it would have."""
    hooks = _hooks()
    seen: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, seen.append)

    assert answers(_called(), hooks) == "{}"
    # And the hook was told the whole of what the tool was called with, as well as the one
    # line a row of a transcript has room for.
    assert (seen[0].tool, seen[0].about) == ("Bash", "ls")
    assert seen[0].input == {"command": "ls"}
    assert seen[0].session == "a-session"
    assert seen[0].agent == "worker"


def test_a_hook_hung_on_one_tool_is_asked_about_that_tool_alone() -> None:
    """The same narrowing a hook hung in the flow's own process gets, over the same seam."""
    hooks = _hooks()
    hooks.on(
        Moment.PRE_TOOL_USE,
        lambda _: Verdict(refused=True, because="no"),
        tool="Write",
    )

    assert answers(_called(tool="Read"), hooks) == "{}"
    assert "deny" in answers(_called(tool="Write"), hooks)


def test_a_moment_this_serves_no_answer_to_is_answered_with_nothing() -> None:
    """A CLI that grows an event is a CLI whose turns must go on running."""
    hooks = _hooks()
    said = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash"})

    assert answers(said, hooks) == "{}"
    assert answers("not a message at all", hooks) == "{}"
    assert answers("[1, 2, 3]", hooks) == "{}"


def test_an_agent_stopped_inside_a_hook_still_stops_the_tool() -> None:
    """There is nowhere here to raise it to, and the tool must not run in the meantime."""
    from hmz.agents import Stopped

    hooks = _hooks()

    def drives(_: Occasion) -> Verdict | None:
        raise Stopped("worker was stopped")

    hooks.on(Moment.PRE_TOOL_USE, drives)
    said = json.loads(answers(_called(), hooks))

    assert said["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "was stopped" in said["hookSpecificOutput"]["permissionDecisionReason"]


def test_the_relay_carries_one_call_to_the_flow_and_the_answer_back(
    serving: Hooks,
) -> None:
    """Spawned exactly as a CLI spawns it: the call on stdin, the verdict on stdout."""
    serving.on(
        Moment.PRE_TOOL_USE,
        lambda one: (
            Verdict(refused=True, because="no rm here") if "rm " in one.about else None
        ),
    )

    def run(
        command: str, *, pretty: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        said = _called(command=command)
        if pretty:
            # A CLI that writes its hook's input over several lines rather than one.
            said = json.dumps(json.loads(said), indent=2)
        return subprocess.run(
            serving.gate().command(),
            input=said.encode(),
            capture_output=True,
            check=False,
        )

    refused, allowed = run("rm -rf /"), run("ls")

    assert refused.returncode == 0
    assert json.loads(refused.stdout)["hookSpecificOutput"]["permissionDecision"] == (
        "deny"
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout) == {}
    # The socket carries a message a line, so a call that arrived over several still has to
    # reach the flow as one: read as a line apiece it would be refused by nobody.
    spread = run("rm -rf /", pretty=True)
    assert json.loads(spread.stdout)["hookSpecificOutput"]["permissionDecision"] == (
        "deny"
    )


def test_a_relay_with_no_flow_behind_it_lets_the_tool_through(serving: Hooks) -> None:
    """A flow that has ended is not a flow that refused, and must not read as one."""
    argv = [*serving.gate().command()[:-1], "/nowhere/hook.sock"]
    done = subprocess.run(argv, input=b"{}", capture_output=True, check=False)

    # Zero and not two: these CLIs read a two as the hook itself having refused.
    assert done.returncode == 0
    assert done.stdout.strip() == b""
    assert "/nowhere/hook.sock" in done.stderr.decode()


def test_a_relay_given_a_line_it_cannot_read_still_refuses_nothing() -> None:
    """Argparse exits two for a bad line, and two is the one status this must never use."""
    argv = [sys.executable, "-m", "hmz", "hook", "--nonsense"]
    done = subprocess.run(argv, input=b"{}", capture_output=True, check=False)

    assert done.returncode == 1


def test_the_relay_is_the_python_running_this_flow(serving: Hooks) -> None:
    """The callback is in this process, so what carries a call to it has to start here."""
    assert serving.gate().command()[:4] == [sys.executable, "-m", "hmz", "hook"]


def test_the_gate_is_reached_only_by_whoever_is_running_the_flow(
    serving: Hooks,
) -> None:
    """A socket is a way into this process, so the directory holding one is this user's."""
    from pathlib import Path

    where = Path(serving.gate().address()).parent

    assert where.stat().st_mode & 0o077 == 0


def test_one_agent_s_moments_are_put_to_a_hook_one_at_a_time(serving: Hooks) -> None:
    """A CLI reaches for several tools at once; a hook has always been a word in the turn."""
    import threading

    inside = threading.Semaphore(0)
    together: list[int] = []
    running = 0
    counting = threading.Lock()

    def slow(_: Occasion) -> Verdict | None:
        nonlocal running
        with counting:
            running += 1
            together.append(running)
        inside.release()
        # Long enough that a second relay would be well inside this one if it could be.
        threading.Event().wait(0.3)
        with counting:
            running -= 1
        return None

    serving.on(Moment.PRE_TOOL_USE, slow)
    calls = [
        subprocess.Popen(
            serving.gate().command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        for _ in range(3)
    ]
    for call in calls:
        assert call.stdin is not None
        call.stdin.write(_called().encode())
        call.stdin.close()
    for call in calls:
        call.wait()

    assert together == [1, 1, 1]


def test_a_gate_goes_when_the_agent_whose_moments_it_serves_does() -> None:
    """Nothing else ever closes one, so a gate that outlived its agent would outlive them all."""
    import gc
    from pathlib import Path

    hooks = _hooks()
    where = Path(hooks.gate().address()).parent

    assert where.exists()

    del hooks
    gc.collect()

    assert not where.exists()


def test_claude_is_told_where_this_agent_s_moments_are_on_its_own_command_line() -> (
    None
):
    """`--settings` is the whole of a settings file for one run: no file of anybody's."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    session = agent.new()

    argv = session._command()
    settings = json.loads(argv[argv.index("--settings") + 1])
    table = settings["hooks"]["PreToolUse"][0]

    assert table["matcher"] == "*"
    assert agent.hooks.gate().address() in table["hooks"][0]["command"]
    # Seconds here, which is what Claude Code counts this in.
    assert table["hooks"][0]["timeout"] == WAITING
    # And what was already said through the same flag is still said.
    assert "fastMode" in settings


def test_qwen_is_told_through_the_settings_file_it_is_already_pointed_at() -> None:
    """One file for one run, at the layer that outranks what a person has configured."""
    agent = QwenCodeAgent(AgentConfig(model="m", effort="high"))
    session = agent.new()

    where = session._environment()[_SETTINGS]
    settings = json.loads(open(where, encoding="utf-8").read())  # noqa: SIM115, PTH123
    table = settings["hooks"]["PreToolUse"][0]

    assert agent.hooks.gate().address() in table["hooks"][0]["command"]
    # Milliseconds here, under the same spelling: Qwen Code took the field and not the unit.
    assert table["hooks"][0]["timeout"] == WAITING * 1000
    # The one switch that would turn the whole table off, said off for this run alone.
    assert settings["disableAllHooks"] is False
    # And what the file was already for is still in it.
    assert settings["model"]["reasoningEffort"] == "high"


def test_two_agents_are_two_gates_and_two_settings_files() -> None:
    """A file keyed by effort alone would point one agent's turns at another's socket."""
    one = QwenCodeAgent(AgentConfig(model="m", effort="high"))
    two = QwenCodeAgent(AgentConfig(model="m", effort="high"))

    theirs = [agent.new()._environment()[_SETTINGS] for agent in (one, two)]

    assert theirs[0] != theirs[1]
    assert one.hooks.gate().address() != two.hooks.gate().address()


def test_a_moment_the_backend_itself_asks_about_is_not_said_twice() -> None:
    """The CLI asks and waits, so a session reading its stream must not fire it again."""
    hooks = _hooks()

    assert not hooks.gated(Moment.PRE_TOOL_USE)
    assert hooks.gated(Moment.STOP) is False

    gate = hooks.gate()
    try:
        assert hooks.gated(Moment.PRE_TOOL_USE)
        # And only that one: every other moment is read off the turn on every backend.
        assert not hooks.gated(Moment.STOP)
        assert not hooks.gated(Moment.USER_PROMPT_SUBMIT)
    finally:
        gate.close()


def test_a_backend_with_no_table_of_its_own_goes_on_watching_its_stream() -> None:
    """Which is what every moment was before this, and still is where there is no seam."""
    agent = ShellAgent(AgentConfig(model="m", effort="high"))
    seen: list[str] = []
    agent.hooks.on(Moment.PRE_TOOL_USE, lambda one: seen.append(one.tool))

    agent("echo hello")

    assert not agent.hooks.gated(Moment.PRE_TOOL_USE)
    assert seen == []  # this stand-in reaches for no tools; the point is that it may


def test_the_backends_that_take_a_table_for_one_run_say_so() -> None:
    """Read off what is written down about the CLI rather than declared a second time."""
    taken = {
        one.name: one.hooks for one in backends.profiles() if one.hooks is not None
    }

    assert taken["claude"] == backends.Hooked(seam="flag", name="--settings")
    assert taken["qwen"].seam == "env"
    for name in taken:
        assert "anchor:hooked" in _profile(name).tags()
    # And a CLI with no such seam is not listed as having one.
    assert "anchor:hooked" not in _profile("opencode").tags()


def test_the_variable_qwen_is_pointed_through_is_written_down_once() -> None:
    """Two spellings of one variable are one that goes on being right in only one place."""
    said = _profile("qwen").hooks

    assert said is not None
    assert said.name == _SETTINGS


def test_an_anchored_turn_is_not_told_about_a_socket_it_cannot_reach() -> None:
    """Its CLI runs on another machine; a relay named there would never answer."""
    from hmz.agents.config import anchored
    from hmz.coganchor.anchor import AnchorConfig

    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="m", effort="high", machine=anchored("ssh://elsewhere")
        )
    )
    # Standing where the machine it names would be, so that asking the agent where its work
    # lands answers without a host having to be there to answer it.
    agent._anchor = AnchorConfig(target="ssh://elsewhere")
    session = agent.new()

    argv = session._command()
    settings = json.loads(argv[argv.index("--settings") + 1])

    assert "hooks" not in settings
    # So the moment goes on being read off the stream, as it does everywhere else.
    assert not agent.hooks.gated(Moment.PRE_TOOL_USE)


def test_the_wait_a_hook_is_given_is_as_long_as_a_turn_may_be_quiet() -> None:
    """A hook may put its question to a person, and that is not a hook that has wedged."""
    assert _profile("claude").silence <= WAITING


def test_the_gate_is_one_gate_however_often_it_is_asked_for() -> None:
    """A CLI restarted mid-session reaches the socket it always did."""
    hooks = _hooks()
    gate = hooks.gate()
    try:
        assert hooks.gate() is gate
        assert gate.address() == gate.address()
    finally:
        gate.close()


def test_what_the_gate_serves_is_the_one_moment_that_needs_it() -> None:
    """The rest are read off the turn everywhere, and firing them here would fire twice."""
    assert Gate.moments == frozenset({Moment.PRE_TOOL_USE})
    assert hooked.Moment.PRE_TOOL_USE.value == "PreToolUse"


def test_a_tool_input_that_is_not_an_object_is_still_answered() -> None:
    """A tool input is whatever that tool takes, and need not be an object at all.

    A gate that died reading one would answer nothing at all -- which is the tool going
    ahead unrefused, the one way a gate must never fail.
    """
    hooks = _hooks()
    hooks.on(Moment.PRE_TOOL_USE, lambda _: Verdict(refused=True, because="no"))
    said = json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": "ls"}
    )

    answer = json.loads(answers(said, hooks))

    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
