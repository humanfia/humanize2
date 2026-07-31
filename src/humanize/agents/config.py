"""What an agent is configured with, before it has run anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Named for the type only: a flow that runs its agents here is the common one, and it
    # should not pay to import the half of coganchor that runs a session, nor the docker
    # client behind a container.
    from humanize.machines import MachineConfig

__all__ = ["PERMISSIONS", "AgentConfig", "anchored"]

#: What an agent may do without being asked, loosest last. Named the way these CLIs name them
#: rather than in a vocabulary of humanize's own, so that a rung reads as the thing it is
#: wherever it is shown. Every backend has a ladder of its own and none of them has the same
#: four rungs, so these are the question rather than any one CLI's answer, and each driver
#: says which of its own settings it reaches for:
#:
#: - `read-only`: it may look at anything and change nothing -- no edits, no commands.
#: - `workspace-write`: it may change the workspace it was given, and is stopped at the edge
#:   of it.
#: - `auto`: it may reach for anything, and what it asks for is granted -- which is where a
#:   hook hung on `PERMISSION_REQUEST` gets a say, since that is the one moment a backend
#:   actually waits on.
#: - `bypass`: nothing is asked and nothing is checked, which is what an unattended flow has
#:   always run its agents at.
#:
#: A backend with no sandbox of its own cannot tell `workspace-write` from `auto`, and says so
#: where it maps them rather than pretending to a rung it has not got.
PERMISSIONS = ("read-only", "workspace-write", "auto", "bypass")


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
      permission: What this agent may do without being asked, as one of :data:`PERMISSIONS`.
        `unchecked` because that is what a flow driving an agent unattended has always run it
        at: a flow watches its agent rather than gating it, and a turn waiting on an approval
        nobody is there to give is a flow that has stopped. Anything tighter is a choice, and
        is made where the agents are chosen.
      provider: Which account this agent's turns run as, by the name a provider of its CLI was
        made under, or "" for the CLI as whoever is at this machine already runs it. It is a
        setting of the agent rather than of the flow because it is the agent that signs in:
        two agents of one CLI, one on a subscription and one on somebody's gateway, are two
        accounts running at once, each refreshing its own token and neither able to read the
        other's -- which is what a provider is for.
    """

    model: str
    effort: str
    machine: MachineConfig | None = None
    skills: tuple[str, ...] | None = None
    permission: str = "bypass"
    provider: str = ""


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
