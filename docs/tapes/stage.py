"""Builds the throwaway world the demo GIFs are recorded in.

Run once as the image is built, so a tape spends its frames on humanize rather than on
`mkdir`. Everything it writes is invented here: a two-file project, a catalogue of models
nobody was asked for, and one trajectory that no agent ever produced.

Nothing here reads the machine it runs on.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import shutil
import subprocess

#: The project every demo runs in. A name with nothing in it.
WORK = pathlib.Path("/work/demo")

#: Where humanize keeps what outlives one run, inside this container.
HOME = pathlib.Path("/root/.humanize")

#: Claude Code's home, inside this container. The trajectory below is written under it so
#: that `hmz trace collect` has something real to read -- real in shape, invented in content.
CLAUDE = pathlib.Path("/root/.claude")

#: The moment the invented trajectory happened, so a rendered GIF does not change every day.
WHEN = datetime.datetime(2026, 7, 20, 10, 0, tzinfo=datetime.UTC)

SESSION = "0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9"

PROJECT = {
    "README.md": "# demo\n\nA tiny calculator, for the documentation's terminal demos.\n",
    "calc.py": 'def add(a, b):\n    """Adds two numbers."""\n    return a - b\n',
    "TASK.md": (
        "# Task\n\n"
        "- [ ] add, subtract, multiply, divide\n"
        "- [ ] divide by zero raises ValueError\n"
        "- [ ] a test file covering all four\n"
    ),
}

#: A flow of the project's own, so `hmz exec` has one to name that is not humanize's.
FLOW = '''"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
'''


def _at(offset: float) -> str:
    """The fixture moment, offset by seconds, as Claude writes a timestamp."""
    return (WHEN + datetime.timedelta(seconds=offset)).isoformat()


def _models() -> None:
    """Writes what each stand-in CLI 'said' it runs, so a prompt has a list to draw."""
    said = {
        "claude": [
            {
                "name": "claude-opus-4-8",
                "efforts": ["max", "xhigh", "high", "medium", "low"],
            },
            {"name": "claude-sonnet-4-8", "efforts": ["high", "medium", "low"]},
        ],
        "codex": [
            {"name": "gpt-5.6-sol", "efforts": ["xhigh", "high", "medium", "low"]},
        ],
    }
    at = HOME / "models"
    at.mkdir(parents=True, exist_ok=True)
    for cli, models in said.items():
        (at / f"{cli}.json").write_text(
            json.dumps(
                {
                    "asked": WHEN.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "models": [{**one, "swarms": False} for one in models],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _project() -> None:
    """Writes the project, and commits it where there is a git to commit it with."""
    WORK.mkdir(parents=True, exist_ok=True)
    for name, text in PROJECT.items():
        (WORK / name).write_text(text, encoding="utf-8")
    # A flow is a directory: the `__init__.py` that is the flow, and whatever it brings.
    flows = WORK / ".humanize" / "flows" / "twice"
    flows.mkdir(parents=True, exist_ok=True)
    (flows / "__init__.py").write_text(FLOW, encoding="utf-8")

    if shutil.which("git") is None:
        return
    run = ("git", "-C", str(WORK))
    subprocess.run([*run, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*run, "config", "user.name", "demo"], check=True)
    subprocess.run([*run, "config", "user.email", "demo@example.invalid"], check=True)
    subprocess.run([*run, "add", "-A"], check=True)
    subprocess.run([*run, "commit", "-qm", "a calculator with a bug in it"], check=True)


def _trajectory() -> None:
    """Writes one invented Claude transcript, so `hmz trace collect` has something to gather."""
    under = CLAUDE / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(WORK))
    under.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "type": "user",
            "timestamp": _at(0),
            "cwd": str(WORK),
            "sessionId": SESSION,
            "promptId": "prompt-1",
            "message": {"role": "user", "content": "work through TASK.md"},
        },
        {
            "type": "assistant",
            "timestamp": _at(2),
            "requestId": "request-1",
            "effort": "high",
            "message": {
                "id": "message-1",
                "model": "claude-opus-4-8",
                "usage": {"input_tokens": 1840, "output_tokens": 260},
                "content": [
                    {"type": "thinking", "thinking": "read the task first"},
                    {"type": "text", "text": "Reading TASK.md."},
                    {
                        "type": "tool_use",
                        "id": "call-read",
                        "name": "Read",
                        "input": {"file_path": str(WORK / "TASK.md")},
                    },
                ],
            },
        },
        {
            "type": "user",
            "timestamp": _at(4),
            "toolUseResult": {"stdout": PROJECT["TASK.md"]},
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call-read",
                        "content": PROJECT["TASK.md"],
                        "is_error": False,
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "timestamp": _at(6),
            "requestId": "request-2",
            "effort": "high",
            "message": {
                "id": "message-2",
                "model": "claude-opus-4-8",
                "usage": {"input_tokens": 2210, "output_tokens": 480},
                "content": [
                    {"type": "text", "text": "add() subtracts. Fixing it."},
                    {
                        "type": "tool_use",
                        "id": "call-edit",
                        "name": "Edit",
                        "input": {"file_path": str(WORK / "calc.py")},
                    },
                ],
            },
        },
        {
            "type": "user",
            "timestamp": _at(9),
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "call-edit", "content": "ok"}
                ],
            },
        },
    ]
    (under / f"{SESSION}.jsonl").write_text(
        "".join(json.dumps(one) + "\n" for one in records), encoding="utf-8"
    )


if __name__ == "__main__":
    _models()
    _project()
    _trajectory()
