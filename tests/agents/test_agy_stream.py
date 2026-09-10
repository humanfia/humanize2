"""Antigravity process reuse, cumulative accounting, and print-mode boundaries."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, ConfigDict

import hmz.agents.agy as agy_driver
from hmz.agents import (
    AgentConfig,
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    Failed,
)
from hmz.agents.event import Usage
from hmz.providers import Provider
from tests.stubs import HereAnchor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_FAKE = r"""
import json, os, pathlib, sys, uuid
flags = dict(zip(sys.argv, sys.argv[1:]))
streaming = flags.get("--input-format") == "stream-json"
ident = flags.get("--conversation") or str(uuid.uuid4())
usage_file = pathlib.Path(LOG).with_name(ident + ".usage")
count = int(usage_file.read_text()) if usage_file.exists() else 0

def emit(record):
    print(json.dumps(record), flush=True)

emit({"event": "init", "conversation_id": ident})

def turn(prompt):
    global count
    with pathlib.Path(LOG).open("a") as log:
        log.write(json.dumps({"pid": os.getpid(), "argv": sys.argv[1:],
          "prompt": prompt, "session": ident,
          "inherited": os.environ.get("AGY_TEST_SETTING")}) + "\n")
    if prompt == "empty":
        sys.exit(0)
    if prompt == "/help":
        emit({"event": "result", "result": {"conversation_id": "",
          "response": "/help Show commands", "status": "SUCCESS",
          "usage": {"input_tokens": 0, "output_tokens": 0},
          "command": {"name": "help"}}})
        return
    if prompt == "recount":
        count = 0  # what a restart or an account fallback does to a cumulative counter
    count += 1
    usage_file.write_text(str(count))
    # A command is the whole prompt; a prompt that merely opens with a path is work, and the
    # streaming transport takes that.
    commanded = prompt.startswith("/") and len(prompt.split()) == 1
    failed = prompt == "fail" or (streaming and commanded)
    text = prompt
    if prompt.lstrip("/") == "read-workspace":
        directories = [sys.argv[i + 1] for i, arg in enumerate(sys.argv[:-1])
                       if arg == "--add-dir"]
        files = [pathlib.Path(root) / "workspace.txt" for root in directories]
        text = next((path.read_text() for path in files if path.exists()), "scratch")
    structured = {"value": 7 if prompt == "invalid-structured" else text}
    if "--json-schema" in flags:
        # Native display text includes rejected finish calls and tool metadata; only
        # structured_output holds the accepted answer without those extra fields.
        text = json.dumps({"value": "display-only", "toolAction": "Finish"})
        text += "\n" + json.dumps({**structured, "toolSummary": "Final answer"})
        if prompt == "invalid-structured":
            text = json.dumps({"value": "valid-display-only"})
    if not failed:
        emit({"event": "step_update", "step_update": {"state": "ACTIVE",
          "step_type": "RESPONSE", "text_delta": text}})
    result = {"conversation_id": ident,
      "response": text if not failed else "", "status": "ERROR" if failed else "SUCCESS",
      "error": "turn refused" if failed else "",
      "usage": {"input_tokens": count * 2, "output_tokens": count * 3}}
    if "--json-schema" in flags:
        result["structured_output"] = structured
    emit({"event": "result", "result": result})
    if prompt == "bad-exit":
        sys.exit(3)

if streaming:
    assert "--print" not in flags
    for line in sys.stdin:
        message = json.loads(line)
        assert message["event"] == "user"
        turn(message["message"]["content"])
else:
    turn(flags.get("--print", ""))
"""


@dataclass
class _Agy:
    agent: AntigravityCLIAgent
    log: Path
    native: Path

    def calls(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


@pytest.fixture
def agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Agy]:
    log = tmp_path / "calls.jsonl"
    binary = tmp_path / "agy"
    binary.write_text(f"#!{sys.executable}\n{_FAKE.replace('LOG', repr(str(log)))}")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    native = tmp_path / "native"
    original = agy_driver._native

    def local_inputs(
        cwd: Path, env: dict[str, str], args: tuple[str, ...] = ()
    ) -> bytes | None:
        return original(cwd, {**env, "HOME": str(native)}, args)

    monkeypatch.setattr(agy_driver, "_native", local_inputs)
    agent = AntigravityCLIAgent(
        AntigravityCLIAgentConfig(model="test-model", effort="low")
    )
    yield _Agy(agent, log, native)
    agent.stop()


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str


def test_two_plain_turns_reuse_process_and_report_usage_deltas(agy: _Agy) -> None:
    session = agy.agent.new()
    first = list(session.stream("first"))
    second = list(session.stream("second"))
    assert [event.kind for event in second] == ["text", "result"]
    assert first[-1].spent.total == second[-1].spent.total == 5
    assert first[-1].tokens == second[-1].tokens == {"test-model": 5}
    one, two = agy.calls()
    assert one["pid"] == two["pid"]
    assert one["session"] == two["session"] == session.id
    assert agy.agent.opened == [session.id]


@pytest.mark.parametrize(("prompt", "shaped"), [("/model", False), ("shape", True)])
def test_finite_turns_preserve_conversation_and_usage_across_restarts(
    agy: _Agy, prompt: str, shaped: bool
) -> None:
    session = agy.agent.new()
    turns = [list(session.stream("first"))]
    turns.append(list(session.stream(prompt, schema=_Answer if shaped else None)))
    turns.append(list(session.stream("third")))
    assert [turn[-1].spent.total for turn in turns] == [5, 5, 5]
    first, finite, third = agy.calls()
    assert len({call["pid"] for call in (first, finite, third)}) == 3
    assert "--print" in finite["argv"]
    assert "--input-format" not in finite["argv"]
    for call in (finite, third):
        assert call["argv"][call["argv"].index("--conversation") + 1] == session.id
    assert agy.agent.opened == [session.id]


def test_first_shaped_turn_opens_once_and_reports_a_valid_shape(agy: _Agy) -> None:
    session = agy.agent.new()
    assert session("first", schema=_Answer) == _Answer(value="first")
    assert list(session.stream("second"))[-1].spent.total == 5
    assert agy.agent.opened == [session.id]


def test_shape_uses_final_native_value_and_plain_turns_resume(agy: _Agy) -> None:
    session = agy.agent.new()
    assert session("first") == "first"
    ident = session.id
    assert session("accepted", schema=_Answer) == _Answer(value="accepted")
    assert session("third") == "third"
    assert session("fourth") == "fourth"
    first, shaped, third, fourth = agy.calls()
    assert len({call["pid"] for call in (first, shaped, third)}) == 3
    assert third["pid"] == fourth["pid"]
    assert {call["session"] for call in agy.calls()} == {ident}


def test_invalid_native_structured_value_cannot_use_valid_display_text(
    agy: _Agy,
) -> None:
    session = agy.agent.new()
    with pytest.raises(ValueError, match="did not answer as a _Answer"):
        session("invalid-structured", schema=_Answer)
    assert session("invalid-structured", schema=_Answer, suppress=True) is None
    assert session("recovered") == "recovered"


def test_local_slash_command_preserves_conversation_usage_baseline(agy: _Agy) -> None:
    session = agy.agent.new()
    first = list(session.stream("first"))[-1]
    help_result = list(session.stream("/help"))[-1]
    third = list(session.stream("third"))[-1]
    assert help_result.text == "/help Show commands"
    assert not help_result.spent
    assert not help_result.tokens
    assert (
        dict(first.spent)
        == dict(third.spent)
        == {
            "input_tokens": 2,
            "output_tokens": 3,
        }
    )
    assert {call["session"] for call in agy.calls()} == {session.id}


def test_finite_result_cannot_hide_nonzero_exit(agy: _Agy) -> None:
    session = agy.agent.new()
    with pytest.raises(Failed) as refused:
        session("bad-exit", schema=_Answer)
    assert refused.value.returncode == 3
    assert session.named is None
    assert list(session.stream("retry"))[-1].spent.total == 5


def test_reconfigure_restarts_with_new_model_and_preserves_native_usage(
    agy: _Agy,
) -> None:
    session = agy.agent.new()
    session("first")
    agy.agent.reconfigure(
        replace(agy.agent.config, model="another-model", permission="auto")
    )
    assert list(session.stream("second"))[-1].tokens == {"another-model": 5}
    one, two = agy.calls()
    assert one["pid"] != two["pid"]
    assert one["session"] == two["session"]
    assert two["argv"][two["argv"].index("--model") + 1] == "another-model"
    assert "--dangerously-skip-permissions" in two["argv"]


def test_environment_changes_restart_the_process(
    agy: _Agy, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = agy.agent.new()
    session("first")
    monkeypatch.setenv("AGY_TEST_SETTING", "changed")
    session("second")
    one, two = agy.calls()
    assert one["pid"] != two["pid"]
    assert two["inherited"] == "changed"


@pytest.mark.parametrize("prompt", ["fail", "empty"])
def test_failed_initial_turn_leaves_no_adopted_id_or_usage_baseline(
    agy: _Agy, prompt: str
) -> None:
    session = agy.agent.new()
    with pytest.raises(Failed):
        session(prompt)
    assert session.named is None
    assert list(session.stream("retry"))[-1].spent.total == 5
    one, two = agy.calls()
    assert one["pid"] != two["pid"]
    assert one["session"] != two["session"]


def test_failure_of_open_conversation_does_not_recharge_earlier_usage(
    agy: _Agy,
) -> None:
    session = agy.agent.new()
    session("first")
    with pytest.raises(Failed):
        session("fail")
    assert list(session.stream("retry"))[-1].spent.total == 5
    assert len({one["session"] for one in agy.calls()}) == 1


@pytest.mark.parametrize(
    "relative", ["settings.json", "skills/new/SKILL.md", "plugins/new/plugin.json"]
)
def test_new_native_configuration_and_skill_roots_restart(
    agy: _Agy, relative: str
) -> None:
    session = agy.agent.new()
    session("first")
    path = agy.native / ".gemini/antigravity-cli" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    session("second")
    one, two = agy.calls()
    assert one["pid"] != two["pid"]
    assert one["session"] == two["session"]


def test_inherited_external_skills_are_watched_and_cycles_terminate(
    agy: _Agy, tmp_path: Path
) -> None:
    root = tmp_path / ".agents"
    root.mkdir()
    shared = tmp_path / "shared.json"
    shared.write_text(
        json.dumps(
            {"inherits": [{"path": str(shared)}], "entries": [{"path": "external"}]}
        )
    )
    (root / "skills.json").write_text(json.dumps({"inherits": [{"path": str(shared)}]}))
    session = agy.agent.new()
    session("first")
    external = tmp_path / "external/new/SKILL.md"
    external.parent.mkdir(parents=True)
    external.write_text("New native skill")
    session("second")
    assert len({call["pid"] for call in agy.calls()}) == 2


def test_runtime_logs_do_not_invalidate_native_configuration(agy: _Agy) -> None:
    session = agy.agent.new()
    session("first")
    runtime = agy.native / ".gemini/antigravity-cli/conversations/run.db"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("native runtime history")
    session("second")
    assert len({call["pid"] for call in agy.calls()}) == 1


def test_native_home_flag_tracks_custom_settings_without_runtime_databases(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    native = tmp_path / "isolated"
    native.mkdir()
    settings = native / "settings.json"
    settings.write_text('{"modelProvider":"gemini"}')
    environment = {"HOME": str(home)}
    args = ("--app_data_dir", os.path.relpath(native, home / ".gemini"))
    before = agy_driver._native(tmp_path, environment, args)
    database = native / "conversations/new.db"
    database.parent.mkdir()
    database.write_text("history")
    assert agy_driver._native(tmp_path, environment, args) == before
    settings.write_text('{"modelProvider":"gemini","verbosity":"high"}')
    assert agy_driver._native(tmp_path, environment, args) != before


def test_a_data_directory_flag_with_nothing_after_it_names_nothing(
    tmp_path: Path,
) -> None:
    """An empty value is not the whole of `~/.gemini`, which is a home read every turn."""
    home = tmp_path / "home"
    (home / ".gemini/antigravity-cli").mkdir(parents=True)
    (home / ".gemini/antigravity-cli/settings.json").write_text("{}")
    environment = {"HOME": str(home)}

    assert agy_driver._native(tmp_path, environment, ("--app_data_dir",)) == (
        agy_driver._native(tmp_path, environment, ())
    )


@pytest.mark.parametrize(
    ("prompt", "shaped"),
    [("read-workspace", False), ("read-workspace", True), ("/read-workspace", False)],
)
def test_session_workspace_is_explicit_in_both_modes_beside_provider_directories(
    agy: _Agy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    shaped: bool,
) -> None:
    workspace = tmp_path / "session workspace"
    workspace.mkdir()
    (workspace / "workspace.txt").write_text("session contents")
    extra = tmp_path / "additional workspace"
    extra.mkdir()
    (extra / "workspace.txt").write_text("other contents")
    provider = Provider("agy", "test", args=("--add-dir", str(extra)))

    def node() -> Provider:
        return provider

    def swaps(_provider: Provider) -> tuple[tuple[str, str], ...]:
        # Credential rewriting is tested independently; here the real spawn path must
        # append the provider's extra roots alongside the session's explicit root.
        return ()

    monkeypatch.setattr(agy.agent, "node", node)
    monkeypatch.setattr(Provider, "swaps", swaps)
    session = agy.agent.new(workspace)
    for _ in range(2):
        if shaped:
            assert session(prompt, schema=_Answer) == _Answer(value="session contents")
        else:
            assert session(prompt) == "session contents"
    one, two = agy.calls()
    for call in (one, two):
        argv = call["argv"]
        roots = [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "--add-dir"]
        assert roots == [str(workspace), str(extra)]
    assert (one["pid"] == two["pid"]) is (not shaped and not prompt.startswith("/"))
    assert one["session"] == two["session"] == session.id


def test_a_prompt_that_opens_with_a_path_is_work_and_keeps_the_process(
    agy: _Agy,
) -> None:
    """A task naming a file is not a command: tearing the process down costs a cold start."""
    session = agy.agent.new()
    session("first")
    assert session("/tmp/build.log has the failure in it") == (
        "/tmp/build.log has the failure in it"
    )
    one, two = agy.calls()
    assert one["pid"] == two["pid"]
    assert "--print" not in two["argv"]


def test_a_backwards_native_counter_charges_the_whole_turn(agy: _Agy) -> None:
    """A conversation whose count started again spent that count, rather than nothing."""
    session = agy.agent.new()
    assert list(session.stream("first"))[-1].spent.total == 5
    assert list(session.stream("second"))[-1].spent.total == 5
    # The counter is back to what one turn costs: what this turn spent is all of it.
    assert dict(list(session.stream("recount"))[-1].spent) == {
        "input_tokens": 2,
        "output_tokens": 3,
    }


def test_one_counter_going_backwards_starts_the_whole_count_again(agy: _Agy) -> None:
    """A restart is the count's, not one column's: kinds still above their old total are new."""
    session = agy.agent.new()
    session._previous = Usage({"input_tokens": 100.0, "output_tokens": 50.0})
    fresh = Usage({"input_tokens": 120.0, "output_tokens": 40.0})
    assert dict(session._delta(fresh)) == {"input_tokens": 120.0, "output_tokens": 40.0}


def test_a_native_home_flag_naming_nothing_leaves_the_default_home(
    tmp_path: Path,
) -> None:
    """Rather than collapsing onto the whole Gemini home and walking all of it."""
    home = tmp_path / "home"
    (home / ".gemini/antigravity-cli").mkdir(parents=True)
    (home / ".gemini/settings.json").write_text("{}")
    environment = {"HOME": str(home)}
    plain = agy_driver._native(tmp_path, environment, ())
    for args in (("--app_data_dir",), ("--app_data_dir=",)):
        assert agy_driver._native(tmp_path, environment, args) == plain
    # And the flag still moves the home when it names one.
    assert agy_driver._native(tmp_path, environment, ("--app_data_dir", "x")) != plain


def test_a_refreshed_provider_credential_does_not_restart_the_process(
    agy: _Agy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A token rotating on its own schedule must not end a conversation's process."""
    token = tmp_path / "token.json"
    token.write_text("first credential")
    provider = Provider("agy", "test")

    def node() -> Provider:
        return provider

    def swaps(_provider: Provider) -> tuple[tuple[str, str], ...]:
        return (("/native/agy/token.json", str(token)),)

    def command(_provider: Provider, argv: list[str] | tuple[str, ...]) -> list[str]:
        # The supervisor answering those paths is tested where it lives; what is in
        # question here is only whether the file's contents reach the restart decision.
        return list(argv)

    monkeypatch.setattr(agy.agent, "node", node)
    monkeypatch.setattr(Provider, "swaps", swaps)
    monkeypatch.setattr(Provider, "command", command)
    session = agy.agent.new()
    session("first")
    token.write_text("refreshed credential")
    session("second")
    one, two = agy.calls()
    assert one["pid"] == two["pid"]
    assert one["session"] == two["session"] == session.id


def test_an_anchored_session_adds_the_mirror_it_actually_works_in(
    agy: _Agy, tmp_path: Path
) -> None:
    """The path the flag pins is the CLI's, and an anchored CLI reads this machine's mirror."""
    workspace, mirror = tmp_path / "workspace", tmp_path / "mirror"
    (workspace / "one").mkdir(parents=True)
    (workspace / "one/workspace.txt").write_text("target contents")
    (mirror / "one").mkdir(parents=True)
    (mirror / "one/workspace.txt").write_text("mirror contents")
    anchor = HereAnchor(target="local", workspace=str(workspace), shadow=str(mirror))
    agent = _AnchoredAntigravity(agy.agent.config, anchor)
    session = agent.new(workspace / "one")

    assert session("read-workspace") == "mirror contents"
    assert anchor.into == [str(workspace / "one")]
    agent.stop()


class _AnchoredAntigravity(AntigravityCLIAgent):
    """Antigravity whose turns land on a machine that is really this one."""

    def __init__(self, config: AgentConfig, anchor: HereAnchor) -> None:
        super().__init__(config)
        self._held = anchor

    @property
    def anchor(self) -> HereAnchor:
        return self._held
