"""The two subpackages composed, which is the only place their fit is checked.

Neither imports the other, and neither can: they are merged projects that share a namespace and
nothing else. A flow is what joins them, by handing exomyth what janus reports -- so nothing but
this checks that an agent's `opened` really names the sessions exomyth files under that agent.

The flow is run for real against a fake `claude` that records a transcript where the real one
would, which is the whole path: the id janus pins, the transcript that id names, and the agent
that says it opened it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from amflows import exomyth
from amflows.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig
from tests.exomyth.conftest import labels

CONFIG = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")

#: A `claude --print` that writes the transcript its session id names, and answers.
FAKE = """
import datetime, json, os, pathlib, re, sys

flags = dict(zip(sys.argv, sys.argv[1:]))  # every flag paired with what follows it
cwd, now = pathlib.Path.cwd(), datetime.datetime.now(datetime.UTC)
taken = flags["--session-id"]
path = (
    pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"])
    / "projects"
    / re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    / f"{taken}.jsonl"
)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    "".join(
        json.dumps(record | {"cwd": str(cwd), "sessionId": taken}) + "\\n"
        for record in (
            {
                "type": "user",
                "timestamp": now.isoformat(),
                "message": {"role": "user", "content": sys.stdin.read()},
            },
            {
                "type": "assistant",
                "timestamp": (now + datetime.timedelta(seconds=1)).isoformat(),
                "requestId": taken,
                "effort": flags["--effort"],
                "message": {
                    "id": taken,
                    "model": flags["--model"],
                    "content": [{"type": "text", "text": "done"}],
                },
            },
        )
    )
)
print("done")
"""


@pytest.fixture
def flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, list[str]]]:
    """Runs a flow's two agents for real, and reports its workspace and what each opened."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{FAKE}")
    fake.chmod(0o755)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    for variable in ("CODEX_HOME", "KIMI_CODE_HOME"):
        monkeypatch.delenv(variable, raising=False)  # neither has a home under our HOME
    monkeypatch.chdir(workspace)
    # The rlar shape, at one model and one effort: what nothing in a transcript tells apart.
    executor = ClaudeCodeAgent(CONFIG, name="executor")
    reviewer = ClaudeCodeAgent(CONFIG, name="reviewer")
    executor.launch().run("do the task")
    reviewer.launch().run("judge the work")
    return workspace, {agent.id: agent.opened for agent in (executor, reviewer)}


def test_a_flow_is_traced_as_the_agents_it_ran(
    flow: tuple[Path, dict[str, list[str]]],
) -> None:
    workspace, agents = flow

    document = exomyth.collect(workspace, agents=agents)

    assert document["otherData"]["sessions"] == "2"
    assert labels(document, "process_name") == {
        "executor · claude-opus-4-8 · high · 1 sessions",
        "reviewer · claude-opus-4-8 · high · 1 sessions",
    }
