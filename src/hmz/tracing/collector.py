"""Aggregation of the agent trajectories a trace was asked for."""

from __future__ import annotations

import json
import math
import os
import pathlib
from typing import TYPE_CHECKING, Any

import dateparser

from hmz import backends

from . import chrome
from .readers import claude, codex, dsh, kimi

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .session import Session

#: Which reader reads which backend's logs. Where those logs are, and in what order the
#: backends are gone through, is :mod:`hmz.backends`.
_READERS = {
    "claude": claude.collect,
    "codex": codex.collect,
    "dsh": dsh.collect,
    "kimi": kimi.collect,
}


def collect(
    workspace: str | os.PathLike[str] | None = None,
    *,
    sessions: str | Iterable[str] | None = None,
    agents: Mapping[str, Iterable[str]] | None = None,
    output: str | os.PathLike[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Aggregates agent trajectories into a Chrome trace.

    A workspace and a set of sessions narrow the trace together: naming
    sessions alone collects them wherever they were recorded, adding a
    workspace keeps only the named sessions recorded there, and naming neither
    collects the current working directory.

    What is collected is gathered by the agent that ran it: one backend at one
    model at one effort, and every sub-agent under it, so that a loop of
    one-shot sessions reads as one agent rather than a hundred. A flow that
    drove the sessions itself knows better, and says so through agents.

    Args:
        workspace: Workspace directory to collect trajectories for, defaults to
            the current working directory unless sessions are named.
        sessions: Sessions to collect, as a comma separated string or an
            iterable of ids, defaults to every session. An id can be given
            whole or shortened the way its session slice shows it, and the
            sub-agents a session started are collected with it.
        agents: What each agent of a flow opened, as the ids the backends gave
            those sessions, which is what an agent reports as its own name
            and its opened. Sessions nobody claims are read as the configuration
            they ran at, so this is only needed to tell apart two agents that
            ran at the same one.
        output: Trace file to write, nothing is written when omitted. Its
            directory is created if it does not exist.
        start: Earliest session time to include, in any wording dateparser
            understands, defaults to the earliest record.
        end: Latest session time to include, defaults to the latest record.

    Returns:
        The Chrome trace document, also written to output when one is given.

    Raises:
        ValueError: If start or end cannot be read as a time, or a named
            session is empty.
    """
    bounds: list[float] = []
    for text, default in ((start, -math.inf), (end, math.inf)):
        if not text:
            bounds.append(default)
            continue
        moment = dateparser.parse(text, settings={"RETURN_AS_TIMEZONE_AWARE": True})
        if moment is None:
            raise ValueError(f"cannot parse time: {text}")
        bounds.append(moment.timestamp())

    if isinstance(sessions, str):
        sessions = (sessions,)
    listed = [name.strip() for value in sessions or () for name in value.split(",")]
    if not all(listed):
        raise ValueError("session id cannot be empty")
    names = tuple(listed) or None
    root = (
        None
        if workspace is None and names
        # `abspath` rather than `Path.resolve`: sessions are matched against the path a
        # flow was run under, which is the name it was given rather than what it links to.
        else pathlib.Path(os.path.abspath(workspace or "."))  # noqa: PTH100
    )

    window = (bounds[0], bounds[1])
    collected: list[Session] = []
    for profile in backends.PROFILES:
        home = profile.directory()
        if home.is_dir():
            collected += _READERS[profile.name](home, root, names, window)

    named = {ident: name for name, opened in (agents or {}).items() for ident in opened}
    known = {item.key: item for item in collected}
    for item in collected:
        # Whatever ran a session ran every sub-agent under it, whatever those were
        # configured with themselves, so each is named after the root it hangs from.
        root_of, seen = item, {item.key}
        while root_of.parent in known and root_of.parent not in seen:
            root_of = known[root_of.parent]
            seen.add(root_of.key)
        parts = (
            named.get(root_of.ident, root_of.backend),
            root_of.args.get("model"),
            root_of.args.get("effort"),
        )
        item.agent = " · ".join(str(part) for part in parts if part)

    document = chrome.build(collected, root, names)
    if output is not None:
        destination = pathlib.Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
    return document
