"""Aggregation of the agent trajectories a trace was asked for."""

from __future__ import annotations

import json
import math
import os
import pathlib
from collections.abc import Iterable
from typing import Any

import dateparser

from . import claude, codex, kimi, trace
from .session import Session

_HOMES = (
    ("CLAUDE_CONFIG_DIR", ".claude", claude.collect),
    ("CODEX_HOME", ".codex", codex.collect),
    ("KIMI_CODE_HOME", ".kimi-code", kimi.collect),
)


def collect(
    workspace: str | os.PathLike[str] | None = None,
    *,
    sessions: str | Iterable[str] | None = None,
    output: str | os.PathLike[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Aggregates agent trajectories into a Chrome trace.

    A workspace and a set of sessions narrow the trace together: naming
    sessions alone collects them wherever they were recorded, adding a
    workspace keeps only the named sessions recorded there, and naming neither
    collects the current working directory.

    Args:
        workspace: Workspace directory to collect trajectories for, defaults to
            the current working directory unless sessions are named.
        sessions: Sessions to collect, as a comma separated string or an
            iterable of ids, defaults to every session. An id can be given
            whole or shortened the way its session slice shows it, and the
            sub-agents a session started are collected with it.
        output: Trace file to write, nothing is written when omitted.
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
        else pathlib.Path(os.path.abspath(workspace or "."))
    )

    window = (bounds[0], bounds[1])
    collected: list[Session] = []
    for variable, default_home, collector in _HOMES:
        home = pathlib.Path(
            os.environ.get(variable) or pathlib.Path.home() / default_home
        )
        if home.is_dir():
            collected += collector(home, root, names, window)

    document = trace.build(collected, root, names)
    if output is not None:
        pathlib.Path(output).write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
    return document
