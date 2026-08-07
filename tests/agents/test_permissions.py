"""What an agent may do without being asked, and how each backend is told it.

One ladder of four rungs, and six backends with a setting of their own apiece. What is checked
here is that each rung reaches the CLI as that CLI's own way of saying it, and that the one
moment a backend actually waits on -- a permission it is asking for -- is answered the way the
rung says it should be.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.agents import (
    PERMISSIONS,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    Moment,
    Verdict,
)
from hmz.agents.codex import unattended

if TYPE_CHECKING:
    from pathlib import Path

#: A `claude` that records the call it was made with, asks to use one tool, and answers with
#: whatever it was told once the answer to that comes back.
_CLAUDE = """
import json, pathlib, sys

log = pathlib.Path(LOG)


def note(entry):
    with log.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


note({"argv": sys.argv[1:]})
flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "control_request", "request_id": "r_1",
                      "request": {"tool_name": "Bash", "input": {"command": "rm -rf /"}}}),
          flush=True)
    answered = json.loads(sys.stdin.readline())
    note({"answered": answered["response"]["response"]})
    print(json.dumps({"type": "result", "result": said}), flush=True)
"""


def _claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts that `claude` on PATH, and says where it writes down what it was asked."""
    log = tmp_path / "claude.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{_CLAUDE.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return log


def _noted(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_the_ladder_is_four_rungs_loosest_last() -> None:
    """Which is what the interface steps through, and what a config is checked against."""
    assert PERMISSIONS == ("read-only", "workspace-write", "auto", "bypass")


def test_an_agent_nobody_was_asked_about_is_allowed_everything() -> None:
    """A flow watches its agent rather than gating it, and always has."""
    assert ClaudeCodeAgentConfig(model="m", effort="high").permission == "bypass"


def test_claude_is_given_its_exact_native_allowed_tool_rules() -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="m",
            effort="high",
            permission="workspace-write",
            allowed_tools=("Bash(git diff *)",),
        )
    ).new()
    argv = session._command()
    assert argv.count("--allowedTools") == 1
    assert argv[argv.index("--allowedTools") + 1] == "Bash(git diff *)"


def test_claude_allowed_tool_rules_are_canonical() -> None:
    with pytest.raises(ValueError, match="unique sorted"):
        ClaudeCodeAgentConfig(
            model="m",
            effort="high",
            allowed_tools=("Read", "Read"),
        )


@pytest.mark.parametrize(
    ("permission", "mode"),
    [("read-only", "plan"), ("workspace-write", "acceptEdits"), ("auto", "auto")],
)
def test_claude_runs_at_the_permission_mode_the_rung_means(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, permission: str, mode: str
) -> None:
    log = _claude(tmp_path, monkeypatch)
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", permission=permission)
    ).new()
    assert session("hi") == "hi"

    argv = _noted(log)[0]["argv"]
    assert argv[argv.index("--permission-mode") + 1] == mode
    assert "--dangerously-skip-permissions" not in argv


def test_claude_unchecked_is_the_flag_claude_documents_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _claude(tmp_path, monkeypatch)
    assert ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()("hi")

    argv = _noted(log)[0]["argv"]
    assert "--dangerously-skip-permissions" in argv
    assert "--permission-mode" not in argv


def test_a_permission_is_granted_unless_the_rung_or_a_hook_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one moment a backend actually waits on, which is the one a refusal reaches."""
    log = _claude(tmp_path, monkeypatch)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    assert agent.new()("hi") == "hi"
    assert _noted(log)[1]["answered"]["behavior"] == "allow"


def test_an_agent_that_may_change_nothing_is_refused_what_would_change_something(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Granting one under `reading` would be handing back the rung the flow asked for."""
    log = _claude(tmp_path, monkeypatch)
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", permission="read-only")
    )
    assert agent.new()("hi") == "hi"
    assert _noted(log)[1]["answered"]["behavior"] == "deny"


def test_a_hook_may_refuse_a_permission_at_any_rung_that_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _claude(tmp_path, monkeypatch)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    with agent.hooks.on(
        Moment.PERMISSION_REQUEST, lambda _: Verdict(refused=True, because="not that")
    ):
        assert agent.new()("hi") == "hi"

    answered = _noted(log)[1]["answered"]
    assert answered["behavior"] == "deny"
    assert answered["message"] == "not that"


@pytest.mark.parametrize(
    ("permission", "sandbox", "policy"),
    [
        ("read-only", "read-only", "never"),
        ("workspace-write", "workspace-write", "never"),
        ("auto", "workspace-write", "on-request"),
        ("bypass", "danger-full-access", "never"),
    ],
)
def test_codex_is_the_one_backend_with_a_sandbox_of_its_own(
    permission: str, sandbox: str, policy: str
) -> None:
    """So its rungs are the real thing rather than an approximation of one."""
    said = unattended(permission)
    assert said["sandbox"] == sandbox
    assert said["approvalPolicy"] == policy
    assert said["serviceTier"] == "default"


def test_codex_is_only_ever_asked_at_the_rung_that_means_the_asking_is_granted() -> (
    None
):
    """Everywhere else a turn waiting on an approval would be a flow that had stopped."""
    asked = [
        rung for rung in PERMISSIONS if unattended(rung)["approvalPolicy"] != "never"
    ]
    assert asked == ["auto"]


def test_a_rung_nobody_wrote_down_is_the_one_an_agent_comes_at() -> None:
    """A config read back out of a file older than this setting is such an agent."""
    assert unattended("") == unattended("bypass")


@pytest.mark.parametrize(
    ("permission", "mode", "planning"),
    [
        ("read-only", "auto", True),
        ("workspace-write", "auto", False),
        ("auto", "auto", False),
        ("bypass", "yolo", False),
    ],
)
def test_kimi_is_told_the_rung_as_a_mode_and_a_plan(
    permission: str, mode: str, planning: bool
) -> None:
    """`manual` is never used: it asks, and an unattended flow has nobody to answer."""
    from hmz.agents.kimi import _PERMITTED

    said = _PERMITTED[permission]
    assert said["permission_mode"] == mode
    assert said["plan_mode"] is planning


def test_every_backend_has_something_to_say_at_every_rung() -> None:
    """A rung a backend quietly ignored would be a setting that lies."""
    from hmz.agents import codex as codex_module
    from hmz.agents import kimi, opencode

    for rung in PERMISSIONS:
        assert rung in kimi._PERMITTED
        assert rung in opencode._PERMITTED
        assert rung in codex_module._PERMITTED


def test_an_agent_allowed_less_is_another_agent_at_the_same_model() -> None:
    """The config is frozen, so the rung is part of what the agent is."""
    from dataclasses import replace

    config = CodexAgentConfig(model="m", effort="high")
    tighter = replace(config, permission="read-only")
    assert config.permission == "bypass"
    assert tighter.permission == "read-only"
    assert tighter.model == config.model


def test_kimi_and_codex_agents_still_build_at_every_rung() -> None:
    """Nothing is started by configuring one, so this costs no process."""
    for rung in PERMISSIONS:
        assert (
            KimiCodeCLIAgent(
                KimiCodeCLIAgentConfig(model="m", effort="high", permission=rung)
            ).config.permission
            == rung
        )
        assert (
            CodexAgent(
                CodexAgentConfig(model="m", effort="high", permission=rung)
            ).config.permission
            == rung
        )


def test_a_failed_turn_is_still_a_failed_turn_at_every_rung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rung says what the agent may do, not what a turn that could not run answers."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\nraise SystemExit(3)\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(subprocess.CalledProcessError):
        ClaudeCodeAgent(
            ClaudeCodeAgentConfig(model="m", effort="high", permission="read-only")
        ).new()("hi")
