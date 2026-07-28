"""Collector for Claude Code transcripts."""

from __future__ import annotations

import datetime
import json
import re
from typing import TYPE_CHECKING, Any, cast

from .session import (
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

if TYPE_CHECKING:
    import pathlib

_INFO_FIELDS = ("cwd", "version", "gitBranch", "sessionId")
_SYSTEM_FIELDS = (
    "subtype",
    "content",
    "level",
    "durationMs",
    "compactMetadata",
    "hookInfos",
)


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Claude sessions and sub-agent transcripts asked for.

    Args:
        home: Claude configuration directory holding the projects folder.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session. A kept
            session pulls in the sub-agents it started.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per transcript, with sub-agents linked to their spawner.
    """
    projects = home / "projects"
    folder = "*" if workspace is None else re.sub(r"[^a-zA-Z0-9]", "-", str(workspace))
    logs: list[tuple[str, str, pathlib.Path, dict[str, Any]]] = []
    spawns: dict[str, str] = {}
    for path in sorted(projects.glob(f"{folder}/*.jsonl")):
        key = f"claude:{path.stem}"
        if wanted(sessions, key):
            logs.append((key, path.stem, path, {}))
    for path in sorted(projects.glob(f"{folder}/*/subagents/**/*.jsonl")):
        if path.name == "journal.jsonl":
            continue
        parts = path.relative_to(projects).parts[1:]
        root = f"claude:{parts[0]}"
        key = f"{root}:{path.stem}"
        if not wanted(sessions, key, path.stem.removeprefix("agent-")):
            continue
        meta_path = path.with_suffix(".meta.json")
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = json.loads(
                    meta_path.read_text(encoding="utf-8", errors="replace")
                )
            except json.JSONDecodeError:
                meta = {}
        name = str(meta.get("agentType") or "subagent")
        if meta.get("description"):
            name = f"{name} · {meta['description']}"
        if "workflows" in parts:
            name = f"{parts[parts.index('workflows') + 1]} · {name}"
        meta["label"] = name
        if isinstance(meta.get("toolUseId"), str):
            spawns[meta["toolUseId"]] = key
        logs.append((key, parts[0], path, meta))

    collected: list[Session] = []
    for key, ident, path, meta in logs:
        actions, info = _parse(path, window, spawns)
        root = f"claude:{ident}"
        short = path.stem.removeprefix("agent-")[:8]
        title = (
            f"{short} · {info['title']}"
            if info.get("title")
            else title_of(short, actions)
        )
        collected.append(
            Session(
                key=key,
                backend="claude",
                ident=ident,
                label="main" if key == root else str(meta.get("label")),
                title=title,
                parent=None if key == root else root,
                args={
                    "log": str(path),
                    **info,
                    **{k: v for k, v in meta.items() if k != "label"},
                },
                actions=actions,
            )
        )
    by_key = {item.key: item for item in collected}
    for owner in collected:
        for action in owner.actions:
            child = by_key.get(action.spawn or "")
            if child is not None:
                child.parent = owner.key
    return collected


def _parse(
    path: pathlib.Path, window: tuple[float, float], spawns: dict[str, str]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one transcript into prompt, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    turn: Action | None = None
    think: Action | None = None
    request: str | None = None
    prev = 0.0
    for record in records(path):
        stamp = record.get("timestamp")
        if not isinstance(stamp, str):
            continue
        at = datetime.datetime.fromisoformat(stamp).timestamp()
        if not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        for field in _INFO_FIELDS:
            if record.get(field) is not None:
                info[field] = record[field]
        if isinstance(record.get("aiTitle"), str):
            info["title"] = record["aiTitle"]
        message = mapping(record.get("message"))
        content = message.get("content")
        blocks: list[dict[str, Any]] = (
            [
                cast("dict[str, Any]", block)
                for block in cast("list[Any]", content)
                if isinstance(block, dict)
            ]
            if isinstance(content, list)
            else []
        )
        kind = record.get("type")

        if kind == "user" and any(
            block.get("type") == "tool_result" for block in blocks
        ):
            for block in blocks:
                call = pending.pop(str(block.get("tool_use_id")), None)
                if call is None:
                    continue
                call.end = at
                call.args["output"] = truncate(text_of(block.get("content")))
                call.args["error"] = bool(block.get("is_error"))
                if isinstance(record.get("toolUseResult"), dict):
                    call.args["result"] = truncate(record["toolUseResult"], 512)
            prev = max(prev, at)
        elif kind == "user":
            prompt = text_of(content)
            if turn is not None and turn.args.get("prompt_id") == record.get(
                "promptId"
            ):
                turn.args["prompt"] = truncate(
                    f"{turn.args['prompt']}\n{prompt}".strip()
                )
                turn.name = f"turn: {summarize(str(turn.args['prompt']))}"
            else:
                if turn is not None:
                    turn.end = max(turn.end, prev, at)
                    actions.append(turn)
                turn = Action(
                    f"turn: {summarize(prompt)}",
                    "turn",
                    at,
                    at,
                    {"prompt_id": record.get("promptId"), "prompt": truncate(prompt)},
                )
                request, think = None, None
            prev = max(prev, at)
        elif kind == "assistant":
            model = message.get("model")
            # Only the answers say what answered them, and Claude lets a session change model
            # mid-conversation, so the first answer is taken: what the session opened at.
            # `<synthetic>` names an answer Claude wrote for itself, such as an API error,
            # rather than a model, and would otherwise take a session with it.
            if "model" not in info and isinstance(model, str) and model[:1] != "<":
                info["model"] = model
                if record.get("effort") is not None:
                    info["effort"] = record["effort"]
            identifier = record.get("requestId") or message.get("id")
            if identifier != request:
                request = str(identifier)
                think = Action(
                    "think",
                    "llm",
                    prev,
                    at,
                    {"model": model, "usage": message.get("usage")},
                )
                actions.append(think)
                prev = at
            for block in blocks:
                prev = _add_block(actions, block, at, prev, think, pending, spawns)
        elif kind == "system":
            details = {key: record[key] for key in _SYSTEM_FIELDS if key in record}
            actions.append(
                Action(
                    f"system: {record.get('subtype')}",
                    "event",
                    at,
                    at,
                    truncate(details, 512),
                )
            )
            prev = max(prev, at)

    closing = max((action.end for action in actions), default=prev)
    for call in pending.values():
        call.end = max(call.start, closing)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, closing)
        actions.append(turn)
    return actions, info


def _add_block(
    actions: list[Action],
    block: dict[str, Any],
    at: float,
    prev: float,
    think: Action | None,
    pending: dict[str, Action],
    spawns: dict[str, str],
) -> float:
    """Records one assistant content block and returns the new cursor time."""
    kind = block.get("type")
    if kind == "thinking" and think is not None:
        reasoning = str(block.get("thinking") or "")
        if reasoning:
            think.args["thinking"] = truncate(
                f"{think.args.get('thinking', '')}\n{reasoning}".strip()
            )
            think.name = f"think: {summarize(reasoning)}"
        think.end = max(think.end, at)
        return max(prev, at)
    if kind == "text":
        body = str(block.get("text") or "")
        actions.append(
            Action(
                f"say: {summarize(body)}", "message", prev, at, {"text": truncate(body)}
            )
        )
        return at
    if kind == "tool_use":
        identifier = str(block.get("id"))
        if at > prev and not pending:
            actions.append(
                Action("generate", "llm", prev, at, {"emits": block.get("name")})
            )
        call = Action(
            label(str(block.get("name")), block.get("input")),
            "tool",
            at,
            at,
            {"tool": block.get("name"), "input": truncate(block.get("input"))},
            spawns.get(identifier),
        )
        pending[identifier] = call
        actions.append(call)
        return max(prev, at)
    return prev
