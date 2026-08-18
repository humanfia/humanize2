"""A place falling back to a place, once the one taking a turn has nowhere left to run.

An account's chain answers an account going down, inside the conversation that was running,
with the same agent at the same model throughout. This is what is left when that is no answer
at all: a model retired, a CLI that will not start, a whole account rate-limited rather than
one request. Another place then -- another CLI, another account, another model -- and the turn
taken in a session of its own, because no backend can be handed another backend's session id.

A place and not an agent: how hard the agent thinks, what it may reach for and which of a
flow's skills it carries are what that agent *is*, settled where it was made, and they come
across the step unchanged. Written down between the two places rather than on either, because
it is about neither on its own.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz import backends, fallbacks
from hmz.agents import AgentConfig, ClaudeCodeAgent, ClaudeCodeAgentConfig, Tool
from hmz.agents.skills import Loaded
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A `claude` that answers whatever it was told, so that a turn which reached it says so.
_CLAUDE = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": "claude took it: " + said}), flush=True)
"""


@pytest.fixture(autouse=True)
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A home nothing has written to, and `shell` as a backend of your own."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    backends.remember("shell", ["sh"])


def _claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts a `claude` that answers on PATH, so a stand-in of one is one that runs."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{_CLAUDE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")


def test_a_step_is_written_down_between_two_places() -> None:
    """Three things and no more: the CLI, the account it runs as, and the model it runs."""
    fallbacks.points("shell/m", "claude@work/claude-opus-5")

    assert fallbacks.falls() == [
        fallbacks.Falls("shell/m", "claude@work/claude-opus-5")
    ]
    assert fallbacks.chain("shell/m") == [
        "shell/m",
        "claude@work/claude-opus-5",
    ]


def test_the_chain_is_this_agent_and_then_wherever_each_one_goes() -> None:
    """A list rather than a list and a special case: the first is always this agent."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("claude/a", "codex/b")

    assert fallbacks.chain("shell/m") == [
        "shell/m",
        "claude/a",
        "codex/b",
    ]
    # And one nobody said anything about is a chain of one.
    assert fallbacks.chain("codex/b") == ["codex/b"]


def test_a_chain_that_comes_round_on_itself_ends_at_the_second_sight_of_a_place() -> (
    None
):
    """Or it would be a turn that could never run out of places to go."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("claude/a", "shell/m")

    assert fallbacks.chain("shell/m") == ["shell/m", "claude/a"]


def test_a_step_that_points_at_itself_or_at_nothing_is_refused_where_it_is_written() -> (
    None
):
    """Rather than found by the turn that needed it, an hour into a loop."""
    with pytest.raises(ValueError, match="cannot fall back to itself"):
        fallbacks.points("claude/a", "claude/a")
    with pytest.raises(ValueError, match="is not a place"):
        fallbacks.points("nothing-is-called-this/a", "claude/a")
    with pytest.raises(ValueError, match="is not a place"):
        fallbacks.points("claude/a", "nothing-is-called-this/a")


def test_writing_one_again_says_the_new_thing_and_not_both() -> None:
    """One place has one place to go: two would be a chain that forks."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("shell/m", "codex/b")

    assert fallbacks.chain("shell/m") == ["shell/m", "codex/b"]
    assert fallbacks.clear("shell/m")
    assert fallbacks.chain("shell/m") == ["shell/m"]
    assert not fallbacks.clear("shell/m")


def test_a_place_is_read_by_whichever_spelling_of_its_cli() -> None:
    """And a model with slashes of its own is a model: only the first of them separates."""
    assert fallbacks.reads("claude-code/m") == "claude/m"
    assert fallbacks.reads("claude@work/m") == "claude@work/m"
    assert fallbacks.reads("opencode/opencode/nemotron") == "opencode/opencode/nemotron"
    assert fallbacks.reads("nothing-is-called-this/m") == ""
    assert fallbacks.reads("claude") == ""
    assert fallbacks.reads("claude@/m") == ""


def test_an_effort_written_down_before_it_left_this_spelling_is_read_past() -> None:
    """A step somebody still means, and how hard an agent thinks is not part of a place."""
    assert fallbacks.reads("claude/claude-opus-5:high") == "claude/claude-opus-5"
    # And a colon that is part of a model's own name is left exactly where it is: only a
    # rung that backend actually has is read as one.
    assert fallbacks.reads("claude/qwen3:8b") == "claude/qwen3:8b"


def test_an_agent_says_which_place_it_runs_at() -> None:
    """The account it was configured with, which is what somebody wrote the step against."""
    assert ShellAgent(CONFIG).spec == "shell/m"
    assert (
        ShellAgent(AgentConfig(model="m", effort="high", provider="work")).spec
        == "shell@work/m"
    )


def test_an_agent_nobody_wrote_a_step_about_stands_in_nowhere() -> None:
    """Which is a turn failing the way a turn has always failed."""
    assert ShellAgent(CONFIG).stands_in() is None


def test_the_stand_in_is_at_the_place_the_step_names_and_is_made_once(
    tmp_path: Path,
) -> None:
    """Kept for the reason an account that has moved stays moved."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert stood_in.backend == "claude"
    assert stood_in.config.model == "claude-opus-5"
    assert agent.stands_in() is stood_in


def test_the_stand_in_is_configured_as_the_agent_that_could_not_run_was() -> None:
    """A step names a place; everything else about an agent is what that agent is."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(
        AgentConfig(model="m", effort="high", permission="read-only", goals=False)
    )

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert stood_in.config.effort == "high"  # a rung Claude has too
    assert stood_in.config.permission == "read-only"
    assert not stood_in.config.goals


def test_a_rung_the_cli_taking_over_has_not_got_is_the_same_rung_of_its_own_ladder() -> (
    None
):
    """Every ladder here is hardest first, so a rung is how far down from the top it was."""
    fallbacks.points("claude/claude-opus-5", "grok/grok-5")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="ultracode")
    )

    stood_in = agent.stands_in()

    # `ultracode` is the top of Claude's ladder and Grok Build has no such word, so the top
    # of its own is what the turn is taken at.
    assert stood_in is not None
    assert stood_in.config.effort == "xhigh"


def test_a_stand_in_that_cannot_be_told_what_this_agent_was_told_is_no_stand_in() -> (
    None
):
    """A setting a backend quietly ignored would be a setting that lies about the turn."""
    fallbacks.points("claude/claude-opus-5", "kimi/kimi-k3")
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", web_search=False)
    )

    # Kimi Code has no way of being told not to search the web, so it is not a place this
    # agent's turns can go: the turn fails the way it failed before anybody wrote a step.
    assert agent.stands_in() is None


def test_the_stand_in_carries_what_the_flow_gave_the_agent(tmp_path: Path) -> None:
    """The skills are the flow's, and the turn that moved is still the flow's turn."""
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    agent.loads([Loaded("reading", tmp_path / "reading", "this flow")])

    stood_in = agent.stands_in()

    assert stood_in is not None
    assert [one.name for one in stood_in.loaded] == ["reading"]


def test_a_stand_in_holds_only_the_steps_after_its_own() -> None:
    """Or a chain read again from the top by each hop would walk the failed ones twice."""
    fallbacks.points("shell/m", "claude/a")
    fallbacks.points("claude/a", "codex/b")
    agent = ShellAgent(CONFIG)

    first = agent.stands_in()

    assert first is not None
    assert first._beyond == ("codex/b",)
    second = first.stands_in()
    assert second is not None
    assert second.spec == "codex/b"
    assert second._beyond == ()
    assert second.stands_in() is None


def test_a_step_naming_a_cli_that_is_not_here_is_a_turn_that_fails_as_it_always_did() -> (
    None
):
    """The answer somebody needs is what went wrong, not what the step said."""
    fallbacks.points("shell/m", "claude/a")
    # Written down while it could be read, and the backend gone by the time it is needed.
    agent = ShellAgent(CONFIG)
    agent._beyond = ("nothing-is-called-this/a",)

    assert agent.stands_in() is None


@pytest.mark.timeout(60)
def test_a_turn_with_nowhere_left_to_run_is_taken_at_the_place_it_falls_back_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the whole of it: the flow asked one agent and another one answered."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)

    # `exit 3` is a turn that failed, and this agent has no account to fall back to.
    assert agent.new()("exit 3") == "claude took it: exit 3"


@pytest.mark.timeout(60)
def test_the_turn_that_moved_is_still_the_one_the_flow_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One `begins` and one `ends` on the agent the flow is driving, whoever took the turn."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    said: list[str] = []
    agent.watch(lambda _agent, _session, event: said.append(event.kind))

    agent.new()("exit 3")

    assert said.count("begins") == 1
    assert said.count("ends") == 1
    assert said.count("result") == 1


@pytest.mark.timeout(60)
def test_a_turn_that_lands_never_asks_where_it_would_have_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chain of four agents all started when the run was would be three CLIs for nothing."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)

    assert agent.new()("echo fine") == "fine"
    assert agent._stands_in is None


def test_the_agent_that_took_the_turn_is_asked_for_the_shape_its_own_way() -> None:
    """A backend that can be held to a shape is told separately, and one that cannot is asked.

    So the prompt is shaped for whoever is about to be asked rather than once for whoever was
    asked first: a stand-in that can be held to it would otherwise be handed a schema in the
    prompt as well as on the flag.
    """
    assert ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new().shapes
    assert not ShellAgent(CONFIG).new().shapes


@pytest.mark.timeout(60)
def test_an_agent_stopped_stops_whatever_is_standing_in_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run ended by hand ends: a stand-in that went on thinking would be one that did not."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    agent.new()("exit 3")  # which is what makes the stand-in

    agent.stop()

    stood_in = agent.stands_in()
    assert stood_in is not None
    assert stood_in.stopped


@pytest.mark.timeout(60)
def test_the_conversation_is_lost_once_rather_than_every_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stateful loop that moved is one conversation on the other side, not one a round."""
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    agent = ShellAgent(CONFIG)
    session = agent.new()

    session("exit 3")
    session("exit 3")

    stood_in = agent.stands_in()
    assert stood_in is not None
    assert len(stood_in.opened) == 1  # one conversation, both of the turns that moved


@pytest.mark.timeout(60)
def test_the_conversation_it_moved_to_ends_when_this_one_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is this conversation carried on somewhere else, so it goes when this one goes.

    Read off what it was carrying, since that is what a session leaves in the workspace: the
    flow's skills go with the turn, put where the backend that took it reads them, and they
    come down when the conversation they were for is over.
    """
    _claude(tmp_path, monkeypatch)
    fallbacks.points("shell/m", "claude/claude-opus-5")
    brought = tmp_path / "brought" / "reading"
    brought.mkdir(parents=True)
    (brought / "SKILL.md").write_text("---\nname: reading\n---\n")
    agent = ShellAgent(CONFIG)
    agent.loads([Loaded("reading", brought, "this flow")])
    session = agent.new()
    session("exit 3")

    # Where Claude reads a project's own, which is not where the agent it moved from would.
    assert (tmp_path / ".claude/skills/reading").is_dir()

    session.close()

    assert not (tmp_path / ".claude").exists()


#: A `claude` that will not run at all at one model, and writes down how it was started at any
#: other: which is a place with nowhere left to go, and the place the step names.
_CLAUDE_GONE = """
import json, pathlib, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
if flags.get("--model") == "gone":
    sys.exit(3)
with pathlib.Path(LOG).open("a") as wrote:
    wrote.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": "claude took it: " + said}), flush=True)
"""


def _gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts that `claude` on PATH, and answers with the log of every start it wrote."""
    log = tmp_path / "starts.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "claude"
    fake.write_text(
        f"#!{sys.executable}\n{_CLAUDE_GONE.replace('LOG', repr(str(log)))}"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return log


def _delegating() -> Tool:
    """One callback of a flow's own, of the kind a loop offers between two rounds."""
    return Tool(name="delegate", about="hand a task on", call=lambda: "did it")


@pytest.mark.timeout(60)
def test_the_stand_in_is_offered_the_callbacks_the_conversation_was_offering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flow's own callbacks go with the turn, the way the flow's skills do.

    They are the conversation's rather than the agent's -- said between two turns, long after
    the step was written down -- so a turn that moved without them would be the flow losing
    what it offered by being moved, and nothing about it would look wrong.
    """
    log = _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "claude/claude-opus-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    session = agent.new()
    session.offers([_delegating()])

    assert session("hello") == "claude took it: hello"

    # One start written down: the model that is gone never got as far as writing one.
    (argv,) = [json.loads(line) for line in log.read_text().splitlines()]
    held = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(held["mcpServers"]) == ["humanize"]


@pytest.mark.timeout(60)
def test_a_stand_in_that_cannot_be_given_the_callbacks_is_no_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A callback quietly never offered is a flow that quietly does not do what it says.

    Which is the rule about a setting the CLI taking over cannot be told, applied to the one
    thing a conversation says after the step was read: the turn fails the way it failed before
    anybody wrote a step down.
    """
    _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "grok/grok-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    said: list[str] = []
    agent.watch(lambda _agent, _session, event: said.append(event.text))
    session = agent.new()
    session.offers([_delegating()])

    with pytest.raises(subprocess.CalledProcessError):
        session("hello")

    # The step is there and the agent for it was made; what stopped the turn going is that
    # Grok Build has no way of being given a tool of a flow's own.
    assert agent.stands_in() is not None
    assert not [one for one in said if "grok" in one]


@pytest.mark.timeout(60)
def test_the_stand_in_is_offered_what_the_agent_holds_and_not_only_this_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI told about its tools once per agent has a sibling's offer in front of it too.

    So the conversation that moves is not always the one that offered: the list to carry is
    the agent's, or a turn that never said anything about tools loses the ones the model
    could see.
    """
    log = _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "claude/claude-opus-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    # Held, or the conversation offering is collected and takes its offer back with it.
    sibling = agent.new()
    sibling.offers([_delegating()])
    session = agent.new()

    assert sibling.tools
    assert session.tools == ()  # this one offered nothing, and moves with them anyway
    assert session("hello") == "claude took it: hello"

    (argv,) = [json.loads(line) for line in log.read_text().splitlines()]
    held = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(held["mcpServers"]) == ["humanize"]


@pytest.mark.timeout(60)
def test_a_sibling_s_callbacks_stop_a_move_to_a_backend_that_takes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same thing: what refuses the move is what the model can see."""
    _gone(tmp_path, monkeypatch)
    fallbacks.points("claude/gone", "grok/grok-5")
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="gone", effort="high"))
    sibling = agent.new()
    sibling.offers([_delegating()])
    session = agent.new()

    assert sibling.tools
    with pytest.raises(subprocess.CalledProcessError):
        session("hello")

    assert agent.stands_in() is not None
