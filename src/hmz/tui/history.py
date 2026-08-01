"""What has been typed here before, so that it can be had back by walking to it.

Everything said goes down, the task that starts a flow and the words put into one already
running alike: both are things a person wrote, and either may be worth writing again.

One file holds them all, under humanize' own home, and every line says which directory it was
typed in. What is walked is what was typed here, and everything ever typed anywhere where
nothing has been typed here yet -- so a directory nothing has been run in still has something
to walk back through. Which of the two it is, is settled when the interface starts rather than
looked up as you walk: the first thing typed here makes this a directory with a history, and a
history that changed under you mid-session would be one nobody could find their way back
through.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, cast

from hmz import home

__all__ = ["History"]


class History:
    """What was typed before, and where in it the editor has walked to."""

    def __init__(self, workspace: Path | None = None) -> None:
        """Reads what there is to walk, which is what was typed here if anything was.

        Args:
          workspace: Where the interface is running, defaulting to this directory.
        """
        self._where = Path(workspace or Path.cwd()).resolve()
        self._file = home() / "history.jsonl"
        #: Oldest first, and never the same thing twice running: a history is for finding
        #: what was said, and one thing said twice is one thing to find.
        self._said: list[str] = []
        said = self._read()
        here = [text for where, text in said if where == str(self._where)]
        for line in here or [text for _, text in said]:
            self._remember(line)
        #: Where the walk is, counting back from the newest, and what was being typed when it
        #: started -- which is given back on the way out, so that a key pressed by mistake
        #: cannot take a prompt with it.
        self._at = 0
        self._draft = ""

    def add(self, text: str) -> None:
        """Writes down something that was just said, and ends whatever walk was under way.

        Args:
          text: What was said, whether it started a flow or was put into one.
        """
        self._at, self._draft = 0, ""
        if not self._remember(text):
            return
        said = json.dumps(
            {
                "at": datetime.datetime.now(datetime.UTC).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                # Which is what tells this directory's from everyone else's, there being one
                # file and not one per project: a project is not a place to keep this.
                "workdir": str(self._where),
                "text": text,
            }
        )
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with self._file.open("a", encoding="utf-8") as stream:
                stream.write(said + "\n")
        except OSError:
            return  # a history nobody can write is not a prompt to lose

    def back(self, typed: str) -> str | None:
        """Walks one further back, keeping whatever was being typed to give back later.

        Args:
          typed: What is in the editor now, which is the draft if no walk is under way.

        Returns:
          What was said then, or None at the far end of what there is -- and None is the
          editor's own to do what it likes with.
        """
        if self._at >= len(self._said):
            return None
        if self._at == 0:
            self._draft = typed
        self._at += 1
        return self._said[-self._at]

    def forward(self) -> str | None:
        """Walks one nearer, and off the near end back to whatever was being typed.

        Returns:
          What was said then, the draft the walk started from once it is over, or None when
          there was no walk to be walking back from.
        """
        if self._at <= 0:
            return None
        self._at -= 1
        return self._draft if self._at == 0 else self._said[-self._at]

    def _remember(self, text: str) -> bool:
        """Takes one thing said into what there is to walk.

        Args:
          text: What was said.

        Returns:
          Whether it was worth keeping, which nothing and a repeat of the last one are not.
        """
        if not text.strip() or (self._said and self._said[-1] == text):
            return False
        self._said.append(text)
        return True

    def _read(self) -> list[tuple[str, str]]:
        """Reads everything ever typed, oldest first.

        Returns:
          Where each was typed and what was typed, as they were written. A line that is not
          one is skipped: this is written to while it is being read, by however many of these
          are open at once.
        """
        try:
            lines = self._file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            return []
        said: list[tuple[str, str]] = []
        for line in lines:
            try:
                held = json.loads(line)
            except ValueError:
                continue
            if not isinstance(held, dict):
                continue
            row = cast("dict[str, Any]", held)
            if isinstance(row.get("text"), str):
                said.append((str(row.get("workdir") or ""), row["text"]))
        return said
