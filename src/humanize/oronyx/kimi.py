"""Collector for Kimi Code wire logs."""

from __future__ import annotations

import json
import pathlib
from typing import Any

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

_STEP_FIELDS = (
    "usage",
    "finishReason",
    "llmFirstTokenLatencyMs",
    "llmStreamDurationMs",
)


def collect(
    home: pathlib.Path,
    workspace: pathlib.Path | None,
    sessions: tuple[str, ...] | None,
    window: tuple[float, float],
) -> list[Session]:
    """Collects the Kimi Code sessions and sub-agent wires asked for.

    Args:
        home: Kimi Code home directory holding the sessions folder.
        workspace: Absolute path of the workspace to collect trajectories for,
            or None to search every workspace.
        sessions: Session ids to keep, or None to keep every session. A kept
            session pulls in the agents that ran under it.
        window: Inclusive epoch second bounds used to cut off records.

    Returns:
        One session per agent wire, with sub-agents linked to their parent.
    """
    collected: list[Session] = []
    for state_path in sorted(home.glob("sessions/*/session_*/state.json")):
        try:
            state: dict[str, Any] = json.loads(
                state_path.read_text(encoding="utf-8", errors="replace")
            )
        except json.JSONDecodeError:
            continue
        if (
            workspace is not None
            and pathlib.Path(str(state.get("workDir"))) != workspace
        ):
            continue
        ident = state_path.parent.name
        agents = mapping(state.get("agents"))
        for agent_id, entry in sorted(agents.items()):
            key = f"kimi:{ident}:{agent_id}"
            if not wanted(sessions, key, ident.removeprefix("session_")):
                continue
            details = mapping(entry)
            wire = pathlib.Path(str(details.get("homedir") or "")) / "wire.jsonl"
            if not wire.is_file():
                wire = state_path.parent / "agents" / str(agent_id) / "wire.jsonl"
            if not wire.is_file():
                continue
            actions, info = _parse(wire, window)
            parent = details.get("parentAgentId")
            collected.append(
                Session(
                    key=key,
                    backend="kimi",
                    # Every agent of a session shares the id `kimi -r` resumes it by.
                    ident=ident,
                    label="main"
                    if agent_id == "main"
                    else f"{details.get('type') or 'agent'} · {agent_id}",
                    title=f"{ident[8:16]} · {state['title']}"
                    if state.get("title")
                    else title_of(ident[8:16], actions),
                    parent=f"kimi:{ident}:{parent}"
                    if isinstance(parent, str)
                    else None,
                    args={"log": str(wire), "work_dir": state.get("workDir"), **info},
                    actions=actions,
                )
            )
    return collected


def _parse(
    path: pathlib.Path, window: tuple[float, float]
) -> tuple[list[Action], dict[str, Any]]:
    """Turns one wire log into prompt, reasoning, tool and message slices."""
    actions: list[Action] = []
    info: dict[str, Any] = {}
    pending: dict[str, Action] = {}
    steps: dict[str, Action] = {}
    turn: Action | None = None
    step: Action | None = None
    prev = 0.0
    for record in records(path):
        moment = record.get("time")
        if not isinstance(moment, (int, float)):
            continue
        at = float(moment) / 1000.0
        if not window[0] <= at <= window[1]:
            continue
        prev = prev or at
        kind = record.get("type")

        if kind == "llm.request":
            info.update(
                {
                    "model": record.get("modelAlias"),
                    "effort": record.get("thinkingEffort"),
                }
            )
        elif kind == "config.update":
            info["profile"] = record.get("profileName")
        elif kind == "permission.set_mode":
            actions.append(
                Action(f"system: permission {record.get('mode')}", "event", at, at, {})
            )
        elif kind in ("turn.prompt", "turn.cancel"):
            if turn is not None:
                turn.end = max(turn.end, prev, at)
                actions.append(turn)
                turn = None
            if kind == "turn.prompt":
                body = text_of(record.get("input"))
                turn = Action(
                    f"turn: {summarize(body)}",
                    "turn",
                    at,
                    at,
                    {"prompt": truncate(body), "origin": record.get("origin")},
                )
            prev, step = max(prev, at), None
        elif kind == "context.append_loop_event":
            event = mapping(record.get("event"))
            prev, step = _add_event(actions, event, at, prev, step, steps, pending)

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
    event: dict[str, Any],
    at: float,
    prev: float,
    step: Action | None,
    steps: dict[str, Action],
    pending: dict[str, Action],
) -> tuple[float, Action | None]:
    """Records one loop event and returns the new cursor and open step."""
    kind = event.get("type")
    if kind == "step.begin":
        opened = Action(
            "think",
            "llm",
            at,
            at,
            {"step": event.get("step"), "turn": event.get("turnId")},
        )
        steps[str(event.get("uuid"))] = opened
        actions.append(opened)
        return max(prev, at), opened
    if kind == "step.end":
        ended = steps.get(str(event.get("uuid")))
        if ended is not None:
            if ended.end <= ended.start:
                ended.end = at
            ended.args.update({field: event.get(field) for field in _STEP_FIELDS})
        return max(prev, at), None
    if kind == "content.part":
        part = mapping(event.get("part"))
        body = str(part.get("think") or part.get("text") or "")
        if part.get("type") == "think":
            target = steps.get(str(event.get("stepUuid")), step)
            if target is None:
                target = Action("think", "llm", prev, at, {})
                actions.append(target)
            target.end = max(target.end, at)
            target.name = f"think: {summarize(body)}"
            target.args["thinking"] = truncate(
                f"{target.args.get('thinking', '')}\n{body}".strip()
            )
        else:
            actions.append(
                Action(
                    f"say: {summarize(body)}",
                    "message",
                    prev,
                    at,
                    {"text": truncate(body)},
                )
            )
        return at, None
    if kind == "tool.call":
        if step is not None:
            step.end = max(step.end, at)
        name = str(event.get("name") or "tool")
        call = Action(
            label(name, event.get("args")),
            "tool",
            at,
            at,
            {
                "tool": name,
                "description": event.get("description"),
                "input": truncate(event.get("args")),
            },
        )
        pending[str(event.get("toolCallId"))] = call
        actions.append(call)
        return max(prev, at), None
    if kind == "tool.result":
        answered = pending.pop(str(event.get("toolCallId")), None)
        if answered is not None:
            result = mapping(event.get("result"))
            answered.end = at
            answered.args["output"] = truncate(text_of(result.get("output")))
            answered.args["error"] = bool(result.get("isError"))
        return max(prev, at), step
    return prev, step
