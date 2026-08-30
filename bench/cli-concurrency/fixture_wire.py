"""Small valid JSON and SSE responses for three model-provider wire protocols."""

# ruff: noqa: INP001 -- standalone benchmark support

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fixture_plan import STEPS, Turn, arguments, command, shell


def response(
    body: dict[str, Any], protocol: str, turn: Turn | None
) -> tuple[dict[str, Any], list[tuple[str | None, Any]]]:
    """Emit exactly one shell tool call or a final answer, with matching streamed content."""
    tool = shell(body) if turn and turn.completed < STEPS else None
    if turn and turn.completed < STEPS and tool is None:
        raise ValueError(
            "No supported shell function was declared for this benchmark task"
        )
    call_id = (
        f"call_fixture_{turn.phase}_{turn.completed}_{uuid.uuid4().hex[:12]}"
        if turn
        else ""
    )
    args = (
        arguments(tool["schema"], command(turn))
        if tool and tool["kind"] != "local_shell"
        else {}
    )
    answer = f"FIXTURE-COMPLETE {turn.marker}" if turn else "FIXTURE-AUXILIARY"
    model = str(body.get("model", "fixture-model"))
    if protocol == "gemini":
        from fixture_gemini import response as gemini_response

        return gemini_response(model, tool, args, call_id, answer)
    if protocol == "anthropic":
        return _anthropic(model, tool, args, call_id, answer)
    if protocol == "responses":
        return _responses(model, tool, args, call_id, answer, turn)
    return _chat(model, tool, args, call_id, answer)


def _anthropic(
    model: str,
    tool: dict[str, Any] | None,
    args: dict[str, Any],
    call_id: str,
    answer: str,
) -> tuple[dict[str, Any], list[tuple[str | None, Any]]]:
    content = (
        {"type": "tool_use", "id": call_id, "name": tool["name"], "input": args}
        if tool
        else {"type": "text", "text": answer}
    )
    usage = {
        "input_tokens": 1000,
        "output_tokens": 40,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    whole = {
        "id": "msg_" + uuid.uuid4().hex,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [content],
        "stop_reason": "tool_use" if tool else "end_turn",
        "stop_sequence": None,
        "usage": usage,
    }
    start = {
        **whole,
        "content": [],
        "stop_reason": None,
        "usage": {**usage, "output_tokens": 0},
    }
    block = {**content, "input": {}} if tool else {"type": "text", "text": ""}
    delta = (
        {"type": "input_json_delta", "partial_json": json.dumps(args)}
        if tool
        else {"type": "text_delta", "text": answer}
    )
    chunks = [
        ("message_start", {"type": "message_start", "message": start}),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": block},
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": delta},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": whole["stop_reason"], "stop_sequence": None},
                "usage": {"output_tokens": 40},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return whole, chunks


def _responses(
    model: str,
    tool: dict[str, Any] | None,
    args: dict[str, Any],
    call_id: str,
    answer: str,
    turn: Turn | None,
) -> tuple[dict[str, Any], list[tuple[str | None, Any]]]:
    ident = "item_" + uuid.uuid4().hex
    if tool and tool["kind"] == "local_shell":
        item = {
            "type": "local_shell_call",
            "id": ident,
            "call_id": call_id,
            "status": "completed",
            "action": {
                "type": "exec",
                "command": ["bash", "-lc", command(turn)],
                "timeout_ms": 60000,
            },
        }
    elif tool:
        item = {
            "type": "function_call",
            "id": ident,
            "call_id": call_id,
            "name": tool["name"],
            "arguments": json.dumps(args),
            "status": "completed",
        }
        if tool["namespace"]:
            item["namespace"] = tool["namespace"]
    else:
        item = {
            "type": "message",
            "id": ident,
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": answer, "annotations": []}],
        }
    envelope = {
        "id": "resp_" + uuid.uuid4().hex,
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
    whole = {
        **envelope,
        "status": "completed",
        "output": [item],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 40,
            "total_tokens": 1040,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }
    chunks: list[tuple[str | None, Any]] = []

    def emit(kind: str, **fields: Any) -> None:
        chunks.append((kind, {"type": kind, "sequence_number": len(chunks), **fields}))

    emit("response.created", response=envelope)
    emit("response.in_progress", response=envelope)
    initial = {**item, "status": "in_progress"}
    if tool and tool["kind"] != "local_shell":
        initial["arguments"] = ""
    elif not tool:
        initial["content"] = []
    emit("response.output_item.added", output_index=0, item=initial)
    fields = {"item_id": ident, "output_index": 0}
    if tool and tool["kind"] != "local_shell":
        emit(
            "response.function_call_arguments.delta", **fields, delta=item["arguments"]
        )
        emit(
            "response.function_call_arguments.done",
            **fields,
            arguments=item["arguments"],
        )
    elif not tool:
        fields["content_index"] = 0
        emit(
            "response.content_part.added",
            **fields,
            part={"type": "output_text", "text": "", "annotations": []},
        )
        emit("response.output_text.delta", **fields, delta=answer)
        emit("response.output_text.done", **fields, text=answer)
        emit("response.content_part.done", **fields, part=item["content"][0])
    emit("response.output_item.done", output_index=0, item=item)
    emit("response.completed", response=whole)
    return whole, chunks


def _chat(
    model: str,
    tool: dict[str, Any] | None,
    args: dict[str, Any],
    call_id: str,
    answer: str,
) -> tuple[dict[str, Any], list[tuple[str | None, Any]]]:
    head = {
        "id": "chatcmpl-" + uuid.uuid4().hex,
        "created": int(time.time()),
        "model": model,
    }
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 40,
        "total_tokens": 1040,
        "prompt_tokens_details": {"cached_tokens": 0},
    }
    message: dict[str, Any] = {"role": "assistant", "content": None if tool else answer}
    delta: dict[str, Any] = {"content": answer}
    if tool:
        call = {
            "id": call_id,
            "type": "function",
            "function": {"name": tool["name"], "arguments": json.dumps(args)},
        }
        message["tool_calls"] = [call]
        delta = {"tool_calls": [{"index": 0, **call}]}
    finish = "tool_calls" if tool else "stop"
    whole = {
        **head,
        "object": "chat.completion",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage,
    }
    chunks: list[tuple[str | None, Any]] = [
        (
            None,
            {
                **head,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": part, "finish_reason": None}],
            },
        )
        for part in ({"role": "assistant", "content": ""}, delta)
    ]
    chunks.extend(
        [
            (
                None,
                {
                    **head,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    "usage": usage,
                },
            ),
            (None, "[DONE]"),
        ]
    )
    return whole, chunks
