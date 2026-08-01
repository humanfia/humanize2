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

    Frozen for the reason :class:`~hmz.agents.config.AgentConfig` is: the machine is
    brought up once and every session of the agent lands on it, so a setting changed
    afterwards would describe something that is not running. It is also why the setting and
    the machine are two things: one config drives as many agents as it is given to, and each
    of them gets a machine of its own.
    """

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
