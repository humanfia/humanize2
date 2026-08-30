"""Linux resource evidence and conservative performance comparisons."""

# ruff: noqa: INP001 -- standalone benchmark scripts, outside the installed package

from __future__ import annotations

import contextlib
import errno
import math
import os
import statistics
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

import psutil

CGROUP_ROOT = Path("/sys/fs/cgroup")
GIB = 1 << 30
CPUS = 4
USAGE_REVISION = "output-key-aliases-v2"
CLEANUP_REVISION = "pidfd-portable-wait-v2"


def _read(where: Path, name: str) -> str:
    try:
        return (where / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def own_cgroup() -> Path:
    """Locate this process in the unified cgroup hierarchy."""
    for line in Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines():
        if line.startswith("0::"):
            return CGROUP_ROOT / line[3:].lstrip("/")
    raise RuntimeError("This benchmark requires the Linux cgroup v2 hierarchy")


def constraints(where: Path) -> dict[str, Any]:
    """Record inherited limits and require four allowed CPUs, 16 GiB and no swap."""
    ancestors = [where, *where.parents]
    hierarchy = [
        {
            "path": str(path),
            **{
                key: _read(path, key)
                for key in (
                    "cpu.max",
                    "cpuset.cpus.effective",
                    "memory.max",
                    "memory.swap.max",
                )
            },
        }
        for path in ancestors
        if path.is_relative_to(CGROUP_ROOT)
    ]
    quotas = [
        int(fields[0]) / int(fields[1])
        for row in hierarchy
        if (fields := row["cpu.max"].split()) and fields[0] != "max"
    ]
    memory = [
        int(row["memory.max"]) for row in hierarchy if row["memory.max"].isdigit()
    ]
    swap = [
        int(row["memory.swap.max"])
        for row in hierarchy
        if row["memory.swap.max"].isdigit()
    ]
    affinity = sorted(os.sched_getaffinity(0))
    effective = {
        "cpu_quota_cores": min(quotas, default=None),
        "allowed_cpus": affinity,
        "memory_max_bytes": min(memory, default=None),
        "memory_swap_max_bytes": min(swap, default=None),
    }
    return {
        "hierarchy": hierarchy,
        "effective": effective,
        "valid_4cpu_16gib": effective["cpu_quota_cores"] == CPUS
        and len(affinity) == CPUS
        and effective["memory_max_bytes"] == 16 * GIB
        and effective["memory_swap_max_bytes"] == 0,
    }


def cgroup_meter(where: Path) -> dict[str, int]:
    """Read cumulative CPU counters and current charged memory/task counts."""
    result = {
        name: int(value)
        for name in ("memory.current", "memory.peak", "pids.current")
        if (value := _read(where, name)).isdigit()
    }
    for name in ("cpu.stat", "memory.events"):
        for line in _read(where, name).splitlines():
            key, value = line.split()
            result[f"{name}.{key}"] = int(value)
    return result


class Processes:
    """Track descendants across reparenting, sample them and clean up a finished rung."""

    def __init__(self, pid: int, *, include_root: bool = True) -> None:
        self.root = psutil.Process(pid)
        self.known: dict[int, psutil.Process] = {pid: self.root} if include_root else {}
        self.sampled: list[dict[str, Any]] = []
        self.wait_fallbacks = 0

    def sample(self) -> dict[str, float]:
        self.sampled = []
        result = dict.fromkeys(
            ("rss_bytes", "processes", "threads", "fds", "cpu_seconds"), 0.0
        )
        with contextlib.suppress(psutil.Error):
            for child in self.root.children(recursive=True):
                self.known[child.pid] = child
        for process in self.known.values():
            with contextlib.suppress(psutil.Error):
                if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                    continue
                with process.oneshot():
                    result["rss_bytes"] += process.memory_info().rss
                    result["threads"] += process.num_threads()
                    result["fds"] += process.num_fds()
                    result["processes"] += 1
                    cpu = process.cpu_times()
                    result["cpu_seconds"] += cpu.user + cpu.system
                    self.sampled.append(
                        {
                            "pid": process.pid,
                            "name": process.name(),
                            "created_unix_seconds": process.create_time(),
                        }
                    )
        return result

    @staticmethod
    def _alive(process: psutil.Process) -> bool:
        try:
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True  # Inaccessible is not evidence that cleanup succeeded.

    def _wait(
        self, processes: list[psutil.Process], timeout: float
    ) -> list[psutil.Process]:
        """Use psutil normally; kernels rejecting pidfds still get bounded, visible cleanup."""
        deadline = time.monotonic() + timeout
        try:
            return psutil.wait_procs(processes, timeout=timeout)[1]
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP):
                raise
        self.wait_fallbacks += 1
        alive = processes
        while True:
            for process in alive:
                # Reap only known children. Reparented nonchildren are checked below.
                with contextlib.suppress(ChildProcessError, ProcessLookupError):
                    if process.is_running():
                        os.waitpid(process.pid, os.WNOHANG)
            alive = [process for process in alive if self._alive(process)]
            remaining = deadline - time.monotonic()
            if not alive or remaining <= 0:
                return alive
            time.sleep(min(0.05, remaining))

    def cleanup(self) -> list[int]:
        """Terminate only this rung's remembered descendants and report any survivors."""
        self.sample()
        processes = list(self.known.values())
        for process in reversed(processes):
            with contextlib.suppress(psutil.Error):
                process.terminate()
        alive = self._wait(processes, timeout=3)
        for process in alive:
            with contextlib.suppress(psutil.Error):
                process.kill()
        alive = self._wait(alive, timeout=3)
        return [process.pid for process in alive if self._alive(process)]


def output_rate(usage: Mapping[str, float], seconds: float) -> float | None:
    """Count output once across normalized Usage and CLIs retaining wire token names."""
    tokens = usage.get("output", usage.get("output_tokens"))
    if (
        isinstance(tokens, bool)
        or not isinstance(tokens, (int, float))
        or not math.isfinite(tokens)
        or tokens < 0
        or not math.isfinite(seconds)
        or seconds <= 0
    ):
        return None
    return tokens / seconds


def percentile(values: list[float], quantile: float) -> float | None:
    """Use nearest rank, retaining small-sample tail values rather than interpolating."""
    return (
        sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]
        if values
        else None
    )


def distribution(values: list[float]) -> dict[str, float | int | None]:
    """Summarize successful samples without replacing missing observations with zeros."""
    return {
        "count": len(values),
        "p50": statistics.median(values) if values else None,
        "p95": percentile(values, 0.95),
        "max": max(values, default=None),
    }


def summarize(rows: list[dict[str, Any]], elapsed: float) -> dict[str, Any]:
    """Report complete task pairs and cold/warm event, tool and work latencies."""
    items = list(
        {row["index"]: row for row in rows if row.get("kind") == "item"}.values()
    )
    good = {row["index"] for row in items if row.get("ok")}
    result: dict[str, Any] = {
        "ok": len(good),
        "failed": len(items) - len(good),
        "wall_seconds": elapsed,
        "completed_tasks_per_second": 2 * len(good) / elapsed if elapsed else 0,
    }
    for phase in ("cold", "warm"):
        turns = [
            row
            for row in rows
            if row.get("kind") == "turn"
            and row.get("phase") == phase
            and row["index"] in good
        ]
        result[phase] = {
            metric: distribution(
                [float(row[metric]) for row in turns if row.get(metric) is not None]
            )
            for metric in (
                "first_event_seconds",
                "first_tool_seconds",
                "result_seconds",
                "work_seconds",
                "output_tokens_per_second",
            )
        }
    return result


def compare(
    current: dict[str, Any], baseline: dict[str, Any], tolerance: float
) -> dict[str, Any]:
    """Gate correctness and both latency tails against a matching serial baseline."""
    ratios: dict[str, float | None] = {}
    gates: dict[str, bool] = {}
    for phase in ("cold", "warm"):
        for metric in ("first_event_seconds", "work_seconds", "result_seconds"):
            for quantile in ("p50", "p95"):
                key = f"{phase}.{metric}.{quantile}"
                reference = baseline[phase][metric][quantile]
                observed = current[phase][metric][quantile]
                ratio = (
                    observed / reference if observed is not None and reference else None
                )
                ratios[key] = ratio
                bound = 2.0 if metric == "first_event_seconds" else 1.0 + tolerance
                gates[key] = ratio is not None and ratio <= bound
    return {
        "ratios": ratios,
        "latency_gates": gates,
        "first_event_limit": 2.0,
        "work_latency_limit": 1.0 + tolerance,
        "passes": current["failed"] == 0
        and baseline["failed"] == 0
        and all(gates.values()),
        "startup_verified": False,
        "startup_note": "First event includes model/network time; it is not pure CLI startup.",
        "compared_at": time.time(),
    }
