"""Reject incomplete work and retries while measuring genuine auxiliary requests."""

# ruff: noqa: INP001, S101, PLR2004 -- standalone measurement regression cases

from __future__ import annotations

from typing import Any

import pytest
from fixture_metrics import measure
from fixture_plan import Turn, auxiliary_reason, request_shape

MARKER = "MEMORY-" + "a" * 32


def _call(step: int, received: int, **extra: Any) -> dict[str, Any]:
    return {
        "completed_steps": step,
        "received_monotonic_ns": received,
        "processing_seconds": 0.001,
        "ok": True,
        "tools": ["bash"],
        "request_kind": "workload",
        **extra,
    }


def test_auxiliary_arrival_counts_toward_startup_but_cannot_replace_work() -> None:
    """A title request is the first provider call, yet the full tool chain remains mandatory."""
    turn = {"turn_started_monotonic_ns": 1_000_000_000, "result_seconds": 2}
    title = _call(0, 1_100_000_000, tools=[], request_kind="auxiliary")
    work = [_call(step, 1_500_000_000 + step * 100_000_000) for step in range(4)]
    result = measure(turn, [title, *work])
    assert result["ok"]
    assert result["first_provider_request_seconds"] == 0.1
    assert result["workload_requests"] == 4
    assert result["auxiliary_requests"] == 1
    assert not measure(turn, [title, *work[1:]])["ok"]
    assert not measure(turn, [title, work[0], *work])["ok"]
    assert not measure(turn, [title, *work, work[0]])["ok"]
    assert not measure(
        turn, [{**title, "ok": False, "error": "old fixture 400"}, *work]
    )["ok"]


def test_provider_failures_clock_errors_and_incomplete_final_exchange_fail() -> None:
    """Artifact success alone cannot bless failed exchanges or inconsistent arrival times."""
    turn = {"turn_started_monotonic_ns": 1_000_000_000, "result_seconds": 2}
    work = [_call(step, 1_500_000_000 + step * 100_000_000) for step in range(4)]
    for index in range(4):
        broken = [dict(call) for call in work]
        broken[index]["ok"] = False
        assert not measure(turn, broken)["ok"]
    assert not measure(turn, work[:-1])["ok"]
    assert not measure({**turn, "turn_started_monotonic_ns": 2_000_000_000}, work)["ok"]
    assert not measure({**turn, "result_seconds": 0.7}, work)["ok"]
    auxiliary = _call(
        0, 1_900_000_000, request_kind="auxiliary", client_disconnected=True, ok=False
    )
    result = measure(turn, [*work, auxiliary])
    assert result["ok"]
    assert result["auxiliary_cancelled_requests"] == 1


@pytest.mark.parametrize(
    "tools", [[], [{"name": "StructuredOutput", "input_schema": {}}]]
)
def test_metadata_without_shell_capability_is_explicitly_auxiliary(
    tools: list[dict[str, Any]],
) -> None:
    """Title/structured-metadata requests cannot execute this shell-based workload."""
    assert (
        auxiliary_reason({"tools": tools}, Turn(MARKER, "cold", 0)) == "no_shell_tool"
    )


def test_explicit_tool_policy_distinguishes_metadata_from_work_without_timing_guess() -> (
    None
):
    """A tool-bearing request is never discarded just because it arrived after completion."""
    body = {"tools": [{"name": "Bash", "input_schema": {}}]}
    turn = Turn(MARKER, "cold", 0)
    assert auxiliary_reason(body, turn) is None
    assert auxiliary_reason({**body, "tool_choice": "none"}, turn) == "tools_disabled"
    assert (
        auxiliary_reason(
            {**body, "tool_choice": {"type": "tool", "name": "title"}}, turn
        )
        == "other_tool_forced"
    )
    assert (
        auxiliary_reason(
            {**body, "tool_choice": {"type": "tool", "name": "Bash"}}, turn
        )
        is None
    )
    shape = request_shape(
        {**body, "messages": [{"role": "user", "content": "private prompt text"}]}
    )
    assert "private prompt text" not in str(shape)
