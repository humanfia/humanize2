"""A small real coding task, repeated with fresh data in one conversation."""

# ruff: noqa: INP001 -- standalone benchmark scripts, outside the installed package

from __future__ import annotations

import hashlib
import json
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

BROKEN = "def score(values):\n    return sum(values)\n"
CHECK = '''"""Check the implementation and leave evidence of successful execution."""
import json
from pathlib import Path
from score import score

root = Path(__file__).parent
fixture = json.loads((root / "fixture.json").read_text())
for values in ([], [-4, 0, 2, 3], fixture["values"]):
    expected = sum(value * value for value in values if value > 0)
    assert score(values) == expected, (values, score(values), expected)
(root / "proof.json").write_text(json.dumps({
    "nonce": fixture["nonce"], "score": score(fixture["values"]), "ok": True,
}))
print("CHECK-PASSED")
'''


def prepare(workspace: Path, index: int) -> dict[str, Any]:
    """Seed two equally sized independent tasks without writing conversation memory."""
    expected: dict[str, Any] = {}
    for phase in ("cold", "warm"):
        where = workspace / phase
        where.mkdir(parents=True)
        # Reproducible inputs, with a per-run nonce proving each artifact is fresh.
        values = [((number * 17 + index * 13) % 71) - 35 for number in range(80)]
        nonce = secrets.token_hex(12)
        fixture = json.dumps({"nonce": nonce, "values": values})
        (where / "fixture.json").write_text(fixture, encoding="utf-8")
        (where / "score.py").write_text(BROKEN, encoding="utf-8")
        (where / "check_task.py").write_text(CHECK, encoding="utf-8")
        expected[phase] = {
            "proof": {
                "nonce": nonce,
                "score": sum(value * value for value in values if value > 0),
                "ok": True,
            },
            "fixture_sha256": hashlib.sha256(fixture.encode()).hexdigest(),
        }
    return expected


def prompt(phase: str, memory: str) -> str:
    """Ask for the same read/edit/execute work in each of two turns."""
    task = (
        f"Work only in the {phase}/ directory of the current workspace. "
        f"Read {phase}/fixture.json, {phase}/score.py and {phase}/check_task.py. "
        f"Fix score(values) in {phase}/score.py to return the sum of squares of strictly "
        "positive values (zero and negative values contribute zero). "
        f"Run python3 {phase}/check_task.py successfully. Do not change fixture.json "
        "or check_task.py, and let that command produce proof.json; do not write proof.json "
        "yourself. Do not delegate or search the web. Keep the final answer brief. "
    )
    if phase == "cold":
        return task + (
            f"Remember this conversation-only marker for the next turn: {memory}. "
            "Do not write the marker into any workspace file."
        )
    return task + (
        "Include in your final answer the exact conversation-only marker from my previous "
        "message. It is not in the task files; recall it from our conversation."
    )


def validate(workspace: Path, phase: str, expected: dict[str, Any]) -> dict[str, Any]:
    """Verify a fresh execution artifact, changed code and untouched task inputs."""
    where = workspace / phase
    try:
        proof = json.loads((where / "proof.json").read_text(encoding="utf-8"))
        source = (where / "score.py").read_text(encoding="utf-8")
        fixture = (where / "fixture.json").read_bytes()
        checks = {
            "execution_proof": proof == expected["proof"],
            "implementation_changed": source != BROKEN,
            "checker_unchanged": (where / "check_task.py").read_text(encoding="utf-8")
            == CHECK,
            "fixture_unchanged": hashlib.sha256(fixture).hexdigest()
            == expected["fixture_sha256"],
        }
        return {
            "ok": all(checks.values()),
            **checks,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "validation_error": str(exc)}
