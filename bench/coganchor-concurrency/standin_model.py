"""A model provider that scripts the same turn for every agent CLI under test.

Five coding agents, three wire protocols.  This answers all three, and answers them the
same way: a fixed number of shell tool calls, then a final sentence.  What each agent does
under coganchor is therefore identical work, which is what makes the concurrency numbers
comparable across backends.

    POST /v1/messages          Anthropic Messages    (claude)
    POST /v1/responses         OpenAI Responses      (codex, grok)
    POST /v1/chat/completions  OpenAI Chat           (dsh, kimi)
    GET  /v1/models            a catalogue           (grok, others probing)
    GET  /api.json             a models.dev registry (kimi provider add)

It runs beside the harness rather than inside the measured cgroup: it stands in for a model
provider, which is not part of what is being sized.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

#: How many shell tool calls one scripted turn makes before it answers.
STEPS = int(os.environ.get("STANDIN_STEPS", "3"))

#: The shell command each of those calls runs, formatted with the step number.  It reads a
#: seeded file and writes one, so every step is a full coganchor round trip: a read
#: materialised from the target, a command run there, and a write pushed back.
COMMAND = os.environ.get(
    "STANDIN_COMMAND",
    "cat seed.txt && echo step-{step} >> touched.txt && ls -1 | wc -l",
)

#: What the turn says when it is done, so a harness can tell a finished turn from a
#: truncated one.
FINAL = os.environ.get("STANDIN_FINAL", "STANDIN-TURN-COMPLETE")

#: Names that mean "run this shell command", best first.  Five CLIs spell it five ways --
#: `Bash`, `shell`, `run_terminal_command`, `execute_command` -- so the pick is scored
#: rather than matched exactly, and a name no pattern claims leaves the turn tool-free.
_SHELL_PATTERNS = (
    re.compile(r"^(bash|shell|sh|local_shell)$", re.IGNORECASE),
    re.compile(
        r"^(run|execute|exec)_?(terminal_?)?(command|shell|bash)s?$", re.IGNORECASE
    ),
    re.compile(r"terminal.*command|command.*terminal", re.IGNORECASE),
    re.compile(r"^(run|execute|exec)[_-]?", re.IGNORECASE),
    re.compile(r"(^|_)(bash|shell|terminal)(_|$)", re.IGNORECASE),
)

_MODEL_IDS = (
    "standin-1",
    "claude-sonnet-4-5",
    "gpt-5-codex",
    "grok-code",
    "deepseek-chat",
    "kimi-k2",
)

_log_lock = threading.Lock()
LOG_PATH = os.environ.get("STANDIN_LOG", "")


def _log(kind: str, detail: object) -> None:
    if not LOG_PATH:
        return
    with _log_lock, Path(LOG_PATH).open("a") as handle:
        handle.write(
            json.dumps({"at": time.time(), "kind": kind, "detail": detail}) + "\n"
        )


# --------------------------------------------------------------------------- tool choice


def _fill(schema: dict[str, Any], command: str) -> dict[str, Any]:
    """Builds arguments for a tool out of the schema the agent declared it with.

    Reading the schema rather than hard-coding one shape per CLI is what keeps this working
    across five different tool vocabularies.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return {"command": command}
    required = schema.get("required")
    required = list(required) if isinstance(required, list) else list(properties)
    filled: dict[str, Any] = {}
    for name in required:
        spec = properties.get(name)
        spec = spec if isinstance(spec, dict) else {}
        kind = spec.get("type")
        if isinstance(kind, list):
            kind = next((one for one in kind if one != "null"), "string")
        lowered = str(name).lower()
        if lowered in ("command", "cmd", "script", "shell_command", "commandline"):
            if kind == "array":
                filled[name] = ["bash", "-lc", command]
            else:
                filled[name] = command
        elif kind == "array":
            filled[name] = []
        elif kind == "boolean":
            filled[name] = False
        elif kind in ("number", "integer"):
            filled[name] = 60000 if "timeout" in lowered else 0
        elif kind == "object":
            filled[name] = {}
        else:
            filled[name] = "sizing coganchor concurrency"
    # A tool whose required list never named the command still has to be given one.
    if not any(
        str(key).lower() in ("command", "cmd", "script", "shell_command", "commandline")
        for key in filled
    ):
        for name, spec in properties.items():
            if str(name).lower() in ("command", "cmd", "script"):
                shape = spec if isinstance(spec, dict) else {}
                filled[name] = (
                    ["bash", "-lc", command]
                    if shape.get("type") == "array"
                    else command
                )
                break
    return filled


def _declared(body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Every tool the request declared, as ``(name, schema, kind)``."""
    found: list[tuple[str, dict[str, Any], str]] = []
    tools = body.get("tools")
    if not isinstance(tools, list):
        return found
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        kind = str(tool.get("type") or "function")
        if kind == "local_shell":
            found.append(("local_shell", {}, "local_shell"))
            continue
        inner = tool.get("function")
        if isinstance(inner, dict):  # chat completions
            name = str(inner.get("name") or "")
            schema = inner.get("parameters")
        else:  # responses / anthropic
            name = str(tool.get("name") or "")
            schema = tool.get("parameters") or tool.get("input_schema")
        if name:
            found.append((name, schema if isinstance(schema, dict) else {}, kind))
    return found


def _shell_tool(body: dict[str, Any]) -> tuple[str, dict[str, Any], str] | None:
    declared = _declared(body)
    for pattern in _SHELL_PATTERNS:
        for entry in declared:
            if pattern.search(entry[0]):
                return entry
    return None


def _steps_taken_anthropic(body: dict[str, Any]) -> int:
    taken = 0
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, list):
            taken += sum(
                1
                for block in content
                if isinstance(block, dict) and block.get("type") == "tool_result"
            )
    return taken


def _steps_taken_responses(body: dict[str, Any]) -> int:
    taken = 0
    items = body.get("input")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and str(item.get("type", "")).endswith(
                (
                    "function_call_output",
                    "local_shell_call_output",
                    "custom_tool_call_output",
                )
            ):
                taken += 1
    return taken


def _steps_taken_chat(body: dict[str, Any]) -> int:
    return sum(
        1
        for message in body.get("messages") or []
        if isinstance(message, dict) and message.get("role") == "tool"
    )


# --------------------------------------------------------------------------- wire shapes


def _sse(handler: BaseHTTPRequestHandler, chunks: list[tuple[str | None, Any]]) -> None:
    """Writes one scripted turn as an event stream, and ends it by closing the connection.

    Closing is the part that matters.  A stream left open on keep-alive with no
    content-length never ends as far as the client is concerned: Claude Code runs the
    turn's tool call and then waits out its own timeout instead of asking for the next
    step, which reads exactly like an agent that gave up after one tool.
    """
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    handler.send_header("connection", "close")
    handler.end_headers()
    for event, payload in chunks:
        blob = payload if isinstance(payload, str) else json.dumps(payload)
        line = (f"event: {event}\n" if event else "") + f"data: {blob}\n\n"
        handler.wfile.write(line.encode())
    handler.wfile.flush()
    handler.close_connection = True


def _anthropic(body: dict[str, Any]) -> list[tuple[str | None, Any]]:
    model = str(body.get("model") or "standin-1")
    step = _steps_taken_anthropic(body)
    tool = _shell_tool(body)
    usage = {
        "input_tokens": 1000 + 100 * step,
        "output_tokens": 40,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    start: list[tuple[str | None, Any]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": f"msg_{uuid.uuid4().hex[:16]}",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": usage,
                },
            },
        )
    ]
    if tool is None or step >= STEPS:
        return [
            *start,
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": FINAL},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": usage,
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    name, schema, _ = tool
    arguments = json.dumps(_fill(schema, COMMAND.format(step=step + 1)))
    return [
        *start,
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": f"step {step + 1}"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:16]}",
                    "name": name,
                    "input": {},
                },
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": arguments},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": usage,
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]


def _responses(body: dict[str, Any]) -> list[tuple[str | None, Any]]:
    model = str(body.get("model") or "standin-1")
    step = _steps_taken_responses(body)
    tool = _shell_tool(body)
    response_id = f"resp_{uuid.uuid4().hex[:16]}"
    usage = {
        "input_tokens": 1000 + 100 * step,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": 40,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 1040 + 100 * step,
    }
    counter = {"n": 0}

    def numbered(event: str, payload: dict[str, Any]) -> tuple[str, Any]:
        payload["sequence_number"] = counter["n"]
        counter["n"] += 1
        return (event, payload)

    shell: dict[str, Any]
    if tool is None or step >= STEPS:
        item = {
            "type": "message",
            "id": f"msg_{uuid.uuid4().hex[:16]}",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": FINAL, "annotations": []}],
        }
    elif tool[2] == "local_shell":
        item = {
            "type": "local_shell_call",
            "id": f"lsh_{uuid.uuid4().hex[:16]}",
            "call_id": f"call_{uuid.uuid4().hex[:16]}",
            "status": "completed",
            "action": {
                "type": "exec",
                "command": ["bash", "-lc", COMMAND.format(step=step + 1)],
                "timeout_ms": 60000,
            },
        }
    else:
        name, schema, _ = tool
        shell = _fill(schema, COMMAND.format(step=step + 1))
        item = {
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:16]}",
            "call_id": f"call_{uuid.uuid4().hex[:16]}",
            "name": name,
            "arguments": json.dumps(shell),
            "status": "completed",
        }

    envelope = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "model": model,
        "status": "in_progress",
        "output": [],
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "usage": None,
    }
    done = dict(envelope, status="completed", output=[item], usage=usage)
    chunks: list[tuple[str | None, Any]] = [
        numbered(
            "response.created", {"type": "response.created", "response": dict(envelope)}
        ),
        numbered(
            "response.in_progress",
            {"type": "response.in_progress", "response": dict(envelope)},
        ),
        numbered(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": dict(item),
            },
        ),
    ]
    if item["type"] == "message":
        chunks.append(
            numbered(
                "response.output_text.delta",
                {
                    "type": "response.output_text.delta",
                    "item_id": item["id"],
                    "output_index": 0,
                    "content_index": 0,
                    "delta": FINAL,
                },
            )
        )
        chunks.append(
            numbered(
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "item_id": item["id"],
                    "output_index": 0,
                    "content_index": 0,
                    "text": FINAL,
                },
            )
        )
    elif item["type"] == "function_call":
        chunks.append(
            numbered(
                "response.function_call_arguments.delta",
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": item["id"],
                    "output_index": 0,
                    "delta": item["arguments"],
                },
            )
        )
        chunks.append(
            numbered(
                "response.function_call_arguments.done",
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": item["id"],
                    "output_index": 0,
                    "arguments": item["arguments"],
                },
            )
        )
    chunks.append(
        numbered(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": dict(item),
            },
        )
    )
    chunks.append(
        numbered("response.completed", {"type": "response.completed", "response": done})
    )
    return chunks


def _chat_chunks(
    body: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str | None, Any]]]:
    model = str(body.get("model") or "standin-1")
    step = _steps_taken_chat(body)
    tool = _shell_tool(body)
    made = f"chatcmpl-{uuid.uuid4().hex[:16]}"
    created = int(time.time())
    usage = {
        "prompt_tokens": 1000 + 100 * step,
        "completion_tokens": 40,
        "total_tokens": 1040 + 100 * step,
        "prompt_tokens_details": {"cached_tokens": 0},
    }
    head = {
        "id": made,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
    }

    if tool is None or step >= STEPS:
        message = {"role": "assistant", "content": FINAL}
        finish = "stop"
        deltas: list[dict[str, Any]] = [
            {"role": "assistant", "content": ""},
            {"content": FINAL},
        ]
    else:
        name, schema, _ = tool
        arguments = json.dumps(_fill(schema, COMMAND.format(step=step + 1)))
        call_id = f"call_{uuid.uuid4().hex[:16]}"
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
        finish = "tool_calls"
        deltas = [
            {"role": "assistant", "content": None},
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ]
            },
        ]

    chunks: list[tuple[str | None, Any]] = [
        (
            None,
            dict(head, choices=[{"index": 0, "delta": delta, "finish_reason": None}]),
        )
        for delta in deltas
    ]
    chunks.append(
        (
            None,
            dict(
                head,
                choices=[{"index": 0, "delta": {}, "finish_reason": finish}],
                usage=usage,
            ),
        )
    )
    chunks.append((None, "[DONE]"))
    whole = {
        "id": made,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage,
    }
    return whole, chunks


# --------------------------------------------------------------------------- the server


def _catalogue() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "created": 1700000000,
                "owned_by": "standin",
            }
            for name in _MODEL_IDS
        ],
    }


def _registry(port: int) -> dict[str, Any]:
    """A models.dev-shaped api.json, which is what ``kimi provider add`` imports."""
    return {
        "standin": {
            "id": "standin",
            "name": "Standin",
            # `type` is Kimi's own addition to the models.dev shape, and an entry without
            # one is skipped as invalid.
            "type": "openai",
            "npm": "@ai-sdk/openai-compatible",
            "api": f"http://127.0.0.1:{port}/v1",
            "env": ["STANDIN_API_KEY"],
            "doc": "http://127.0.0.1/standin",
            "models": {
                "standin-1": {
                    "id": "standin-1",
                    "name": "Standin 1",
                    "attachment": False,
                    "reasoning": False,
                    "tool_call": True,
                    "temperature": True,
                    "knowledge": "2026-01",
                    "release_date": "2026-01-01",
                    "last_updated": "2026-01-01",
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "open_weights": False,
                    "cost": {"input": 0.0, "output": 0.0},
                    "limit": {"context": 200000, "output": 32000},
                }
            },
        }
    }


class Handler(BaseHTTPRequestHandler):
    """The one handler all three wire protocols are answered from, by path."""

    protocol_version = "HTTP/1.1"
    port = 0

    def log_message(self, *args: object) -> None:
        pass

    def _json(self, payload: object, status: int = 200) -> None:
        blob = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path.endswith("api.json"):
            self._json(_registry(self.port))
        elif path.endswith("/models"):
            self._json(_catalogue())
        elif path.endswith("/api-key"):
            self._json(
                {
                    "redacted_api_key": "standin",
                    "name": "standin",
                    "acls": ["api-key:model:*"],
                    "api_key_blocked": False,
                    "api_key_disabled": False,
                    "team_blocked": False,
                }
            )
        else:
            self._json({"object": "ok"})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        path = self.path.split("?")[0]
        streaming = bool(body.get("stream", False))
        try:
            if path.endswith("/messages"):
                _log(
                    "messages",
                    {
                        "step": _steps_taken_anthropic(body),
                        "tools": [one[0] for one in _declared(body)],
                        "picked": (_shell_tool(body) or ("-",))[0],
                    },
                )
                chunks = _anthropic(body)
                if streaming:
                    _sse(self, chunks)
                else:
                    self._json(_anthropic_whole(body))
            elif path.endswith("/responses"):
                _log(
                    "responses",
                    {
                        "step": _steps_taken_responses(body),
                        "tools": [one[0] for one in _declared(body)],
                        "picked": (_shell_tool(body) or ("-",))[0],
                    },
                )
                chunks = _responses(body)
                if streaming:
                    _sse(self, chunks)
                else:
                    self._json(json.loads(json.dumps(chunks[-1][1]))["response"])
            elif path.endswith("/chat/completions"):
                _log(
                    "chat",
                    {
                        "step": _steps_taken_chat(body),
                        "tools": [one[0] for one in _declared(body)],
                        "picked": (_shell_tool(body) or ("-",))[0],
                    },
                )
                whole, chunks = _chat_chunks(body)
                if streaming:
                    _sse(self, chunks)
                else:
                    self._json(whole)
            else:
                self._json(
                    {"error": {"message": f"no route {path}", "type": "not_found"}}, 404
                )
        except (BrokenPipeError, ConnectionResetError):
            pass


def _anthropic_whole(body: dict[str, Any]) -> dict[str, Any]:
    """The same scripted turn, for a client that asked for it unstreamed."""
    step = _steps_taken_anthropic(body)
    tool = _shell_tool(body)
    content: list[dict[str, Any]]
    if tool is None or step >= STEPS:
        content = [{"type": "text", "text": FINAL}]
        stop = "end_turn"
    else:
        name, schema, _ = tool
        content = [
            {"type": "text", "text": f"step {step + 1}"},
            {
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex[:16]}",
                "name": name,
                "input": _fill(schema, COMMAND.format(step=step + 1)),
            },
        ]
        stop = "tool_use"
    return {
        "id": f"msg_{uuid.uuid4().hex[:16]}",
        "type": "message",
        "role": "assistant",
        "model": str(body.get("model") or "standin-1"),
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 40},
    }


if __name__ == "__main__":
    port = int(sys.argv[1])
    Handler.port = port
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"standin model on {port}", flush=True)
    server.serve_forever()
