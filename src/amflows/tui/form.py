"""Filling a command in rather than typing it, for when you would have to look the flags up.

A command named with no arguments opens this, because that is the moment you did not know
what to write. What comes back out is the argument list the command line would have taken,
so there is one command underneath either way.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

__all__ = ["Field", "Form"]


@dataclass(frozen=True, slots=True)
class Field:
    """One thing to fill in, and how it reaches the command line.

    Attributes:
      name: What to call it on screen.
      flag: The option it becomes, or "" for a positional.
      hint: What it is, shown under the name.
      value: What it starts as.
      choices: What it may be, if it is a choice rather than free text.
      repeats: Whether commas in the value are separate values, each with its own flag.
    """

    name: str
    flag: str = ""
    hint: str = ""
    value: str = ""
    choices: Sequence[str] = ()
    repeats: bool = False


class Form(ModalScreen[list[str] | None]):
    """A command, filled in. Answers with the argument list, or None if it was dismissed."""

    CSS = """
    Form { align: center middle; }
    #sheet {
        width: 74;
        max-height: 80%;
        padding: 1 2;
        background: $panel;
        border: round $primary;
    }
    #sheet > Label.name { color: $text; text-style: bold; padding-top: 1; }
    #sheet > Label.hint { color: $text-muted; }
    #buttons { height: auto; align-horizontal: right; padding-top: 1; }
    #buttons Button { margin-left: 2; }
    """

    BINDINGS: ClassVar = [("escape", "dismiss_form", "cancel")]

    def __init__(self, command: str, fields: Iterable[Field]):
        """Initializes a form for one command.

        Args:
          command: The command being filled in, which titles the sheet.
          fields: What to fill in, in the order to ask for it.
        """
        super().__init__()
        self._command = command
        self._fields = list(fields)

    def compose(self) -> ComposeResult:
        """Lays the fields out, one labelled input or choice apiece."""
        with VerticalScroll(id="sheet"):
            yield Label(f"[b]/{self._command}[/b]", classes="name")
            for index, field in enumerate(self._fields):
                yield Label(field.name, classes="name")
                if field.hint:
                    yield Label(field.hint, classes="hint")
                if field.choices:
                    yield Select(
                        [(choice, choice) for choice in field.choices],
                        value=field.value or field.choices[0],
                        allow_blank=False,
                        id=f"field-{index}",
                    )
                else:
                    yield Input(value=field.value, id=f"field-{index}")
            with Horizontal(id="buttons"):
                yield Button("cancel", id="cancel")
                yield Button("run", variant="primary", id="ok")

    def on_mount(self) -> None:
        """Puts the cursor in the first thing to fill in."""
        if self._fields:
            self.query_one("#field-0").focus()

    def action_dismiss_form(self) -> None:
        """Leaves without running anything."""
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Answers with the command line the fields spell, or with nothing."""
        self.dismiss(self._argv() if event.button.id == "ok" else None)

    def on_input_submitted(self) -> None:
        """Enter anywhere in the sheet runs it, which is what enter is for."""
        self.dismiss(self._argv())

    def _argv(self) -> list[str]:
        """The fields as the argument list the command line would have been given.

        Returns:
          The arguments, with empty fields left out entirely.
        """
        argv: list[str] = []
        positional: list[str] = []
        for index, field in enumerate(self._fields):
            # Both an input and a choice answer to `value`, which is all that is wanted here.
            widget = self.query_one(f"#field-{index}")
            value = str(getattr(widget, "value", "") or "").strip()
            if not value:
                continue
            if not field.flag:
                positional.append(value)
            elif field.repeats:
                for one in value.split(","):
                    if one.strip():
                        argv += [field.flag, one.strip()]
            else:
                argv += [field.flag, value]
        return argv + positional


def fields_for(command: str) -> list[Field]:
    """What a command asks for, when it is asked for with nothing.

    Args:
      command: The command, as `amflows` spells it.

    Returns:
      The fields to fill in, which is nothing at all for a command with no form of its own.
    """
    if command == "run":
        flows = sorted(_flows_here())
        return [
            Field(
                name="flow",
                flag="-f",
                hint="the Python file with a run(agents, task) in it",
                value=flows[0] if flows else "",
                choices=flows,
            ),
            Field(
                name="agents",
                flag="-a",
                hint="backend/model/effort, comma separated, one per agent the flow drives",
                value="claude/claude-opus-4-8/high",
            ),
            Field(name="task", hint="what to have them do"),
        ]
    if command == "collect":
        return [
            Field(name="workspace", hint="which directory, or blank for this one"),
            Field(name="session", flag="--session", hint="only these, comma separated"),
            Field(name="output", flag="--output", hint="where to write it"),
            Field(name="start", flag="--start", hint="e.g. 2 days ago"),
            Field(name="end", flag="--end", hint="e.g. yesterday 18:00"),
        ]
    if command == "anchor":
        return [
            Field(
                name="target",
                flag="--target",
                hint="ssh://HOST, docker://CONTAINER, tcp://HOST:PORT or local[:DIR]",
                value="local",
            ),
            Field(
                name="workspace",
                flag="--workspace",
                hint="the project directory as the target has it",
            ),
            Field(name="agent", hint="the agent to run there, e.g. claude"),
        ]
    return []


def _flows_here() -> Iterator[str]:
    """Every file below this directory that looks like a flow.

    Pruned as it descends rather than filtered afterwards: a checkout with a virtualenv in it
    holds thousands of Python files, and this runs while somebody is waiting for a sheet.

    Yields:
      The path of each file declaring a `run(agents` of its own.
    """
    for here, folders, files in os.walk("."):
        folders[:] = [
            folder
            for folder in folders
            if not folder.startswith(".") and folder != "__pycache__"
        ]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = Path(here, name)
            with contextlib.suppress(OSError):
                if "def run(agents" in path.read_text(errors="ignore"):
                    yield str(path)
