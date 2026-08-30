"""Provider throttling stops future dispatch without discarding the finished rung."""

# ruff: noqa: INP001, S101, PLR2004, SLF001 -- standalone benchmark regressions
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import run
from metrics import summarize


@pytest.mark.parametrize(
    "error",
    [
        "Failed: HTTP 429",  # Retained native Grok error context.
        "Failed: 429 status code (no body)",  # Retained native Pi error context.
        "Failed: HTTP/1.1 429 Too Many Requests",
        'Failed: {"status_code": 429}',
        "Failed: API error: 429",
        "Failed: rate_limit_exceeded",
        "Failed: RateLimitError",
        "Failed: Too many requests",
    ],
)
def test_explicit_native_throttling_errors_are_recognized(error: str) -> None:
    """Native status and named rate-limit errors provide explicit failure context."""
    assert run._rate_limited([{"kind": "item", "ok": False, "error": error}])


@pytest.mark.parametrize(
    "error",
    [
        "Failed: missing MEMORY-a429bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "Failed: task 429 did not create its proof",
        "Failed: code 429 in the fixture is incorrect",
        "Failed: HTTP 401; request id 429",
        "Failed: HTTP 4290",
        "Failed: expected 429 tokens",
        "Failed: worker watchdog",
        None,
    ],
)
def test_task_numbers_and_unrelated_errors_do_not_stop_dispatch(
    error: str | None,
) -> None:
    """Unrelated numeric values in a failed task are not a provider status."""
    assert not run._rate_limited([{"kind": "item", "ok": False, "error": error}])


def test_only_item_errors_trigger_throttling_stop() -> None:
    """Successful output and turn metadata never classify the provider as throttled."""
    assert not run._rate_limited(
        [
            {"kind": "turn", "error": "HTTP 429"},
            {"kind": "item", "text": "HTTP 429", "ok": True},
        ]
    )


def _dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: str,
    fail_repeat: int,
) -> tuple[list[tuple[str, int, int]], dict[Path, bytes]]:
    """Complete local rungs with real aggregation, never starting a CLI or worker."""
    dispatched: list[tuple[str, int, int]] = []
    retained: dict[Path, bytes] = {}

    def rung(spec: dict[str, Any], _where: Path, _every: float) -> dict[str, Any]:
        dispatched.append((spec["backend"], spec["concurrency"], spec["repeat"]))
        folder = Path(spec["directory"])
        folder.mkdir(parents=True)
        rows: list[dict[str, Any]] = []
        for index in range(spec["concurrency"]):
            failed = (
                spec["backend"] == "grok"
                and spec["concurrency"] == 1
                and spec["repeat"] == fail_repeat
                and index == 0
            )
            rows.extend(
                {
                    "kind": "turn",
                    "index": index,
                    "phase": phase,
                    "ok": not failed,
                    "first_event_seconds": 0.5,
                    "first_tool_seconds": 1,
                    "result_seconds": 2,
                    "work_seconds": 1,
                }
                for phase in ("cold", "warm")
            )
            item: dict[str, Any] = {"kind": "item", "index": index, "ok": not failed}
            if failed:
                item["error"] = error
            rows.append(item)
        for row in rows:
            run._write(folder / "items.jsonl", row)
        # A completed rung includes its original turn/resource evidence and cleanup.
        (folder / "events-0-cold.jsonl").write_text('{"kind":"tool"}\n')
        (folder / "resources.jsonl").write_text('{"processes":0}\n')
        (folder / "complete").touch()
        retained.update({path: path.read_bytes() for path in folder.iterdir()})
        return {
            **summarize(rows, 4),
            "kind": "rung",
            "backend": spec["backend"],
            "concurrency": spec["concurrency"],
            "repeat": spec["repeat"],
            "directory": str(folder),
            "resources_peak": {},
            "cleanup_survivors": [],
            "worker_complete": True,
        }

    monkeypatch.setattr(run, "_rung", rung)
    monkeypatch.setattr(run, "_inventory", Mock(return_value={}))
    monkeypatch.setattr(run, "own_cgroup", Mock(return_value=tmp_path))
    monkeypatch.setattr(
        run, "constraints", Mock(return_value={"valid_4cpu_16gib": True})
    )
    monkeypatch.setattr(
        run.ctypes, "CDLL", Mock(return_value=Mock(prctl=Mock(return_value=0)))
    )
    monkeypatch.setattr(
        run.subprocess, "run", Mock(return_value=SimpleNamespace(stdout="test-commit"))
    )
    monkeypatch.setattr(
        run.sys,
        "argv",
        [
            "run.py",
            "--backends",
            "grok,pi",
            "--model",
            "local-test",
            "--concurrency",
            "1,2",
            "--repeats",
            "3",
            "--output",
            str(tmp_path / "evidence"),
        ],
    )
    return dispatched, retained


@pytest.mark.parametrize(
    "error", ["Failed: HTTP 429", "Failed: 429 status code (no body)"]
)
@pytest.mark.parametrize("fail_repeat", [0, 1, 2])
def test_throttling_preserves_completed_evidence_and_stops_all_later_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: str,
    fail_repeat: int,
) -> None:
    """A completed throttled rung is retained and never dispatches another job."""
    dispatched, retained = _dispatch(monkeypatch, tmp_path, error, fail_repeat)
    assert run.main() == 1
    assert dispatched == [("grok", 1, repeat) for repeat in range(fail_repeat + 1)]
    assert all(path.read_bytes() == before for path, before in retained.items())
    rows = run._rows(tmp_path / "evidence/results.jsonl")
    rungs = [row for row in rows if row["kind"] == "rung"]
    assert len(rungs) == fail_repeat + 1
    assert all(row["worker_complete"] and not row["cleanup_survivors"] for row in rungs)
    aggregates = [row for row in rows if row["kind"] == "aggregate"]
    assert len(aggregates) == 1
    aggregate = aggregates[0]
    assert aggregate["repeats"] == fail_repeat + 1
    assert aggregate["requested_repeats"] == 3
    assert aggregate["partial"] is (fail_repeat < 2)
    assert aggregate["stopped_reason"] == "provider_rate_limit"
    assert aggregate["ok"] == fail_repeat
    assert aggregate["failed"] == 1
    assert aggregate["wall_seconds"] == 4 * (fail_repeat + 1)


def test_unrelated_marker_error_does_not_skip_later_rungs_or_backends(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An ordinary task failure retains the previous full-run dispatch policy."""
    dispatched, retained = _dispatch(
        monkeypatch,
        tmp_path,
        "Failed: missing MEMORY-a429bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        0,
    )
    assert run.main() == 1  # Ordinary failure still reports failure after the full run.
    assert dispatched == [
        (backend, level, repeat)
        for backend in ("grok", "pi")
        for level in (1, 2)
        for repeat in range(3)
    ]
    assert all(path.read_bytes() == before for path, before in retained.items())
    aggregates = [
        row
        for row in run._rows(tmp_path / "evidence/results.jsonl")
        if row["kind"] == "aggregate"
    ]
    assert len(aggregates) == 4
    assert all(
        row["repeats"] == row["requested_repeats"] == 3
        and not row["partial"]
        and row["stopped_reason"] is None
        for row in aggregates
    )
