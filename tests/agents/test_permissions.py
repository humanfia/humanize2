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
from dataclasses import replace
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
    ("service_tier", "fast_mode"), [("default", False), ("fast", True)]
)
def test_claude_maps_the_common_service_tier_to_fast_mode(
    service_tier: str, fast_mode: bool
) -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-5",
            effort="max",
            service_tier=service_tier,
        )
    ).new()
    argv = session._command()
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings == {"fastMode": fast_mode}


def test_service_tier_is_closed() -> None:
    with pytest.raises(ValueError, match="service_tier must be one of"):
        ClaudeCodeAgentConfig(
            model="claude-opus-5",
            effort="max",
            service_tier="slow",
        )


def test_the_permission_rung_is_closed() -> None:
    """A rung no backend has a word for is refused where it is written, not reached down for.

    Every driver maps the rung to a setting of its own, so one outside the ladder would be a
    key that is not there in whichever backend ran it -- said here instead, where they all pass.
    """
    with pytest.raises(ValueError, match="permission must be one of"):
        ClaudeCodeAgentConfig(model="m", effort="high", permission="whatever")


def test_fast_service_tier_fails_before_an_unsupported_backend_turn() -> None:
    with pytest.raises(ValueError, match="does not support service tier"):
        KimiCodeCLIAgent(
            KimiCodeCLIAgentConfig(
                model="kimi-code/k3",
                effort="high",
                service_tier="fast",
            )
        )


def test_a_tier_a_backend_cannot_send_is_refused_however_it_is_asked_for() -> None:
    """`reconfigure` is the other way in, and a flow may reach for it mid-run."""
    agent = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    )

    with pytest.raises(ValueError, match="does not support service tier"):
        agent.reconfigure(replace(agent.config, service_tier="fast"))

    assert agent.config.service_tier == "default"  # left as it was


def test_a_tier_a_backend_can_send_is_taken_by_reconfigure() -> None:
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="max"))

    agent.reconfigure(replace(agent.config, service_tier="fast"))

    assert agent.config.service_tier == "fast"
    argv = agent.new()._command()
    assert json.loads(argv[argv.index("--settings") + 1]) == {"fastMode": True}


@pytest.mark.parametrize(
    ("permission", "mode"),
    [
        ("read-only", "plan"),
        ("workspace-write", "acceptEdits"),
        ("auto", "auto"),
        ("bypass", "manual"),
    ],
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
    # No rung skips the asking: `--dangerously-skip-permissions` is the flag an account may
    # forbid, so humanize never sends it and answers the asking itself instead.
    assert "--dangerously-skip-permissions" not in argv


def test_claude_takes_the_asking_for_bypass_rather_than_skipping_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bypass` runs at `manual` and routes every request to humanize, which answers it.

    Which is what lets a `bypass` agent run on an account whose managed settings forbid
    `bypassPermissions`: the mode humanize uses is one every account allows, and the deciding
    is humanize's rather than the flag's. `stdio` is the request reaching us, and it is only
    on for `bypass` -- the other rungs are enforced by the mode Claude runs them at.
    """
    log = _claude(tmp_path, monkeypatch)
    assert ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()("hi")

    argv = _noted(log)[0]["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert argv[argv.index("--permission-prompt-tool") + 1] == "stdio"
    assert "--dangerously-skip-permissions" not in argv


@pytest.mark.parametrize("permission", ["read-only", "workspace-write", "auto"])
def test_claude_routes_the_asking_home_only_for_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, permission: str
) -> None:
    """Every other rung is the mode's to enforce, so nothing is routed for it to answer."""
    log = _claude(tmp_path, monkeypatch)
    ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", permission=permission)
    ).new()("hi")

    assert "--permission-prompt-tool" not in _noted(log)[0]["argv"]


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


def test_codex_maps_fast_to_its_priority_service_tier() -> None:
    assert unattended("read-only", "fast")["serviceTier"] == "priority"


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
    from hmz.agents import kimi, opencode, zcode

    for rung in PERMISSIONS:
        assert rung in kimi._PERMITTED
        assert rung in opencode._PERMITTED
        assert rung in codex_module._PERMITTED
        assert rung in zcode._PERMITTED


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


#: A `codex app-server` on a machine whose Codex was given requirements of somebody else's: an
#: enterprise policy that arrives with the account, or the `requirements.toml` a platform that
#: packages Codex puts on its machines. One forbidding the sandbox `bypass` is refuses the whole
#: call rather than running it tighter, which is every turn of an unattended flow failing there.
#: A model of `boom` is refused for a reason that is not the rung, which must not be stepped.
_REQUIRED = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    call = json.loads(line)
    with LOG.open("a") as stream:
        json.dump(call, stream)
        stream.write("\\n")
    if "id" not in call:
        continue
    told = call.get("params") or {}
    if told.get("sandbox") == "danger-full-access":
        send({"jsonrpc": "2.0", "id": call["id"], "error": {"code": -32600, "message":
              'failed to load configuration: `approval_policy = "never"` cannot be used '
              'because requirements do not allow `sandbox_mode = "danger-full-access"`; '
              "Codex would fall back to read-only permissions with approvals disabled. "
              "Choose an `approval_policy` based on what you need, such as `on-request`, "
              "or choose an allowed sandbox mode."}})
        continue
    if told.get("model") == "boom":
        send({"jsonrpc": "2.0", "id": call["id"], "error": {"code": -32600, "message":
              "the model is not supported when using a ChatGPT account"}})
        continue
    send({"jsonrpc": "2.0", "id": call["id"], "result": {"thread": {"id": "thread_fake"}}
          if call["method"] == "thread/start" else {}})
    if call["method"] == "thread/start":
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
    if call["method"] == "turn/start":
        send({"method": "turn/started", "params": {"turnId": "turn_fake"}})
        send({"method": "item/completed",
              "params": {"item": {"type": "agentMessage", "text": "done"}}})
        send({"method": "turn/completed", "params": {}})
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
"""


def _codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts that `codex` on PATH, and says where it writes down what it was asked."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "codex"
    fake.write_text(f"#!{sys.executable}\n{_REQUIRED}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return binaries / "codex.log"


def test_codex_runs_a_rung_down_where_this_machine_will_not_take_the_one_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bypass` is what an unattended flow runs at, and some installations forbid it.

    The rung below is the same freedom with the asking turned back on, and the asking is
    granted here -- so the flow runs rather than failing on every turn it takes.
    """
    log = _codex(tmp_path, monkeypatch)
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    assert session("do the task") == "done"

    started = [call for call in _noted(log) if call.get("method") == "thread/start"]
    assert [one["params"]["sandbox"] for one in started] == [
        "danger-full-access",
        "workspace-write",
    ]
    assert started[-1]["params"]["approvalPolicy"] == "on-request"


def test_codex_finds_out_what_this_machine_takes_once_and_not_once_a_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One refusal is the whole cost of finding out, and a resumed thread is told the same."""
    log = _codex(tmp_path, monkeypatch)
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()
    session("do the task")
    session("and the next")

    calls = _noted(log)
    refused = [
        one for one in calls if one["params"].get("sandbox") == "danger-full-access"
    ]
    resumed = [one for one in calls if one.get("method") == "thread/resume"]
    assert len(refused) == 1
    assert resumed[0]["params"]["sandbox"] == "workspace-write"
    assert resumed[0]["params"]["approvalPolicy"] == "on-request"
    assert [
        one["params"]["approvalPolicy"]
        for one in calls
        if one.get("method") == "turn/start"
    ] == ["on-request", "on-request"]


def test_codex_steps_down_for_the_rung_and_for_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal about the account or the model is the turn's answer, not a rung to walk down."""
    _codex(tmp_path, monkeypatch)
    session = CodexAgent(CodexAgentConfig(model="boom", effort="high")).new()

    with pytest.raises(subprocess.CalledProcessError, match="not supported"):
        session("do the task")


@pytest.mark.parametrize(
    ("refused", "instead"),
    [
        ("bypass", "auto"),
        ("auto", "workspace-write"),
        ("workspace-write", "read-only"),
        ("read-only", ""),
    ],
)
def test_the_rung_below_each_rung_is_the_next_one_down(
    refused: str, instead: str
) -> None:
    """And below the bottom there is nothing: a machine that will not run one at all."""
    from hmz.agents.codex import _tighter

    assert _tighter(refused) == instead
