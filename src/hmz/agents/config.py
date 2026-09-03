"""What an agent is configured with, before it has run anything."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Named for the type only: a flow that runs its agents here is the common one, and it
    # should not pay to import the half of coganchor that runs a session, nor the docker
    # client behind a container.
    from hmz.machines import MachineConfig

__all__ = [
    "PERMISSIONS",
    "SERVICE_TIERS",
    "AgentConfig",
    "AgentDefaults",
    "Forks",
    "Goal",
    "Isolated",
    "Remote",
    "anchored",
    "isolated",
]

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

#: How quickly a provider is asked to serve one agent, independent of how hard its model
#: reasons. Backends map these common meanings into their own request vocabulary and refuse
#: ``fast`` when they cannot express it exactly.
SERVICE_TIERS = ("default", "fast")


class Goal:
    """What a flow writes beside an agent it runs under the backend's own goal feature.

    `pursue` is the agent keeping itself going toward an objective it decides for itself is
    met, and four backends have it. A flow built on that is not a flow any agent can drive,
    so it says which of its agents has to have one, by writing this where it declares them::

        class Agents(NamedTuple):
            worker: Annotated[AgentBase, Goal]

    and an agent whose backend has no goal feature is refused before the first turn rather
    than raising in the middle of one, which is where a loop would otherwise find out.
    """


class Forks:
    """What a flow writes beside an agent it will branch a conversation of.

    `Session.fork` branches an already-open conversation into an independent one, preserving
    the parent's prefix for the backend's own cache. Only Claude and Codex have a native
    history operation for it, so a flow built on it is not a flow any agent can drive. It says
    which of its agents has to have one, by writing this where it declares them::

        class Agents(NamedTuple):
            worker: Annotated[AgentBase, Forks]

    and an agent whose backend has no native fork is refused before the first turn rather than
    raising in the middle of one, which is where a loop would otherwise find out.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefaults:
    """The initial goal availability offered for one place in a flow.

    This is only an input to agent selection. Once an agent is chosen, the effective value
    lives in :attr:`AgentConfig.goals` and can be changed independently in the picker.

    Attributes:
      goals: Whether a newly selected agent starts with backend goals available.
    """

    goals: bool = True


class Remote:
    """What a flow writes beside an agent that may be pointed at another machine.

    Where an agent's turns land is not a setting anybody may reach for: a flow is written for
    one shape of work, and one whose agents read this project cannot have one of them reading
    somebody else's. So a flow says which of its agents may be sent elsewhere, by writing this
    where it declares them::

        class Agents(NamedTuple):
            builder: Annotated[AgentBase, Remote]
            reviewer: AgentBase

    and only that one may be given a machine. The others run here, whatever anybody chooses.
    """


@dataclass(frozen=True, slots=True)
class Isolated:
    """What a flow writes beside an agent that is to work in a container of its own.

    A machine nobody configures: the flow says the image, humanize starts the container, the
    project directory is mounted into it at the path it already has, and the agent -- which
    goes on running here, with its own credentials and its own trajectory -- reaches it
    through coganchor. What is isolated is the tools and the libraries a command finds, not
    the work::

        class Agents(NamedTuple):
            tester: Annotated[AgentBase, Isolated("python:3.12")]

    Attributes:
      image: The image to run, which needs a `python3` for coganchor's target half and
        whatever else the flow expects the agent to reach for.
    """

    image: str = "python:3.12"


@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    """The settings every session of an agent runs at.

    Frozen, because a session resumes under the settings it opened with: a config that changed
    mid-flow would silently split one conversation across two models.

    Attributes:
      model: The model name or identifier the backend is asked for.
      effort: The reasoning effort the backend is asked for, in the backend's own wording.
      service_tier: How quickly the provider is asked to serve the same model and effort, as
        one of :data:`SERVICE_TIERS`. ``fast`` buys lower latency rather than less reasoning.
      machine: The machine the agent's work lands on, or None to work on this one. One that is
        already running is named by the anchor onto it; one started for the agent is started on
        the first turn and says where it is itself. The agent runs here either way, so its
        credentials and its trajectory stay where a flow can reach them; what moves is the
        project it reads and the commands it runs.
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
      goals: Whether backend goals are available to this agent. This is always an explicit
        on/off setting; a flow may suggest the initial picker value with `AgentDefaults`, but
        that suggestion is resolved before the agent is constructed.
      web_search: Whether this agent may search the web. On, because that is what a coding
        agent has always been able to do and what most work wants; off is a choice, and is
        made where the agents are chosen -- a run that must read only this repository, one
        under a rate limit somebody is paying per query on, one whose answers have to be
        reproducible tomorrow. It is said the same way on every backend that can be told, in
        both directions rather than only one: a CLI whose own web search is off until it is
        asked for is asked for it here, so that on means the same thing wherever it is read.
        A backend with no way of being told refuses it off, the way one with no service tier
        to send refuses `fast` -- an agent that quietly went on searching would be a setting
        that lies.
    """

    model: str
    effort: str
    service_tier: str = "default"
    machine: MachineConfig | None = None
    permission: str = "bypass"
    provider: str = ""
    goals: bool = True
    web_search: bool = True

    def __post_init__(self) -> None:
        if self.service_tier not in SERVICE_TIERS:
            raise ValueError(
                "service_tier must be one of "
                f"{', '.join(SERVICE_TIERS)}, not {self.service_tier!r}"
            )


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
    from hmz.coganchor import AnchorConfig
    from hmz.machines import AnchoredConfig

    return AnchoredConfig(anchor=AnchorConfig(target=target))


def isolated(image: str, workspace: str | None = None) -> MachineConfig:
    """A container of the agent's own, holding the project directory it is to work in.

    What :class:`Isolated` comes to, built where a flow's declaration is read rather than by
    whoever is choosing agents: an isolated agent is one nobody configures, so nothing above
    this is asked which image or which directory.

    Args:
      image: The image to run.
      workspace: The directory to mount, defaulting to the one the flow is running in. It is
        mounted rather than copied, at the path it already has, so the work outlives the
        container.

    Returns:
      The machine to configure such an agent with.
    """
    from hmz.machines import DockerConfig

    return DockerConfig(image=image, workspace=workspace)
