"""What an isolation backend is: a machine started for an agent, and the anchor onto it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from humanize.coganchor import AnchorConfig


@dataclass(frozen=True, kw_only=True)
class IsolationConfig(ABC):
    """The settings the machine an agent's turns are confined to is built from.

    Frozen for the reason :class:`~humanize.janus.agents.config.AgentConfig` is: the machine is
    once and every session of the agent lands on it, so a setting changed afterwards would
    describe something that is not running.

    Attributes:
      workspace: The project directory to give that machine, defaulting to this one. It is the
        directory itself that goes there, not a copy of it, so the work outlives the machine.
    """

    workspace: str | None = None

    @abstractmethod
    def create(self) -> IsolationBase:
        """Builds the backend these settings describe, without starting anything yet.

        Returns:
          A backend that has yet to be started.
        """


class IsolationBase(ABC):
    """One isolated machine, from the turn that needs it until the agent holding it is gone."""

    def __init__(self, config: IsolationConfig) -> None:
        """Initializes a backend that has started nothing.

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

    @abstractmethod
    def stop(self) -> None:
        """Takes the machine down, leaving the workspace it was given behind.

        Called once per backend that started one, and never for a backend that did not, so it
        answers for whatever :meth:`start` had got as far as creating.
        """
