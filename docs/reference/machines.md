# Machines

Where an agent's turns land. One setting on the agent's config, with three answers — and, for an
agent a [flow](/reference/flows) drives, the flow says whether it may be given any answer but the first.

The agent process always stays on **this** machine, whichever answer you give — keeping its
credentials, its state directory and its link to its model provider. What moves is the project
it reads and the commands it runs.

## The three answers

```python
from hmz.agents import ClaudeCodeAgentConfig
from hmz.coganchor import AnchorConfig
from hmz.machines import AnchoredConfig, DockerConfig

here    = ClaudeCodeAgentConfig(model=…, effort=…)
there   = ClaudeCodeAgentConfig(model=…, effort=…, machine=AnchoredConfig(
              anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")))
its_own = ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

It is **one** setting because it is one question. A machine that is already running and a
machine started for the agent are both answers to "where does this work land", and an agent has
one answer to that.

## Which agents may be moved at all

Whether that question may be asked of a given agent is the **[flow's](/reference/flows)** to say, and not
a setting anybody may reach for. A flow is written for one shape of work, and one whose agents
read this project cannot have one of them reading somebody else's. So a flow declares it beside
each agent it drives, exactly as it declares [the moments that agent must
run](/reference/flows#asking-for-an-agent-that-can-do-something):

```python
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated, Remote

class Agents(NamedTuple):
    builder: Annotated[AgentBase, Remote]                  # may be pointed at a machine
    tester: Annotated[AgentBase, Isolated("python:3.12")]  # a container of the flow's own
    reviewer: AgentBase                                    # here, and nowhere else
```

### A place that says nothing

Runs here, and **cannot be pointed anywhere**. This is a change: it used to be that anything
could be given a machine at the prompt. An agent that was configured with one and handed to such
a place is refused before the first turn, naming the flow that refused it:

```text
onbox: reviewer runs on this machine -- this flow does not say it works anywhere else, so it cannot be pointed at one
```

Most places are this one, and a flow that says nothing about where its agents work is a flow
whose agents work where it does.

### `Remote`

The only kind of place that may be pointed at a machine. *Which* machine is not the flow's
business — it is settled by whoever chose the agent, as a `machine=` on its config or on the
`where` row of the interface's own sheet for that agent — and it may be either of the two
answers below. A `Remote` place
that nobody pointed anywhere runs here, like any other.

`Remote` is the class itself, written beside the type. It takes no arguments and carries nothing:
all it says is that this is a place where the question may be asked.

### `Isolated("python:3.12")`

A container of the flow's own, and the one machine **nobody configures** — not the person at the
prompt, not the command line. The flow names the image, and the rest follows from it:

- the project directory is mounted into the container **at the path it already has here**, so a
  path is the same path on both sides and the work outlives the container;
- the agent goes on running **here**, with its own credentials and its own trajectory — what is
  isolated is the tools and the libraries a command finds, not the work;
- the work reaches the container through [coganchor](/reference/remote-execution), as a `docker://`
  target, which is the road every other machine's work takes too;
- it comes up on the agent's first turn and goes when the agent does, as
  [any of them does](#when-the-machine-comes-up-and-when-it-goes).

Which is [a container of the agent's own](#a-container-of-the-agent-s-own), settled where the
flow's declaration is read rather than where the agents are chosen. `hmz.agents.isolated`
is what it comes to, if the same thing is ever wanted by hand:

```python
from hmz.agents import isolated

isolated("python:3.12")              # DockerConfig(image="python:3.12", workspace=None)
isolated("python:3.12", "/srv/one")  # the same, holding that directory instead
```

An agent configured with a machine and handed to such a place is refused, since there was nothing
to answer — and so is one that has already opened a session, which is a conversation that cannot
be moved after the fact:

```text
onbox: tester works in a container of this flow's own, so there is nothing to point it at
/.../flow.py: tester ClaudeCodeAgent#1a2b3c4d has already opened a session
```

## This machine

The default, and nothing to configure. `machine=None`, `agent.anchor` is `None`, turns run as
ordinary local processes in whatever directory the flow was started in.

Nothing below is needed for this.

## A machine that is already running

An ssh host, a container someone else started, a machine left listening on a port, or another
directory on this machine standing in for one.

```python
from hmz.coganchor import AnchorConfig
from hmz.machines import AnchoredConfig

machine = AnchoredConfig(
    anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")
)
```

`AnchorConfig` is where every detail lives — the target, the workspace as the target has it,
what to keep local, where the agent's own network connections go. All of it, and what does and
does not cross, is in [Remote execution](/reference/remote-execution).

Nothing is brought up and nothing is taken down: the machine is somebody else's, and all this
says is that the agent's turns land there rather than here.

**Requirements:** Linux on x86-64 here; a POSIX system with a recent `python3` there. No root,
no compiler, no kernel module, nothing installed on the far end.

## A container of the agent's own

A container of the image you name, holding this project directory at the path it already has
and running as you — so the work it leaves behind is yours, in your own workspace, and
everything else is the image's.

```python
from hmz.machines import DockerConfig

machine = DockerConfig(image="python:3.12", workspace="/path/to/project")
```

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | The image to run. Needs a `python3` for the target half, plus whatever the agent is expected to reach for. |
| `workspace` | this directory | The project directory to give it. The directory **itself**, mounted — not a copy — so the work outlives the container. |

The container:

- runs as your uid and gid, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` [target](/reference/remote-execution#targets), and needs no port and no
  secret;
- is labelled `humanize=<your uid>`.

An image with no `python3` in it is refused as the container starts, rather than a turn later.

A flow that wants this for one of its own agents writes
[`Isolated("python:3.12")`](#isolated-python-3-12) beside the place instead of building a config:
the image is then the flow's, the workspace is the directory the flow is running in, and nobody
is asked anything.

**Requirements:** everything the answer above needs, plus the `docker` command and a daemon to
reach.

**Cleaning up after a flow that was killed outright:**

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

The label carries your uid, so this cannot reach past you on a machine several people share.

## When the machine comes up, and when it goes

The same for every kind:

- **Brought up on the agent's first turn**, not when the agent is constructed. Configuring an
  agent pulls no image and starts no container, so a flow that configures more agents than it
  drives pays only for the ones it drives.
- **Shared by every session that agent opens.** Its sessions are turns of one conversation each
  and must find the workspace as the last turn left it.
- **One machine per agent.** Two agents built from the same config get one machine each — the
  config is a setting, not the machine.
- **Taken down when the agent is collected**, or at exit for one held to the end. A machine
  that was already running is left running; only what was started here is stopped.
- **The workspace is left behind** either way.

## Choosing between them

| You want | Use |
| --- | --- |
| The agent to work in this checkout, as you | **this machine** |
| The work to happen on a bigger box, a GPU host, or a machine with the right toolchain | **already running**, `ssh://` |
| To keep reconnecting cheap across a long loop of short turns | **already running**, `tcp://` with a listening target |
| The agent confined to a toolchain that is not yours, without giving up your workspace | **a container of its own** |
| A flow's own agent confined that way, with nobody asked which image | `Isolated("…")` [beside the place](#isolated-python-3-12) |
| To confine what the agent may *do* | none of these — see below |

**Isolation here is about environment, not permission.** A container gives the agent a
different toolchain and a different filesystem, and mounts your workspace into it. It does not
stop the agent editing that workspace, and an `hmz anchor` export bounds which files a request
may name but does not confine the commands that request can run. Read
[Security](/guide/security).

## Writing a machine of your own

Two classes: the setting, and the machine it brings up.

```python
from dataclasses import dataclass

from hmz.coganchor import AnchorConfig
from hmz.machines import MachineBase, MachineConfig

@dataclass(frozen=True, kw_only=True)
class PodmanConfig(MachineConfig):
    image: str = "python:3.12"

    def create(self) -> "Podman":
        return Podman(self)

class Podman(MachineBase):
    _config: PodmanConfig

    def start(self) -> AnchorConfig:
        ...  # bring it up, and answer with the anchor that reaches it

    def stop(self) -> None:
        ...  # take down what start() brought up; leave the workspace behind
```

They are two classes because one config drives as many agents as it is given to, and each of
them gets a machine of its own. `start` must take down whatever it created if it cannot finish;
`stop` is called once per machine that was started and never for one that was not, so it only
has to answer for what `start` got as far as creating. `stop` has a do-nothing default, which is
what `AnchoredConfig` uses.

The contract is `src/hmz/machines/SPEC.md`.

## API summary

```python
from hmz.machines import (
    MachineConfig,   # the setting: .create() -> MachineBase
    MachineBase,     # the machine: .start() -> AnchorConfig, .stop() -> None
    AnchoredConfig,  # a machine that is already running
    Anchored,
    DockerConfig,    # a container started for the agent
    Docker,
)
```

And on the agent side:

```python
agent.anchor   # AnchorConfig | None -- where its turns land, bringing the machine up if it must
```

And what a flow writes beside a place, with the two shorthands that build the settings above:

```python
from hmz.agents import (
    Remote,     # this place may be pointed at a machine
    Isolated,   # this place is a container of the flow's own: Isolated("python:3.12")
    anchored,   # anchored("ssh://build-box") -> AnchoredConfig, from a target as it is written
    isolated,   # isolated("python:3.12") -> DockerConfig, which is what Isolated comes to
)
```
