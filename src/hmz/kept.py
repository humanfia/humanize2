"""What an agent is, written down, and the ones written down under a name.

An agent is a CLI, an account, a model at an effort, what it may do and the machine its work
lands on -- and not the skills it carries, which are its CLI's own. That is worth saying once
and reaching for from every
flow that wants one like it, so the ones said under a name are a file of humanize's own --
not a workspace's, since none of that is a thing about the project it happens to be working
in, and not any flow's, since a flow that imports one takes a copy rather than a link.

Here rather than beside the interface because both ways in read it: the interface's `/agents`
walks these, and `hmz agents` says the same store as arguments. One place a thing is kept is
one place it is kept, whichever way somebody reached it -- and a command line that had to load
a terminal interface to read a file of six lines would be paying for a layer it does not use.

How one agent goes into a file is here for the same reason twice over: the file of the ones
kept under a name and the file of what each workspace was last set up to run write an agent
the same way, and two places writing one shape is two places to drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple, cast

import yaml

from hmz import home

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = ["Kept", "Runs", "Templates", "read_back", "written"]


class Runs(NamedTuple):
    """What one agent of a flow was set up to run, and where its turns land.

    Attributes:
      spec: The agent itself, as `cli/model:effort` -- the same word a command line takes.
      anchor: The machine its work lands on, as a target, or "" to work on this one.
      permission: What it may do without being asked, as one of `hmz.agents.PERMISSIONS`,
        or "" for the one an agent nobody has been asked about runs at.
      provider: The account its turns run as, by the name a provider of its CLI was made
        under, or "" to run as this machine is already signed in.
      goals: Whether backend goals are available. This is always an on/off answer; any
        suggestion attached to the flow's agent place is resolved before this is constructed.
      web_search: Whether it may search the web. On is what an agent nobody has been asked
        about does, and is written down all the same, for the reason `goals` is: it is an
        answer somebody gave rather than a silence.
    """

    spec: str
    anchor: str = ""
    permission: str = ""
    provider: str = ""
    goals: bool = True
    web_search: bool = True


class Kept(NamedTuple):
    """One agent written down under a name, to be imported from any flow that wants one.

    Beside :class:`Runs` because it is one: an agent is a CLI, an account, a model at an
    effort and what it may do, and a name is the only thing a saved one has that an agent of
    a flow has not -- a flow's is called what the flow calls it.

    Attributes:
      name: What it is called, which is what it is imported by and nothing else.
      runs: What it is.
    """

    name: str
    runs: Runs


def written(runs: Runs) -> dict[str, Any]:
    """One agent as it goes into a file, which is the shape both of these files hold.

    Read from both ends, as a command line reads one: a model may hold slashes of its own,
    while a CLI and an effort never do.

    Args:
      runs: What the agent is.

    Returns:
      Its fields, less any that says nothing -- an agent that works here, may do whatever an
      agent nobody was asked about may do, and runs as this machine is signed in is one every
      field of which is the field's own silence.
    """
    cli, _, rest = runs.spec.partition("/")
    model, _, effort = rest.rpartition(":")
    held: dict[str, Any] = {"cli": cli, "model": model, "effort": effort}
    if runs.anchor:
        held["anchor"] = runs.anchor
    if runs.permission:
        held["permission"] = runs.permission
    if runs.provider:
        held["provider"] = runs.provider
    # Both values are material: on may be an override of a workflow whose default is off, so
    # what is written down always records the explicit two-way choice. Web search is written
    # the same way and for the same reason.
    held["goals"] = runs.goals
    held["web_search"] = runs.web_search
    return held


def read_back(held: dict[str, Any], *, goals: bool = True) -> Runs | None:
    """One agent as it comes back off a file, or None where what is there is not one.

    Args:
      held: What the file holds for it.
      goals: Whether goals are available where the entry does not say -- which is every entry
        written before there was such a setting.

    Returns:
      The agent, or None for an entry written by hand and not the way these are written.
    """
    cli, model, effort = held.get("cli"), held.get("model"), held.get("effort")
    if not (cli and model and effort):
        return None
    # An entry that says nothing about what it may do runs at what an agent nobody has been
    # asked about has always run at; one that names no account runs as this machine is signed
    # in. A `skills` an older file holds is the CLI's own business now, and is read past.
    said = held.get("goals")
    searches = held.get("web_search")
    return Runs(
        f"{cli}/{model}:{effort}",
        str(held.get("anchor") or ""),
        str(held.get("permission") or ""),
        str(held.get("provider") or ""),
        said if isinstance(said, bool) else goals,
        # An entry written before there was such a setting is one whose agent searched the
        # web, that being what every agent did then.
        searches if isinstance(searches, bool) else True,
    )


class Templates:
    """The agents written down under a name, read once and written whole as they change.

    A file of humanize's own rather than of any workspace: an agent is a CLI, an account, a
    model at an effort and what it may do, and none of those is a thing about the project it
    happens to be working in. A flow that imports one takes a copy, so an agent tuned inside a
    flow does not quietly rewrite the one it was copied from.
    """

    def __init__(self, at: Path | None = None) -> None:
        """Reads what has been written down, if anything has.

        Args:
          at: The file to keep them in, defaulting to `agents.yaml` under humanize's home.
        """
        self._file = at or (home() / "agents.yaml")
        self._held = self._read()

    def all(self) -> list[Kept]:
        """Every agent written down, by name, in the order they are kept in.

        Returns:
          One apiece, and nothing at all where the file is missing, unreadable, or not what
          this writes -- none of which is a reason for the interface not to open.
        """
        agents = self._held.get("agents")
        if not isinstance(agents, dict):
            return []
        said: list[Kept] = []
        for name, raw in cast("dict[str, Any]", agents).items():
            if not isinstance(raw, dict):
                continue
            runs = read_back(cast("dict[str, Any]", raw))
            if runs is not None:
                said.append(Kept(str(name), runs))
        return said

    def find(self, name: str) -> Kept | None:
        """The one written down under a name, or None where none is."""
        return next((one for one in self.all() if one.name == name), None)

    def keep(self, agents: Sequence[Kept]) -> None:
        """Writes down exactly these, which is what the sheet was holding when it was saved.

        Whole rather than one at a time: a menu is answered once, and what it answers with is
        the list as it now is -- so one taken away there is one gone from here.

        Args:
          agents: What to keep, in the order to keep them.
        """
        self._held["agents"] = {one.name: written(one.runs) for one in agents}
        self._write()

    def _read(self) -> dict[str, Any]:
        """Everything the file holds, which is nothing at all when it cannot be read."""
        try:
            held = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return {}
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def _write(self) -> None:
        """Puts the file back. One nobody can write is a convenience lost, not a reason to stop."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                yaml.safe_dump(self._held, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        except (OSError, yaml.YAMLError):
            return
