"""Tests for collecting named sessions instead of a whole workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from humanize import oronyx
from tests.oronyx.conftest import (
    CLAUDE_ELSEWHERE,
    CLAUDE_SESSION,
    CODEX_SUBTHREAD,
    CODEX_THREAD,
    KIMI_SESSION,
    keys,
    labels,
    slices,
)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

_CLAUDE = (f"claude:{CLAUDE_SESSION}", f"claude:{CLAUDE_SESSION}:agent-abc12345")
_CODEX = (f"codex:{CODEX_THREAD}", f"codex:{CODEX_SUBTHREAD}")
_KIMI = (f"kimi:{KIMI_SESSION}:main", f"kimi:{KIMI_SESSION}:explore-1")
_ELSEWHERE = f"claude:{CLAUDE_ELSEWHERE}"


@pytest.mark.parametrize(
    "named",
    [CLAUDE_SESSION, CLAUDE_SESSION[:8], _CLAUDE[0]],
    ids=["whole", "shortened", "key"],
)
def test_answers_to_every_spelling_of_an_id(
    claude_home: pathlib.Path, named: str
) -> None:
    assert keys(oronyx.collect(sessions=named)) == set(_CLAUDE)


@pytest.mark.parametrize(
    ("named", "expected"),
    [
        (
            [CLAUDE_SESSION[:8], CODEX_THREAD[:8], KIMI_SESSION],
            {*_CLAUDE, *_CODEX, *_KIMI},
        ),
        ([CLAUDE_SESSION, CLAUDE_ELSEWHERE], {*_CLAUDE, _ELSEWHERE}),
        ([CODEX_THREAD], set(_CODEX)),
        ([CODEX_SUBTHREAD, "abc12345"], {_CODEX[1], _CLAUDE[1]}),
        ([KIMI_SESSION[8:16]], set(_KIMI)),
        ([_KIMI[1]], {_KIMI[1]}),
        (["nope"], set[str]()),
    ],
    ids=["agents", "workspaces", "children", "alone", "shortened", "one", "unknown"],
)
def test_collects_the_named_sessions_wherever_they_ran(
    homes: None, named: list[str], expected: set[str]
) -> None:
    assert keys(oronyx.collect(sessions=named)) == expected


def test_draws_the_spawn_of_a_collected_sub_agent(codex_home: pathlib.Path) -> None:
    document = oronyx.collect(sessions=[CODEX_THREAD])

    assert any(event["ph"] == "s" for event in document["traceEvents"])


def test_puts_a_lone_sub_agent_on_a_sub_agent_track(codex_home: pathlib.Path) -> None:
    document = oronyx.collect(sessions=[CODEX_SUBTHREAD])

    assert labels(document, "thread_name") == {"subagent"}


def test_narrows_named_sessions_to_a_workspace(
    claude_home: pathlib.Path, workspace: pathlib.Path, elsewhere: pathlib.Path
) -> None:
    kept = oronyx.collect(elsewhere, sessions=[CLAUDE_ELSEWHERE])

    assert keys(kept) == {_ELSEWHERE}
    assert oronyx.collect(workspace, sessions=[CLAUDE_ELSEWHERE])["traceEvents"] == []


def test_applies_the_time_window_to_named_sessions(claude_home: pathlib.Path) -> None:
    whole = oronyx.collect(sessions=[CLAUDE_SESSION])
    window = oronyx.collect(sessions=[CLAUDE_SESSION], end="2026-07-20 10:00:05+00:00")

    assert window["otherData"]["end"] == "2026-07-20T10:00:05+00:00"
    assert 0 < len(slices(window)) < len(slices(whole))


def test_treats_no_named_session_as_every_session(
    homes: None, workspace: pathlib.Path
) -> None:
    assert oronyx.collect(workspace, sessions=[]) == oronyx.collect(workspace)


def test_rejects_an_empty_session_id(homes: None) -> None:
    with pytest.raises(ValueError, match="session id cannot be empty"):
        oronyx.collect(sessions=["", CLAUDE_SESSION])


def test_takes_the_sessions_from_any_iterable(
    homes: None, workspace: pathlib.Path
) -> None:
    drained: Iterator[str] = iter([])

    assert keys(oronyx.collect(sessions=iter([CLAUDE_SESSION]))) == set(_CLAUDE)
    assert oronyx.collect(workspace, sessions=drained) == oronyx.collect(workspace)


@pytest.mark.parametrize(
    "named",
    [
        f"{CLAUDE_SESSION[:8]},{CODEX_THREAD[:8]}",
        f" {CLAUDE_SESSION[:8]} , {CODEX_THREAD[:8]} ",
        [f"{CLAUDE_SESSION[:8]},{CODEX_THREAD[:8]}"],
        [CLAUDE_SESSION[:8], CODEX_THREAD[:8]],
    ],
    ids=["comma", "padded", "listed", "repeated"],
)
def test_separates_sessions_on_commas(homes: None, named: str | list[str]) -> None:
    assert keys(oronyx.collect(sessions=named)) == {*_CLAUDE, *_CODEX}


def test_rejects_a_session_missing_between_commas(homes: None) -> None:
    with pytest.raises(ValueError, match="session id cannot be empty"):
        oronyx.collect(sessions=f"{CLAUDE_SESSION},,{KIMI_SESSION}")


def test_reports_the_scope_it_collected(homes: None, workspace: pathlib.Path) -> None:
    named = oronyx.collect(sessions=f"{CLAUDE_SESSION},{KIMI_SESSION}")["otherData"]
    both = oronyx.collect(workspace, sessions=[CLAUDE_SESSION])["otherData"]

    assert "workspace" not in named
    assert named["selected"] == f"{CLAUDE_SESSION}, {KIMI_SESSION}"
    assert both["workspace"] == str(workspace)
    assert both["selected"] == CLAUDE_SESSION
