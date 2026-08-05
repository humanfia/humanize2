"""Chrome trace rendering of collected agent sessions."""

from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING, Any

from .profile import Thread as _Thread
from .session import Action, Session, summarize

if TYPE_CHECKING:
    import pathlib

    from .profile import Process

#: What a reader of these logs joins the halves of a name with, which is what a track of one
#: kind of sub-agent is named off the front of.
_DOT = " · "

#: How many session ids a trace says outright before it says how many there were instead.
#: Every process of a trace carries this label, so it is read far more often than it is long.
_NAMEABLE = 4

_LANE_STRIDE = 100


def build(
    sessions: list[Session],
    workspace: pathlib.Path | None,
    names: tuple[str, ...] | None,
    profiled: list[Process] | None = None,
) -> dict[str, Any]:
    """Renders sessions as a Chrome JSON trace with one process per agent.

    One process is one agent and everything it drove; one track is one of that
    agent's sub-agents. Sessions of the same agent that never run at the same
    time share a track, so a loop of one-shot sessions and a burst of short
    lived sub-agents both read as one dense band instead of a staircase of near
    empty rows. Root sessions and sub-agents are kept on separate tracks, and
    actions that do overlap spill into extra lanes.

    A profiled run brings the programs its agents started, and they are drawn
    the same way: one process per program, one track per thread of it. Which is
    the point of putting them in one document -- an agent's turn is mostly
    other programs, and on one timeline the question of what a run was doing at
    a given moment has one answer rather than two.

    Args:
        sessions: Sessions collected from every agent.
        workspace: Workspace the sessions were collected for, if any.
        names: Session ids the collection was narrowed to, if any.
        profiled: Programs the run started while it ran, if it was profiled.

    Returns:
        A Chrome trace document ready to be serialized as JSON.
    """
    scope: dict[str, str] = {}
    if workspace is not None:
        scope["workspace"] = str(workspace)
    if names:
        # A handful of ids is what somebody asked for, said back to them; a run's worth of
        # them is a label nobody can read, and how many there were is the whole of what it
        # would have told them anyway.
        scope["selected"] = (
            ", ".join(names) if len(names) <= _NAMEABLE else f"{len(names)} sessions"
        )
    label = " · ".join(scope.values())
    live = [item for item in sessions if item.actions]
    ran = list(profiled or ())
    if not live and not ran:
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
        groups, key=lambda agent: min(spans[item.key][0] for item in groups[agent])
    )
    for pid, agent in enumerate(order, start=1):
        members = groups[agent]
        events.append(
            _meta(
                pid, 0, "process_name", {"name": f"{agent} · {len(members)} sessions"}
            )
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
            stem = _stem(depth, row)
            entries: list[tuple[Session, Action]] = []
            for item in row:
                start, finish = spans[item.key]
                banner = Action(
                    summarize(f"{item.label} · {item.title}", 120),
                    "session",
                    start,
                    finish,
                    {**item.args, "agent": item.agent, "parent": item.parent},
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

    _programs(events, ran, len(order) + 1, label)
    began = [start for start, _ in spans.values()] + [one.began for one in ran]
    over = [finish for _, finish in spans.values()] + [one.ended for one in ran]
    held = {
        **scope,
        "agents": ", ".join(sorted({item.agent for item in live})),
        "backends": ", ".join(sorted({item.backend for item in live})),
        "sessions": str(len(live)),
        "slices": str(sum(len(item.actions) for item in live)),
        "tracks": str(sum(1 for event in events if event["name"] == "thread_name")),
        "start": _stamp(min(began)),
        "end": _stamp(max(over)),
    }
    if ran:
        # Said only where there is a profile: an `otherData` that reported nought programs
        # on every trace would be one more thing to read past on the traces that are only
        # ever sessions.
        held["programs"] = str(len(ran))
    return {
        "traceEvents": events,
        "displayTimeUnit": "ms",
        "otherData": held,
    }


def _programs(
    events: list[dict[str, Any]], ran: list[Process], first: int, label: str
) -> None:
    """Draws the programs a profiled run started, the way the agents themselves are drawn.

    One process apiece and one track per thread, which is the same shape as one agent and
    its sub-agents -- that is the whole point of one document: a turn is mostly other
    programs, and a timeline with the turns on it and not what they ran is a timeline that
    stops exactly where the time went.

    Args:
        events: What has been drawn so far, appended to.
        ran: The programs, oldest first.
        first: The first process id to give them, after the agents' own.
        label: What every process of this trace is labelled with.
    """
    for pid, one in enumerate(sorted(ran, key=lambda one: (one.began, one.pid)), first):
        events.append(_meta(pid, 0, "process_name", {"name": one.label}))
        events.append(_meta(pid, 0, "process_sort_index", {"sort_index": pid}))
        events.append(_meta(pid, 0, "process_labels", {"labels": label}))
        threads = one.threads or (_Thread(one.pid, one.began, one.ended, 0.0),)
        for at, thread in enumerate(threads):
            tid = (at + 1) * _LANE_STRIDE
            # The thread that ran `main` is the one the process is named after; the rest are
            # its own, and are named as the operating system names them.
            named = "main" if thread.tid == one.pid else f"thread {thread.tid}"
            events.append(_meta(pid, tid, "thread_name", {"name": named}))
            events.append(_meta(pid, tid, "thread_sort_index", {"sort_index": tid}))
            events.append(
                {
                    "ph": "X",
                    "pid": pid,
                    "tid": tid,
                    "cat": "process",
                    "name": one.label if named == "main" else named,
                    "ts": round(thread.began * 1e6),
                    "dur": max(round((thread.ended - thread.began) * 1e6), 1),
                    "args": {
                        "pid": one.pid,
                        "ppid": one.ppid,
                        "argv": " ".join(one.argv),
                        "cpu": round(thread.cpu, 3),
                        "at": _stamp(thread.began),
                    },
                }
            )


def _stem(depth: int, row: list[Session]) -> str:
    """What one track of an agent's process is called.

    A track is a sub-agent, so it is named after the sub-agent it holds: the backends say
    what kind each was -- what a Claude sub-agent was started as, what a Codex thread is for
    -- and a row of five explorations reads better as `subagent · explore` than as
    `subagent #2`. The agent's own sessions are `main`, being the conversations somebody
    started rather than anything a turn reached for.

    Args:
        depth: How far under a root session this row is.
        row: The sessions packed into it.

    Returns:
        The name, without the number that tells two rows of one kind apart.
    """
    if depth == 0:
        return "main"
    stem = "subagent" if depth == 1 else f"subagent {depth}"
    # What kind of sub-agent rather than which one: a label says what it was started as and
    # then what that one was for, and a track is the first half of that -- five explorations
    # are one track called `explore` rather than five names run together.
    kinds = {
        item.label.split(_DOT)[0].strip()
        for item in row
        if item.label and item.label != "main"
    }
    return f"{stem} · {kinds.pop()}" if len(kinds) == 1 else stem


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
