"""What an agent is configured with, before it has run anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Named for the type only: a flow that runs its agents here is the common one, and it
    # should not pay to import the half of coganchor that runs a session, nor the docker
    # client behind a container.
    from humanize.machines import MachineConfig

__all__ = ["AgentConfig", "anchored"]


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
      skills: The skills of its CLI this agent is to have, by the name the CLI knows each one
        under, or None for the CLI as it comes -- which is every skill it finds. Said as what
        the agent has rather than as what it has not, because that is what it is: an agent
        told which skills to have has exactly those, whatever is installed afterwards. Every
        backend here is told the other way round -- a CLI comes with its skills loaded and
        has to be talked out of one -- which :func:`humanize.agents.skills.leaving` works out
        by looking at what is installed.
    """

    model: str
    effort: str
    machine: MachineConfig | None = None
    skills: tuple[str, ...] | None = None


def anchored(target: str) -> MachineConfig | None:
    """The machine an agent's turns land on, named the way a target is written.

    A machine that is already running is the answer whoever is at a prompt has: they name
    where the work goes -- a container, a host, this machine -- and nothing is brought up or
    taken down for them. Here rather than beside the machines themselves so that a caller
    which may not name that layer can still say where an agent works.

    Args:
      target: Where the work lands, as `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT`
        or `local[:DIR]`, or "" for this machine.

    Returns:
      The machine to configure an agent with, or None to run its turns here.

    Raises:
      ValueError: If the target cannot be read, said where it is written rather than hours
        into the flow that was configured with it.
    """
    if not target:
        return None
    from humanize.coganchor import AnchorConfig
    from humanize.machines import AnchoredConfig

    return AnchoredConfig(anchor=AnchorConfig(target=target))
