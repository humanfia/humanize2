"""Checks for isolated provider routing and strict synthetic startup evidence."""

# ruff: noqa: INP001, PLR2004, S101 -- benchmark tests and numeric expectations

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from fixture_metrics import analyze
from setup_fixture import FAKE_KEY, setup


def test_setup_covers_all_backends_without_copying_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Supported configs route to loopback; unverified backends are explicitly accounted for."""
    from hmz import backends

    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "original"))
    directory = tmp_path / "fixture"
    record = setup(directory, "http://127.0.0.1:18999")
    assert os.environ["HUMANIZE_HOME"] == str(tmp_path / "original")
    assert set(record["configured_unvalidated"]) | set(
        record["unsupported_or_unverified"]
    ) == {profile.name for profile in backends.PROFILES}
    assert not (tmp_path / "original").exists()
    assert len(record["configured_unvalidated"]) == 10
    assert "cursor_fixture" not in record
    models = json.loads((directory / "models.json").read_text(encoding="utf-8"))
    assert models["kimi"]["model"] == "__kimi_env_model__"
    base = directory / "humanize" / "providers"
    codex = json.loads(
        (base / "codex" / "cli-fixture" / "provider.json").read_text(encoding="utf-8")
    )
    assert "model_providers.humanize.wire_api=responses" in codex["args"]
    dsh = json.loads(
        (base / "dsh" / "cli-fixture" / "provider.json").read_text(encoding="utf-8")
    )
    assert dsh["way"] == "key"
    assert dsh["env"] == {
        "DEEPSEEK_API_KEY": FAKE_KEY,
        "DEEPSEEK_BASE_URL": "http://127.0.0.1:18999/v1",
    }
    pi = json.loads(
        (base / "pi" / "cli-fixture" / "provider.json").read_text(encoding="utf-8")
    )
    assert pi["args"] == ["--extension", str(directory / "native" / "pi-fixture.mjs")]
    agy = json.loads(
        (base / "agy" / "cli-fixture" / "provider.json").read_text(encoding="utf-8")
    )
    assert agy["env"] == {
        "GEMINI_API_KEY": FAKE_KEY,
        "GOOGLE_GEMINI_BASE_URL": "http://127.0.0.1:18999",
    }
    assert agy["args"][0] == "--app_data_dir"
    assert not Path(agy["args"][1]).is_absolute()
    assert json.loads(
        (directory / "native" / "agy" / "settings.json").read_text(encoding="utf-8")
    ) == {"modelProvider": "gemini"}
    assert models["agy"]["provider"] == "cli-fixture"
    with pytest.raises(ValueError, match="loopback"):
        setup(tmp_path / "outside", "https://api.example.com")


def test_cursor_local_setup_uses_only_the_selected_official_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit local package adds one dummy provider without invoking or editing it."""
    package = tmp_path / "official"
    package.mkdir()
    official = package / "cursor-agent-local"
    original = b"#!/bin/sh\nexit 99\n"
    official.write_bytes(original)
    official.chmod(0o700)
    (package / "package.json").write_text(
        json.dumps({"name": "@anysphere/agent-cli-local-runtime"}), encoding="utf-8"
    )
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "original-home"))
    original_path = os.environ.get("PATH", "")
    directory = tmp_path / "fixture"
    record = setup(directory, "http://127.0.0.1:18999", cursor_local_official=official)
    assert os.environ["HUMANIZE_HOME"] == str(tmp_path / "original-home")
    assert os.environ.get("PATH", "") == original_path
    assert official.read_bytes() == original
    assert not (tmp_path / "original-home").exists()
    assert len(record["configured_unvalidated"]) == 11
    assert "cursor" not in record["unsupported_or_unverified"]
    assert "zcode" in record["unsupported_or_unverified"]
    assert (directory / "bin/cursor-agent").is_symlink()
    assert (directory / "bin/cursor-agent").resolve() == official
    assert record["environment"]["PATH"].split(os.pathsep)[0] == str(directory / "bin")
    models = json.loads((directory / "models.json").read_text(encoding="utf-8"))
    assert models["cursor"] == {
        "model": "fixture-model",
        "effort": "",
        "provider": "cli-fixture",
    }
    provider = json.loads(
        (directory / "humanize/providers/cursor/cli-fixture/provider.json").read_text(
            encoding="utf-8"
        )
    )
    assert provider["args"] == []
    assert provider["env"] == {
        "CURSOR_ENABLE_AUTHLESS": "1",
        "CURSOR_LOCAL_AGENT_BASE_URL": "http://127.0.0.1:18999/v1",
        "CURSOR_LOCAL_AGENT_API_KEY": FAKE_KEY,
        "CURSOR_CONFIG_DIR": str(directory / "native/cursor"),
    }
    assert (
        json.loads(
            (directory / "native/cursor/cli-config.json").read_text(encoding="utf-8")
        )
        == {}
    )
    assert (
        record["cursor_fixture"]["official_executable_sha256"]
        == hashlib.sha256(original).hexdigest()
    )
    assert record["cursor_fixture"]["standard_cursor_service_auth_covered"] is False


@pytest.mark.parametrize("contents", [None, "not json", "[]", '{"name":"unrelated"}'])
def test_cursor_local_setup_rejects_missing_or_wrong_package(
    tmp_path: Path, contents: str | None
) -> None:
    """A similarly named launcher without the local package cannot select this protocol."""
    official = tmp_path / "cursor-agent-local"
    official.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    official.chmod(0o700)
    if contents is not None:
        (tmp_path / "package.json").write_text(contents, encoding="utf-8")
    directory = tmp_path / "fixture"
    with pytest.raises(ValueError, match="Cursor local"):
        setup(directory, "http://127.0.0.1:18999", cursor_local_official=official)
    assert not directory.exists()


def test_startup_join_rejects_incomplete_fixture_work(tmp_path: Path) -> None:
    """A quick first request is insufficient when a turn skipped its actual work."""
    rung = tmp_path / "rung"
    rung.mkdir()
    turns = [
        {
            "kind": "turn",
            "index": 0,
            "phase": phase,
            "correlation_id": "marker",
            "turn_started_monotonic_ns": 1_000_000_000,
            "result_seconds": 5,
        }
        for phase in ("cold", "warm")
    ]
    (rung / "items.jsonl").write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in [{"kind": "item", "index": 0, "ok": True}, *turns]
        ),
        encoding="utf-8",
    )
    journal = tmp_path / "results.jsonl"
    journal.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"kind": "metadata", "limits": {"valid_4cpu_16gib": True}},
                {
                    "kind": "rung",
                    "directory": str(rung),
                    "backend": "codex",
                    "concurrency": 1,
                    "settings": {"model": "fixture-model"},
                },
            ]
        ),
        encoding="utf-8",
    )
    requests = tmp_path / "requests.jsonl"
    requests.write_text(
        "\n".join(
            json.dumps(
                {
                    "correlation_id": "marker",
                    "phase": phase,
                    "received_monotonic_ns": 2_000_000_000 + step,
                    "processing_seconds": 0.001,
                    "completed_steps": step,
                    "ok": True,
                }
            )
            for phase in ("cold", "warm")
            for step in range(4 if phase == "cold" else 1)
        ),
        encoding="utf-8",
    )
    result = analyze(journal, requests)[0]
    assert result["good_turns"] == 1
    assert result["failed_turns"] == 1
    assert result["cold"]["first_provider_request_seconds"]["p50"] == 1
    assert result["warm"]["first_provider_request_seconds"]["p50"] is None
