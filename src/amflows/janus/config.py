"""What an agent is configured with, before it has run anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Named for the type only: an unanchored flow is the common one, and it should not pay to
    # import the half of coganchor that runs a session, nor the docker client behind isolation.
    from amflows.coganchor import AnchorConfig

    from .isolation import IsolationConfig


@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    """The settings every session of an agent runs at.

    Frozen, because a session resumes under the settings it opened with: a config that changed
    mid-flow would silently split one conversation across two models.

    Attributes:
      model: The model name or identifier the backend is asked for.
      effort: The reasoning effort the backend is asked for, in the backend's own wording.
      anchor: The machine the agent's work lands on, or None to work on this one. The agent
        itself runs here either way, so its credentials and its trajectory stay where a flow
        can reach them; what moves is the project it reads and the commands it runs.
      isolation: The machine to start for the agent and land its work on, or None to use one
        that is already running. It is an anchor the agent brings with it rather than finds:
        the backend starts the machine on the first turn and is the one that says where it is.
    """

    model: str
    effort: str
    anchor: AnchorConfig | None = None
    isolation: IsolationConfig | None = None

    def __post_init__(self) -> None:
        """Refuses a config that names two machines at once.

        Raises:
          ValueError: If both an anchor and an isolation are given. Each of them says where the
            work lands, and the agent has one answer to that.
        """
        if self.anchor is not None and self.isolation is not None:
            raise ValueError(
                "an agent is anchored or isolated, not both: an isolation is an anchor onto "
                "the machine it starts"
            )
