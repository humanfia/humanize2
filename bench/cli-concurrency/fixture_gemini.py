"""Translate Gemini content/function exchanges into the fixture's common task history."""

# ruff: noqa: INP001 -- standalone benchmark provider protocol

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any
from urllib.parse import unquote

from fixture_plan import CALL


def normalize(body: dict[str, Any], path: str) -> dict[str, Any]:
    """Match function responses to actual preceding calls, even when a CLI rewrites IDs."""
    messages: list[dict[str, Any]] = []
    pending: dict[str, deque[str]] = defaultdict(deque)
    for content in body.get("contents", []):
        if not isinstance(content, dict):
            continue
        role = "assistant" if content.get("role") == "model" else "user"
        texts = []
        for part in content.get("parts", []):
            if not isinstance(part, dict):
                continue
            if "text" in part:
                text = part["text"]
                # The official CLI wraps submitted user text in this exact envelope.
                # Strip only a leading, closed envelope; quoted requests in reminders
                # must not restart an already completed fixture turn.
                if (
                    role == "user"
                    and text.startswith("<USER_REQUEST>\n")
                    and "</USER_REQUEST>" in text
                ):
                    text = text.removeprefix("<USER_REQUEST>\n")
                texts.append({"type": "text", "text": text})
            if call := part.get("functionCall"):
                ident = str(call.get("id", ""))
                # Antigravity may replace provider call IDs. A harmless shell comment
                # preserves this fixture's step identity in the actual command history.
                for value in call.get("args", {}).values():
                    if isinstance(value, str) and (match := CALL.search(value)):
                        ident = match.group()
                        break
                pending[str(call.get("name", ""))].append(ident)
            if output := part.get("functionResponse"):
                waiting = pending[str(output.get("name", ""))]
                ident = waiting.popleft() if waiting else str(output.get("id", ""))
                messages.append({"role": "tool", "tool_call_id": ident, "content": ""})
        if texts:
            messages.append({"role": role, "content": texts})
    functions = [
        {
            "name": function["name"],
            "input_schema": function.get(
                "parameters", function.get("parametersJsonSchema", {})
            ),
        }
        for group in body.get("tools", [])
        for function in group.get("functionDeclarations", [])
    ]
    policy = body.get("toolConfig", {}).get("functionCallingConfig", {})
    allowed = policy.get("allowedFunctionNames", [])
    choice: str | dict[str, Any] | None = None
    if policy.get("mode") == "NONE":
        choice = "none"
    elif len(allowed) == 1:
        choice = {"type": "tool", "name": allowed[0]}
    return {
        "messages": messages,
        "tools": functions,
        "tool_choice": choice,
        "model": unquote(path.split("/models/", 1)[-1].rsplit(":", 1)[0]),
        "stream": path.endswith(":streamGenerateContent"),
        "max_tokens": body.get("generationConfig", {}).get("maxOutputTokens"),
        "system": body.get("systemInstruction", {}),
    }


def response(
    model: str,
    tool: dict[str, Any] | None,
    args: dict[str, Any],
    call_id: str,
    answer: str,
) -> tuple[dict[str, Any], list[tuple[str | None, Any]]]:
    """Emit a Gemini candidate whose JSON and SSE representations have identical content."""
    if tool:
        for name, value in args.items():
            if name.lower() in ("command", "commandline", "cmd", "shell_command"):
                args[name] = value + " # " + call_id
        part = {"functionCall": {"name": tool["name"], "args": args, "id": call_id}}
    else:
        part = {"text": answer}
    whole = {
        "candidates": [
            {
                "content": {"role": "model", "parts": [part]},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 1000,
            "candidatesTokenCount": 40,
            "totalTokenCount": 1040,
        },
        "modelVersion": model,
    }
    return whole, [(None, whole)]
