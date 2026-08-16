"""The moments of a turn, and what a flow said to do about them.

Driven against the shell-backed stand-in rather than a real agent: a moment is something the
session says as it drives the backend, so a backend that is `sh -c` reaches every one of them
except the one only Claude asks about.
"""

from __future__ import annotations

import subprocess

import pytest

from hmz.agents import (
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    HumanAgent,
    KimiCodeCLIAgent,
    Moment,
    Occasion,
    OpencodeAgent,
    Unhooked,
    Verdict,
    ZcodeAgent,
)
from tests.stubs import ShellAgent


def _agent() -> ShellAgent:
    """One stand-in agent, at a configuration nothing here reads."""
    return ShellAgent(AgentConfig(model="m", effort="high"), name="worker")


def test_a_hook_is_told_what_happened_and_says_nothing() -> None:
    """The common case: a hook that only watches leaves the turn exactly as it was."""
    agent = _agent()
    seen: list[Occasion] = []
    agent.hooks.on(Moment.USER_PROMPT_SUBMIT, seen.append)

    assert agent("echo hello") == "hello"
    assert [occasion.moment for occasion in seen] == [Moment.USER_PROMPT_SUBMIT]
    assert seen[0].prompt == "echo hello"
    assert seen[0].agent == "worker"


def test_a_session_says_when_it_starts_and_when_it_is_closed() -> None:
    """Once apiece, and only for a session that ever ran a turn."""
    agent = _agent()
    said: list[Moment] = []
    agent.hooks.on(Moment.SESSION_START, lambda occasion: said.append(occasion.moment))
    agent.hooks.on(Moment.SESSION_END, lambda occasion: said.append(occasion.moment))

    session = agent.new()
    session("echo one")
    session("echo two")  # a second turn is not a second session
    session.close()
    session.close()  # nor is being closed twice a second ending

    assert said == [Moment.SESSION_START, Moment.SESSION_END]

    # And one that never ran never began, so it never ended either.
    agent.new().close()
    assert said == [Moment.SESSION_START, Moment.SESSION_END]


def test_a_hook_adds_to_what_the_agent_is_told() -> None:
    """What `UserPromptSubmit` is for: the turn runs, and runs on more than it was given."""
    agent = _agent()
    agent.hooks.on(
        Moment.USER_PROMPT_SUBMIT, lambda _: Verdict(adds="echo and this too")
    )

    # Both lines reach the shell, which is the prompt this stand-in runs.
    assert agent("echo first").splitlines() == ["first", "and this too"]


def test_a_refused_prompt_is_a_turn_that_does_not_run() -> None:
    """And answers with why, since a turn still has to end on exactly one answer."""
    agent = _agent()
    agent.hooks.on(
        Moment.USER_PROMPT_SUBMIT,
        lambda _: Verdict(refused=True, because="not on a Friday"),
    )

    assert agent("touch ran.txt") == "not on a Friday"
    assert agent.opened == []  # nothing was run, so nothing was opened


def test_a_refused_stop_sends_the_agent_on_and_the_last_answer_is_the_turn_s() -> None:
    """A `Stop` hook that refuses is what a goal is: the turn is not over until it is."""
    agent = _agent()
    rounds: list[int] = []

    def again(occasion: Occasion) -> Verdict | None:
        rounds.append(occasion.again)
        if occasion.again < 2:
            return Verdict(refused=True, because=f"echo round {occasion.again + 1}")
        return None

    agent.hooks.on(Moment.STOP, again)

    assert agent("echo round 0") == "round 2"
    assert rounds == [0, 1, 2]


def test_a_stop_that_refuses_with_nothing_to_say_is_a_turn_that_stopped() -> None:
    """There is nothing to send the agent on with, so the refusal is not one."""
    agent = _agent()
    agent.hooks.on(Moment.STOP, lambda _: Verdict(refused=True))

    assert agent("echo done") == "done"


def test_a_hook_hung_for_a_while_is_taken_down_at_the_end_of_it() -> None:
    """Hung and taken down while the agent is running, which a settings file cannot be."""
    agent = _agent()
    seen: list[Occasion] = []

    with agent.hooks.on(Moment.USER_PROMPT_SUBMIT, seen.append):
        agent("echo one")
    agent("echo two")

    assert [occasion.prompt for occasion in seen] == ["echo one"]

    hung = agent.hooks.on(Moment.USER_PROMPT_SUBMIT, seen.append)
    agent("echo three")
    hung.off()
    hung.off()  # taking down what is already down is not an error
    agent("echo four")

    assert [occasion.prompt for occasion in seen] == ["echo one", "echo three"]


def test_a_hook_that_raises_has_said_nothing() -> None:
    """A flow must not fail because something hung off it did."""
    agent = _agent()

    def broken(_: Occasion) -> Verdict:
        raise RuntimeError("hook is wrong")

    agent.hooks.on(Moment.USER_PROMPT_SUBMIT, broken)

    assert agent("echo fine") == "fine"


def test_the_verdicts_of_two_hooks_are_one_verdict() -> None:
    agent = _agent()
    agent.hooks.on(Moment.USER_PROMPT_SUBMIT, lambda _: Verdict(adds="one"))
    agent.hooks.on(
        Moment.USER_PROMPT_SUBMIT, lambda _: Verdict(refused=True, because="no")
    )
    agent.hooks.on(Moment.USER_PROMPT_SUBMIT, lambda _: Verdict(adds="two"))

    said = agent.hooks.fire(Occasion(moment=Moment.USER_PROMPT_SUBMIT, agent="worker"))

    assert said == Verdict(refused=True, because="no", adds="one\n\ntwo")


def test_a_hook_may_be_hung_on_one_tool_alone() -> None:
    agent = _agent()
    seen: list[str] = []
    agent.hooks.on(
        Moment.PRE_TOOL_USE, lambda occasion: seen.append(occasion.tool), tool="Bash"
    )

    agent.hooks.fire(Occasion(moment=Moment.PRE_TOOL_USE, agent="worker", tool="Read"))
    agent.hooks.fire(Occasion(moment=Moment.PRE_TOOL_USE, agent="worker", tool="Bash"))

    assert seen == ["Bash"]


def test_a_moment_the_backend_does_not_run_is_refused_where_it_is_hung() -> None:
    """Rather than quietly never firing, which is a flow that quietly does nothing."""
    agent = _agent()

    with pytest.raises(Unhooked, match="worker does not run PermissionRequest"):
        agent.hooks.on(Moment.PERMISSION_REQUEST, lambda _: None)


def test_which_moments_each_backend_runs_is_said_on_the_agent() -> None:
    """Three of them ask before a tool is used and wait for the answer; the rest do not."""
    assert Moment.PERMISSION_REQUEST in ClaudeCodeAgent.moments
    assert Moment.PERMISSION_REQUEST in CodexAgent.moments
    assert Moment.PERMISSION_REQUEST in ZcodeAgent.moments
    assert Moment.PERMISSION_REQUEST not in KimiCodeCLIAgent.moments
    assert Moment.PERMISSION_REQUEST not in OpencodeAgent.moments
    assert Moment.STOP in CodexAgent.moments
    # The person at the prompt takes no turn of a model, so there is no moment in one.
    assert HumanAgent.moments == frozenset()


def test_a_hook_is_told_the_name_the_flow_gave_the_agent() -> None:
    agent = ShellAgent(AgentConfig(model="m", effort="high"))
    agent.rename("builder")
    seen: list[str] = []
    agent.hooks.on(
        Moment.USER_PROMPT_SUBMIT, lambda occasion: seen.append(occasion.agent)
    )

    agent("echo hi")

    assert seen == ["builder"]
    with pytest.raises(Unhooked, match="builder does not run"):
        agent.hooks.on(Moment.PERMISSION_REQUEST, lambda _: None)


def test_a_turn_that_failed_is_still_a_failed_turn() -> None:
    """The moments are around the turn, not instead of it."""
    agent = _agent()
    stopped: list[Occasion] = []
    agent.hooks.on(Moment.STOP, stopped.append)

    with pytest.raises(subprocess.CalledProcessError):
        agent("exit 3")

    assert stopped == []  # a turn that failed never got as far as stopping


def test_claude_puts_a_permission_to_the_hook_and_takes_no_for_an_answer() -> None:
    """The one moment a refusal reaches the backend: it asked, and it is waiting."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    session = agent.new()
    written: list[str] = []
    session._send = written.append  # pyright: ignore[reportAttributeAccessIssue]
    seen: list[Occasion] = []

    def gate(occasion: Occasion) -> Verdict | None:
        seen.append(occasion)
        if occasion.tool == "Write":
            return Verdict(refused=True, because="not that file")
        return None

    agent.hooks.on(Moment.PERMISSION_REQUEST, gate)

    # Read to the end: what a line says is a generator, and a request is answered as it goes.
    for line in (
        (
            '{"type": "control_request", "request_id": "1", "request": '
            '{"subtype": "can_use_tool", "tool_name": "Write", "input": '
            '{"file_path": "/etc"}}}'
        ),
        (
            '{"type": "control_request", "request_id": "2", "request": '
            '{"subtype": "can_use_tool", "tool_name": "Read", "input": '
            '{"file_path": "/etc"}}}'
        ),
    ):
        assert list(session._read(line)) == []

    refused, allowed = (line for line in written)
    assert '"behavior": "deny"' in refused
    assert "not that file" in refused
    assert '"behavior": "allow"' in allowed
    # What it was called with, both as the line a transcript has room for and in full.
    assert [(one.tool, one.about) for one in seen] == [
        ("Write", "/etc"),
        ("Read", "/etc"),
    ]
    assert seen[0].input == {"file_path": "/etc"}


def test_an_agent_stopped_inside_a_hook_stops_the_flow() -> None:
    """The one thing a hook may raise: a run ended by hand is not a run that finished."""
    from hmz.agents import Stopped

    agent = _agent()
    other = _agent()

    def drives(_: Occasion) -> Verdict | None:
        other.stop()
        return Verdict(refused=True, because=other("echo never"))

    agent.hooks.on(Moment.STOP, drives)

    with pytest.raises(Stopped):
        agent("echo hello")
