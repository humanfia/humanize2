"""Protocol, turn isolation and actual workload checks for the synthetic provider."""

# ruff: noqa: INP001, S101, PLR2004 -- benchmark tests and their literal expectations

from __future__ import annotations

import http.client
import json
import subprocess
import threading
from typing import TYPE_CHECKING, Any

import pytest
from fixture_plan import Turn, arguments, locate
from fixture_server import Fixture
from fixture_wire import response
from workload import prepare, prompt, validate

if TYPE_CHECKING:
    from pathlib import Path

MARKER = "MEMORY-" + "a" * 32
SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string"}},
    "required": ["command"],
}


def _request(protocol: str) -> dict[str, Any]:
    if protocol == "anthropic":
        return {
            "model": "fixture-model",
            "messages": [],
            "tools": [{"name": "Bash", "input_schema": SCHEMA}],
        }
    if protocol == "responses":
        return {
            "model": "fixture-model",
            "input": [],
            "tools": [
                {"type": "function", "name": "exec_command", "parameters": SCHEMA}
            ],
        }
    return {
        "model": "fixture-model",
        "messages": [],
        "tools": [
            {
                "type": "function",
                "function": {"name": "run_shell_command", "parameters": SCHEMA},
            }
        ],
    }


def _call(protocol: str, whole: dict[str, Any]) -> tuple[str, str]:
    if protocol == "anthropic":
        block = whole["content"][0]
        return block["id"], block["input"]["command"]
    if protocol == "responses":
        block = whole["output"][0]
        return block["call_id"], json.loads(block["arguments"])["command"]
    block = whole["choices"][0]["message"]["tool_calls"][0]
    return block["id"], json.loads(block["function"]["arguments"])["command"]


def _append(
    protocol: str,
    items: list[dict[str, Any]],
    whole: dict[str, Any],
    call: str,
    output: str,
) -> None:
    if protocol == "anthropic":
        items.extend(
            [
                {"role": "assistant", "content": whole["content"]},
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": call, "content": output}
                    ],
                },
            ]
        )
    elif protocol == "responses":
        items.extend(
            [
                whole["output"][0],
                {"type": "function_call_output", "call_id": call, "output": output},
            ]
        )
    else:
        items.extend(
            [
                whole["choices"][0]["message"],
                {"role": "tool", "tool_call_id": call, "content": output},
            ]
        )


@pytest.mark.parametrize("protocol", ["anthropic", "responses", "chat"])
def test_two_complete_real_workloads_reset_at_the_new_user_turn(
    tmp_path: Path, protocol: str
) -> None:
    """Every protocol requests read/edit/execute twice instead of reusing old tool counts."""
    expected = prepare(tmp_path, 0)
    body = _request(protocol)
    items = body.get("messages", body.get("input"))
    for phase in ("cold", "warm"):
        items.append({"role": "user", "content": prompt(phase, MARKER)})
        for step in range(3):
            turn = locate(body)
            assert turn == Turn(MARKER, phase, step)
            whole, _ = response(body, protocol, turn)
            call, script = _call(protocol, whole)
            ran = subprocess.run(
                ["bash", "-lc", script],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=True,
            )
            _append(protocol, items, whole, call, ran.stdout)
        whole, _ = response(body, protocol, locate(body))
        assert MARKER in json.dumps(whole)
        assert validate(tmp_path, phase, expected[phase])["ok"]


def test_responses_incremental_history_and_namespace_arguments() -> None:
    """Continuation IDs carry task identity; streamed function arguments are sent once."""
    body = _request("responses")
    body["tools"] = [{"type": "namespace", "name": "functions", "tools": body["tools"]}]
    body["input"] = [
        {
            "type": "function_call_output",
            "call_id": "call_fixture_warm_1_abc",
            "output": "done",
        }
    ]
    turn = locate(body, Turn(MARKER, "warm", 1))
    assert turn == Turn(MARKER, "warm", 2)
    whole, chunks = response(body, "responses", turn)
    added = next(
        payload["item"]
        for kind, payload in chunks
        if kind == "response.output_item.added"
    )
    assert added["arguments"] == ""
    assert added["namespace"] == "functions"
    delta = next(
        payload["delta"]
        for kind, payload in chunks
        if kind == "response.function_call_arguments.delta"
    )
    assert delta == whole["output"][0]["arguments"]


def test_http_stream_finishes_and_records_request_arrival_without_auth(
    tmp_path: Path,
) -> None:
    """The SSE connection terminates and measurements retain no credential headers."""
    log = tmp_path / "requests.jsonl"
    with Fixture(0, log, ["fixture-model"]) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = _request("chat")
        body["messages"] = [{"role": "user", "content": prompt("cold", MARKER)}]
        body["stream"] = True
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=3
        )
        try:
            connection.request(
                "POST",
                "/v1/chat/completions",
                json.dumps(body),
                {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer never-log-this-fixture-value",
                },
            )
            received = connection.getresponse()
            assert received.status == 200
            assert received.read().endswith(b"data: [DONE]\n\n")
        finally:
            connection.close()
            server.shutdown()
            thread.join(timeout=2)
    recorded = log.read_text(encoding="utf-8")
    assert "never-log-this-fixture-value" not in recorded
    row = json.loads(recorded)
    assert row["received_monotonic_ns"] > 0
    assert row["first_provider_request"]
    assert row["correlation_id"] == MARKER
    assert row["phase"] == "cold"
    assert row["completed_steps"] == 0


def test_unknown_shell_schema_cannot_silently_produce_fake_success() -> None:
    """A tool grammar the fixture cannot drive is an explicit unsupported case."""
    with pytest.raises(ValueError, match="command argument"):
        arguments({"properties": {"unrecognized": {"type": "string"}}}, "true")
    with pytest.raises(ValueError, match="No supported shell"):
        response({"tools": []}, "chat", Turn(MARKER, "cold", 0))


def test_quoted_completion_review_does_not_restart_work_or_mask_a_retry() -> None:
    """Grok's injected user-role quote preserves tool history; a new actual task resets it."""
    body = _request("chat")
    task = prompt("cold", MARKER)
    items = [{"role": "user", "content": f"<user_query>\n{task}\n</user_query>"}]
    items.extend(
        {
            "role": "tool",
            "tool_call_id": f"call_fixture_cold_{step}_abc",
            "content": "done",
        }
        for step in range(3)
    )
    items.append({"role": "assistant", "content": f"FIXTURE-COMPLETE {MARKER}"})
    items.append(
        {
            "role": "user",
            "content": (
                "<system-reminder>Review the request before finishing:\n"
                f"{task}\n</system-reminder>"
            ),
        }
    )
    body["messages"] = items
    turn = locate(body)
    assert turn == Turn(MARKER, "cold", 3)
    from fixture_plan import auxiliary_reason

    assert auxiliary_reason(body, turn) == "completion_review"
    whole, _ = response(body, "chat", turn)
    assert "tool_calls" not in whole["choices"][0]["message"]
    assert MARKER in whole["choices"][0]["message"]["content"]
    # An actual duplicated task remains workload step0, so the metric's exact chain rejects it.
    items[-1] = {"role": "user", "content": task}
    turn = locate(body)
    assert turn == Turn(MARKER, "cold", 0)
    assert auxiliary_reason(body, turn) is None
    # A quoted instruction before completing work cannot be hidden as a completion review.
    items.pop(-2)
    items[-1] = {"role": "user", "content": f"Review: {task}"}
    assert auxiliary_reason(body, locate(body)) is None
