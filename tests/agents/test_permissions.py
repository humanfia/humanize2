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


#: A `claude` on an account somebody else settled the rules for: its managed settings forbid
#: `bypassPermissions` and say so nowhere -- the command line is taken, the first line out says
#: the turn is running at `default`, and a turn left there is declined every edit and ends
#: successfully having changed nothing. `--model stuck` is an account that will not grant the
#: rung below either; `--model sealed` is one that starts no turn at the mode it was asked for,
#: which is a rung with nothing under it that would not be a promotion.
_MANAGED = """
import json, pathlib, select, sys

log = pathlib.Path(LOG)


def note(entry):
    with log.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


note({"argv": sys.argv[1:]})
flags = dict(zip(sys.argv, sys.argv[1:]))
asked = flags.get("--permission-mode") or "bypassPermissions"
granted = "default" if asked == "bypassPermissions" or flags.get("--model") == "sealed" else asked
send({"type": "system", "subtype": "init", "permissionMode": granted,
      "session_id": flags.get("--session-id") or flags.get("--resume")})
words = ""
while True:
    # A window before answering, which is the ordering the real CLI has: the prompt is written
    # first and the step lands microseconds after the init line, while the model is still being
    # asked. Answering the moment the prompt arrives would be a turn no step could ever reach.
    ready, _, _ = select.select([sys.stdin], [], [], 0.5)
    if ready:
        line = sys.stdin.readline()
        if not line:
            break
        said = json.loads(line)
        if said.get("type") == "control_request":
            note({"asked": said["request"]})
            stuck = flags.get("--model") == "stuck"
            send({"type": "control_response", "response": {
                "subtype": "error" if stuck else "success",
                "request_id": said["request_id"],
                "response": {"mode": said["request"]["mode"]},
                "error": "Cannot set permission mode to bypassPermissions because it is "
                         "disabled by settings or configuration"}})
            if not stuck:
                granted = said["request"]["mode"]
                # As Claude does: the mode it is now at, said again on a line of its own.
                send({"type": "system", "subtype": "status", "permissionMode": granted,
                      "session_id": flags.get("--session-id") or flags.get("--resume")})
        else:
            words = said["message"]["content"][0]["text"]
        continue
    if words:
        note({"ran": granted})
        # Answered at whatever rung it ended up at: a turn left at `default` is declined its
        # edits and still ends successfully, saying it could not -- which is the whole defect,
        # and what a run of these tests against an unstepped driver must show rather than hang.
        send({"type": "result", "subtype": "success", "is_error": False,
              "result": words if granted != "default"
              else "I don't have permission to write that file"})
        words = ""
"""


def _managed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts that `claude` on PATH, and says where it writes down what it was asked."""
    log = tmp_path / "claude.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{_MANAGED.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return log


def test_claude_runs_a_rung_down_where_this_account_will_not_start_at_the_one_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bypass` is what an unattended flow runs at, and some accounts forbid it silently.

    The rung below is the same freedom with the asking turned back on, and the asking is
    granted here -- so the flow does the work rather than answering that it could not.
    """
    log = _managed(tmp_path, monkeypatch)
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()

    assert session("do the task") == "do the task"

    noted = _noted(log)
    assert "--dangerously-skip-permissions" in noted[0]["argv"]
    # Once: Claude says the mode again on every line of status once one has been set, and a
    # session that read one of those as an answer would ask for the rung for the whole turn.
    assert [one["asked"] for one in noted if "asked" in one] == [
        {"subtype": "set_permission_mode", "mode": "auto"}
    ]
    assert noted[-1]["ran"] == "auto"


def test_claude_says_it_is_running_a_rung_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rung nobody asked for is a thing to say, once, the way the other backend says it."""
    _managed(tmp_path, monkeypatch)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    said: list[str] = []
    agent.watch(lambda _agent, _session, event: said.append(event.text))

    agent.new()("do the task")

    stepped = (
        "claude: this account will not run an agent at bypass, so it runs at auto,"
    )
    assert [one for one in said if stepped in one] == [
        f"{stepped} where the account's own rules still apply"
    ]


def test_claude_fails_the_turn_where_the_rung_below_is_refused_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The turn is still at `default`, where the answer says the work is done and it is not."""
    _managed(tmp_path, monkeypatch)
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="stuck", effort="high")).new()

    with pytest.raises(subprocess.CalledProcessError, match="disabled by settings"):
        session("do the task")


def test_claude_does_not_step_a_rung_the_account_granted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is asked for again where the turn is already running at what it asked for."""
    log = _managed(tmp_path, monkeypatch)
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", permission="read-only")
    ).new()

    assert session("do the task") == "do the task"
    assert not [one for one in _noted(log) if "asked" in one]


def test_claude_is_never_promoted_for_having_been_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent told it may change nothing is not handed the workspace by a step down."""
    log = _managed(tmp_path, monkeypatch)
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="sealed", effort="high", permission="read-only")
    ).new()

    with pytest.raises(
        subprocess.CalledProcessError, match="not run an agent at read-only"
    ):
        session("do the task")
    assert not [one for one in _noted(log) if "asked" in one]


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
