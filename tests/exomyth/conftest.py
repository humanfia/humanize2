"""Fake agent home directories used by the test suite."""

from __future__ import annotations

import datetime
import json
import pathlib
import re
from typing import Any

import pytest

_BASE = datetime.datetime(2026, 7, 20, 10, 0, tzinfo=datetime.UTC)
CLAUDE_SESSION = "0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9"
CLAUDE_ELSEWHERE = "7c8d9e0f-1a2b-3c4d-5e6f-708192a3b4c5"
CODEX_THREAD = "5f6e7d8c-1a2b-3c4d-5e6f-708192a3b4c5"
CODEX_SUBTHREAD = "9182a3b4-c5d6-e7f8-0912-a3b4c5d6e7f8"
KIMI_SESSION = "session_20260720T100000_abcdef"


def _stamp(offset: float) -> str:
    """Formats a fixture time the way Claude and Codex write timestamps."""
    return (_BASE + datetime.timedelta(seconds=offset)).isoformat()


def _millis(offset: float) -> int:
    """Formats a fixture time the way Kimi Code writes timestamps."""
    return int((_BASE + datetime.timedelta(seconds=offset)).timestamp() * 1000)


def _write(path: pathlib.Path, records: list[dict[str, Any]]) -> None:
    """Writes records as a JSON Lines file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def sandbox(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hides the real agent homes so tests never read the developer's logs."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "KIMI_CODE_HOME"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates the workspace the fake trajectories were recorded for."""
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.fixture
def elsewhere(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a second workspace, recorded by Claude only."""
    path = tmp_path / "elsewhere"
    path.mkdir()
    return path


@pytest.fixture
def claude_home(
    tmp_path: pathlib.Path,
    workspace: pathlib.Path,
    elsewhere: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> pathlib.Path:
    """Builds a Claude home with a transcript per workspace and a sub-agent."""
    home = tmp_path / "claude"
    project = home / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(workspace))
    _write(
        project / f"{CLAUDE_SESSION}.jsonl",
        [
            {
                "type": "user",
                "timestamp": _stamp(0),
                "cwd": str(workspace),
                "version": "2.0.1",
                "gitBranch": "main",
                "sessionId": CLAUDE_SESSION,
                "promptId": "prompt-1",
                "message": {"role": "user", "content": "map the repo"},
            },
            {
                "type": "assistant",
                "timestamp": _stamp(2),
                "requestId": "request-1",
                "message": {
                    "id": "message-1",
                    "model": "claude-opus-5",
                    "usage": {"input_tokens": 12, "output_tokens": 34},
                    "content": [
                        {"type": "thinking", "thinking": "look around first"},
                        {"type": "text", "text": "listing the files"},
                        {
                            "type": "tool_use",
                            "id": "call-ls",
                            "name": "Bash",
                            "input": {"command": "ls", "description": "List files"},
                        },
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": _stamp(4),
                "toolUseResult": {"stdout": "README.md"},
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-ls",
                            "content": "README.md",
                            "is_error": False,
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "timestamp": _stamp(5),
                "requestId": "request-2",
                "message": {
                    "id": "message-2",
                    "model": "claude-opus-5",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call-agent",
                            "name": "Agent",
                            "input": {
                                "description": "scout the tests",
                                "prompt": "find the tests",
                            },
                        }
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": _stamp(9),
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-agent",
                            "content": "no tests yet",
                        }
                    ],
                },
            },
            {
                "type": "system",
                "timestamp": _stamp(10),
                "subtype": "compact_boundary",
                "level": "info",
                "compactMetadata": {"trigger": "manual"},
            },
        ],
    )
    subagents = project / CLAUDE_SESSION / "subagents"
    subagents.mkdir(parents=True, exist_ok=True)
    (subagents / "agent-abc12345.meta.json").write_text(
        json.dumps(
            {
                "agentType": "Explore",
                "description": "scout the tests",
                "toolUseId": "call-agent",
            }
        ),
        encoding="utf-8",
    )
    _write(
        subagents / "agent-abc12345.jsonl",
        [
            {
                "type": "user",
                "timestamp": _stamp(6),
                "cwd": str(workspace),
                "promptId": "prompt-2",
                "message": {"role": "user", "content": "find the tests"},
            },
            {
                "type": "assistant",
                "timestamp": _stamp(8),
                "requestId": "request-3",
                "message": {
                    "id": "message-3",
                    "model": "claude-sonnet-5",
                    "content": [{"type": "text", "text": "no tests yet"}],
                },
            },
        ],
    )
    other = home / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(elsewhere))
    _write(
        other / f"{CLAUDE_ELSEWHERE}.jsonl",
        [
            {
                "type": "user",
                "timestamp": _stamp(20),
                "cwd": str(elsewhere),
                "sessionId": CLAUDE_ELSEWHERE,
                "promptId": "prompt-3",
                "message": {"role": "user", "content": "read the other repo"},
            }
        ],
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return home


@pytest.fixture
def codex_home(
    tmp_path: pathlib.Path, workspace: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    """Builds a Codex home with one main rollout and one sub-agent rollout."""
    home = tmp_path / "codex"
    rollouts = home / "sessions" / "2026" / "07" / "20"
    _write(
        rollouts / f"rollout-2026-07-20T10-00-00-{CODEX_THREAD}.jsonl",
        [
            {
                "timestamp": _stamp(0),
                "type": "session_meta",
                "payload": {
                    "id": CODEX_THREAD,
                    "cwd": str(workspace),
                    "cli_version": "0.5.0",
                    "originator": "cli",
                    "git": {"branch": "main"},
                },
            },
            {
                "timestamp": _stamp(0),
                "type": "turn_context",
                "payload": {
                    "model": "gpt-5.6",
                    "effort": "high",
                    "approval_policy": "never",
                    "sandbox_policy": "workspace-write",
                },
            },
            {
                "timestamp": _stamp(1),
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": "turn-1"},
            },
            {
                "timestamp": _stamp(1),
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "port the module"},
            },
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
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "call_id": "call-shell",
                    "arguments": json.dumps({"command": "cat module.py"}),
                },
            },
            {
                "timestamp": _stamp(6),
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-shell",
                    "output": "print('hi')",
                },
            },
            {
                "timestamp": _stamp(7),
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "run_agent",
                    "call_id": "call-agent",
                    "arguments": json.dumps({"task_name": "scout.md"}),
                },
            },
            {
                "timestamp": _stamp(12),
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-agent",
                    "output": "scouted",
                },
            },
            {
                "timestamp": _stamp(13),
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "ported the module"},
            },
            {
                "timestamp": _stamp(14),
                "type": "event_msg",
                "payload": {"type": "task_complete", "last_agent_message": "done"},
            },
        ],
    )
    _write(
        rollouts / f"rollout-2026-07-20T10-00-08-{CODEX_SUBTHREAD}.jsonl",
        [
            {
                "timestamp": _stamp(8),
                "type": "session_meta",
                "payload": {
                    "id": CODEX_SUBTHREAD,
                    "cwd": str(workspace),
                    "parent_thread_id": CODEX_THREAD,
                    "agent_path": "agents/scout.md",
                    "agent_nickname": "scout",
                },
            },
            {
                "timestamp": _stamp(9),
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "scout the module"},
            },
            {
                "timestamp": _stamp(11),
                "type": "event_msg",
                "payload": {"type": "task_complete", "last_agent_message": "scouted"},
            },
        ],
    )
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


@pytest.fixture
def kimi_home(
    tmp_path: pathlib.Path, workspace: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    """Builds a Kimi Code home with a main wire and a sub-agent wire."""
    home = tmp_path / "kimi"
    session = home / "sessions" / "project" / KIMI_SESSION
    main = session / "agents" / "main"
    session.mkdir(parents=True, exist_ok=True)
    (session / "state.json").write_text(
        json.dumps(
            {
                "workDir": str(workspace),
                "title": "wire up the loop",
                "agents": {
                    "main": {"type": "main", "homedir": str(main)},
                    "explore-1": {"type": "explore", "parentAgentId": "main"},
                },
            }
        ),
        encoding="utf-8",
    )
    _write(
        main / "wire.jsonl",
        [
            {
                "time": _millis(0),
                "type": "llm.request",
                "modelAlias": "kimi-k2",
                "thinkingEffort": "high",
            },
            {
                "time": _millis(0),
                "type": "config.update",
                "profileName": "default",
            },
            {
                "time": _millis(1),
                "type": "permission.set_mode",
                "mode": "auto",
            },
            {
                "time": _millis(1),
                "type": "turn.prompt",
                "origin": "cli",
                "input": "wire up the loop",
            },
            {
                "time": _millis(2),
                "type": "context.append_loop_event",
                "event": {
                    "type": "step.begin",
                    "uuid": "step-1",
                    "step": 1,
                    "turnId": "turn-1",
                },
            },
            {
                "time": _millis(3),
                "type": "context.append_loop_event",
                "event": {
                    "type": "content.part",
                    "stepUuid": "step-1",
                    "part": {"type": "think", "think": "read the loop first"},
                },
            },
            {
                "time": _millis(4),
                "type": "context.append_loop_event",
                "event": {
                    "type": "tool.call",
                    "toolCallId": "tool-1",
                    "name": "Read",
                    "description": "Read the loop",
                    "args": {"file_path": "loop.py"},
                },
            },
            {
                "time": _millis(6),
                "type": "context.append_loop_event",
                "event": {
                    "type": "tool.result",
                    "toolCallId": "tool-1",
                    "result": {"output": "while True:", "isError": False},
                },
            },
            {
                "time": _millis(7),
                "type": "context.append_loop_event",
                "event": {
                    "type": "content.part",
                    "stepUuid": "step-1",
                    "part": {"type": "text", "text": "the loop is wired"},
                },
            },
            {
                "time": _millis(8),
                "type": "context.append_loop_event",
                "event": {
                    "type": "step.end",
                    "uuid": "step-1",
                    "finishReason": "stop",
                    "usage": {"total_tokens": 99},
                },
            },
        ],
    )
    _write(
        session / "agents" / "explore-1" / "wire.jsonl",
        [
            {
                "time": _millis(4),
                "type": "turn.prompt",
                "origin": "agent",
                "input": "explore the loop",
            },
            {
                "time": _millis(5),
                "type": "context.append_loop_event",
                "event": {
                    "type": "content.part",
                    "part": {"type": "text", "text": "explored"},
                },
            },
        ],
    )
    monkeypatch.setenv("KIMI_CODE_HOME", str(home))
    return home


@pytest.fixture
def homes(
    claude_home: pathlib.Path, codex_home: pathlib.Path, kimi_home: pathlib.Path
) -> None:
    """Builds every agent home for the workspace."""


def loaded(path: pathlib.Path) -> dict[str, Any]:
    """Reads back a written trace document."""
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def slices(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns the complete duration events of a trace document."""
    return [event for event in document["traceEvents"] if event["ph"] == "X"]


def banners(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns the widest slice of every session a trace document holds."""
    return [event for event in slices(document) if event["cat"] == "session"]


def keys(document: dict[str, Any]) -> set[str]:
    """Returns the key of every session a trace document holds."""
    return {str(event["args"]["session"]) for event in banners(document)}


def labels(document: dict[str, Any], meta: str) -> set[str]:
    """Returns the names carried by one kind of trace metadata event."""
    return {
        str(event["args"]["name"])
        for event in document["traceEvents"]
        if event["name"] == meta
    }


def named(document: dict[str, Any], name: str) -> dict[str, Any]:
    """Returns the single slice whose name starts with the given prefix."""
    found = [event for event in slices(document) if event["name"].startswith(name)]
    assert len(found) == 1, f"expected one {name!r} slice, got {len(found)}"
    return found[0]
