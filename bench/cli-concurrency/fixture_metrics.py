"""Join synthetic provider arrivals to measured turns without calling event latency startup."""

# ruff: noqa: INP001 -- standalone benchmark analysis

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fixture_plan import SHELL_NAMES
from metrics import distribution

STARTUP_LIMIT = 2.0


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def measure(turn: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep auxiliary traffic visible while requiring every workload exchange exactly once."""
    auxiliary = [
        call
        for call in calls
        if call.get("request_kind") == "auxiliary"
        or (
            "request_kind" not in call
            and "tools" in call
            and not any(SHELL_NAMES.search(name) for name in call.get("tools", []))
        )
    ]
    work = [call for call in calls if call not in auxiliary]
    result: dict[str, Any] = {
        "ok": False,
        "requests": len(calls),
        "workload_requests": len(work),
        "auxiliary_requests": len(auxiliary),
        "auxiliary_failed_requests": sum(bool(call.get("error")) for call in auxiliary),
        "auxiliary_cancelled_requests": sum(
            bool(call.get("client_disconnected")) for call in auxiliary
        ),
    }
    if not calls or not turn.get("turn_started_monotonic_ns"):
        return {**result, "error": "No matching request or turn-start timestamp"}
    started = turn["turn_started_monotonic_ns"]
    first = (calls[0]["received_monotonic_ns"] - started) / 1e9
    result.update(
        first_provider_request_seconds=first,
        fixture_processing_seconds=sum(call["processing_seconds"] for call in calls),
        fixture_work_overhead_seconds=turn["result_seconds"] - first,
    )
    if [call["completed_steps"] for call in work] != [0, 1, 2, 3]:
        result["error"] = "Unexpected workload request sequence"
    elif not all(call.get("ok") for call in work):
        result["error"] = "Workload provider failure"
    elif result["auxiliary_failed_requests"]:
        result["error"] = "Auxiliary provider failure; repeat with corrected fixture"
    elif (
        not 0
        <= first
        <= (work[-1]["received_monotonic_ns"] - started) / 1e9
        <= turn["result_seconds"]
    ):
        result["error"] = "Inconsistent clock order"
    else:
        result["ok"] = True
    return result


def analyze(journal: Path, requests: Path) -> list[dict[str, Any]]:
    """Require correct task pairs, four completed fixture exchanges and valid clock order."""
    calls: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _rows(requests):
        if row.get("correlation_id") and row.get("phase"):
            calls[row["correlation_id"], row["phase"]].append(row)
    rows = _rows(journal)
    metadata = next(row for row in rows if row.get("kind") == "metadata")
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for rung in rows:
        if rung.get("kind") != "rung":
            continue
        folder = Path(rung["directory"])
        if not folder.exists():
            folder = journal.parent / folder.name
        items = _rows(folder / "items.jsonl")
        good = {
            row["index"] for row in items if row.get("kind") == "item" and row.get("ok")
        }
        group = groups[rung["backend"], rung["concurrency"]]
        for row in items:
            if row.get("kind") != "turn":
                continue
            requests_for_turn = sorted(
                calls.get((row.get("correlation_id", ""), row["phase"]), []),
                key=lambda call: call["received_monotonic_ns"],
            )
            measured = {
                **measure(row, requests_for_turn),
                "phase": row["phase"],
                "settings": rung["settings"],
            }
            if rung.get("cleanup_survivors") or rung.get("watchdog_killed"):
                measured.update(ok=False, error="Rung did not cleanly finish")
            elif row["index"] not in good:
                measured.update(ok=False, error="Task pair failed")
            group.append(measured)
        expected = 2 * rung["concurrency"]
        observed = sum(row.get("kind") == "turn" for row in items)
        for _ in range(expected - observed):
            group.append(
                {"ok": False, "error": "Missing turn", "settings": rung["settings"]}
            )
    summaries = []
    for (backend, concurrency), turns in groups.items():
        summary: dict[str, Any] = {
            "kind": "fixture_aggregate",
            "backend": backend,
            "concurrency": concurrency,
            "settings": turns[0]["settings"],
            "synthetic_model": True,
            "measurement_revision": "workload-and-auxiliary-v2",
            "good_turns": sum(turn["ok"] for turn in turns),
            "failed_turns": sum(not turn["ok"] for turn in turns),
            "limits_valid": metadata["limits"]["valid_4cpu_16gib"],
            "errors": sorted({turn["error"] for turn in turns if "error" in turn}),
        }
        for phase in ("cold", "warm"):
            successful = [
                turn for turn in turns if turn.get("phase") == phase and turn["ok"]
            ]
            summary[phase] = {
                metric: distribution([turn[metric] for turn in successful])
                for metric in (
                    "first_provider_request_seconds",
                    "fixture_work_overhead_seconds",
                    "fixture_processing_seconds",
                    "requests",
                    "workload_requests",
                    "auxiliary_requests",
                    "auxiliary_failed_requests",
                    "auxiliary_cancelled_requests",
                )
            }
        summaries.append(summary)
    return summaries


def compare_startup(
    current: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    """Require valid constrained timings and gate startup p50/p95 at at most 2x baseline."""
    ratios = {}
    for phase in ("cold", "warm"):
        for quantile in ("p50", "p95"):
            value = current[phase]["first_provider_request_seconds"][quantile]
            reference = baseline[phase]["first_provider_request_seconds"][quantile]
            ratios[f"{phase}.{quantile}"] = (
                value / reference if value is not None and reference else None
            )
    return {
        "startup_ratios": ratios,
        "startup_limit": STARTUP_LIMIT,
        "passes": current["failed_turns"] == 0
        and baseline["failed_turns"] == 0
        and current["limits_valid"]
        and baseline["limits_valid"]
        and all(
            ratio is not None and ratio <= STARTUP_LIMIT for ratio in ratios.values()
        ),
        "real_model_work_speed_verified": False,
    }


def main() -> None:
    """Write startup/fixture-overhead distributions and optional prior-baseline gates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Harness results.jsonl")
    parser.add_argument(
        "--requests", type=Path, required=True, help="Fixture request journal"
    )
    parser.add_argument(
        "--baseline", type=Path, help="Previously emitted fixture metrics JSONL"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new metrics output file")
    references = _rows(args.baseline) if args.baseline else []
    summaries = analyze(args.run, args.requests)
    for row in summaries:
        baseline = next(
            (
                old
                for old in references
                if old["backend"] == row["backend"]
                and old["concurrency"] == 1
                and old["settings"] == row["settings"]
            ),
            None,
        )
        if args.baseline and baseline is None:
            parser.error(f"No matching serial fixture baseline for {row['backend']}")
        if baseline is not None:
            row["comparison"] = compare_startup(row, baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row) + "\n" for row in summaries), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
