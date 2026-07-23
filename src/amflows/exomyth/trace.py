"""Chrome trace rendering of collected agent sessions."""

from __future__ import annotations

import datetime
import math
import pathlib
from typing import Any

from .session import Action, Session, summarize

_LANE_STRIDE = 100


def build(
    sessions: list[Session],
    workspace: pathlib.Path | None,
    names: tuple[str, ...] | None,
) -> dict[str, Any]:
    """Renders sessions as a Chrome JSON trace with one process per agent.

    Sessions of the same agent that never run at the same time share a track, so
    a loop of one-shot sessions and a burst of short lived sub-agents both read
    as one dense band instead of a staircase of near empty rows. Root sessions
    and sub-agents are kept on separate tracks, and actions that do overlap
    spill into extra lanes.

    Args:
        sessions: Sessions collected from every agent.
        workspace: Workspace the sessions were collected for, if any.
        names: Session ids the collection was narrowed to, if any.

    Returns:
        A Chrome trace document ready to be serialized as JSON.
    """
    scope: dict[str, str] = {}
    if workspace is not None:
        scope["workspace"] = str(workspace)
    if names:
        scope["selected"] = ", ".join(names)
    label = " · ".join(scope.values())
    live = [item for item in sessions if item.actions]
    if not live:
        return {"traceEvents": [], "displayTimeUnit": "ms", "otherData": scope}
    spans = {
        item.key: (
            min(action.start for action in item.actions),
            max(action.end for action in item.actions),
        )
        for item in live
    }
    known = {item.key: item for item in live}
    depths: dict[str, int] = {}
    for item in live:
        depth, cursor, seen = 0, item, {item.key}
        while cursor.parent in known and cursor.parent not in seen:
            cursor = known[cursor.parent]
            seen.add(cursor.key)
            depth += 1
        depths[item.key] = depth if cursor.parent is None else depth + 1
    groups: dict[str, list[Session]] = {}
    for item in live:
        groups.setdefault(item.agent, []).append(item)

    events: list[dict[str, Any]] = []
    tracks: dict[str, tuple[int, int]] = {}
    origins: dict[str, tuple[int, int, float]] = {}
    order = sorted(
        groups, key=lambda name: min(spans[item.key][0] for item in groups[name])
    )
    for pid, name in enumerate(order, start=1):
        members = groups[name]
        events.append(
            _meta(pid, 0, "process_name", {"name": f"{name} · {len(members)} sessions"})
        )
        events.append(_meta(pid, 0, "process_sort_index", {"sort_index": pid}))
        events.append(_meta(pid, 0, "process_labels", {"labels": label}))
        rows: list[list[Session]] = []
        shape: list[tuple[int, float]] = []
        for item in sorted(
            members, key=lambda item: (depths[item.key], spans[item.key][0], item.key)
        ):
            depth, (start, finish) = depths[item.key], spans[item.key]
            index = next(
                (
                    at
                    for at, (level, free) in enumerate(shape)
                    if level == depth and free <= start
                ),
                len(rows),
            )
            if index == len(rows):
                rows.append([])
                shape.append((depth, -math.inf))
            rows[index].append(item)
            shape[index] = (depth, finish)
        for ordinal, row in enumerate(rows):
            depth = shape[ordinal][0]
            rank = sum(1 for level, _ in shape[:ordinal] if level == depth) + 1
            stem = (
                "main"
                if depth == 0
                else "subagent"
                if depth == 1
                else f"subagent {depth}"
            )
            entries: list[tuple[Session, Action]] = []
            for item in row:
                start, finish = spans[item.key]
                banner = Action(
                    summarize(f"{item.label} · {item.title}", 120),
                    "session",
                    start,
                    finish,
                    {**item.args, "parent": item.parent},
                )
                entries.append((item, banner))
                entries.extend((item, action) for action in item.actions)
            _render(
                events,
                entries,
                pid,
                (ordinal + 1) * _LANE_STRIDE,
                stem if rank == 1 else f"{stem} #{rank}",
                tracks,
                origins,
            )

    for key, (pid, tid, at) in sorted(origins.items()):
        target = tracks.get(key)
        if target is None:
            continue
        flow = len(events)
        shared = {"cat": "spawn", "name": "spawn", "id": flow}
        events.append(
            {"ph": "s", "pid": pid, "tid": tid, "ts": round(at * 1e6), **shared}
        )
        events.append(
            {
                "ph": "f",
                "bp": "e",
                "pid": target[0],
                "tid": target[1],
                "ts": round(spans[key][0] * 1e6),
                **shared,
            }
        )

    return {
        "traceEvents": events,
        "displayTimeUnit": "ms",
        "otherData": {
            **scope,
            "agents": ", ".join(sorted({item.agent for item in live})),
            "sessions": str(len(live)),
            "slices": str(sum(len(item.actions) for item in live)),
            "tracks": str(sum(1 for event in events if event["name"] == "thread_name")),
            "start": _stamp(min(start for start, _ in spans.values())),
            "end": _stamp(max(finish for _, finish in spans.values())),
        },
    }


def _render(
    events: list[dict[str, Any]],
    entries: list[tuple[Session, Action]],
    pid: int,
    base: int,
    name: str,
    tracks: dict[str, tuple[int, int]],
    origins: dict[str, tuple[int, int, float]],
) -> None:
    """Packs one row of sessions into nested lanes and emits its trace events."""
    lanes: list[list[float]] = []
    for item, action in sorted(
        entries, key=lambda entry: (entry[1].start, -entry[1].end)
    ):
        lane = 0
        while lane < len(lanes):
            stack = lanes[lane]
            while stack and stack[-1] <= action.start:
                stack.pop()
            if not stack or stack[-1] >= action.end:
                break
            lane += 1
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append(action.end)
        events.append(
            {
                "ph": "X",
                "pid": pid,
                "tid": base + lane,
                "cat": action.category,
                "name": action.name,
                "ts": round(action.start * 1e6),
                "dur": max(round((action.end - action.start) * 1e6), 1),
                "args": {
                    **action.args,
                    "at": _stamp(action.start),
                    "session": item.key,
                },
            }
        )
        if action.category == "session":
            tracks[item.key] = (pid, base + lane)
        if action.spawn:
            origins[action.spawn] = (pid, base + lane, action.start)
    for lane in range(len(lanes)):
        label = name if lane == 0 else f"{name} ~{lane + 1}"
        events.append(_meta(pid, base + lane, "thread_name", {"name": label}))
        events.append(
            _meta(pid, base + lane, "thread_sort_index", {"sort_index": base + lane})
        )


def _meta(pid: int, tid: int, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Builds one Chrome trace metadata event."""
    return {"ph": "M", "pid": pid, "tid": tid, "name": name, "args": args}


def _stamp(at: float) -> str:
    """Formats an epoch second value as an ISO 8601 UTC timestamp."""
    return datetime.datetime.fromtimestamp(at, datetime.UTC).isoformat()
