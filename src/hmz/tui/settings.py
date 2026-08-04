"""What was set up to run here, kept so that opening the interface again finds it that way.

One file under humanize's own home, holding one entry per workspace: the flow that was last
run there, and for each flow the workspace has run, what each of its agents was running. So a
project that is driven by one flow on two agents is driven by them again tomorrow, rather than
falling back to the default every time it is opened.

Kept per flow rather than per workspace alone, because what an agent runs is only meaningful
against the flow that drives it: a flow's second agent is its reviewer, and the flow before it
had no second agent at all. And keyed by what the flow calls each one where it calls them
anything, so that a flow which grows an agent in the middle does not silently hand the
reviewer's model to the builder.

Beside that, and in a file of its own, the agents that were written down to be used again:
what an agent is -- a CLI, an account, a model at an effort, what it may do -- is worth saying
once and reaching for from every flow that needs one like it. Those are not a workspace's, and
not any flow's: an agent kept under a name is a template, and a flow that imports one takes a
copy rather than a link.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz import home
from hmz.kept import Runs, read_back, written

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Settings"]


class Settings:
    """What one workspace was last set up to run, read once and written as it changes."""

    def __init__(self, workspace: Path | None = None) -> None:
        """Reads what was kept, if anything was.

        Args:
          workspace: Which project this is for, defaulting to this directory.
        """
        self._where = str(Path(workspace or Path.cwd()).resolve())
        self._file = home() / "settings.yaml"
        self._held = self._read()

    @property
    def flow(self) -> str:
        """The flow this workspace was last run with, or "" if it never has been."""
        return str(self._mine().get("flow") or "")

    def agents(
        self, flow: str, goal_defaults: Sequence[bool] | None = None
    ) -> list[Runs]:
        """What each agent of one flow was last running here, and where its turns landed.

        Args:
          flow: The flow they were driving.
          goal_defaults: What each agent place currently suggests. Used only for an entry
            written before goal selection was stored; with none, goals default on.

        Returns:
          One `cli/model:effort` apiece with the machine it was anchored to, what it may do
          without being asked and the account it ran as, in the order the flow takes them,
          and nothing at all for a flow this workspace has not run.
        """
        flows: dict[str, Any] = self._mine().get("flows") or {}
        kept: dict[str, Any] = flows.get(flow) or {}
        agents: dict[str, Any] = kept.get("agents") or {}
        said: list[Runs] = []
        for at, raw in enumerate(agents.values()):
            if not isinstance(raw, dict):
                return []  # written by hand and not the way this writes it
            # An anchor is what a workspace that has one has: an entry written before there
            # were any is a workspace whose agents work here, which is what leaving it out
            # already meant.
            runs = read_back(
                cast("dict[str, Any]", raw),
                goals=goal_defaults[at]
                if goal_defaults is not None and at < len(goal_defaults)
                else True,
            )
            if runs is None:
                return []
            said.append(runs)
        return said

    def flows(self) -> dict[str, Any]:
        """What every flow this workspace has run was last set up with, by flow.

        Read whole rather than a flow at a time because the menu that reads it turns between
        flows: what was remembered for the one being turned to is what that page shows, and
        going back to the file for each of them would be reading it once per keypress.

        Returns:
          One entry per flow, as it was written down, and nothing at all for a workspace that
          has run none.
        """
        held = self._mine().get("flows")
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def config(self, flow: str) -> dict[str, Any]:
        """How one flow was last set up here, for a flow that can be set up at all.

        Kept beside what its agents run and for the same reason: a flow of forty settings is
        not one to answer again every morning. Read back through the flow's own model rather
        than trusted, so a setting the flow has since dropped or renamed is one the model
        refuses rather than one that quietly comes back.

        Args:
          flow: The flow it was set up for.

        Returns:
          What was set, field by field, and nothing at all for a flow this workspace has
          never set up.
        """
        flows: dict[str, Any] = self._mine().get("flows") or {}
        kept: dict[str, Any] = flows.get(flow) or {}
        held = kept.get("config")
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def remember(
        self,
        flow: str,
        names: tuple[str, ...],
        models: Sequence[Runs],
        config: dict[str, Any] | None = None,
    ) -> None:
        """Writes down what this workspace is set up to run, so that it opens that way.

        Args:
          flow: The flow to run.
          names: What that flow calls each agent it drives, which is "" apiece for a flow
            that said how many it drives and nothing more.
          models: What each of them runs and where, in the order the flow takes them.
          config: What the flow itself was set up with, or None to leave whatever was kept
            for it as it was -- choosing the agents again is not a way of forgetting how the
            flow was set up.
        """
        agents: dict[str, dict[str, Any]] = {
            # By what the flow calls it, or by where it comes in the line when it has no name.
            (names[at] if at < len(names) and names[at] else str(at + 1)): written(runs)
            for at, runs in enumerate(models)
        }
        mine = self._mine()
        mine["flow"] = flow
        kept: dict[str, Any] = {"agents": agents}
        held = config if config is not None else self.config(flow)
        if held:
            kept["config"] = held
        mine.setdefault("flows", {})[flow] = kept
        self._write()

    def _mine(self) -> dict[str, Any]:
        """This workspace's entry, made if it is not there and replaced if it is not one."""
        if not isinstance(self._held.get("workspaces"), dict):
            self._held["workspaces"] = {}
        workspaces = cast("dict[str, Any]", self._held["workspaces"])
        if not isinstance(workspaces.get(self._where), dict):
            workspaces[self._where] = {}
        return cast("dict[str, Any]", workspaces[self._where])

    def _read(self) -> dict[str, Any]:
        """Everything the file holds, which is nothing at all when it cannot be read.

        A settings file that is missing, unreadable, or not what this writes is a workspace
        with nothing remembered about it -- never a reason not to open.
        """
        try:
            held = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return {}
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def _write(self) -> None:
        """Puts the whole file back, keeping every other workspace's entry as it was.

        A file nobody can write is not a reason to stop: what it holds is a convenience, and
        an interface that refused to run because it could not remember would be worse than
        one that forgets.
        """
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                yaml.safe_dump(self._held, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        except (OSError, yaml.YAMLError):
            return
