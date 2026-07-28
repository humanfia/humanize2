"""End-to-end tests driving the real coding agents.

These cost tokens and need network access, so they only run with
``pytest --run-agents``.  Each one gives the agent a task whose inputs exist
*only* on the target machine and whose effects are checked *only* on the target
machine, so a pass means the whole loop worked: the agent ran here, and every
file it touched lived there.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.coganchor.conftest import Anchorage

pytestmark = pytest.mark.agent

#: Per-agent invocation.  ``{prompt}`` is substituted at run time.
AGENT_COMMANDS: dict[str, tuple[str, ...]] = {
    "claude": ("claude", "-p", "{prompt}", "--dangerously-skip-permissions"),
    "codex": (
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "{prompt}",
    ),
    # kimi's prompt mode already runs unattended and rejects --yolo/--auto.
    "kimi": ("kimi", "-p", "{prompt}"),
}

AGENT_TIMEOUT = 300


@dataclass(frozen=True, slots=True)
class AgentTask:
    """One instruction given to a real agent, checked on the target."""

    name: str
    prompt: str
    seed: dict[str, str] = field(default_factory=dict[str, str])
    #: Substrings the agent's answer must contain (case-insensitive).
    answer: tuple[str, ...] = ()
    #: Substrings that must appear in a target file afterwards.
    target_contains: dict[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )
    target_missing: tuple[str, ...] = ()


AGENT_TASKS: tuple[AgentTask, ...] = (
    AgentTask(
        name="read_a_file",
        seed={"notes.txt": "The project codeword is HALIBUT.\n"},
        prompt="Read notes.txt and reply with only the codeword.",
        answer=("halibut",),
    ),
    AgentTask(
        name="read_a_nested_file",
        seed={"src/config/settings.py": "TIMEOUT_SECONDS = 137\n"},
        prompt=(
            "What is TIMEOUT_SECONDS set to in src/config/settings.py? Reply with only the number."
        ),
        answer=("137",),
    ),
    AgentTask(
        name="create_a_file",
        prompt=(
            "Create a file called greeting.txt whose entire contents are exactly: "
            "hello from the agent"
        ),
        target_contains={"greeting.txt": ("hello from the agent",)},
    ),
    AgentTask(
        name="edit_an_existing_file",
        seed={"version.txt": "version = 1.0.0\n"},
        prompt="Edit version.txt so the version reads 2.0.0 instead of 1.0.0. Change nothing else.",
        target_contains={"version.txt": ("2.0.0",)},
    ),
    AgentTask(
        name="run_a_shell_command",
        seed={"data.csv": "a,1\nb,2\nc,3\n"},
        prompt=(
            "Run a shell command to count the lines in data.csv, then reply with only that number."
        ),
        answer=("3",),
    ),
    AgentTask(
        name="search_the_workspace",
        seed={
            "app/handler.py": "def handle():\n    raise NotImplementedError\n",
            "app/util.py": "def helper():\n    return 1\n",
        },
        prompt="Which file under app/ raises NotImplementedError? Reply with only the filename.",
        answer=("handler.py",),
    ),
    AgentTask(
        name="create_a_directory_and_file",
        prompt=(
            "Create a directory called reports and inside it a file summary.md "
            "containing the single word: complete"
        ),
        target_contains={"reports/summary.md": ("complete",)},
    ),
    AgentTask(
        name="delete_a_file",
        seed={"obsolete.txt": "remove me\n", "keep.txt": "keep me\n"},
        prompt="Delete obsolete.txt. Leave keep.txt alone.",
        target_missing=("obsolete.txt",),
    ),
    AgentTask(
        name="multi_step_refactor",
        seed={"calc.py": "def add(a, b):\n    return a - b\n"},
        prompt=(
            "calc.py has a bug: add() subtracts instead of adding. Fix it, then run "
            "'python3 -c \"import calc; print(calc.add(2,3))\"' and reply with the output."
        ),
        answer=("5",),
        target_contains={"calc.py": ("a + b",)},
    ),
    AgentTask(
        name="report_the_working_directory",
        seed={"marker.txt": "here\n"},
        prompt=(
            "Run the shell command 'ls' and reply with the names of the files you see, "
            "comma separated."
        ),
        answer=("marker.txt",),
    ),
)


def _skip_unless_installed(agent: str) -> str:
    path = shutil.which(agent)
    if not path:
        pytest.skip(f"{agent} is not installed on this host")
    return path


@pytest.mark.parametrize("agent", sorted(AGENT_COMMANDS), ids=str)
@pytest.mark.parametrize("task", AGENT_TASKS, ids=lambda task: task.name)
def test_agent_task(anchorage: Anchorage, agent: str, task: AgentTask) -> None:
    _skip_unless_installed(agent)
    anchorage.seed(task.seed)

    command = tuple(part.format(prompt=task.prompt) for part in AGENT_COMMANDS[agent])
    result = anchorage.run(*command, timeout=AGENT_TIMEOUT)
    transcript = (result.stdout + result.stderr).lower()

    for expected in task.answer:
        assert expected.lower() in transcript, (
            f"{agent}/{task.name}: expected {expected!r} in the answer\n{transcript[-2000:]}"
        )
    for name, fragments in task.target_contains.items():
        path = anchorage.target / name
        assert path.exists(), (
            f"{agent}/{task.name}: {name} never reached the target\n{transcript[-2000:]}"
        )
        content = path.read_text()
        for fragment in fragments:
            assert fragment in content, (
                f"{agent}/{task.name}: {name} lacks {fragment!r}; it holds:\n{content}"
            )
    for name in task.target_missing:
        assert not (anchorage.target / name).exists(), (
            f"{agent}/{task.name}: {name} still exists on the target"
        )


@pytest.mark.parametrize("agent", sorted(AGENT_COMMANDS), ids=str)
def test_agent_starts_under_interception(anchorage: Anchorage, agent: str) -> None:
    """The cheapest possible check that each agent runs at all."""
    _skip_unless_installed(agent)
    result = anchorage.run(agent, "--version", timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "the agent printed no version"
