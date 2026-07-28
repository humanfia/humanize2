"""The subpackages composed, which is the only place their fit is checked.

oronyx imports neither of the others and neither imports it: a flow is what joins them, by
handing oronyx what janus reports -- so nothing but this checks that an agent's `opened` really
names the sessions oronyx files under that agent. janus does read coganchor's settings, but only
as settings; that they still describe a session it can drive is checked here too.

The flows are run for real against a fake `claude` that records a transcript where the real one
would and writes a file where it is told to, which is the whole path: the id janus pins, the
transcript that id names, the agent that says it opened it, and the machine the work landed on.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from humanize import oronyx
from humanize.coganchor import AnchorConfig
from humanize.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig
from tests.coganchor.conftest import VIRTUAL_WORKSPACE
from tests.oronyx.conftest import labels

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")

#: A `claude --print` speaking the streaming protocol: it writes the transcript its session id
#: names, works, and answers, once per turn written to it.
FAKE = """
import datetime, json, os, pathlib, re, sys

flags = dict(zip(sys.argv, sys.argv[1:]))  # every flag paired with what follows it
cwd = pathlib.Path.cwd()
taken = flags.get("--session-id") or flags["--resume"]
print(json.dumps({"type": "system", "session_id": taken}), flush=True)
path = (
    pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"])
    / "projects"
    / re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    / f"{taken}.jsonl"
)
path.parent.mkdir(parents=True, exist_ok=True)
for line in sys.stdin:
    now = datetime.datetime.now(datetime.UTC)
    said = json.loads(line)["message"]["content"][0]["text"]
    with pathlib.Path("landed.txt").open("a") as landed:  # the work, wherever the workspace is
        landed.write(taken)
    with path.open("a") as trajectory:
        trajectory.write(
            "".join(
                json.dumps(record | {"cwd": str(cwd), "sessionId": taken}) + "\\n"
                for record in (
                    {
                        "type": "user",
                        "timestamp": now.isoformat(),
                        "message": {"role": "user", "content": said},
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
    print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts a fake `claude` on PATH, hides the real agent homes, and returns the workspace."""
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
    return workspace


@pytest.fixture
def flow(sandbox: Path) -> tuple[Path, dict[str, list[str]]]:
    """Runs a flow's two agents for real, and reports its workspace and what each opened."""
    # The rlar shape, at one model and one effort: what nothing in a transcript tells apart.
    actor = ClaudeCodeAgent(CONFIG, name="actor")
    reviewer = ClaudeCodeAgent(CONFIG, name="reviewer")
    actor.new()("do the task")
    reviewer.new()("review the work")
    return sandbox, {agent.id: agent.opened for agent in (actor, reviewer)}


def test_a_flow_is_traced_as_the_agents_it_ran(
    flow: tuple[Path, dict[str, list[str]]],
) -> None:
    workspace, agents = flow

    document = oronyx.collect(workspace, agents=agents)

    assert document["otherData"]["sessions"] == "2"
    assert labels(document, "process_name") == {
        "actor · claude-opus-4-8 · high · 1 sessions",
        "reviewer · claude-opus-4-8 · high · 1 sessions",
    }


@pytest.mark.timeout(180)
def test_an_anchored_flow_leaves_its_work_there_and_its_trajectory_here(
    sandbox: Path, tmp_path: Path
) -> None:
    """An anchor moves the work, not the conversation, so the flow reads back the same way.

    The agent runs on this machine whatever the anchor says, keeping its credentials and the
    transcript a trace is built from; the file it writes is checked on the target, where the
    workspace it was given only ever existed.
    """
    target, mirror = tmp_path / "target", tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-4-8",
            effort="high",
            anchor=AnchorConfig(
                target=f"local:{target}",
                workspace=VIRTUAL_WORKSPACE,
                shadow=str(mirror),
            ),
        ),
        name="actor",
    )
    session = agent.new()

    assert session("do the task") == "done"  # the turn is the flow's, as it always was
    # A second turn resumes the conversation and reaches the target through the mirror the
    # first one left behind, which is the shape every flow humanize comes with runs in.
    assert session("keep going") == "done"

    assert (target / "landed.txt").read_text() == session.id * 2
    assert not (
        sandbox / "landed.txt"
    ).exists()  # nothing landed where the flow was started

    document = oronyx.collect(sessions=session.id, agents={agent.id: agent.opened})

    assert document["otherData"]["sessions"] == "1"
    assert labels(document, "process_name") == {
        "actor · claude-opus-4-8 · high · 1 sessions"
    }
