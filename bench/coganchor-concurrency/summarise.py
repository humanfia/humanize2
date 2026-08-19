"""Read the ladders and say, per backend, how many anchored agents 16 CPUs and 64 GiB hold.

Two numbers per backend, because they answer different questions:

``correct``
    The widest rung on which every agent finished its turn and left its work on the target.
    The ceiling on what works at all.
``comfortable``
    The widest rung that is also within twice the turn latency of a single agent.  Past it
    the machine is still correct and simply slower, which for a flow of long turns may be
    perfectly acceptable -- so it is reported beside the ceiling rather than instead of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "lab"
SLOWDOWN = 2.0

BACKENDS = ("claude", "codex", "grok", "kimi", "dsh")


def rungs(backend: str) -> list[dict[str, object]]:
    path = LAB / f"ladder-{backend}.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


print(
    f"{'backend':8} {'N':>4} {'ok':>4} {'fail':>4} {'p50 s':>7} {'p95 s':>7} "
    f"{'wall s':>7} {'turns/min':>10} {'mem GiB':>8} {'pids':>6} {'cpu%':>6} {'tgt%':>5}"
)
print("-" * 92)
verdicts: dict[str, dict[str, object]] = {}
for backend in BACKENDS:
    ladder = rungs(backend)
    if not ladder:
        continue
    base = next((r for r in ladder if r["concurrency"] == 1), None)
    baseline = float(base["turn_p50"]) if base else 0.0
    correct = 0
    comfortable = 0
    peak_rate = 0.0
    for rung in ladder:
        n = int(rung["concurrency"])
        wall = float(rung.get("wall_seconds", 0)) or 1.0
        rate = int(rung["ok"]) / wall * 60
        print(
            f"{backend:8} {n:4d} {int(rung['ok']):4d} {int(rung['failed']):4d} "
            f"{float(rung.get('turn_p50', -1)):7.2f} {float(rung.get('turn_p95', -1)):7.2f} "
            f"{float(rung.get('wall_seconds', -1)):7.1f} {rate:10.0f} "
            f"{float(rung.get('peak_memory_gib', -1)):8.2f} "
            f"{int(rung.get('peak_pids', -1)):6d} "
            f"{float(rung.get('cpu_busy_ratio', -1)) * 100:5.0f}% "
            f"{float(rung.get('target_busy_ratio', 0)) * 100:4.1f}%"
        )
        if int(rung["failed"]) == 0:
            correct = max(correct, n)
            peak_rate = max(peak_rate, rate)
            if baseline and float(rung["turn_p95"]) <= SLOWDOWN * baseline:
                comfortable = max(comfortable, n)
    per = next((r for r in ladder if int(r["concurrency"]) == correct), None)
    verdicts[backend] = {
        "correct": correct,
        "comfortable": comfortable,
        "mem_per_agent_mib": (
            round(float(per["peak_memory_gib"]) * 1024 / correct, 1)
            if per and correct
            else -1
        ),
        "pids_per_agent": (
            round(int(per["peak_pids"]) / correct, 1) if per and correct else -1
        ),
        "errors": (per or {}).get("errors", []),
        "peak_turns_per_min": round(peak_rate),
    }
    print("-" * 92)

print()
print(f"{'backend':8} {'all correct up to':>18} {'and still quick to':>19} "
      f"{'MiB/agent':>10} {'procs/agent':>12} {'peak turns/min':>15}")
for backend, verdict in verdicts.items():
    print(
        f"{backend:8} {verdict['correct']:18d} {verdict['comfortable']:19d} "
        f"{verdict['mem_per_agent_mib']:10} {verdict['pids_per_agent']:12} "
        f"{verdict['peak_turns_per_min']:15}"
    )
print()
print(json.dumps(verdicts, indent=2))
