"""Gemini function-history correlation and real checker execution across two turns."""

# ruff: noqa: INP001, S101, PLR2004 -- standalone fixture tests

from __future__ import annotations

import http.client
import json
import subprocess
import threading
from typing import TYPE_CHECKING, Any

from fixture_gemini import normalize
from fixture_plan import Turn, locate
from fixture_server import Fixture
from fixture_wire import response
from workload import prepare, prompt, validate

if TYPE_CHECKING:
    from pathlib import Path

MARKER = "MEMORY-" + "d" * 32
ROUTE = "/v1beta/models/gemini-3.7-flash:streamGenerateContent"
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "CommandLine": {"type": "STRING"},
        "Cwd": {"type": "STRING"},
        "WaitMsBeforeAsync": {"type": "INTEGER", "maximum": 10000},
        "toolAction": {"type": "STRING"},
        "toolSummary": {"type": "STRING"},
    },
    "required": [
        "CommandLine",
        "Cwd",
        "WaitMsBeforeAsync",
        "toolAction",
        "toolSummary",
    ],
}


def _body() -> dict[str, Any]:
    return {
        "contents": [],
        "tools": [
            {"functionDeclarations": [{"name": "run_command", "parameters": SCHEMA}]}
        ],
    }


def test_gemini_real_tasks_reset_and_match_responses_when_cli_rewrites_ids(
    tmp_path: Path,
) -> None:
    """Actual shell work completes twice, and only observed function responses advance it."""
    expected = prepare(tmp_path, 0)
    body = _body()
    for phase in ("cold", "warm"):
        body["contents"].append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"<USER_REQUEST>\n{prompt(phase, MARKER)}\n</USER_REQUEST>"
                    }
                ],
            }
        )
        for step in range(3):
            normalized = normalize(body, ROUTE)
            turn = locate(normalized)
            assert turn == Turn(MARKER, phase, step)
            whole, _ = response(normalized, "gemini", turn)
            content = whole["candidates"][0]["content"]
            call = content["parts"][0]["functionCall"]
            assert call["args"]["WaitMsBeforeAsync"] == 10000
            ran = subprocess.run(
                ["bash", "-lc", call["args"]["CommandLine"]],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=True,
            )
            call["id"] = "native-regenerated-call-id"
            body["contents"].append(content)
            assert (
                locate(normalize(body, ROUTE)) == turn
            )  # A requested call is not completed work.
            body["contents"].append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": "run_command",
                                "response": {"output": ran.stdout},
                            }
                        }
                    ],
                }
            )
        turn = locate(normalize(body, ROUTE))
        assert turn == Turn(MARKER, phase, 3)
        whole, _ = response(normalize(body, ROUTE), "gemini", turn)
        assert MARKER in whole["candidates"][0]["content"]["parts"][0]["text"]
        body["contents"].append(whole["candidates"][0]["content"])
        assert validate(tmp_path, phase, expected[phase])["ok"]


def test_gemini_http_stream_routes_model_and_journals_safe_correlation(
    tmp_path: Path,
) -> None:
    """The official Gemini route returns valid SSE and attributes the request to its task."""
    log = tmp_path / "requests.jsonl"
    with Fixture(0, log, ["gemini-3.7-flash"]) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = _body()
        body["contents"] = [
            {"role": "user", "parts": [{"text": prompt("cold", MARKER)}]}
        ]
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=3
        )
        try:
            connection.request(
                "POST",
                ROUTE + "?alt=sse&key=fake-secret-must-not-log",
                json.dumps(body),
                {"Content-Type": "application/json"},
            )
            received = connection.getresponse()
            assert received.status == 200
            payload = json.loads(received.read().decode().removeprefix("data: "))
            assert (
                payload["candidates"][0]["content"]["parts"][0]["functionCall"]["name"]
                == "run_command"
            )
        finally:
            connection.close()
            server.shutdown()
            thread.join(timeout=2)
    recorded = log.read_text(encoding="utf-8")
    assert "fake-secret-must-not-log" not in recorded
    row = json.loads(recorded)
    assert row["protocol"] == "gemini"
    assert row["model"] == "gemini-3.7-flash"
    assert row["correlation_id"] == MARKER
    assert row["request_kind"] == "workload"


def test_gemini_quoted_or_incomplete_request_envelope_is_not_a_new_task() -> None:
    """A task echoed in native review text cannot masquerade as a newly submitted turn."""
    for text in (
        f"Review the prior request:\n<USER_REQUEST>\n{prompt('cold', MARKER)}\n</USER_REQUEST>",
        f"<USER_REQUEST>\n{prompt('cold', MARKER)}",
    ):
        body = _body()
        body["contents"] = [{"role": "user", "parts": [{"text": text}]}]
        assert locate(normalize(body, ROUTE)) is None
