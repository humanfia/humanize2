"""Collector for DeepSeek Harness session logs."""

from __future__ import annotations

import json
import pathlib
from typing import Any, cast

from hmz.tracing.session import (
    Action,
    Session,
    label,
    mapping,
    records,
    summarize,
    text_of,
    title_of,
    truncate,
    wanted,
)

_HEADER_FIELDS = (
    "version",
    "createdAt",
    "cwd",
    "parentSession",
    "origin",
    "delegationDepth",
    "agentPreset",
)


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the DeepSeek Harness sessions and descendants asked for.

    Args:
        home: Humanize's DeepSeek Harness home containing the sessions folder.
        workspace: Absolute workspace path to keep, or None for every workspace.
        sessions: Session ids to keep, or None to keep every session.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per durable JSONL log, with descendants linked to their parent.
    """
    logs: dict[str, tuple[pathlib.Path, dict[str, Any]]] = {}
    for path in sorted((home / "sessions").glob("*/*/session.jsonl")):
        header = _header(path)
        ident = header.get("id")
        cwd = header.get("cwd")
        if not isinstance(ident, str) or not ident:
            continue
        if workspace is not None and pathlib.Path(str(cwd)) != workspace:
            continue
        logs[ident] = (path, header)

    kept = {ident for ident in logs if wanted(sessions, f"dsh:{ident}")}
    frontier = kept
    while frontier:
        frontier = {
            ident
            for ident, (_, header) in logs.items()
            if header.get("parentSession") in frontier
        } - kept
        kept |= frontier

    collected: list[Session] = []
    for ident in sorted(kept):
        path, header = logs[ident]
        actions, info = _parse(path, window)
        parent = header.get("parentSession")
        short = ident.removeprefix("session-")[:8]
        named = info.get("title")
        title = f"{short} · {named}" if named else title_of(short, actions)
        label_name = info.get("label")
        if not isinstance(label_name, str) or not label_name:
            label_name = "subagent" if isinstance(parent, str) else "main"
        collected.append(
            Session(
                key=f"dsh:{ident}",
                backend="dsh",
                ident=ident,
                label=label_name,
                title=title,
                parent=f"dsh:{parent}" if isinstance(parent, str) else None,
                args={
                    "log": str(path),
                    **{field: header.get(field) for field in _HEADER_FIELDS},
                    **{
                        key: value
                        for key, value in info.items()
                        if key not in ("label", "title")
                    },
                },
                actions=actions,
            )
        )
    return collected


def _header(path: pathlib.Path) -> dict[str, Any]:
    """Reads a session header without letting one damaged log stop collection."""
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            loaded: object = json.loads(stream.readline())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    header = cast("dict[str, Any]", loaded)
    return header if header.get("type") == "session" else {}


def _parse(
    path: pathlib.Path, window: tuple[float, float]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one dsh event log into turn, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    steps: dict[tuple[object, object], Action] = {}
    turn: Action | None = None
    prev = 0.0
    for record in records(path):
        moment = record.get("time")
        if not isinstance(moment, (int, float)) or isinstance(moment, bool):
            continue
        at = float(moment) / 1000.0
        if not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        kind = record.get("type")
        data = mapping(record.get("data"))

        if kind == "session/title" and isinstance(data.get("title"), str):
            info["title"] = data["title"]
        elif kind == "subagent/descriptor" and isinstance(data.get("label"), str):
            info["label"] = data["label"]
        elif kind == "request/header":
            config = mapping(mapping(data.get("header")).get("config"))
            for source, target in (
                ("provider", "provider"),
                ("model", "model"),
                ("reasoningEffort", "effort"),
                ("maxTokens", "max_tokens"),
            ):
                if config.get(source) is not None:
                    info[target] = config[source]
        elif kind == "turn/start":
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
            turn = Action(
                "turn",
                "turn",
                at,
                at,
                {"turn": data.get("turn")},
            )
        elif kind == "user/message":
            source = mapping(data.get("source"))
            if source.get("kind") != "user":
                continue
            body = text_of(data.get("content"))
            if not body:
                continue
            if turn is None:
                turn = Action("turn", "turn", at, at, {})
            turn.name = f"turn: {summarize(body)}"
            turn.args["prompt"] = truncate(body)
            prev = max(prev, at)
        elif kind == "step/start":
            step = Action(
                "think",
                "llm",
                at,
                at,
                {"turn": data.get("turn"), "step": data.get("step")},
            )
            steps[(data.get("turn"), data.get("step"))] = step
            actions.append(step)
        elif kind == "assistant/message":
            prev = _message(actions, data, at, prev, steps, info)
        elif kind == "tool/call":
            arguments = _arguments(data.get("arguments"))
            name = str(data.get("name") or "tool")
            call = Action(
                label(name, arguments),
                "tool",
                at,
                at,
                {"tool": name, "input": truncate(arguments)},
            )
            pending[str(data.get("callId"))] = call
            actions.append(call)
            prev = max(prev, at)
        elif kind == "tool/result":
            identifier, output, failed = _tool_result(data)
            call = pending.pop(identifier, None)
            if call is not None:
                call.end = max(call.start, at)
                call.args["output"] = truncate(output)
                call.args["error"] = failed
                if data.get("error") is not None:
                    call.args["failure"] = truncate(data["error"], 512)
            prev = max(prev, at)
        elif kind == "step/end":
            step = steps.get((data.get("turn"), data.get("step")))
            if step is not None and step.end <= step.start:
                step.end = max(step.start, at)
            prev = max(prev, at)
        elif kind == "turn/end":
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                turn.args["reason"] = truncate(data.get("reason"), 512)
                actions.append(turn)
                turn = None
            prev = max(prev, at)

    closing = max((action.end for action in actions), default=prev)
    for call in pending.values():
        call.end = max(call.start, closing)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, closing)
        actions.append(turn)
    return actions, info


def _message(
    actions: list[Action],
    data: dict[str, Any],
    at: float,
    prev: float,
    steps: dict[tuple[object, object], Action],
    info: dict[str, Any],
) -> float:
    """Records a finalized assistant message and returns the new time cursor."""
    message = mapping(data.get("message"))
    source = mapping(message.get("source"))
    if info.get("provider") is None and source.get("provider") is not None:
        info["provider"] = source["provider"]
    if info.get("model") is None and source.get("model") is not None:
        info["model"] = source["model"]
    key = (data.get("turn"), data.get("step"))
    think = steps.get(key)
    if think is None:
        think = Action(
            "think",
            "llm",
            prev,
            at,
            {"turn": data.get("turn"), "step": data.get("step")},
        )
        steps[key] = think
        actions.append(think)
    think.end = max(think.end, at)
    if data.get("usage") is not None:
        think.args["usage"] = truncate(data["usage"])
    if source:
        think.args["source"] = truncate(source)

    content = message.get("content", data.get("content"))
    blocks = cast("list[Any]", content) if isinstance(content, list) else []
    spoken: list[str] = []
    reasoned: list[str] = []
    for raw in blocks:
        block = mapping(raw)
        body = block.get("text")
        if not isinstance(body, str) or not body:
            continue
        if block.get("type") == "reasoning":
            reasoned.append(body)
        elif block.get("type") == "text":
            spoken.append(body)
    if reasoned:
        reasoning = "\n".join(reasoned)
        think.name = f"think: {summarize(reasoning)}"
        think.args["thinking"] = truncate(reasoning)
    if spoken:
        body = "".join(spoken)
        actions.append(
            Action(
                f"say: {summarize(body)}",
                "message",
                at,
                at,
                {"text": truncate(body)},
            )
        )
    return max(prev, at)


def _arguments(value: Any) -> Any:
    """Reads a tool's JSON arguments while preserving non-JSON input verbatim."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _tool_result(data: dict[str, Any]) -> tuple[str, str, bool]:
    """Extracts the call id, readable output and failure flag from a tool result."""
    message = mapping(data.get("message"))
    source = mapping(message.get("source"))
    identifier = str(source.get("callId") or "")
    output: list[str] = []
    failed = bool(data.get("error"))
    content = message.get("content")
    for raw in cast("list[Any]", content) if isinstance(content, list) else []:
        block = mapping(raw)
        if block.get("type") != "tool-result":
            continue
        identifier = str(block.get("toolCallId") or identifier)
        body = text_of(block.get("content"))
        if body:
            output.append(body)
        failed = failed or bool(block.get("isError"))
    return identifier, "\n".join(output), failed
