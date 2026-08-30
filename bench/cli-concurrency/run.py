"""Benchmark installed official CLIs through hmz using real model endpoints.

Each rung has one Python worker holding concurrent hmz sessions. The supervising process
records resource usage and bounds cleanup even when a CLI ignores session cancellation.
"""

# ruff: noqa: INP001 -- invoked by path, not shipped as part of hmz

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from metrics import (
    CLEANUP_REVISION,
    USAGE_REVISION,
    Processes,
    cgroup_meter,
    compare,
    constraints,
    output_rate,
    own_cgroup,
    summarize,
)
from workload import prepare, prompt, validate

_RATE_LIMIT = re.compile(
    r"\b(?:http(?:/\d(?:\.\d)?)?(?:\s*error)?|status(?:[\s_-]+code)?|"
    r"api\s+error|error\s+code)\b[\s\"':=_-]*429\b|"
    r"\b429\s+(?:status|too\s+many)\b|"
    r"\brate[-_ ]?limit(?:ed|ing|error|exceeded)?(?:[-_ ](?:exceeded|error))?\b|"
    r"\btoo\s+many\s+requests\b",
    re.IGNORECASE,
)


def _rate_limited(rows: list[dict[str, Any]]) -> bool:
    """Only explicit provider error context stops dispatch; task numbers are not status."""
    return any(
        row.get("kind") == "item"
        and isinstance(error := row.get("error"), str)
        and _RATE_LIMIT.search(error)
        for row in rows
    )


def _write(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        with contextlib.suppress(ValueError):
            result.append(json.loads(line))
    return result


def _agy_workspace(session: Any) -> None:
    """Give an older AgY adapter its actual task workspace without changing its source."""
    original = session._turn  # noqa: SLF001 -- explicit benchmark compatibility option
    workspace = str(Path(session.cwd).resolve())

    def turn(prompt_text: str) -> tuple[list[str], str | None]:
        argv, stdin = original(prompt_text)
        present = any(
            argument == f"--add-dir={workspace}"
            or (
                argument == "--add-dir"
                and index + 1 < len(argv)
                and argv[index + 1] == workspace
            )
            for index, argument in enumerate(argv)
        )
        return (
            argv if present else [argv[0], "--add-dir", workspace, *argv[1:]]
        ), stdin

    session._turn = turn  # noqa: SLF001 -- per-session wrapper, no shared/provider mutation


def _worker(spec: dict[str, Any]) -> int:
    import hmz
    from hmz.agents import driver
    from hmz.providers.store import environ

    output = Path(spec["directory"]) / "items.jsonl"
    lock = threading.Lock()
    done: set[int] = set()
    sessions: dict[int, Any] = {}
    started: dict[int, float] = {}
    timed_out: dict[int, float] = {}
    ready = threading.Barrier(spec["concurrency"])
    agent_type, config_type = driver(spec["backend"])

    def emit(row: dict[str, Any]) -> None:
        with lock:
            _write(output, row)

    def make_agent() -> Any:
        return agent_type(config_type(**spec["settings"]))

    shared = make_agent() if spec["instances"] == "shared" else None
    package = Path(hmz.__file__).resolve().parent
    source_hashes = {
        str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*"))
        if path.suffix in (".py", ".yml", ".yaml")
    }
    emit(
        {
            "kind": "ready",
            "at": time.time(),
            "hmz_file": str(Path(hmz.__file__).resolve()),
            "hmz_source_sha256": source_hashes,
        }
    )

    def item(index: int) -> None:
        workspace = Path(spec["directory"]) / "workspaces" / str(index)
        expected = prepare(workspace, index)
        memory = "MEMORY-" + secrets.token_hex(16)
        agent = shared
        record: dict[str, Any] = {"kind": "item", "index": index, "ok": False}
        try:
            ready.wait(timeout=30)
            began = time.monotonic()
            started[index] = began
            agent = shared if shared is not None else make_agent()
            session = agent.new(cwd=workspace)
            if spec["backend"] == "agy" and spec.get("agy_add_dir"):
                _agy_workspace(session)
                record["native_workspace_args"] = [
                    "--add-dir",
                    str(workspace.resolve()),
                ]
            sessions[index] = session
            record["setup_seconds"] = time.monotonic() - began
            record["workspace"] = str(workspace)
            valid = True
            for phase in ("cold", "warm"):
                turn_began = began if phase == "cold" else time.monotonic()
                turn: dict[str, Any] = {
                    "kind": "turn",
                    "index": index,
                    "phase": phase,
                    "correlation_id": memory,
                    "turn_started_monotonic_ns": int(turn_began * 1e9),
                    "first_event_seconds": None,
                    "first_tool_seconds": None,
                    "result_seconds": None,
                    "work_seconds": None,
                    "output_tokens_per_second": None,
                    "event_count": 0,
                    "tool_count": 0,
                    "result_count": 0,
                }
                answer = ""
                events = workspace.parent.parent / f"events-{index}-{phase}.jsonl"
                for event in session.stream(prompt(phase, memory)):
                    elapsed = time.monotonic() - turn_began
                    if turn["first_event_seconds"] is None:
                        turn["first_event_seconds"] = elapsed
                    turn["event_count"] += 1
                    if event.kind == "tool":
                        turn["tool_count"] += 1
                        if turn["first_tool_seconds"] is None:
                            turn["first_tool_seconds"] = elapsed
                    if event.kind == "result":
                        turn["result_count"] += 1
                        turn["result_seconds"] = elapsed
                        answer = event.text
                        turn["usage"] = dict(event.spent)
                    _write(
                        events,
                        {"at_seconds": elapsed, "kind": event.kind, "text": event.text},
                    )
                elapsed = time.monotonic() - turn_began
                first_tool = turn["first_tool_seconds"]
                turn["work_seconds"] = (
                    elapsed - first_tool if first_tool is not None else None
                )
                turn["turn_seconds"] = elapsed
                turn["usage_rate_revision"] = USAGE_REVISION
                turn["output_tokens_per_second"] = output_rate(
                    turn.get("usage", {}), elapsed
                )
                turn["validation"] = validate(workspace, phase, expected[phase])
                marker_written = any(
                    memory.encode() in path.read_bytes()
                    for path in workspace.rglob("*")
                    if path.is_file()
                    and not any(
                        part.startswith(".")
                        for part in path.relative_to(workspace).parts
                    )
                )
                turn["context_marker_absent_from_task_files"] = not marker_written
                turn["context_ok"] = not marker_written and (
                    phase == "cold" or memory in answer
                )
                turn["ok"] = (
                    turn["validation"]["ok"]
                    and turn["context_ok"]
                    and turn["result_count"] == 1
                    and turn["tool_count"] > 0
                )
                valid = valid and turn["ok"]
                emit(turn)
                record["session_id"] = session.id
            record["ok"] = valid and index not in timed_out
        except Exception as exc:  # noqa: BLE001 -- a failing CLI is a benchmark datum
            message = str(exc)
            environment = dict(os.environ)
            if agent is not None:
                with contextlib.suppress(Exception):
                    environment.update(environ(agent.provider))
            for key, value in environment.items():
                if value and any(
                    word in key.upper()
                    for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")
                ):
                    message = message.replace(value, "<redacted>")
            record["error"] = f"{type(exc).__name__}: {message[:2000]}"
        finally:
            record["timed_out"] = index in timed_out
            record["seconds"] = time.monotonic() - started.get(index, time.monotonic())
            emit(record)
            done.add(index)

    threads = [
        threading.Thread(target=item, args=(index,), daemon=True)
        for index in range(spec["concurrency"])
    ]
    for thread in threads:
        thread.start()
    watchdog = time.monotonic() + spec["timeout"] + 45
    while len(done) < len(threads) and time.monotonic() < watchdog:
        now = time.monotonic()
        for index, began in list(started.items()):
            if index in done:
                continue
            if now - began > spec["timeout"] and index not in timed_out:
                timed_out[index] = now
                session = sessions.get(index)
                if session is not None:
                    threading.Thread(target=session.close, daemon=True).start()
            if index in timed_out and now - timed_out[index] > spec["grace"]:
                emit({"kind": "item", "index": index, "ok": False, "timed_out": True})
                done.add(index)
        time.sleep(0.05)
    for index in range(len(threads)):
        if index not in done:
            emit(
                {
                    "kind": "item",
                    "index": index,
                    "ok": False,
                    "error": "worker watchdog",
                }
            )
    # Stay alive until the parent has sampled every descendant, including CLI servers
    # that detached from our process group. This also avoids unbounded SDK atexit hooks.
    sys.stdout.flush()
    sys.stderr.flush()
    (Path(spec["directory"]) / "complete").touch()
    while True:
        signal.pause()


def _rung(spec: dict[str, Any], where: Path, every: float) -> dict[str, Any]:
    directory = Path(spec["directory"])
    directory.mkdir(parents=True)
    spec_path = directory / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    before = cgroup_meter(where)
    started = time.monotonic()
    peaks: dict[str, float] = {}
    known = None
    process = None
    killed = False
    try:
        with (directory / "worker.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    str(spec_path),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            known = Processes(os.getpid(), include_root=False)
            last = before
            last_at = started
            while process.poll() is None:
                resource = known.sample()
                meter = cgroup_meter(where)
                # Timestamp after reading the counters, including process-sampling work
                # in this interval rather than charging it to an earlier instant.
                now = time.monotonic()
                interval = now - last_at
                cpu = (
                    meter.get("cpu.stat.usage_usec", 0)
                    - last.get("cpu.stat.usage_usec", 0)
                ) / 1e6
                resource["cpu_busy_cores"] = cpu / interval if interval else 0
                resource["cgroup_memory_bytes"] = meter.get("memory.current", 0)
                resource["cgroup_tasks"] = meter.get("pids.current", 0)
                for key, value in resource.items():
                    peaks[key] = max(peaks.get(key, 0), value)
                _write(
                    directory / "resources.jsonl",
                    {
                        "at_seconds": now - started,
                        "sampled_monotonic_ns": int(now * 1e9),
                        "cgroup_cpu_usec": meter.get("cpu.stat.usage_usec", 0),
                        "process_records": known.sampled,
                        **resource,
                    },
                )
                last, last_at = meter, now
                if (directory / "complete").exists():
                    break
                if now - started > spec["timeout"] + spec["grace"] + 60:
                    killed = True
                    break
                time.sleep(every)
    finally:
        if process is not None:
            # CLI servers may start their own session, so kill the group as well as the
            # remembered process tree. psutil retains creation times against PID reuse.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        survivors = known.cleanup() if known is not None else []
        if process is not None:
            process.wait(timeout=10)
    elapsed = time.monotonic() - started
    after = cgroup_meter(where)
    rows = _rows(directory / "items.jsonl")
    seen = {row["index"] for row in rows if row.get("kind") == "item"}
    for index in range(spec["concurrency"]):
        if index not in seen:
            missing = {
                "kind": "item",
                "index": index,
                "ok": False,
                "error": "worker exited before result",
            }
            rows.append(missing)
            _write(directory / "items.jsonl", missing)
    summary = summarize(rows, elapsed)
    ready = next((row["at"] for row in rows if row.get("kind") == "ready"), None)
    summary.update(
        kind="rung",
        backend=spec["backend"],
        settings=spec["settings"],
        instances=spec["instances"],
        concurrency=spec["concurrency"],
        repeat=spec["repeat"],
        directory=str(directory),
        resources_peak=peaks,
        cpu_seconds=(
            after.get("cpu.stat.usage_usec", 0) - before.get("cpu.stat.usage_usec", 0)
        )
        / 1e6,
        cgroup_before=before,
        cgroup_after=after,
        worker_ready_at=ready,
        hmz_source=next((row for row in rows if row.get("kind") == "ready"), None),
        worker_returncode=process.returncode if process else None,
        watchdog_killed=killed,
        worker_complete=(directory / "complete").exists(),
        cleanup_survivors=survivors,
        cleanup_revision=CLEANUP_REVISION,
        cleanup_wait_fallbacks=known.wait_fallbacks if known else 0,
        usage_rate_revision=USAGE_REVISION,
        agy_add_dir=spec.get("agy_add_dir", False),
    )
    return summary


def _inventory(names: list[str]) -> dict[str, Any]:
    from hmz import backends

    result = {}
    for name in names:
        profile = backends.named(name)
        command = profile.command or name
        executable = shutil.which(command)
        held: dict[str, Any] = {
            "command": command,
            "executable": executable,
            "efforts": profile.efforts,
        }
        if executable:
            path = Path(executable).resolve()
            held["resolved_executable"] = str(path)
            with path.open("rb") as handle:
                held["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
        result[name] = held
    return result


def main() -> int:
    """Run serial rungs and retain enough evidence to reproduce every performance gate."""
    from hmz import backends

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--backends", default=",".join(profile.name for profile in backends.PROFILES)
    )
    parser.add_argument(
        "--config", type=Path, help="JSON mapping backend to model/provider/effort"
    )
    parser.add_argument(
        "--model", help="Default model when absent from the backend config"
    )
    parser.add_argument(
        "--provider",
        default="",
        help="Default hmz provider name; empty uses native login",
    )
    parser.add_argument("--concurrency", default="1,2,4")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--timeout",
        type=float,
        default=240,
        help="Seconds allowed for both turns of one item",
    )
    parser.add_argument(
        "--grace",
        type=float,
        default=10,
        help="Seconds for a timed out session to close",
    )
    parser.add_argument("--sample-every", type=float, default=0.2)
    parser.add_argument("--instances", choices=("shared", "separate"), default="shared")
    parser.add_argument("--work-tolerance", type=float, default=0.10)
    parser.add_argument(
        "--agy-add-dir",
        action="store_true",
        help="Add each AgY task workspace to native args; use equally for original/candidate",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Prior results.jsonl containing serial baseline aggregates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New evidence directory (default a fresh temporary directory)",
    )
    parser.add_argument(
        "--allow-unconstrained",
        action="store_true",
        help="Diagnostic only; disable strict 4 CPU/16 GiB check",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Show supported CLIs and installation provenance",
    )
    args = parser.parse_args()
    if args.worker:
        return _worker(json.loads(args.worker.read_text(encoding="utf-8")))
    names = args.backends.split(",")
    inventory = _inventory(names)
    if args.list:
        sys.stdout.write(json.dumps(inventory, indent=2) + "\n")
        return 0
    levels = sorted({int(level) for level in args.concurrency.split(",")})
    if any(level < 1 for level in levels) or args.repeats < 1:
        parser.error("Concurrency and repeats must be positive")
    if args.timeout <= 0 or args.grace <= 0 or args.sample_every <= 0:
        parser.error("Timeout, grace and sample interval must be positive")
    # Adopt orphaned CLI grandchildren so detached servers remain measurable and killable.
    # Linux PR_SET_CHILD_SUBREAPER; no CLI process or installed binary is modified.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot become a child subreaper")
    where = own_cgroup()
    limits = constraints(where)
    if not args.allow_unconstrained and not limits["valid_4cpu_16gib"]:
        parser.error(
            "Require CPUQuota=400%, affinity of four CPUs, MemoryMax=16G and "
            "MemorySwapMax=0; use --allow-unconstrained only for diagnostics"
        )
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    directory = (
        args.output.resolve()
        if args.output
        else Path(tempfile.mkdtemp(prefix="hmz-cli-bench-"))
    )
    directory.mkdir(parents=True, exist_ok=True)
    journal = directory / "results.jsonl"
    if journal.exists():
        parser.error("Output already contains results; choose a new directory")
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    _write(
        journal,
        {
            "kind": "metadata",
            "sampler_revision": "counter-before-timestamp-v2",
            "harness_source_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(Path(__file__).parent.glob("*.py"))
            },
            "at": time.time(),
            "limits": limits,
            "inventory": inventory,
            "git_commit": git.stdout.strip(),
            "python": sys.version,
            "arguments": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
        },
    )
    sys.stdout.write(f"Evidence: {directory}\n")
    sys.stdout.flush()
    references = _rows(args.baseline) if args.baseline else []
    failed = False
    for backend in names:
        profile = backends.named(backend)
        settings = {
            "model": args.model,
            "provider": args.provider,
            "effort": profile.efforts[-1],
            "permission": "bypass",
            "web_search": True,
            **config.get(backend, {}),
        }
        if not settings["model"]:
            _write(
                journal,
                {
                    "kind": "unavailable",
                    "backend": backend,
                    "error": "No model configured",
                },
            )
            failed = True
            continue
        baseline = next(
            (
                row
                for row in reversed(references)
                if row.get("kind") == "aggregate"
                and row.get("backend") == backend
                and row.get("concurrency") == 1
                and row.get("settings") == settings
            ),
            None,
        )
        if args.baseline and baseline is None:
            parser.error(
                f"No matching serial baseline for {backend} and its exact settings"
            )
        for level in levels:
            aggregate_rows: list[dict[str, Any]] = []
            elapsed = 0.0
            completed_repeats = 0
            stopped_reason = None
            for repeat in range(args.repeats):
                spec = {
                    "backend": backend,
                    "settings": settings,
                    "concurrency": level,
                    "repeat": repeat,
                    "instances": args.instances,
                    "agy_add_dir": args.agy_add_dir,
                    "timeout": args.timeout,
                    "grace": args.grace,
                    "directory": str(directory / f"{backend}-n{level}-r{repeat}"),
                }
                summary = _rung(spec, where, args.sample_every)
                _write(journal, summary)
                failed = (
                    failed
                    or summary["failed"] > 0
                    or bool(summary["cleanup_survivors"])
                )
                rung_rows = _rows(Path(spec["directory"]) / "items.jsonl")
                for row in rung_rows:
                    if "index" in row:
                        row["index"] += repeat * level
                    aggregate_rows.append(row)
                elapsed += summary["wall_seconds"]
                completed_repeats += 1
                sys.stdout.write(
                    json.dumps(
                        {
                            key: summary[key]
                            for key in (
                                "backend",
                                "concurrency",
                                "repeat",
                                "ok",
                                "failed",
                                "wall_seconds",
                                "resources_peak",
                            )
                        }
                    )
                    + "\n"
                )
                sys.stdout.flush()
                if _rate_limited(rung_rows):
                    stopped_reason = "provider_rate_limit"
                    break
            aggregate = summarize(aggregate_rows, elapsed)
            aggregate.update(
                kind="aggregate",
                backend=backend,
                concurrency=level,
                settings=settings,
                repeats=completed_repeats,
                requested_repeats=args.repeats,
                partial=completed_repeats < args.repeats,
                stopped_reason=stopped_reason,
            )
            if baseline is not None:
                aggregate["comparison"] = compare(
                    aggregate, baseline, args.work_tolerance
                )
            if level == 1 and not args.baseline:
                baseline = aggregate
            elif baseline is not None:
                aggregate["comparison"] = compare(
                    aggregate, baseline, args.work_tolerance
                )
            _write(journal, aggregate)
            if stopped_reason is not None:
                return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
