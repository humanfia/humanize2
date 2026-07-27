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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from humanize import home

__all__ = ["Settings"]


class Settings:
    """What one workspace was last set up to run, read once and written as it changes."""

    def __init__(self, workspace: Path | None = None):
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

    def agents(self, flow: str) -> list[str]:
        """What each agent of one flow was last running here.

        Args:
          flow: The flow they were driving.

        Returns:
          One `cli/model:effort` apiece, in the order the flow takes them, and nothing at all
          for a flow this workspace has not run.
        """
        kept = (self._mine().get("flows") or {}).get(flow) or {}
        said = []
        for agent in (kept.get("agents") or {}).values():
            if not isinstance(agent, dict):
                return []  # written by hand and not the way this writes it
            cli, model, effort = (
                agent.get("cli"),
                agent.get("model"),
                agent.get("effort"),
            )
            if not (cli and model and effort):
                return []
            said.append(f"{cli}/{model}:{effort}")
        return said

    def remember(self, flow: str, names: tuple[str, ...], models: list[str]) -> None:
        """Writes down what this workspace is set up to run, so that it opens that way.

        Args:
          flow: The flow to run.
          names: What that flow calls each agent it drives, which is "" apiece for a flow
            that said how many it drives and nothing more.
          models: One `cli/model:effort` apiece, in the order the flow takes them.
        """
        agents: dict[str, dict[str, str]] = {}
        for at, spec in enumerate(models):
            # Read from both ends, as a command line reads one: a model may hold slashes of
            # its own, while a CLI and an effort never do.
            cli, _, rest = spec.partition("/")
            model, _, effort = rest.rpartition(":")
            # By what the flow calls it, or by where it comes in the line when it has no name.
            named = names[at] if at < len(names) and names[at] else str(at + 1)
            agents[named] = {"cli": cli, "model": model, "effort": effort}
        mine = self._mine()
        mine["flow"] = flow
        mine.setdefault("flows", {})[flow] = {"agents": agents}
        self._write()

    def _mine(self) -> dict[str, Any]:
        """This workspace's entry, made if it is not there and replaced if it is not one."""
        if not isinstance(self._held.get("workspaces"), dict):
            self._held["workspaces"] = {}
        workspaces = self._held["workspaces"]
        if not isinstance(workspaces.get(self._where), dict):
            workspaces[self._where] = {}
        return workspaces[self._where]

    def _read(self) -> dict[str, Any]:
        """Everything the file holds, which is nothing at all when it cannot be read.

        A settings file that is missing, unreadable, or not what this writes is a workspace
        with nothing remembered about it -- never a reason not to open.
        """
        try:
            held = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return {}
        return held if isinstance(held, dict) else {}

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
