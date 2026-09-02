"""The rollout items a Codex thread can hold that the shared fixture does not.

`test_collect.py` reads one realistic thread end to end, which covers the spine -- the
session meta, a turn, a reasoning summary, a shell call and its output. What it does not
hold is the rest of the vocabulary: a web search, an applied patch, a sub-agent's activity,
a context that was compacted, and the token counts a turn is billed by.

Each is written here on its own, against a rollout built for it, so that a reader which
quietly stopped recognising one of them is a failing test rather than a trace with a hole
in it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.tracing.readers import codex

if TYPE_CHECKING:
    import pathlib

    from hmz.runtime.tracing.session import Action, Session

#: The thread every rollout below is written under.
THREAD = "01998f1a-0000-7000-8000-00000000beef"

#: The moment a rollout starts, as Codex writes one.
_BEGAN = 1_780_000_000.0


def _stamp(seconds: float) -> str:
    """One moment, as a Codex rollout spells it."""
    import datetime

    return (
        datetime.datetime.fromtimestamp(_BEGAN + seconds, tz=datetime.UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


@pytest.fixture
def rollout(
    tmp_path: pathlib.Path,
) -> Any:
    """Writes one thread out of the records handed in, and reads it back.

    Returns:
      A callable taking the records after the session meta and the turn context, and
      answering with the one session that came of them.
    """
    home = tmp_path / "codex"
    workspace = tmp_path / "project"
    workspace.mkdir()

    def written(*records: dict[str, Any]) -> Session:
        at = home / "sessions" / "2026" / "07" / "20"
        at.mkdir(parents=True, exist_ok=True)
        head = [
            {
                "timestamp": _stamp(0),
                "type": "session_meta",
                "payload": {
                    "id": THREAD,
                    "cwd": str(workspace),
                    "cli_version": "0.5.0",
                    "originator": "cli",
                },
            },
            {
                "timestamp": _stamp(0),
                "type": "turn_context",
                "payload": {"model": "gpt-5.6", "effort": "high"},
            },
            {
                "timestamp": _stamp(1),
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": "turn-1"},
            },
        ]
        (at / f"rollout-2026-07-20T10-00-00-{THREAD}.jsonl").write_text(
            "\n".join(json.dumps(one) for one in [*head, *records]) + "\n",
            encoding="utf-8",
        )
        (one,) = codex.collect(home, workspace, None, (float("-inf"), float("inf")))
        return one

    return written


def _named(session: Session, starting: str) -> Action:
    """The one action whose name starts like this, for a test about that action."""
    found = [one for one in session.actions if one.name.startswith(starting)]
    assert len(found) == 1, [one.name for one in session.actions]
    return found[0]


def test_a_web_search_is_the_query_it_was_made_with(rollout: Any) -> None:
    said = rollout(
        {
            "timestamp": _stamp(4),
            "type": "response_item",
            "payload": {
                "type": "web_search_call",
                "action": {"type": "search", "query": "how to port a module"},
            },
        }
    )

    found = _named(said, "web_search")

    assert "how to port a module" in found.name
    assert found.args["tool"] == "web_search"


def test_a_patch_that_was_applied_says_which_files_it_touched(rollout: Any) -> None:
    said = rollout(
        {
            "timestamp": _stamp(5),
            "type": "event_msg",
            "payload": {
                "type": "patch_apply_end",
                "changes": {"one.py": {"update": {}}, "two.py": {"add": {}}},
                "stdout": "Success. Updated the following files:",
                "success": True,
            },
        }
    )

    found = _named(said, "apply_patch")

    assert "one.py" in found.name
    assert "two.py" in found.name
    assert found.args["success"] is True


def test_what_a_sub_agent_did_is_written_down_as_the_agent_that_did_it(
    rollout: Any,
) -> None:
    said = rollout(
        {
            "timestamp": _stamp(6),
            "type": "event_msg",
            "payload": {
                "type": "sub_agent_activity",
                "kind": "started",
                "agent_path": "reviewer",
            },
        }
    )

    found = _named(said, "agent started")

    assert "reviewer" in found.name
    assert found.category == "event"


def test_a_context_that_was_compacted_is_an_event_on_the_timeline(rollout: Any) -> None:
    """A turn that forgot most of what it knew is the explanation for the next one."""
    said = rollout(
        {
            "timestamp": _stamp(7),
            "type": "event_msg",
            "payload": {"type": "context_compacted"},
        }
    )

    assert _named(said, "system: context_compacted").category == "event"


def test_what_a_turn_spent_is_read_off_the_count_it_was_told(rollout: Any) -> None:
    said = rollout(
        {
            "timestamp": _stamp(3),
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "read the module"}],
            },
        },
        {
            "timestamp": _stamp(4),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"input_tokens": 120, "output_tokens": 34}
                },
            },
        },
    )

    found = _named(said, "think")

    assert found.args["usage"] == {"input_tokens": 120, "output_tokens": 34}


def test_reasoning_said_outside_a_summary_joins_the_thinking_it_belongs_to(
    rollout: Any,
) -> None:
    """Codex says a thought twice: the summary, and the reasoning behind it."""
    said = rollout(
        {
            "timestamp": _stamp(3),
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "read the module"}],
            },
        },
        {
            "timestamp": _stamp(4),
            "type": "event_msg",
            "payload": {"type": "agent_reasoning", "text": "and then port it"},
        },
    )

    found = _named(said, "think")

    assert "read the module" in found.args["reasoning"]
    assert "and then port it" in found.args["reasoning"]


def test_a_tool_call_nothing_answered_is_marked_as_the_one_that_did_not_finish(
    rollout: Any,
) -> None:
    """A run killed mid-call leaves one open, and a trace that hid it would read as done."""
    said = rollout(
        {
            "timestamp": _stamp(4),
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "call_id": "call-shell",
                "arguments": json.dumps({"command": "sleep 600"}),
            },
        }
    )

    found = _named(said, "shell")

    assert found.args["unfinished"] is True


def test_a_tool_call_that_was_answered_carries_what_it_answered_with(
    rollout: Any,
) -> None:
    said = rollout(
        {
            "timestamp": _stamp(4),
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "call_id": "call-shell",
                "arguments": json.dumps({"command": "cat one.py"}),
            },
        },
        {
            "timestamp": _stamp(5),
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-shell",
                "output": "the file's contents",
            },
        },
    )

    found = _named(said, "shell")

    assert "the file's contents" in found.args["output"]
    assert "unfinished" not in found.args
