"""What a machine is: the setting that names one, and the machine that setting brings up."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.coganchor import AnchorConfig


@dataclass(frozen=True, kw_only=True)
class MachineConfig(ABC):
    """Which machine an agent's turns land on, as a setting rather than as a machine.

    Frozen for the reason :class:`~hmz.coganchor.agents.config.AgentConfig` is: the machine is
    brought up once and every session of the agent lands on it, so a setting changed
    afterwards would describe something that is not running. It is also why the setting and
    the machine are two things: one config drives as many agents as it is given to, and each
    of them gets a machine of its own.
    """

    @property
    def capabilities(self) -> frozenset[str]:
        """What a machine of these settings comes to, before one has been brought up.

        Answered by the setting rather than by the machine, and so without starting
        anything: a flow written for work that has to happen somewhere isolated must be able
        to refuse a place that is not, and refusing it after an image has been pulled and a
        container started is refusing it a turn too late.

        The names are one shared vocabulary. Of a place: `remote` for work that lands through
        an anchor rather than as an ordinary process here -- which a `local:` target answers
        to as much as an `ssh://` one does, that being what standing in for a machine means;
        `isolated` for a place whose tools are the image's rather than this machine's;
        `managed` for one that was started for the agent and goes down with it; and `linux`
        or `darwin` for a platform the settings already settle. What a setting cannot promise
        it does not name here -- the platform of a machine that was already running is read
        from the handshake instead, and :attr:`MachineBase.capabilities` is where the
        declared answer and the observed one meet.

        Returns:
          The names this place answers to. Empty here, so that a machine says what it comes
          to rather than being read as coming to everything it never denied.
        """
        return frozenset()

    @abstractmethod
    def create(self) -> MachineBase:
        """Builds the machine these settings describe, without bringing it up yet.

        Returns:
          A machine that has yet to be started.
        """


class MachineBase(ABC):
    """One machine, from the turn that needs it until the agent holding it is gone."""

    def __init__(self, config: MachineConfig) -> None:
        """Initializes a machine that has started nothing.

        Args:
          config: What the machine is built from.
        """
        self._config = config
        self._seen: frozenset[str] = frozenset()

    @property
    def capabilities(self) -> frozenset[str]:
        """What this machine comes to, so far as anything has been able to tell.

        Its settings' answer, which was there to be read before it was brought up, together
        with whatever the machine itself has said since it was reached -- the platform it
        turns out to be running, which no setting can promise on its behalf.
        """
        return self._config.capabilities | self._seen

    def observe(self, anchor: AnchorConfig) -> frozenset[str]:
        """Asks the machine what it is, over the road a turn takes, and holds the answer.

        The handshake already carries the platform the target is running, so a machine that
        was reached at all has said which of `linux` and `darwin` it is. It is read here
        rather than declared because it cannot be known until something has connected -- and
        it is read against what the settings promised, so that a place which cannot serve
        what was asked of it fails as the machine starts rather than turns later.

        What it asks is what :func:`~hmz.coganchor.check` asks -- the handshake and then the
        workspace -- so a machine that answered but cannot serve the directory it was pointed
        at fails here too. That is the same bar `start` is held to, and it is one connection
        rather than two for a machine that has to make both checks anyway.

        Args:
          anchor: What reaches the machine, which is what :meth:`start` answers with.

        Returns:
          What the machine comes to now, the observed names included.

        Raises:
          OSError: If the machine cannot be reached, or has not got the workspace the anchor
            names.
          RuntimeError: If it is not the machine its settings promised. Which capability it
            could not serve is in the message: a place refused for being the wrong one is no
            use to whoever has to go and find another.
        """
        from hmz.coganchor import check
        from hmz.coganchor.proto import PLATFORMS, hello_capabilities

        seen = hello_capabilities(check(anchor))
        # The platform alone is checked, that being the only part of the vocabulary a
        # handshake speaks to: whether a machine is somebody else's, whose it is to take down
        # and what its tools are is settled by how it was reached, and asking the target
        # about any of them would be asking it to vouch for itself.
        missing = (self._config.capabilities & PLATFORMS) - seen
        if missing:
            raise RuntimeError(
                f"the machine at {anchor.target} cannot serve "
                f"{', '.join(sorted(missing))}: it says it is "
                f"{', '.join(sorted(seen)) or 'a platform this has no name for'}"
            )
        self._seen = seen
        return self.capabilities

    @abstractmethod
    def start(self) -> AnchorConfig:
        """Brings the machine up, ready for turns to be run against it.

        Returns:
          The anchor that reaches it, which is what an agent's turns run under.
        """

    def stop(self) -> None:  # noqa: B027  -- empty on purpose, and so not abstract
        """Takes down whatever :meth:`start` brought up, leaving the workspace behind.

        Does nothing by default: a machine that was already running when it was named is one
        nobody here is entitled to take down. Called once per machine that was started, and
        never for one that was not, so it answers for whatever `start` had got as far as
        creating.
        """
