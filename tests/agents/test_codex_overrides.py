"""Whether this agent's app-server `-c` is the window Codex itself reports.

The rest of the suite checks that humanize put `-c` on the argv. Only a real
`codex app-server` can say whether it took the keys: it writes the effective
window on `task_started`. A value well below the catalog default is used so
that honouring the override cannot be mistaken for the catalog clamp.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, cast

import pytest

from hmz.agents import CodexAgent, CodexAgentConfig

pytestmark = pytest.mark.agent

#: Below every catalog default this machine has been seen to report (258400), so a
#: server that ignored `-c` cannot land in this band by accident.
_ASKED_WINDOW = 50_000
_ASKED_COMPACT = 40_000

_SESSIONS = Path.home() / ".codex" / "sessions"


def _window_in(path: Path) -> int | None:
    """The window Codex wrote on the first `task_started` in this rollout, if any."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = cast("dict[str, Any]", json.loads(line))
        except ValueError:
            continue
        raw = row.get("payload")
        payload = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
        if payload.get("type") != "task_started":
            continue
        held = payload.get("model_context_window")
        if isinstance(held, int):
            return held
        if isinstance(held, str) and held.isdigit():
            return int(held)
    return None


def _window_codex_reported(session_id: str, started: float) -> int:
    """The effective window Codex recorded for this thread.

    Args:
      session_id: The thread the turn landed in, as the app server named it.
      started: Unix time just before the agent was constructed, so an older
        rollout is not read as this one.

    Returns:
      The `model_context_window` Codex wrote on `task_started`.

    Raises:
      AssertionError: If Codex never wrote one for this thread.
    """
    found: list[Path] = []
    if _SESSIONS.is_dir():
        for path in _SESSIONS.rglob("*.jsonl"):
            try:
                if path.stat().st_mtime < started - 2:
                    continue
            except OSError:
                continue
            found.append(path)
    for path in found:
        if (
            session_id
            and session_id in path.name
            and (window := _window_in(path)) is not None
        ):
            return window
    for path in sorted(found, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if session_id and session_id not in text:
            continue
        if (window := _window_in(path)) is not None:
            return window
    raise AssertionError(
        f"Codex never reported a context window for thread {session_id!r}"
    )


def _turn(overrides: tuple[tuple[str, str], ...]) -> tuple[str, int]:
    """One cheap turn on a Codex agent, and the window Codex reported for it."""
    started = time.time()
    agent = CodexAgent(
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="low",
            goals=False,
            overrides=overrides,
        )
    )
    session = agent.new()
    said = list(session.stream("Reply with exactly: OK. Use no tools."))
    assert said[-1].kind == "result", said[-1]
    assert session.id
    return session.id, _window_codex_reported(session.id, started)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory of its own for the turn to work in."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(600)
def test_codex_reports_the_window_this_agent_asked_for(workspace: Path) -> None:
    """`-c` is this server's, and Codex's own `task_started` is what says it took it."""
    if shutil.which("codex") is None:
        pytest.skip("codex is not installed here")

    _, window = _turn(
        (
            ("model_context_window", str(_ASKED_WINDOW)),
            ("model_auto_compact_token_limit", str(_ASKED_COMPACT)),
        )
    )

    assert _ASKED_COMPACT <= window <= _ASKED_WINDOW, (
        f"Codex reported {window} after -c model_context_window={_ASKED_WINDOW}; "
        "the catalog default on this machine has been 258400"
    )
