"""A flow that is running, and the handful of things there are to do to one.

:class:`hmz.runner.Runner` is a flow loaded and handed its agents; running it is a call that
returns when the flow does, which for a loop meant to run for a week is not a call anything
holding a terminal can make. This is that call put on a thread of its own, with the two things
somebody watching a run asks for -- whether it is still going, and to stop it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import threading

    from hmz.agents import AgentBase
    from hmz.runner import Runner

__all__ = ["Run"]


class Run:
    """One run of one flow: the agents driving it, and how it ends."""

    def __init__(self, runner: Runner, task: str) -> None:
        """Holds a loaded flow and what it is to have its agents do.

        Nothing is started here: a run is started by :meth:`start`, or run to its return by
        :meth:`run`, so that whoever made one chooses which of the two they are holding.

        Args:
          runner: The flow, loaded and handed the agents it declared.
          task: What the flow is to have them do.
        """
        self._runner = runner
        self._task = task
        self._thread: threading.Thread | None = None
        self._raised: BaseException | None = None

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent this drives, the person the flow talks to among them."""
        return self._runner.agents

    @property
    def running(self) -> bool:
        """Whether the flow is still going, which is False before it is started."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def raised(self) -> BaseException | None:
        """Whatever the flow raised, for a run started on a thread of its own and now over."""
        return self._raised

    def run(self) -> None:
        """Runs the flow here, until it returns.

        Raises:
          BaseException: Whatever the flow raised, as it raised it.
        """
        self._runner.run(self._task)

    def start(self) -> None:
        """Starts the flow on a thread of its own, and returns at once.

        One run in a container at a time, per process: the container a run works in is the
        process's, since a flow that called another is one run working in one place -- so two
        of these started at once with an image between them would be two runs reaching for
        one container. Runs on this machine have no such thing between them. The second of
        two is refused where the container is settled, which is on the thread this starts --
        so what says so is :attr:`raised` rather than this call, and a caller holding two
        runs in containers has to read it. :meth:`run` raises it where it stands.

        Raises:
          RuntimeError: If it has already been started.
        """
        import threading

        if self._thread is not None:
            raise RuntimeError("this run has already been started")
        self._thread = threading.Thread(
            target=self._drives, name="humanize-run", daemon=True
        )
        self._thread.start()

    def _drives(self) -> None:
        """Runs the flow, keeping whatever it raised for whoever asks afterwards."""
        try:
            self._runner.run(self._task)
        except BaseException as why:  # noqa: BLE001 -- kept rather than swallowed
            self._raised = why

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the flow to end.

        Args:
          timeout: How long to wait, or None for as long as it takes.

        Returns:
          Whether it has ended.
        """
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def stop(self) -> None:
        """Tells every agent to take no further turn, so the loop ends rather than handing on.

        The turn running now is closed out first: a flow told to stop unwinds in its own time.
        :meth:`close` is what does not wait for it.
        """
        self._runner.stop()

    def close(self) -> None:
        """Closes every conversation still open, which is the backend's process going.

        What the flow gets back is a turn that failed, the same thing it would have got had
        the agent fallen over by itself. The last thing there is to do about a run.
        """
        import contextlib

        for agent in self.agents:
            for session in agent.sessions:
                with contextlib.suppress(Exception):
                    session.close()
