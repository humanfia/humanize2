"""Verify real Usage objects and cleanup when the kernel rejects pidfd waits."""

# ruff: noqa: INP001, S101, PLR2004, SLF001 -- standalone benchmark regressions

from __future__ import annotations

import errno
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import Mock

import psutil
from metrics import Processes, output_rate
from recover_usage import recovered_turn

from hmz.agents.event import Usage

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_real_usage_mappings_recover_wire_alias_without_double_counting() -> None:
    """Qwen/Grok wire names and normalized Usage names produce the same measurable rate."""
    for usage in (
        Usage(output=816),
        Usage(output_tokens=816),
        Usage(output=816, output_tokens=2000),
    ):
        assert output_rate(usage, 8) == 102
        recovered = recovered_turn(
            {
                "usage": dict(usage),
                "first_tool_seconds": 2,
                "work_seconds": 6,
                "result_seconds": 7,
                "output_tokens_per_second": None,
            }
        )
        assert recovered["output_tokens_per_second"] == 102
        assert recovered["duration_basis"] == "first_tool_seconds+work_seconds"
    assert output_rate(Usage(output=0, output_tokens=100), 8) == 0
    assert output_rate(Usage(), 8) is None
    assert output_rate(Usage(output=-1), 8) is None
    assert output_rate(Usage(output=float("nan")), 8) is None
    assert output_rate(Usage(output=1), 0) is None


def test_pidfd_einval_fallback_preserves_live_process_and_reaps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real child stays visible when psutil raises the observed kernel pidfd error."""

    def unsupported(
        _processes: list[psutil.Process], *, timeout: float
    ) -> tuple[list[psutil.Process], list[psutil.Process]]:
        del timeout
        raise OSError(errno.EINVAL, "pidfd unsupported")

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    tracker = Processes(child.pid)
    try:
        tracker.sample()
        identity = next(row for row in tracker.sampled if row["pid"] == child.pid)
        assert identity["name"]
        assert identity["created_unix_seconds"] > 0
        monkeypatch.setattr(psutil, "wait_procs", unsupported)
        assert tracker._wait([tracker.root], timeout=0.01) == [tracker.root]
        assert tracker.wait_fallbacks == 1
        assert tracker.cleanup() == []
        assert child.wait(timeout=2) is not None
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)


def test_cleanup_races_and_inaccessible_processes_remain_distinct() -> None:
    """A vanished PID is gone; access denied cannot be reported as successful cleanup."""
    process = Mock(spec=psutil.Process)
    process.is_running.return_value = True
    process.status.side_effect = psutil.NoSuchProcess(pid=123)
    assert not Processes._alive(process)
    process.status.side_effect = psutil.AccessDenied(pid=123)
    assert Processes._alive(process)


def test_recovery_writes_separate_artifact_and_preserves_raw_journal(
    tmp_path: Path,
) -> None:
    """Recovering the missing token rate never rewrites the evidence used to derive it."""
    import hashlib
    import json

    from recover_usage import recover

    folder = tmp_path / "rung"
    folder.mkdir()
    items = folder / "items.jsonl"
    items.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"kind": "item", "index": 0, "ok": True},
                {
                    "kind": "turn",
                    "index": 0,
                    "phase": "cold",
                    "usage": {"output_tokens": 816},
                    "first_tool_seconds": 2,
                    "work_seconds": 6,
                    "result_seconds": 7,
                },
            ]
        ),
        encoding="utf-8",
    )
    journal = tmp_path / "results.jsonl"
    journal.write_text(
        json.dumps(
            {
                "kind": "rung",
                "directory": str(folder),
                "backend": "qwen",
                "concurrency": 1,
                "settings": {},
            }
        ),
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in (items, journal)}
    derived = recover(journal)
    assert all(path.read_bytes() == data for path, data in before.items())
    turn = next(row for row in derived if row["kind"] == "usage_recovered_turn")
    assert turn["output_tokens_per_second"] == 102
    assert turn["source_items_sha256"] == hashlib.sha256(before[items]).hexdigest()
