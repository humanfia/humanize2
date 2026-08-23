"""Builds the throwaway world the demo GIFs are recorded in.

Run once as the image is built, so a tape spends its frames on humanize rather than on
`mkdir`. Everything it writes is invented here: a two-file project, a catalogue of models
nobody was asked for, trajectories that no agent ever produced, and the runs that would have
opened them -- written down by the code that writes down a real run rather than by a second
copy of its format kept here.

Nothing here reads the machine it runs on.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

#: The project every demo runs in. A name with nothing in it.
WORK = pathlib.Path("/work/demo")

#: Where humanize keeps what outlives one run, inside this container.
HOME = pathlib.Path("/root/.humanize")

#: Claude Code's home, inside this container. The trajectories below are written under it so
#: that `hmz trace collect` has something real to read -- real in shape, invented in content.
CLAUDE = pathlib.Path("/root/.claude")

#: The moment the invented work happened, so a rendered GIF does not change every day.
WHEN = datetime.datetime(2026, 7, 20, 10, 0, tzinfo=datetime.UTC)

#: The two conversations that were invented for it: one per run below.
SESSION = "0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9"
NIGHTLY = "5f6e7d8c-1a2b-3c4d-5e6f-708192a3b4c5"

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

#: And one that says it can be picked up where the last run of it left off, so that the runs
#: of this project are two kinds: one to read, and one to carry on.
NIGHTLY_FLOW = '''"""A loop that runs for as long as there is anything left on the list.

It says it can be picked up, so what it is keeping track of -- which round it is on, and what
it has already fixed -- outlives the run and is handed to the next one.
"""

from typing import Any

from hmz.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    (agent,) = agents
    state["rounds"] = state.get("rounds", 0) + 1
    while True:
        said = agent.new()(f"{task}. Round {state['rounds']}.")
        state.setdefault("fixed", []).append(said)
'''


#: How long after the first run the second one happened, so that two runs of one project
#: read as two moments rather than as one.
LATER = 6300


def _at(offset: float) -> str:
    """The fixture moment, offset by seconds, as Claude writes a timestamp."""
    return (WHEN + datetime.timedelta(seconds=offset)).isoformat()


def _stamped(offset: float) -> str:
    """The same, as humanize names an epic's directory."""
    moment = WHEN + datetime.timedelta(seconds=offset)
    return moment.strftime("%Y%m%dT%H%M%S.") + f"{moment.microsecond // 1000:03d}Z"


def _written(offset: float) -> str:
    """The same, as humanize writes a moment inside a record."""
    moment = WHEN + datetime.timedelta(seconds=offset)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


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
    for called, source in (("twice", FLOW), ("nightly", NIGHTLY_FLOW)):
        flows = WORK / ".humanize" / "flows" / called
        flows.mkdir(parents=True, exist_ok=True)
        (flows / "__init__.py").write_text(source, encoding="utf-8")

    if shutil.which("git") is None:
        return
    run = ("git", "-C", str(WORK))
    subprocess.run([*run, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*run, "config", "user.name", "demo"], check=True)
    subprocess.run([*run, "config", "user.email", "demo@example.invalid"], check=True)
    subprocess.run([*run, "add", "-A"], check=True)
    subprocess.run([*run, "commit", "-qm", "a calculator with a bug in it"], check=True)


def _turns(
    session: str, asked: str, doing: list[tuple[str, str, str]], began: float = 0
) -> list[Any]:
    """One invented Claude transcript: a prompt, and what the agent said it did about it.

    Args:
      session: The id Claude would have given the conversation.
      asked: What it was asked for.
      doing: One `(what it thought, what it said, the tool it reached for)` per turn.
      began: How long after the fixture moment this conversation happened.

    Returns:
      The records, in the order Claude writes them.
    """
    records: list[Any] = [
        {
            "type": "user",
            "timestamp": _at(began),
            "cwd": str(WORK),
            "sessionId": session,
            "promptId": "prompt-1",
            "message": {"role": "user", "content": asked},
        }
    ]
    for at, (thought, said, tool) in enumerate(doing, start=1):
        records.append(
            {
                "type": "assistant",
                "timestamp": _at(began + at * 2),
                "requestId": f"request-{at}",
                "effort": "high",
                "message": {
                    "id": f"message-{at}",
                    "model": "claude-opus-4-8",
                    "usage": {"input_tokens": 1840 * at, "output_tokens": 260 * at},
                    "content": [
                        {"type": "thinking", "thinking": thought},
                        {"type": "text", "text": said},
                        {
                            "type": "tool_use",
                            "id": f"call-{at}",
                            "name": tool,
                            "input": {"file_path": str(WORK / "calc.py")},
                        },
                    ],
                },
            }
        )
        records.append(
            {
                "type": "user",
                "timestamp": _at(began + at * 2 + 1),
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": f"call-{at}",
                            "content": "ok",
                            "is_error": False,
                        }
                    ],
                },
            }
        )
    return records


def _trajectories() -> None:
    """Writes the invented transcripts, so a trace has something to gather."""
    under = CLAUDE / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(WORK))
    under.mkdir(parents=True, exist_ok=True)
    held = {
        SESSION: _turns(
            SESSION,
            "work through TASK.md",
            [
                ("read the task first", "Reading TASK.md.", "Read"),
                ("add() subtracts", "add() subtracts. Fixing it.", "Edit"),
            ],
        ),
        NIGHTLY: _turns(
            NIGHTLY,
            "keep the tests green",
            [
                ("run them first", "Running the tests.", "Bash"),
                ("divide by zero", "divide() raises nothing. Fixing it.", "Edit"),
                ("and again", "Running the tests again.", "Bash"),
            ],
            began=LATER,
        ),
    }
    for session, records in held.items():
        (under / f"{session}.jsonl").write_text(
            "".join(json.dumps(one) + "\n" for one in records), encoding="utf-8"
        )


def _ticks(began: float) -> Any:
    """A clock for one invented run: its moments, a few seconds apart, from where it started.

    Args:
      began: How long after the fixture moment the run started.

    Returns:
      Something to call for each line the run writes.
    """
    held = iter(_written(began + at) for at in range(0, 2000, 3))
    return lambda: next(held)


class _Held:
    """One invented name, in the shape `uuid` hands one over in."""

    def __init__(self, hex_: str) -> None:
        self.hex = hex_


class _Invented:
    """Stands in for `uuid`, so that a run is named the way everything else here is named."""

    def __init__(self) -> None:
        self._held = iter(f"{at:06x}" for at in range(0xA1B2C3, 0xA1B2FF))

    def uuid4(self) -> _Held:
        """The next invented name."""
        return _Held(next(self._held))


@dataclass
class _Drove:
    """An agent that never ran, so the invented runs are written down as real ones are.

    What an epic asks of an agent is its name, its backend, what it was configured with and
    whether it was stopped -- so this is those, and nothing that could take a turn.
    """

    id: str
    backend: str
    config: Any
    epic: Any = None
    stopped: bool = False
    loaded: tuple[Any, ...] = field(default_factory=tuple)

    @property
    def provider(self) -> None:
        """The account this machine is signed into, which is the one nobody made."""
        return None


def _runs() -> None:
    """Writes down two runs of this project, as the code that writes down a real run.

    Invented, like everything else here -- the moments included, so that a rendered GIF says
    the same date tomorrow. What is not invented is the shape: this is `hmz.epic` writing
    its own record, linking each session to the transcript above and keeping what a flow that
    can be picked up left behind.
    """
    from hmz import epic as written_as
    from hmz.agents import AgentConfig

    moments = iter(
        [_stamped(0), _stamped(LATER)]
        + [_stamped(LATER + 600 + at) for at in range(20)]
    )
    written_as._stamp = lambda: next(moments)  # noqa: SLF001 -- the moment is invented too
    # And the six hex that tell two runs started in one millisecond apart, so that a demo
    # rendered again differs where humanize has changed and nowhere else.
    written_as.uuid = _Invented()

    config = AgentConfig(model="claude-opus-4-8", effort="high")
    written_as._now = _ticks(0)  # noqa: SLF001 -- each run happened when it happened
    first = _Drove(id="builder", backend="claude", config=config)
    with written_as.Epic("twice", [first], "work through TASK.md", WORK) as one:
        first.epic = one
        one.opened(first, SESSION)

    written_as._now = _ticks(LATER)  # noqa: SLF001
    second = _Drove(id="fixer", backend="claude", config=config)
    with written_as.Epic(
        "nightly", [second], "keep the tests green", WORK, resumable=True
    ) as two:
        second.epic = two
        two.opened(second, NIGHTLY)
        held = two.state("nightly")
        held["rounds"] = 3
        held["fixed"] = ["add() subtracted", "divide() raised nothing"]
        _profile(two.path)


#: What the invented run is to have spent its minutes on: an agent's turn is mostly other
#: programs, and a profiled run is what puts them on the same timeline as the turn.
PROGRAMS = (
    ("pytest", ("pytest", "-q"), LATER + 2.0, LATER + 7.4),
    ("ruff", ("ruff", "check", "."), LATER + 7.6, LATER + 8.1),
    ("git", ("git", "diff", "--stat"), LATER + 8.2, LATER + 8.4),
)


def _profile(at: pathlib.Path) -> None:
    """Writes the programs the invented run 'started', for the profile a trace draws.

    Args:
      at: The epic's own directory.
    """
    from hmz.tracing.profile import PROFILE

    lines: list[str] = []
    for pid, (name, argv, began, ended) in enumerate(PROGRAMS, start=41_207):
        said = {
            "pid": pid,
            "ppid": 41_206,
            "name": name,
            "argv": list(argv),
            "began": (WHEN + datetime.timedelta(seconds=began)).timestamp(),
            "seen": (WHEN + datetime.timedelta(seconds=began)).timestamp(),
            "ended": (WHEN + datetime.timedelta(seconds=ended)).timestamp(),
            "threads": [
                [
                    pid,
                    (WHEN + datetime.timedelta(seconds=began)).timestamp(),
                    (WHEN + datetime.timedelta(seconds=ended)).timestamp(),
                    ended - began,
                ]
            ],
        }
        lines.append(json.dumps({"event": "ran", **said}))
        lines.append(json.dumps({"event": "left", **said}))
    (at / PROFILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _account() -> None:
    """Writes down one account, so that a demo of the accounts has one to be about.

    A gateway at a reserved-invalid name, holding the words `not-a-real-token`: nothing here
    signs in to anything, and what is drawn of an account is the names of the variables it
    sets rather than what they are set to.
    """
    from hmz import providers

    providers.add(
        "claude",
        "gateway",
        "gateway",
        {
            "ANTHROPIC_BASE_URL": "https://gateway.example.invalid",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )


def _settings() -> None:
    """Answers what a first start asks, and turns profiling on for the demo project.

    Answered rather than left: humanize asks once whether it may report its own failures, and
    a demo that opened on that question would be a demo of that question -- and one keystroke
    away from answering it on camera. This machine has been asked and has said no, which is
    also the only answer a throwaway container should have.
    """
    from hmz.kept import Runs
    from hmz.settings import Settings

    Settings(WORK).answers(enable_sentry=False)
    Settings(WORK).profiles(on=True)
    # And what this project was last set up to run, so that what humanize remembers about a
    # directory is a directory it has been used in.
    Settings(WORK).remember("twice", ("",), [Runs("claude/claude-opus-4-8:high")])


if __name__ == "__main__":
    _models()
    _project()
    _trajectories()
    _runs()
    _account()
    _settings()
