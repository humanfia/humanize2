"""Derive corrected token rates from immutable retained benchmark journals."""

# ruff: noqa: INP001 -- standalone analysis, never runs a CLI or edits source journals

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from metrics import USAGE_REVISION, distribution, output_rate

ANALYSIS_REVISION = "retained-usage-rates-v1"


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def recovered_turn(turn: dict[str, Any]) -> dict[str, Any]:
    """Recover exact stream duration from its retained parts, without using result latency."""
    seconds = turn.get("turn_seconds")
    basis = "turn_seconds"
    if seconds is None:
        tool, work = turn.get("first_tool_seconds"), turn.get("work_seconds")
        seconds = tool + work if tool is not None and work is not None else None
        basis = "first_tool_seconds+work_seconds"
    usage = turn.get("usage", {})
    key = (
        "output"
        if "output" in usage
        else "output_tokens"
        if "output_tokens" in usage
        else None
    )
    return {
        "analysis_revision": ANALYSIS_REVISION,
        "usage_rate_revision": USAGE_REVISION,
        "usage_key": key,
        "reported_output_tokens": usage.get(key) if key else None,
        "duration_basis": basis if seconds is not None else None,
        "turn_seconds": seconds,
        "original_output_tokens_per_second": turn.get("output_tokens_per_second"),
        "output_tokens_per_second": output_rate(usage, seconds)
        if seconds is not None
        else None,
    }


def recover(journal: Path) -> list[dict[str, Any]]:
    """Emit auditable derived turns and success-only rates, preserving every original file."""
    result: list[dict[str, Any]] = [
        {
            "kind": "usage_recovery_metadata",
            "analysis_revision": ANALYSIS_REVISION,
            "usage_rate_revision": USAGE_REVISION,
            "source_journal": str(journal.resolve()),
            "source_journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest(),
            "rate_note": (
                "Reported output tokens per full stream duration, not model decoding speed."
            ),
        }
    ]
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for rung in _rows(journal):
        if rung.get("kind") != "rung":
            continue
        folder = Path(rung["directory"])
        if not folder.exists():
            folder = journal.parent / folder.name
        source = folder / "items.jsonl"
        rows = _rows(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        good = {
            row["index"] for row in rows if row.get("kind") == "item" and row.get("ok")
        }
        clean = not rung.get("cleanup_survivors") and not rung.get("watchdog_killed")
        for turn in rows:
            if turn.get("kind") != "turn":
                continue
            derived = {
                "kind": "usage_recovered_turn",
                "backend": rung["backend"],
                "concurrency": rung["concurrency"],
                "repeat": rung.get("repeat"),
                "settings": rung["settings"],
                "index": turn["index"],
                "phase": turn["phase"],
                "correlation_id": turn.get("correlation_id"),
                "source_items": str(source.resolve()),
                "source_items_sha256": digest,
                "eligible": turn["index"] in good and clean,
                **recovered_turn(turn),
            }
            groups[rung["backend"], rung["concurrency"]].append(derived)
            result.append(derived)
    for (backend, concurrency), turns in groups.items():
        result.append(
            {
                "kind": "usage_recovery_aggregate",
                "analysis_revision": ANALYSIS_REVISION,
                "backend": backend,
                "concurrency": concurrency,
                "settings": turns[0]["settings"],
                "eligible_turns": sum(turn["eligible"] for turn in turns),
                "ineligible_turns": sum(not turn["eligible"] for turn in turns),
                **{
                    phase: distribution(
                        [
                            turn["output_tokens_per_second"]
                            for turn in turns
                            if turn["phase"] == phase
                            and turn["eligible"]
                            and turn["output_tokens_per_second"] is not None
                        ]
                    )
                    for phase in ("cold", "warm")
                },
            }
        )
    return result


def main() -> None:
    """Write a separate correction artifact; existing paths are never overwritten."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Retained results.jsonl"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New derived JSONL path"
    )
    args = parser.parse_args()
    derived = recover(args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        for row in derived:
            handle.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
