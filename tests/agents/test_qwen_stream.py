"""Qwen's retained process, resumed shaped turns, and configuration boundaries."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Barrier
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz import home
from hmz.coganchor.agents import Failed, QwenCodeAgent, QwenCodeAgentConfig
from hmz.coganchor.agents import qwen as backend
from hmz.coganchor.agents.skills import Loaded
from hmz.coganchor.machines import AnchoredConfig
from tests.stubs import HereAnchor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


_FAKE = r"""
import json, os, pathlib, sys, uuid

flags = dict(zip(sys.argv, sys.argv[1:]))
streaming = flags.get("--input-format") == "stream-json"
assert not (streaming and "--json-schema" in flags)
ident = flags.get("--resume") or str(uuid.uuid4())
system = pathlib.Path(os.environ["QWEN_CODE_SYSTEM_SETTINGS_PATH"])
settings = json.loads(system.read_text())
lowest = pathlib.Path(os.environ.get("QWEN_CODE_SYSTEM_DEFAULTS_PATH")
  or system.parent / "system-defaults.json")
defaults = json.loads(lowest.read_text()) if lowest.exists() else None
skills = sorted(p.parent.name for p in pathlib.Path(".agents/skills").glob("*/SKILL.md"))


def emit(record):
    print(json.dumps({"session_id": ident, **record}), flush=True)


def turn(prompt):
    if prompt == "migrate":
        system.write_text(json.dumps({**settings, "$version": 4}, indent=2) + "\n")
    if prompt == "migrate-defaults":
        lowest.write_text(json.dumps({**defaults, "$version": 4}, indent=2) + "\n")
    with pathlib.Path(LOG).open("a") as log:
        log.write(json.dumps({"pid": os.getpid(), "argv": sys.argv[1:],
          "prompt": prompt, "effort": settings["model"]["reasoningEffort"],
          "session": ident, "skills": skills, "defaults": defaults,
          "compiled": os.environ.get("NODE_COMPILE_CACHE")}) + "\n")
    emit({"type": "system", "subtype": "init"})
    ledger = pathlib.Path(LOG).with_name(ident + ".usage.json")
    previous = json.loads(ledger.read_text()) if ledger.exists() else {}
    if prompt == "reset-counter":
        previous = {}
    count = 4 if prompt == "many" else 1
    usage = {"input_tokens": 1000, "output_tokens": 40} if count == 4 else {
      "input_tokens": 2, "output_tokens": 3}
    totals = {key: previous.get(key, 0) + value * count for key, value in usage.items()}
    ledger.write_text(json.dumps(totals))
    if prompt == "fail":
        emit({"type": "result", "is_error": True, "error": {"message": "turn refused"},
          "usage": totals})
        return
    text = json.dumps({"value": prompt}) if "--json-schema" in flags else prompt
    if count == 1:
        usage = {"input_tokens": 2}
    if prompt == "zero":
        usage = {"input_tokens": 0, "output_tokens": 0}
    if prompt in ("result-only", "reset-counter"):
        usage = {}
    for index in range(count):
        message = {"type": "assistant", "message": {"id": str(index), "content": [
          {"type": "text", "text": text}], "usage": usage}}
        emit(message)
        if prompt == "repeat":
            emit(message)
    emit({"type": "result", "result": text, "usage": totals})
    if prompt == "bad-exit":
        sys.exit(3)


if streaming:
    for line in sys.stdin:
        turn(json.loads(line)["message"]["content"])
else:
    turn(sys.stdin.read())
"""


@dataclass
class _Qwen:
    agent: QwenCodeAgent
    log: Path

    def calls(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


@pytest.fixture
def qwen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Qwen]:
    log = tmp_path / "calls.jsonl"
    binary = tmp_path / "qwen"
    binary.write_text(f"#!{sys.executable}\n{_FAKE.replace('LOG', repr(str(log)))}")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    agent = QwenCodeAgent(QwenCodeAgentConfig(model="test-model", effort="low"))
    yield _Qwen(agent, log)
    agent.stop()


class _Answer(BaseModel):
    value: str


def test_plain_turns_reuse_process_without_reusing_usage_or_display_state(
    qwen: _Qwen,
) -> None:
    session = qwen.agent.new()
    first = list(session.stream("first"))
    second = list(session.stream("second"))
    assert [event.kind for event in second] == ["text", "result"]
    assert first[-1].spent.total == second[-1].spent.total == 5
    assert dict(second[-1].spent) == {"input_tokens": 2, "output_tokens": 3}
    calls = qwen.calls()
    assert calls[0]["pid"] == calls[1]["pid"]
    assert calls[0]["session"] == calls[1]["session"] == session.id
    assert qwen.agent.opened == [session.id]


def test_shape_turn_resumes_and_returns_to_streaming_without_changing_conversation(
    qwen: _Qwen,
) -> None:
    session = qwen.agent.new()
    assert session("first") == "first"
    assert session("shape", schema=_Answer) == _Answer(value="shape")
    assert session("third") == "third"
    first, shaped, third = qwen.calls()
    assert len({one["pid"] for one in (first, shaped, third)}) == 3
    assert "--input-format" in first["argv"]
    assert "--input-format" not in shaped["argv"]
    assert "--json-schema" in shaped["argv"]
    assert "--input-format" in third["argv"]
    for call in (shaped, third):
        assert call["argv"][call["argv"].index("--resume") + 1] == session.id
    assert qwen.agent.opened == [session.id]


def test_first_shaped_turn_opens_only_one_conversation(qwen: _Qwen) -> None:
    session = qwen.agent.new()
    assert session("shape", schema=_Answer) == _Answer(value="shape")
    assert session("plain") == "plain"
    assert qwen.agent.opened == [session.id]
    first, second = qwen.calls()
    assert first["session"] == second["session"]
    assert first["pid"] != second["pid"]


def test_shape_success_record_does_not_hide_a_nonzero_exit(qwen: _Qwen) -> None:
    session = qwen.agent.new()
    with pytest.raises(Failed) as refused:
        session("bad-exit", schema=_Answer)
    assert refused.value.returncode == 3
    assert qwen.agent.opened == []


def test_reconfigure_restarts_with_new_model_permissions_and_web_policy(
    qwen: _Qwen,
) -> None:
    session = qwen.agent.new()
    session("first")
    qwen.agent.reconfigure(
        replace(
            qwen.agent.config,
            model="second-model",
            permission="read-only",
            web_search=False,
        )
    )
    session("second")
    first, second = qwen.calls()
    assert first["pid"] != second["pid"]
    assert first["session"] == second["session"]
    argv = second["argv"]
    assert argv[argv.index("--model") + 1] == "second-model"
    excluded = argv[argv.index("--exclude-tools") + 1].split(",")
    assert {"write_file", "run_shell_command", "web_search", "web_fetch"} <= set(
        excluded
    )


def test_session_effort_restarts_without_rewriting_old_settings(qwen: _Qwen) -> None:
    session = qwen.agent.new()
    session("first")
    session.effort = "high"
    session("second")
    first, second = qwen.calls()
    assert first["pid"] != second["pid"]
    assert first["effort"] == "low"
    assert second["effort"] == "high"
    assert first["session"] == second["session"]


def test_a_provider_error_answered_as_a_landed_turn_is_a_failed_turn(
    qwen: _Qwen,
) -> None:
    """Qwen marks it a success and exits zero, and the whole of its answer is the error.

    A loop handed that as an answer would be running on an error message as the work of the
    turn before it -- and a 401 that reads as a landed turn is an account nothing ever falls
    back from, since nothing here would have seen a failure at all.
    """
    session = qwen.agent.new()

    with pytest.raises(Failed, match="401 Invalid API key") as refused:
        session("[API Error: 401 Invalid API key]")

    assert refused.value.fault == "refused"
    assert (
        session.named is None
    )  # and it leaves the conversation unopened, as any failure does


def test_failed_opening_turn_does_not_adopt_id_or_leave_process_running(
    qwen: _Qwen,
) -> None:
    session = qwen.agent.new()
    with pytest.raises(Failed, match="turn refused"):
        session("fail")
    assert session.named is None
    assert qwen.agent.opened == []
    assert session("retry") == "retry"
    first, second = qwen.calls()
    assert first["pid"] != second["pid"]
    assert first["session"] != second["session"]
    assert "--resume" not in second["argv"]


def test_dynamic_flow_skills_restart_and_resume_the_same_session(
    qwen: _Qwen, tmp_path: Path
) -> None:
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review work.\n---\nReview work.\n"
    )
    qwen.agent.loads([Loaded("review", skill)])
    session = qwen.agent.new()
    session("first")
    session.loads([])
    session("second")
    first, second = qwen.calls()
    assert first["skills"] == ["review"]
    assert second["skills"] == []
    assert first["pid"] != second["pid"]
    assert first["session"] == second["session"]


def test_changed_native_settings_restart_the_held_process(
    qwen: _Qwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = tmp_path / "native-home"
    native.mkdir()
    monkeypatch.setenv("QWEN_HOME", str(native))
    settings = native / "settings.json"
    settings.write_text('{"context":{"fileName":"QWEN.md"}}')
    session = qwen.agent.new()
    session("first")
    settings.write_text('{"context":{"fileName":"AGENTS.md"}}')
    session("second")
    first, second = qwen.calls()
    assert first["pid"] != second["pid"]
    assert first["session"] == second["session"]


def test_new_native_skill_directory_is_visible_on_the_next_turn(
    qwen: _Qwen, tmp_path: Path
) -> None:
    session = qwen.agent.new()
    session("first")
    skill = tmp_path / ".agents/skills/new-native-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Native skill installed between turns.")
    session("second")
    first, second = qwen.calls()
    assert first["skills"] == []
    assert second["skills"] == ["new-native-skill"]
    assert first["pid"] != second["pid"]
    assert first["session"] == second["session"]


def test_native_custom_skill_paths_are_fingerprinted(
    qwen: _Qwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = tmp_path / "native-home"
    native.mkdir()
    monkeypatch.setenv("QWEN_HOME", str(native))
    external = tmp_path / "custom-skills"
    (native / "settings.json").write_text(
        json.dumps({"skills": {"directories": [str(external)]}})
    )
    session = qwen.agent.new()
    session("first")
    external.mkdir()
    (external / "SKILL.md").write_text("New external skill.")
    session("second")
    first, second = qwen.calls()
    assert first["pid"] != second["pid"]
    assert first["session"] == second["session"]


def test_unparsed_native_settings_keep_the_original_fresh_process_behavior(
    qwen: _Qwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = tmp_path / "native-home"
    native.mkdir()
    monkeypatch.setenv("QWEN_HOME", str(native))
    settings = native / "settings.json"
    original = '{// Qwen accepts JSON comments\n"skills":{"directories":[]}}'
    settings.write_text(original)
    session = qwen.agent.new()
    session("first")
    session("second")
    first, second = qwen.calls()
    assert first["pid"] != second["pid"]
    assert first["session"] == second["session"]
    assert settings.read_text() == original


def test_cli_migration_of_generated_effort_file_keeps_process_warm(
    qwen: _Qwen, tmp_path: Path
) -> None:
    session = qwen.agent.new()
    session("migrate")
    session("second")
    native = tmp_path / ".qwen/settings.json"
    native.parent.mkdir()
    native.write_text('{"context":{"fileName":"AGENTS.md"}}')
    session("third")
    first, second, third = qwen.calls()
    assert first["pid"] == second["pid"]
    assert second["pid"] != third["pid"]
    assert first["session"] == second["session"] == third["session"]


def test_headless_defaults_are_written_where_the_cli_reads_them_lowest(
    qwen: _Qwen,
) -> None:
    qwen.agent.new()("first")
    (call,) = qwen.calls()
    # The generated pair is shared by every session at one effort and outlives this test,
    # so only what was asked for is asserted, not the whole file.
    assert call["defaults"]["general"] == {
        "preventSystemSleep": False,
        "enableAutoUpdate": False,
    }


@pytest.mark.parametrize("named", [None, ""])
def test_cli_migration_of_generated_defaults_file_keeps_process_warm(
    qwen: _Qwen, monkeypatch: pytest.MonkeyPatch, named: str | None
) -> None:
    # Empty reads as unset in Qwen's own resolver, so the generated file is still the one
    # it migrates -- and watching it would restart an otherwise unchanged CLI every turn.
    if named is not None:
        monkeypatch.setenv("QWEN_CODE_SYSTEM_DEFAULTS_PATH", named)
    session = qwen.agent.new()
    session("migrate-defaults")
    session("second")
    first, second = qwen.calls()
    assert first["pid"] == second["pid"]
    assert first["session"] == second["session"]


def test_defaults_file_the_environment_names_is_watched_like_any_other(
    qwen: _Qwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    theirs = tmp_path / "their-defaults.json"
    theirs.write_text('{"general":{"preventSystemSleep":true}}')
    monkeypatch.setenv("QWEN_CODE_SYSTEM_DEFAULTS_PATH", str(theirs))
    session = qwen.agent.new()
    session("first")
    session("second")
    theirs.write_text('{"general":{"preventSystemSleep":false}}')
    session("third")
    first, second, third = qwen.calls()
    assert first["defaults"] == {"general": {"preventSystemSleep": True}}
    assert first["pid"] == second["pid"]
    assert second["pid"] != third["pid"]
    assert first["session"] == second["session"] == third["session"]


def test_compiled_bundle_is_shared_unless_the_environment_names_its_own(
    qwen: _Qwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qwen.agent.new()("first")
    (shared,) = qwen.calls()
    # Under humanize's own home, as pi keeps its own: a path outside it would be a cache an
    # isolated run still wrote into whoever is sitting here's real one.
    assert shared["compiled"] == str(home() / "compiled" / "qwen")
    monkeypatch.setenv("NODE_COMPILE_CACHE", str(tmp_path / "theirs"))
    qwen.agent.new()("second")
    _, theirs = qwen.calls()
    assert theirs["compiled"] == str(tmp_path / "theirs")


def test_an_anchored_turn_is_given_no_compile_cache(qwen: _Qwen) -> None:
    """It runs on another machine, where a path named from this one is somebody else's."""
    anchored = QwenCodeAgent(
        QwenCodeAgentConfig(
            model="test-model",
            effort="low",
            machine=AnchoredConfig(
                anchor=HereAnchor(target="ssh://box", workspace="/srv")
            ),
        )
    )
    anchored.new()("first")
    assert all(one["compiled"] is None for one in qwen.calls())


def test_usage_counts_each_model_request_once_across_warm_turns(qwen: _Qwen) -> None:
    session = qwen.agent.new()
    for _ in range(2):
        events = list(session.stream("many"))
        assert dict(events[-1].spent) == {"input_tokens": 4000, "output_tokens": 160}
        assert events[-1].tokens == {"test-model": 4160}


def test_repeated_message_id_is_not_metered_twice(qwen: _Qwen) -> None:
    events = list(qwen.agent.new().stream("repeat"))
    assert [event.kind for event in events] == ["text", "result"]
    assert events[-1].spent.total == 5


def test_explicit_zero_message_counters_override_terminal_usage(qwen: _Qwen) -> None:
    events = list(qwen.agent.new().stream("zero"))
    assert dict(events[-1].spent) == {"input_tokens": 0, "output_tokens": 0}


def test_result_only_counters_survive_shaped_turns_and_process_restarts(
    qwen: _Qwen,
) -> None:
    session = qwen.agent.new()
    for schema in (None, _Answer, None):
        events = list(session.stream("result-only", schema=schema))
        assert dict(events[-1].spent) == {"input_tokens": 2, "output_tokens": 3}
    assert len({call["pid"] for call in qwen.calls()}) == 3


def test_result_only_counter_reset_does_not_subtract_old_process_totals(
    qwen: _Qwen,
) -> None:
    session = qwen.agent.new()
    for prompt in ("result-only", "result-only", "reset-counter", "result-only"):
        events = list(session.stream(prompt))
        assert events[-1].spent.total == 5


@pytest.mark.parametrize("opened", [False, True])
def test_error_usage_is_not_charged_to_the_next_success(
    qwen: _Qwen, opened: bool
) -> None:
    session = qwen.agent.new()
    if opened:
        session("result-only")
    with pytest.raises(Failed, match="turn refused"):
        session("fail")
    events = list(session.stream("result-only"))
    assert dict(events[-1].spent) == {"input_tokens": 2, "output_tokens": 3}


@pytest.mark.parametrize("opened", [False, True])
def test_failed_shaped_process_does_not_recharge_its_terminal_usage(
    qwen: _Qwen, opened: bool
) -> None:
    session = qwen.agent.new()
    if opened:
        session("result-only")
    with pytest.raises(Failed):
        session("bad-exit", schema=_Answer)
    events = list(session.stream("result-only"))
    assert dict(events[-1].spent) == {"input_tokens": 2, "output_tokens": 3}


def test_concurrent_first_turns_keep_one_effort_file_and_each_process_warm(
    qwen: _Qwen, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend, "_EFFORTS", {})
    ready = Barrier(4)

    def turns(index: int) -> None:
        session = qwen.agent.new()
        ready.wait(timeout=5)
        assert session(f"cold-{index}") == f"cold-{index}"
        assert session(f"warm-{index}") == f"warm-{index}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(turns, range(4)))
    calls = qwen.calls()
    for index in range(4):
        first, second = [call for call in calls if call["prompt"].endswith(f"-{index}")]
        assert first["pid"] == second["pid"]
    assert len({call["pid"] for call in calls}) == 4
