"""What an agent is configured with, before it has run anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Named for the type only: a flow that runs its agents here is the common one, and it
    # should not pay to import the half of coganchor that runs a session, nor the docker
    # client behind a container.
    from humanize.machines import MachineConfig


@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    """The settings every session of an agent runs at.

    Frozen, because a session resumes under the settings it opened with: a config that changed
    mid-flow would silently split one conversation across two models.

    Attributes:
      model: The model name or identifier the backend is asked for.
      effort: The reasoning effort the backend is asked for, in the backend's own wording.
      machine: The machine the agent's work lands on, or None to work on this one. One that is
        already running is named by the anchor onto it; one started for the agent is started on
        the first turn and says where it is itself. The agent runs here either way, so its
        credentials and its trajectory stay where a flow can reach them; what moves is the
        project it reads and the commands it runs.
    """

    model: str
    effort: str
    machine: MachineConfig | None = None
