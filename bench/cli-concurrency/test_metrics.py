"""Regression checks for benchmark evidence, tail gates and artifact validation."""

# ruff: noqa: INP001, S101, PLR2004 -- standalone benchmark tests and numeric expectations

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

from metrics import compare, distribution, percentile, summarize
from workload import prepare, validate

if TYPE_CHECKING:
    from pathlib import Path


def test_small_sample_percentile_keeps_the_worst_case() -> None:
    """A three-run baseline must not silently discard its slowest startup."""
    assert percentile([1, 2, 100], 0.95) == 100
    assert distribution([]) == {"count": 0, "p50": None, "p95": None, "max": None}


def test_failed_task_pair_cannot_improve_reported_speed() -> None:
    """Fast failed turns do not make the success-only latency distribution look better."""
    rows = [
        {"kind": "item", "index": 0, "ok": False},
        {"kind": "turn", "index": 0, "phase": "cold", "result_seconds": 0.001},
        {"kind": "item", "index": 1, "ok": True},
        {"kind": "turn", "index": 1, "phase": "cold", "result_seconds": 10},
    ]
    summary = summarize(rows, 20)
    assert summary["failed"] == 1
    assert summary["cold"]["result_seconds"]["p50"] == 10
    assert summary["completed_tasks_per_second"] == 0.1


def test_latency_gate_rejects_slow_work_and_incomplete_baselines() -> None:
    """Passing event latency alone never establishes acceptable work speed."""
    rows = [{"kind": "item", "index": 0, "ok": True}]
    rows.extend(
        {
            "kind": "turn",
            "index": 0,
            "phase": phase,
            "first_event_seconds": 1,
            "work_seconds": 10,
            "result_seconds": 11,
        }
        for phase in ("cold", "warm")
    )
    baseline = summarize(rows, 22)
    current = summarize(rows, 22)
    assert compare(current, baseline, 0.10)["passes"]
    current["warm"]["work_seconds"]["p95"] = 11.1
    assert not compare(current, baseline, 0.10)["passes"]
    baseline["failed"] = 1
    assert not compare(summarize(rows, 22), baseline, 0.10)["passes"]
    assert not compare(current, baseline, 0.10)["startup_verified"]


def test_artifacts_require_real_successful_execution(tmp_path: Path) -> None:
    """Missing, stale and tampered artifacts fail; an executed fixed implementation passes."""
    expected = prepare(tmp_path, 0)
    assert not validate(tmp_path, "cold", expected["cold"])["ok"]
    source = tmp_path / "cold" / "score.py"
    source.write_text(
        "def score(values):\n    return sum(v * v for v in values if v > 0)\n",
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, str(tmp_path / "cold" / "check_task.py")], check=True
    )
    assert validate(tmp_path, "cold", expected["cold"])["ok"]
    fixture = tmp_path / "cold" / "fixture.json"
    changed = json.loads(fixture.read_text(encoding="utf-8"))
    changed[
        "values"
    ].reverse()  # Same sum and nonce, but a modified input must still fail.
    fixture.write_text(json.dumps(changed), encoding="utf-8")
    assert not validate(tmp_path, "cold", expected["cold"])["ok"]
    assert not validate(tmp_path, "warm", expected["warm"])["ok"]
