# Machines

Where an agent's turns land. One setting on the agent's config, with three answers.

The agent process always stays on **this** machine, whichever answer you give — keeping its
credentials, its state directory and its link to its model provider. What moves is the project
it reads and the commands it runs.

## Table of Contents

- [The three answers](#the-three-answers)
- [This machine](#this-machine)
- [A machine that is already running](#a-machine-that-is-already-running)
- [A container of the agent's own](#a-container-of-the-agents-own)
- [When the machine comes up, and when it goes](#when-the-machine-comes-up-and-when-it-goes)
- [Choosing between them](#choosing-between-them)
- [Writing a machine of your own](#writing-a-machine-of-your-own)
- [API summary](#api-summary)

## The three answers

```python
from humanize.agents import ClaudeCodeAgentConfig
from humanize.coganchor import AnchorConfig
from humanize.machines import AnchoredConfig, DockerConfig

here    = ClaudeCodeAgentConfig(model=…, effort=…)
there   = ClaudeCodeAgentConfig(model=…, effort=…, machine=AnchoredConfig(
              anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")))
its_own = ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

It is **one** setting because it is one question. A machine that is already running and a
machine started for the agent are both answers to "where does this work land", and an agent has
one answer to that.

## This machine

The default, and nothing to configure. `machine=None`, `agent.anchor` is `None`, turns run as
ordinary local processes in whatever directory the flow was started in.

Nothing below is needed for this.

## A machine that is already running

An ssh host, a container someone else started, a machine left listening on a port, or another
directory on this machine standing in for one.

```python
from humanize.coganchor import AnchorConfig
from humanize.machines import AnchoredConfig

machine = AnchoredConfig(
    anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")
)
```

`AnchorConfig` is where every detail lives — the target, the workspace as the target has it,
what to keep local, where the agent's own network connections go. All of it, and what does and
does not cross, is in [Remote execution](remote-execution.md).

Nothing is brought up and nothing is taken down: the machine is somebody else's, and all this
says is that the agent's turns land there rather than here.

**Requirements:** Linux on x86-64 here; a POSIX system with a recent `python3` there. No root,
no compiler, no kernel module, nothing installed on the far end.

## A container of the agent's own

A container of the image you name, holding this project directory at the path it already has
and running as you — so the work it leaves behind is yours, in your own workspace, and
everything else is the image's.

```python
from humanize.machines import DockerConfig

machine = DockerConfig(image="python:3.12", workspace="/path/to/project")
```

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | The image to run. Needs a `python3` for the target half, plus whatever the agent is expected to reach for. |
| `workspace` | this directory | The project directory to give it. The directory **itself**, mounted — not a copy — so the work outlives the container. |

The container:

- runs as your uid and gid, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` [target](remote-execution.md#targets), and needs no port and no
  secret;
- is labelled `humanize=<your uid>`.

An image with no `python3` in it is refused as the container starts, rather than a turn later.

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
| To confine what the agent may *do* | none of these — see below |

**Isolation here is about environment, not permission.** A container gives the agent a
different toolchain and a different filesystem, and mounts your workspace into it. It does not
stop the agent editing that workspace, and an `hmz anchor` export bounds which files a request
may name but does not confine the commands that request can run. Read
[Security](../README.md#security).

## Writing a machine of your own

Two classes: the setting, and the machine it brings up.

```python
from dataclasses import dataclass

from humanize.coganchor import AnchorConfig
from humanize.machines import MachineBase, MachineConfig


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

The contract is `src/humanize/machines/SPEC.md`.

## API summary

```python
from humanize.machines import (
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
