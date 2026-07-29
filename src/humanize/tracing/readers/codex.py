"""Collector for Codex rollout logs."""

from __future__ import annotations

import datetime
import json
import pathlib
from typing import Any

from humanize.tracing.session import (
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

_META_FIELDS = (
    "cwd",
    "cli_version",
    "originator",
    "agent_path",
    "agent_nickname",
    "git",
)
_TURN_FIELDS = ("model", "effort", "approval_policy", "sandbox_policy")


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Codex threads and sub-agent threads asked for.

    Args:
        home: Codex home directory holding the rollout folders.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Thread ids to keep, or None to keep every thread. A kept
            thread pulls in the sub-agent threads it started.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per rollout, with sub-agent threads linked to their spawner.
    """
    metas: dict[str, tuple[pathlib.Path, dict[str, Any]]] = {}
    for path in sorted(home.glob("**/rollout-*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as stream:
            head = stream.readline()
        try:
            record: dict[str, Any] = json.loads(head)
        except json.JSONDecodeError:
            continue
        payload = mapping(record.get("payload"))
        if record.get("type") != "session_meta" or (
            workspace is not None and pathlib.Path(str(payload.get("cwd"))) != workspace
        ):
            continue
        metas[str(payload.get("id"))] = (path, payload)

    kept = {ident for ident in metas if wanted(sessions, f"codex:{ident}")}
    frontier = kept
    while frontier:
        frontier = {
            ident
            for ident, (_, payload) in metas.items()
            if payload.get("parent_thread_id") in frontier
        } - kept
        kept |= frontier
    metas = {ident: entry for ident, entry in metas.items() if ident in kept}

    spawns: dict[tuple[str, str], str] = {}
    for ident, (_, payload) in metas.items():
        parent, agent_path = payload.get("parent_thread_id"), payload.get("agent_path")
        if isinstance(parent, str) and isinstance(agent_path, str):
            spawns[(parent, agent_path.rsplit("/", 1)[-1])] = f"codex:{ident}"

    collected: list[Session] = []
    for ident, (path, payload) in metas.items():
        actions, info = _parse(path, window, ident, spawns)
        name = payload.get("agent_path") or payload.get("agent_nickname")
        ancestor = payload.get("parent_thread_id")
        collected.append(
            Session(
                key=f"codex:{ident}",
                backend="codex",
                ident=ident,
                label=str(name) if name else "main",
                title=title_of(ident[:8], actions),
                parent=f"codex:{ancestor}"
                if isinstance(ancestor, str) and ancestor != ident
                else None,
                args={
                    "log": str(path),
                    **{k: payload.get(k) for k in _META_FIELDS},
                    **info,
                },
                actions=actions,
            )
        )
    return collected


def _parse(
    path: pathlib.Path,
    window: tuple[float, float],
    ident: str,
    spawns: dict[tuple[str, str], str],
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one rollout into prompt, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    turn: Action | None = None
    think: Action | None = None
    prev = 0.0
    for record in records(path):
        stamp = record.get("timestamp")
        if not isinstance(stamp, str):
            continue
        at = datetime.datetime.fromisoformat(stamp).timestamp()
        if not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        payload = mapping(record.get("payload"))
        kind, item = record.get("type"), payload.get("type")

        if kind == "turn_context":
            info.update({field: payload.get(field) for field in _TURN_FIELDS})
        elif item == "task_started":
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
            turn = Action("turn", "turn", at, at, {"turn_id": payload.get("turn_id")})
            think = None
        elif item == "user_message":
            body = str(payload.get("message") or "")
            if turn is None:
                turn = Action("turn", "turn", at, at, {})
            turn.name = f"turn: {summarize(body)}"
            turn.args["prompt"] = truncate(body)
        elif item in ("task_complete", "turn_aborted"):
            if turn is not None:
                turn.args["result"] = truncate(
                    payload.get("last_agent_message") or payload.get("reason")
                )
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
            turn, think = None, None
        elif item == "reasoning":
            body = text_of(payload.get("summary"))
            if think is None:
                think = Action("think", "llm", prev, at, {})
                actions.append(think)
            think.end = max(think.end, at)
            if body:
                think.args["reasoning"] = truncate(
                    f"{think.args.get('reasoning', '')}\n{body}".strip()
                )
                think.name = f"think: {summarize(body)}"
            prev = at
        elif item == "agent_reasoning" and think is not None:
            body = str(payload.get("text") or "")
            think.args["reasoning"] = truncate(
                f"{think.args.get('reasoning', '')}\n{body}".strip()
            )
            think.name = f"think: {summarize(body)}"
            think.end = max(think.end, at)
            prev = max(prev, at)
        elif item == "token_count" and think is not None:
            counts = payload.get("info")
            if isinstance(counts, dict):
                think.args["usage"] = mapping(counts).get("last_token_usage")
        else:
            prev, think = _add_event(
                actions, kind, item, payload, at, prev, think, pending, ident, spawns
            )
    prev = max((action.end for action in actions), default=prev)
    for call in pending.values():
        call.end = max(call.start, prev)
        call.args["unfinished"] = True
    if turn is not None:
        turn.end = max(turn.end, prev)
        actions.append(turn)
    return actions, info


def _add_event(
    actions: list[Action],
    kind: Any,
    item: Any,
    payload: dict[str, Any],
    at: float,
    prev: float,
    think: Action | None,
    pending: dict[str, Action],
    ident: str,
    spawns: dict[tuple[str, str], str],
) -> tuple[float, Action | None]:
    """Records one non-reasoning rollout entry and returns the new cursor."""
    if item == "agent_message" and kind == "event_msg":
        body = str(payload.get("message") or "")
        actions.append(
            Action(
                f"say: {summarize(body)}", "message", prev, at, {"text": truncate(body)}
            )
        )
        return at, None
    if item == "agent_message" and kind == "response_item":
        recipient = payload.get("recipient")
        actions.append(
            Action(
                f"send: {recipient}",
                "message",
                prev,
                at,
                {
                    "author": payload.get("author"),
                    "recipient": recipient,
                    "text": truncate(text_of(payload.get("content"))),
                },
            )
        )
        return at, None
    if item in ("function_call", "custom_tool_call"):
        name = str(payload.get("name") or "tool")
        raw = (
            payload.get("arguments")
            if item == "function_call"
            else payload.get("input")
        )
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            parsed = raw
        target = mapping(parsed).get("task_name")
        if at > prev and not pending:
            actions.append(Action("generate", "llm", prev, at, {"emits": name}))
        call = Action(
            label(name, parsed),
            "tool",
            at,
            at,
            {
                "tool": name,
                "namespace": payload.get("namespace"),
                "input": truncate(parsed),
            },
            spawns.get((ident, str(target))),
        )
        pending[str(payload.get("call_id"))] = call
        actions.append(call)
        return max(prev, at), None
    if item in ("function_call_output", "custom_tool_call_output"):
        answered = pending.pop(str(payload.get("call_id")), None)
        if answered is not None:
            answered.end = at
            answered.args["output"] = truncate(text_of(payload.get("output")))
        return max(prev, at), think
    if item == "web_search_call":
        action = mapping(payload.get("action"))
        actions.append(
            Action(
                f"web_search: {summarize(str(action.get('query') or ''))}",
                "tool",
                prev,
                at,
                {"tool": "web_search", "input": truncate(action)},
            )
        )
        return at, None
    if item == "patch_apply_end":
        changes = mapping(payload.get("changes"))
        actions.append(
            Action(
                f"apply_patch: {summarize(', '.join(changes))}",
                "tool",
                prev,
                at,
                truncate(
                    {
                        "changes": changes,
                        "stdout": payload.get("stdout"),
                        "success": payload.get("success"),
                    },
                    512,
                ),
            )
        )
        return at, None
    if item == "sub_agent_activity":
        actions.append(
            Action(
                f"agent {payload.get('kind')}: {payload.get('agent_path')}",
                "event",
                at,
                at,
                truncate(payload),
            )
        )
        return max(prev, at), think
    if kind == "compacted" or item == "context_compacted":
        actions.append(Action("system: context_compacted", "event", at, at, {}))
        return max(prev, at), think
    return prev, think
