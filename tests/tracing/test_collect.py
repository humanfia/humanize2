"""Tests for the tracing.collect library entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import tracing
from hmz.tracing import collector
from tests.tracing.conftest import (
    CLAUDE_ELSEWHERE,
    CLAUDE_SESSION,
    FLOW,
    banners,
    labels,
    loaded,
    named,
    slices,
)

if TYPE_CHECKING:
    import pathlib


def test_exposes_collect_as_the_public_api() -> None:
    assert tracing.__all__ == ["collect"]
    assert tracing.collect is collector.collect


def test_collects_every_agent(homes: None, workspace: pathlib.Path) -> None:
    document = tracing.collect(workspace)

    summary = document["otherData"]
    assert summary["workspace"] == str(workspace)
    assert summary["backends"] == "claude, codex, kimi"
    assert summary["agents"] == (
        "claude · claude-opus-5 · xhigh, codex · gpt-5.6 · high, kimi · kimi-k2 · high"
    )
    assert summary["sessions"] == "6"
    assert summary["start"] == "2026-07-20T10:00:00+00:00"
    assert summary["end"] == "2026-07-20T10:00:14+00:00"


def test_renders_one_session_slice_per_track(
    homes: None, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace)

    names = [str(event["name"]) for event in banners(document)]
    assert len(names) == 6
    assert sum(name.startswith("main · ") for name in names) == 3
    assert any(name.startswith("Explore · scout the tests · ") for name in names)
    assert any(name.startswith("agents/scout.md · ") for name in names)
    assert any(name.startswith("explore · explore-1 · ") for name in names)


def test_reports_claude_prompt_reasoning_and_tool(
    claude_home: pathlib.Path, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace)

    assert document["otherData"]["backends"] == "claude"
    turn = named(document, "turn: map the repo")
    assert turn["args"]["prompt"] == "map the repo"
    think = named(document, "think: look around first")
    assert think["args"]["model"] == "claude-opus-5"
    assert think["args"]["usage"] == {"input_tokens": 12, "output_tokens": 34}
    call = named(document, "Bash: List files")
    assert call["args"]["input"] == {"command": "ls", "description": "List files"}
    assert call["args"]["output"] == "README.md"
    assert call["args"]["error"] is False
    assert call["dur"] == 2_000_000
    assert named(document, "say: listing the files")["args"]["text"] == (
        "listing the files"
    )
    assert named(document, "system: compact_boundary")["args"]["level"] == "info"


def test_reports_codex_prompt_reasoning_and_tool(
    codex_home: pathlib.Path, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace)

    assert document["otherData"]["backends"] == "codex"
    turn = named(document, "turn: port the module")
    assert turn["args"]["prompt"] == "port the module"
    assert turn["args"]["result"] == "done"
    assert named(document, "think: read the module")["cat"] == "llm"
    call = named(document, "shell: cat module.py")
    assert call["args"]["input"] == {"command": "cat module.py"}
    assert call["args"]["output"] == "print('hi')"
    assert call["dur"] == 2_000_000
    assert named(document, "say: ported the module")["args"]["text"] == (
        "ported the module"
    )


def test_reports_dsh_prompt_reasoning_tool_and_usage(
    dsh_home: pathlib.Path, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace)

    assert document["otherData"]["backends"] == "dsh"
    assert document["otherData"]["agents"] == ("dsh · deepseek-v4-flash · high")
    assert named(document, "turn: inspect the module")["args"]["reason"] == {
        "kind": "completed"
    }
    think = named(document, "think: read it first")
    assert think["args"]["usage"] == {
        "inputTokens": 20,
        "outputTokens": 10,
        "cacheReadTokens": 100,
        "reasoningTokens": 4,
    }
    call = named(document, "bash: cat module.py")
    assert call["args"]["input"] == {"command": "cat module.py"}
    assert call["args"]["output"] == "print('hi')"
    assert call["args"]["error"] is False
    assert call["dur"] == 2_000_000
    assert named(document, "say: inspected the module")["args"]["text"] == (
        "inspected the module"
    )


def test_reports_kimi_prompt_reasoning_and_tool(
    kimi_home: pathlib.Path, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace)

    assert document["otherData"]["backends"] == "kimi"
    assert named(document, "turn: wire up the loop")["args"]["origin"] == "cli"
    think = named(document, "think: read the loop first")
    assert think["args"]["thinking"] == "read the loop first"
    assert think["args"]["finishReason"] == "stop"
    call = named(document, "Read: loop.py")
    assert call["args"]["input"] == {"file_path": "loop.py"}
    assert call["args"]["output"] == "while True:"
    assert call["dur"] == 2_000_000
    assert named(document, "system: permission auto")["cat"] == "event"


def test_links_sub_agents_to_their_spawner(
    homes: None, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace)

    flows = [event for event in document["traceEvents"] if event["ph"] in ("s", "f")]
    assert len(flows) == 4
    assert {flow["id"] for flow in flows if flow["ph"] == "s"} == {
        flow["id"] for flow in flows if flow["ph"] == "f"
    }
    sessions = banners(document)
    roles = {
        event["args"]["session"]: event["name"].split(" · ")[0] for event in sessions
    }
    assert {
        roles[event["args"]["session"]]: roles.get(event["args"]["parent"])
        for event in sessions
    } == {
        "main": None,
        "Explore": "main",
        "agents/scout.md": "main",
        "explore": "main",
    }


def test_names_tracks_after_their_role(homes: None, workspace: pathlib.Path) -> None:
    """A process is an agent and a track is one of its sub-agents, named for what it was.

    Which is what a track of five explorations reads as: `subagent · Explore` says what was
    running on it, where `subagent #2` says only that it was the second row drawn.
    """
    document = tracing.collect(workspace)

    tracks = {name.split(" ~")[0] for name in labels(document, "thread_name")}
    assert tracks == {
        "main",
        "subagent · Explore",
        "subagent · agents/scout.md",
        "subagent · explore",
    }


def test_gathers_a_configuration_and_its_sub_agents_into_one_agent(
    homes: None, workspace: pathlib.Path
) -> None:
    """A backend at a model at an effort is one agent, sub-agents included.

    The Explore under the Claude session answered at sonnet and medium, and is still part of
    the agent that started it: what a sub-agent is configured with is its parent's business.
    """
    document = tracing.collect(workspace)

    assert labels(document, "process_name") == {
        "claude · claude-opus-5 · xhigh · 2 sessions",
        "codex · gpt-5.6 · high · 2 sessions",
        "kimi · kimi-k2 · high · 2 sessions",
    }


def test_gathers_the_runs_of_one_configuration_into_one_agent(
    claude_home: pathlib.Path,
) -> None:
    """Two runs of one coding agent are one agent, whichever workspace each ran in."""
    document = tracing.collect(sessions=[CLAUDE_SESSION, CLAUDE_ELSEWHERE])

    assert labels(document, "process_name") == {
        "claude · claude-opus-5 · xhigh · 3 sessions"
    }


def test_tells_apart_the_agents_a_flow_names(claude_home: pathlib.Path) -> None:
    """The case configuration cannot answer: one model at one effort, run as two agents.

    The actor's two sessions are its own and the sub-agent it started, which it never had
    to claim: a sub-agent belongs to whoever ran the session that started it.
    """
    document = tracing.collect(sessions=[CLAUDE_SESSION, CLAUDE_ELSEWHERE], agents=FLOW)

    assert labels(document, "process_name") == {
        "actor · claude-opus-5 · xhigh · 2 sessions",
        "reviewer · claude-opus-5 · xhigh · 1 sessions",
    }
    assert document["otherData"]["agents"] == (
        "actor · claude-opus-5 · xhigh, reviewer · claude-opus-5 · xhigh"
    )


def test_names_the_agent_of_every_session_a_flow_claims(
    homes: None, workspace: pathlib.Path
) -> None:
    """A flow names what it drove; everything else is still read as a configuration.

    Each backend is claimed by the id it hands out: the whole id for Claude, and for Kimi the
    session it prints to resume, which its logs name a folder after. Codex ran outside the
    flow here, so it is read as the configuration it ran at.
    """
    document = tracing.collect(workspace, agents=FLOW)

    assert labels(document, "process_name") == {
        "actor · claude-opus-5 · xhigh · 2 sessions",
        "worker · kimi-k2 · high · 2 sessions",
        "codex · gpt-5.6 · high · 2 sessions",
    }
    assert {event["args"]["agent"] for event in banners(document)} == {
        "actor · claude-opus-5 · xhigh",
        "worker · kimi-k2 · high",
        "codex · gpt-5.6 · high",
    }


def test_defaults_to_the_current_directory(
    homes: None, workspace: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(workspace)

    assert tracing.collect() == tracing.collect(workspace)


def test_accepts_a_workspace_string(homes: None, workspace: pathlib.Path) -> None:
    assert tracing.collect(str(workspace)) == tracing.collect(workspace)


def test_ignores_another_workspace(homes: None, tmp_path: pathlib.Path) -> None:
    document = tracing.collect(tmp_path / "nowhere")

    assert document == {
        "traceEvents": [],
        "displayTimeUnit": "ms",
        "otherData": {"workspace": str(tmp_path / "nowhere")},
    }


def test_skips_agents_without_a_home(
    claude_home: pathlib.Path,
    workspace: pathlib.Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing"))

    assert tracing.collect(workspace)["otherData"]["backends"] == "claude"


def test_cuts_off_records_outside_the_window(
    homes: None, workspace: pathlib.Path
) -> None:
    whole = tracing.collect(workspace)
    window = tracing.collect(
        workspace,
        start="2026-07-20 10:00:04+00:00",
        end="2026-07-20 10:00:08+00:00",
    )

    assert 0 < len(slices(window)) < len(slices(whole))
    assert window["otherData"]["start"] == "2026-07-20T10:00:04+00:00"
    assert window["otherData"]["end"] == "2026-07-20T10:00:08+00:00"


def test_returns_an_empty_document_for_an_empty_window(
    homes: None, workspace: pathlib.Path
) -> None:
    document = tracing.collect(workspace, end="2026-07-20 09:00:00+00:00")

    assert document["traceEvents"] == []
    assert document["otherData"] == {"workspace": str(workspace)}


def test_rejects_a_time_it_cannot_read(workspace: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="cannot parse time: not a time at all!!"):
        tracing.collect(workspace, start="not a time at all!!")


def test_writes_the_output_file(
    homes: None, workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    output = tmp_path / "nested" / "trace.json"
    output.parent.mkdir()

    document = tracing.collect(workspace, output=output)

    assert loaded(output) == document


def test_writes_relative_output_next_to_the_caller(
    homes: None, workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    document = tracing.collect(workspace, output="trace.json")

    assert loaded(tmp_path / "trace.json") == document


def test_writes_nothing_without_an_output(
    homes: None, workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    tracing.collect(workspace)

    assert list(tmp_path.glob("*.json")) == []


def test_keeps_unicode_readable(
    kimi_home: pathlib.Path, workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    path = next(kimi_home.glob("sessions/*/*/agents/main/wire.jsonl"))
    path.write_text(
        path.read_text(encoding="utf-8").replace("wire up the loop", "接上循环"),
        encoding="utf-8",
    )

    tracing.collect(workspace, output=tmp_path / "trace.json")

    assert "接上循环" in (tmp_path / "trace.json").read_text(encoding="utf-8")


def test_a_forked_child_is_drawn_under_its_parent(
    claude_home: pathlib.Path, workspace: pathlib.Path
) -> None:
    """A fork is a native branch, not a sub-agent, so the cycle's relation supplies the link."""
    document = collector.collect(workspace, parents={CLAUDE_SESSION: "parent-xyz"})

    assert any(
        event["args"].get("parent") == "claude:parent-xyz"
        for event in banners(document)
    )
