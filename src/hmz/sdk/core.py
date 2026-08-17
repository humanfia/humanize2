"""humanize as one object, which is what a command line, an interface and a daemon all hold.

Everything humanize does is done to one workspace: what was set up to run there, the runs that
have already happened there, and the flow that is running there now. The things that are not a
workspace's -- the agents written down under a name, the accounts they run as, where flows come
from -- are still reached from here, because there is one of each and one place to ask for it.

Each of them is fetched when it is asked for and not before. A command line that only lists the
agents kept under a name must not load the tracer, the sandbox and every coding agent driver
there is to do it, and `hmz anchor` must not load any of this at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import os
    from collections.abc import Sequence

    from pydantic import BaseModel

    from hmz.agents import AgentBase
    from hmz.backends import Profile
    from hmz.runner import Runner
    from hmz.sdk.accounts import Accounts
    from hmz.sdk.agents import Agents
    from hmz.sdk.cycles import Cycles
    from hmz.sdk.fallbacks import Fallbacks
    from hmz.sdk.flows import Flows, Flowverses
    from hmz.sdk.running import Run
    from hmz.settings import Settings

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
        self._agents: Agents | None = None
        self._accounts: Accounts | None = None
        self._fallbacks: Fallbacks | None = None
        self._cycles: Cycles | None = None

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
            from hmz.settings import Settings

            self._settings = Settings(
                Path(self._workspace) if self._workspace is not None else None
            )
        return self._settings

    @property
    def flows(self) -> Flows:
        """The flows there are to run, and the places they come from."""
        if self._flows is None:
            from hmz.sdk.flows import Flows

            self._flows = Flows()
        return self._flows

    @property
    def verses(self) -> Flowverses:
        """Where flows come from, which is the same store `/flowverses` walks."""
        return self.flows.verses

    @property
    def agents(self) -> Agents:
        """The agents written down under a name, to be reached for from any flow."""
        if self._agents is None:
            from hmz.sdk.agents import Agents

            self._agents = Agents()
        return self._agents

    @property
    def accounts(self) -> Accounts:
        """The accounts an agent may be run as, and what each backend runs as one."""
        if self._accounts is None:
            from hmz.sdk.accounts import Accounts

            self._accounts = Accounts()
        return self._accounts

    @property
    def fallbacks(self) -> Fallbacks:
        """Where a turn goes when the place taking it cannot take it at all."""
        if self._fallbacks is None:
            from hmz.sdk.fallbacks import Fallbacks

            self._fallbacks = Fallbacks()
        return self._fallbacks

    @property
    def cycles(self) -> Cycles:
        """The runs of this workspace that have already happened."""
        if self._cycles is None:
            from hmz.sdk.cycles import Cycles

            self._cycles = Cycles(self._workspace)
        return self._cycles

    def backends(self) -> tuple[Profile, ...]:
        """Every coding agent CLI humanize drives, whether or not it is installed here."""
        from hmz import backends

        return backends.profiles()

    def reports(self) -> bool:
        """Starts reporting humanize's own failures, where that has been answered yes.

        Returns:
          Whether anything is being reported. Nothing is by a machine nobody has been asked
          on: a run with nobody at a terminal is a run with nobody to ask, and silence is not
          an answer.
        """
        from hmz import telemetry

        return telemetry.start()

    def read(
        self, argv: list[str]
    ) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, str]:
        """Reads an `hmz exec` line into a flow, the agents, the task, and the flow's setup.

        Args:
          argv: The line, as `hmz exec` takes it.

        Returns:
          The flow's path, the agents to drive it with, the task, what to set the flow up
          with, and the image to run the whole of it in.

        Raises:
          SystemExit: If the line does not name a flow and an agent apiece, as argparse
            rejects it.
        """
        from hmz.runner import flow_and_agents

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
        from hmz.runner import Runner

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
        from hmz.sdk.running import Run

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
        flow, agents, task, config, container = self.read(argv)
        # Through a run, which is the one thing a flow being driven is: an SDK user who ran a
        # line and one who built a run are then holding the same thing.
        self.run(flow, agents, task, config, container=container).run()
