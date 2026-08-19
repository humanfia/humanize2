"""Run N anchored humanize agents at once and say whether all N behaved.

Runs *inside* the constrained cgroup.  One process, N agents, one session each, one turn
each, all going together -- the fan-out shape humanize documents, with every turn's work
landing on the mock target rather than here.

Everything it needs from outside is already up when it starts: the stand-in model provider
and the ``hmz anchor serve`` standing in for the controlled end both run beyond the cgroup,
because neither is part of what is being sized.

Prints one JSON object on stdout describing the run.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = "do the work"
DONE = "STANDIN-TURN-COMPLETE"

#: Where the cgroup this is running in reports what it is using.
_CGROUP = Path("/sys/fs/cgroup")


def _own_cgroup() -> Path:
    """The directory of the cgroup this process is in, for reading its own meters."""
    try:
        line = Path("/proc/self/cgroup").read_text().strip().splitlines()[-1]
        return _CGROUP / line.split(":")[-1].lstrip("/")
    except (OSError, IndexError):
        return _CGROUP


def _meter(where: Path) -> dict[str, float]:
    def number(name: str, key: str | None = None) -> float:
        try:
            text = (where / name).read_text()
        except OSError:
            return -1.0
        if key is None:
            return float(text.strip().split()[0]) if text.strip() else -1.0
        for line in text.splitlines():
            if line.startswith(key + " "):
                return float(line.split()[1])
        return -1.0

    return {
        "memory_bytes": number("memory.current"),
        "pids": number("pids.current"),
        "cpu_usec": number("cpu.stat", "usage_usec"),
    }


class Sampler(threading.Thread):
    """Reads the cgroup's own meters while the run is going."""

    def __init__(self, where: Path, every: float = 0.5) -> None:
        super().__init__(daemon=True)
        self.where = where
        self.every = every
        self.samples: list[dict[str, float]] = []
        self.stopped = threading.Event()

    def run(self) -> None:
        while not self.stopped.wait(self.every):
            sample = _meter(self.where)
            sample["at"] = time.time()
            self.samples.append(sample)


def _target_cpu() -> float:
    """CPU seconds burnt so far by the mock controlled end, listeners and their children.

    Read so the report can say whether the stand-in was near its own limit: a ceiling found
    while the target is idle is a fact about the machine running hmz, and one found while
    the target is saturated is a fact about the stand-in.
    """
    ticks = os.sysconf("SC_CLK_TCK")
    total = 0.0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode()
            if "anchor serve --listen" not in command:
                continue
            fields = (entry / "stat").read_text().rsplit(") ", 1)[-1].split()
            # utime, stime, cutime, cstime -- the children matter most: every command a
            # session runs on the target is one of them.
            total += sum(int(fields[index]) for index in (11, 12, 13, 14)) / ticks
        except (OSError, ValueError, IndexError):
            continue
    return total


def _prepare(lab: Path, index: int, seed_bytes: int) -> tuple[Path, Path]:
    """A fresh mirror and a fresh copy on the mock target for one session."""
    workspace = lab / "ws" / str(index)
    target = lab / "tgt" / str(index)
    for path in (workspace, target):
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
    # The target's data is the mocked part: a seeded file each turn reads, and a small tree
    # around it so a listing is not trivially empty.
    (target / "seed.txt").write_text("seeded on the target\n" + "x" * seed_bytes + "\n")
    for name in ("README.md", "main.py", "notes.txt"):
        (target / name).write_text(f"# {name}\n" + "line\n" * 40)
    (target / "pkg").mkdir(exist_ok=True)
    for number in range(8):
        (target / "pkg" / f"mod{number}.py").write_text(
            f"def f():\n    return {number}\n"
        )
    return workspace, target


#: The thinking level each backend is asked for.  Uniform where it can be: dsh's ladder has
#: no bottom rung by that name, so it takes the lowest it has.
_EFFORT = {"dsh": "high"}


def _turn(
    backend: str, model: str, workspace: Path, target: Path, endpoint: str
) -> dict[str, object]:
    from hmz.agents import driver
    from hmz.coganchor import AnchorConfig
    from hmz.machines import AnchoredConfig

    record: dict[str, object] = {"workspace": str(workspace)}
    started = time.time()
    try:
        agent_type, settings = driver(backend)
        anchor = AnchorConfig(
            target=endpoint,
            workspace=str(workspace),
            remote_path=str(target),
            # The rig wipes and reseeds both sides of every slot before each rung, so the
            # mirror is deliberately new each time -- and a slot that served a different
            # listener on the previous rung would otherwise be refused as one that mirrors
            # another target.
            force=True,
        )
        agent = agent_type(
            settings(  # type: ignore[call-arg]
                model=model,
                effort=_EFFORT.get(backend, "low"),
                machine=AnchoredConfig(anchor=anchor),
                permission="bypass",
                # On for every backend rather than off: kimi and dsh have no way of being
                # told not to search, and the scripted turn never reaches for it anyway, so
                # this is the one setting all five can be given alike.
                web_search=True,
            )
        )
        session = agent.new(cwd=str(workspace))
        said = list(session.stream(PROMPT))
        record["answer"] = (said[-1].text if said else "")[-160:]
        record["events"] = len(said)
        # A daemon that will not stop is not this turn's verdict.
        with contextlib.suppress(Exception):
            agent.stop()
    except Exception as exc:  # noqa: BLE001 -- every failure is a datum
        record["error"] = f"{type(exc).__name__}: {exc}"[:1500]
    record["seconds"] = round(time.time() - started, 2)

    landed = target / "touched.txt"
    try:
        record["steps_on_target"] = len(
            [line for line in landed.read_text().splitlines() if line.strip()]
        )
    except OSError:
        record["steps_on_target"] = 0
    record["said_done"] = DONE in str(record.get("answer", ""))
    record["ok"] = (
        bool(record["said_done"])
        and int(record["steps_on_target"]) >= 1
        and "error" not in record
    )
    return record


def main() -> int:
    """Run one rung -- N agents at once -- and print a JSON object describing it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--lab", required=True)
    parser.add_argument(
        "--endpoint",
        required=True,
        help="tcp://HOST:PORT of the mock target; several, comma-separated, are spread over",
    )
    parser.add_argument("--seed-bytes", type=int, default=4096)
    args = parser.parse_args()

    lab = Path(args.lab)
    slots = [_prepare(lab, index, args.seed_bytes) for index in range(args.concurrency)]

    where = _own_cgroup()
    before = _meter(where)
    sampler = Sampler(where)
    sampler.start()

    # humanize echoes every turn's transcript.  At two hundred agents that is a great deal
    # of writing to one pipe, and it is not what is being measured, so it goes to a file for
    # the length of the run and stdout is given back for the summary.
    endpoints = [one for one in args.endpoint.split(",") if one]

    transcript = lab / "logs" / f"{args.backend}-{args.concurrency}.transcript"
    with transcript.open("w") as handle, contextlib.redirect_stdout(handle):
        target_cpu_before = _target_cpu()

        started = time.time()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [
                pool.submit(
                    _turn,
                    args.backend,
                    args.model,
                    workspace,
                    target,
                    endpoints[index % len(endpoints)],
                )
                for index, (workspace, target) in enumerate(slots)
            ]
            results = [future.result() for future in futures]
        elapsed = time.time() - started
        target_cpu = _target_cpu() - target_cpu_before

    sampler.stopped.set()
    sampler.join(timeout=2)

    times = sorted(float(one["seconds"]) for one in results)
    good = [one for one in results if one["ok"]]
    peak_memory = max((one["memory_bytes"] for one in sampler.samples), default=-1.0)
    peak_pids = max((one["pids"] for one in sampler.samples), default=-1.0)
    cpu_used = (
        (sampler.samples[-1]["cpu_usec"] - before["cpu_usec"]) / 1e6
        if sampler.samples and before["cpu_usec"] >= 0
        else -1.0
    )
    summary = {
        "backend": args.backend,
        "concurrency": args.concurrency,
        "ok": len(good),
        "failed": len(results) - len(good),
        "wall_seconds": round(elapsed, 2),
        "turn_p50": round(statistics.median(times), 2) if times else -1,
        "turn_p95": round(times[max(0, int(len(times) * 0.95) - 1)], 2)
        if times
        else -1,
        "turn_max": round(times[-1], 2) if times else -1,
        "peak_memory_gib": round(peak_memory / (1 << 30), 2),
        "peak_pids": int(peak_pids),
        "cpu_seconds": round(cpu_used, 1),
        "cpu_busy_ratio": round(cpu_used / elapsed / 16, 2)
        if elapsed > 0 and cpu_used >= 0
        else -1,
        "target_cpu_seconds": round(target_cpu, 1),
        # Against the 208 CPUs the mock target has to itself, outside the cgroup.
        "target_busy_ratio": round(target_cpu / elapsed / 208, 3)
        if elapsed > 0
        else -1,
        "errors": sorted(
            {str(one.get("error", "")) for one in results if one.get("error")}
        )[:5],
        "no_done": sum(1 for one in results if not one["said_done"]),
        "no_landing": sum(1 for one in results if not int(one["steps_on_target"])),
        "steps_landed": sorted({int(one["steps_on_target"]) for one in results}),
    }
    print(json.dumps(summary), flush=True)
    detail = lab / "runs" / f"{args.backend}-{args.concurrency}.json"
    detail.parent.mkdir(parents=True, exist_ok=True)
    detail.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
