"""humanize as one object, which is what a command line, an interface and a daemon all hold.

Everything humanize does is done to one workspace: what was set up to run there, the runs that
have already happened there, and the flow that is running there now. The things that are not a
workspace's -- the accounts agents run as, where flows come from -- are still reached from
here, because there is one of each and one place to ask for it.

The front door of :mod:`hmz.runtime` and reached by its name: a command line names the runtime
and holds this, a daemon holding a run apart from a terminal holds it too and the interface it
holds reaches it through that daemon, and :mod:`hmz.sdk` is the same object handed to whoever
is calling humanize from outside. One list of what humanize can do rather than one per way in.

Each of them is fetched when it is asked for and not before. A command line that only lists the
places flows come from must not load the tracer, the sandbox and every coding agent driver
there is to do it, and `hmz internal anchor` must not load any of this at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import os
    from collections.abc import Sequence

    from pydantic import BaseModel

    from hmz.coganchor.agents import AgentBase
    from hmz.coganchor.backends import Profile
    from hmz.runtime.doing.accounts import Accounts
    from hmz.runtime.doing.epics import Epics
    from hmz.runtime.doing.fallbacks import Fallbacks
    from hmz.runtime.doing.flows import Flows, Flowverses
    from hmz.runtime.doing.running import Run
    from hmz.runtime.runner import Runner
    from hmz.runtime.settings import Settings

__all__ = ["Hmz"]


class Hmz:
    """One workspace, and everything humanize can be asked to do in it."""

    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None:
        """Holds the workspace, and nothing else until something is asked of it.

        Args:
          workspace: The project directory this is about, or None for wherever humanize is
            being run. Kept exactly as it was given: a workspace nobody named is one that
            follows a flow which changes directory, and one that was named is the directory
            it named, spelled the way it was named.
        """
        self._workspace: str | os.PathLike[str] | None = workspace
        self._settings: Settings | None = None
        self._flows: Flows | None = None
        self._accounts: Accounts | None = None
        self._fallbacks: Fallbacks | None = None
        self._epics: Epics | None = None

    @property
    def workspace(self) -> Path:
        """The project directory this is about."""
        return Path(self._workspace) if self._workspace is not None else Path.cwd()

    @property
    def home(self) -> Path:
        """Where humanize keeps what outlives one run of one flow."""
        from hmz import home

        return home()

    @property
    def settings(self) -> Settings:
        """What humanize remembers: what was set up to run here, and what is true everywhere."""
        if self._settings is None:
            from hmz.runtime.settings import Settings

            self._settings = Settings(
                Path(self._workspace) if self._workspace is not None else None
            )
        return self._settings

    @property
    def flows(self) -> Flows:
        """The flows there are to run, and the places they come from."""
        if self._flows is None:
            from hmz.runtime.doing.flows import Flows

            self._flows = Flows()
        return self._flows

    @property
    def verses(self) -> Flowverses:
        """Where flows come from, which is the same store `/flowverses` walks."""
        return self.flows.verses

    @property
    def accounts(self) -> Accounts:
        """The accounts an agent may be run as, and what each backend runs as one."""
        if self._accounts is None:
            from hmz.runtime.doing.accounts import Accounts

            self._accounts = Accounts()
        return self._accounts

    @property
    def fallbacks(self) -> Fallbacks:
        """Where a turn goes when the place taking it cannot take it at all."""
        if self._fallbacks is None:
            from hmz.runtime.doing.fallbacks import Fallbacks

            self._fallbacks = Fallbacks()
        return self._fallbacks

    @property
    def epics(self) -> Epics:
        """The runs of this workspace that have already happened."""
        if self._epics is None:
            from hmz.runtime.doing.epics import Epics

            self._epics = Epics(self._workspace)
        return self._epics

    def backends(self) -> tuple[Profile, ...]:
        """Every coding agent CLI humanize drives, whether or not it is installed here."""
        from hmz.coganchor import backends

        return backends.profiles()

    def reports(self) -> bool:
        """Starts reporting humanize's own failures, where that has been answered yes.

        Returns:
          Whether anything is being reported. Nothing is by a machine nobody has been asked
          on: a run with nobody at a terminal is a run with nobody to ask, and silence is not
          an answer.
        """
        from hmz.runtime import telemetry

        return telemetry.start()

    def read(
        self, argv: list[str]
    ) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, bool]:
        """Reads an `hmz exec` line into a flow, the agents, the task, and the flow's setup.

        Args:
          argv: The line, as `hmz exec` takes it.

        Returns:
          The flow's path, the agents to drive it with in the order the flow takes them, the
          task, what to set the flow up with, and whether the line asked for the run to be
          written for a program rather than for a person.

        Raises:
          SystemExit: If the line does not name a flow and an agent apiece, as argparse
            rejects it.
        """
        from hmz.runtime.runner import flow_and_agents

        return flow_and_agents(argv)

    def runner(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
    ) -> Runner:
        """Loads a flow and hands it the agents it was written for.

        Args:
          flow: The Python file the flow is written in, or the name it is offered under.
          agents: The agents to hand it, as many as it declares.
          config: What it was set up with, for a flow that says it can be.
          resume: The run to pick up from, for a flow that says it can be picked up.
          container: The image to run the whole of it in, or "" for this machine.

        Returns:
          The flow, loaded, with the agents it drives in hand.

        Raises:
          NotAFlow: If the flow is not there, is not a flow, or takes other agents than these.
        """
        from hmz.runtime.runner import Runner

        return Runner(flow, agents, config, resume=resume, container=container)

    def run(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        task: str,
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
    ) -> Run:
        """A run of one flow, loaded and ready to be started.

        Args:
          flow: The Python file the flow is written in, or the name it is offered under.
          agents: The agents to hand it, as many as it declares.
          task: What the flow is to have them do.
          config: What it was set up with, for a flow that says it can be.
          resume: The run to pick up from, for a flow that says it can be picked up.
          container: The image to run the whole of it in, or "" for this machine.

        Returns:
          The run. Nothing has started: `run()` runs it here, `start()` on a thread.

        Raises:
          NotAFlow: If the flow is not there, is not a flow, or takes other agents than these.
        """
        from hmz.runtime.doing.running import Run

        return Run(self.runner(flow, agents, config, resume, container), task)

    def exec(self, argv: list[str]) -> None:
        """Runs the flow one `hmz exec` line names, on the agents it names, to its return.

        Args:
          argv: The line, as `hmz exec` takes it.

        Raises:
          NotAFlow: If the line names a flow that is not there, or takes other agents than it
            declares -- which is a line that was wrong before anything ran.
          SystemExit: If the line is not one argparse accepts.
        """
        # What the line said about who is reading is the command line's to act on: this
        # answers with the run itself rather than with a rendering of it.
        flow, agents, task, config, _ = self.read(argv)
        # Through a run, which is the one thing a flow being driven is: whoever ran a line
        # through this and whoever built a run are then holding the same thing.
        self.run(flow, agents, task, config).run()
