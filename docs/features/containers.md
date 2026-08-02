# Containers

A container of the agent's own: an image you name, brought up on the agent's first turn and
removed with the agent, holding **this project directory at the path it already has** and running
as you.

So the work it leaves behind is yours, in your own workspace, and everything else is the image's.

## From a flow

The usual way. The flow writes the image beside the place, and nobody is asked anything:

```python
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated

class Agents(NamedTuple):
    """The two this drives."""

    tester: Annotated[AgentBase, Isolated("python:3.12")]   # a container of the flow's own
    reviewer: AgentBase                                     # here, and nowhere else
```

The image is the flow's, the workspace is the directory the flow is running in, and nothing can
point that agent anywhere else — including you. The `/agents` sheet reads it back on the model
step as `◉ in a container of python:3.12` and asks no third question.

## From Python

For an agent you build yourself, for a place the flow declared `Remote`:

```python
from hmz.machines import DockerConfig

ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | Needs a `python3` for the target half, plus whatever the agent will reach for. |
| `workspace` | this directory | The directory **itself**, mounted — not a copy — so the work outlives the container. |

An image with no `python3` in it is refused as the container starts, rather than a turn later.

## What the container is

- runs as **your uid and gid**, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` [target](/features/remote-execution), and needs no port and no
  secret;
- is labelled `humanize=<your uid>`.

## When it comes up, and when it goes

- **On the agent's first turn**, not when the agent is constructed. Configuring an agent pulls no
  image and starts no container.
- **Shared by every session that agent opens** — its sessions must find the workspace as the last
  turn left it.
- **One machine per agent.** Two agents built from the same config get one container each.
- **Taken down when the agent is collected**, or at exit for one held to the end.
- **The workspace is left behind** either way.

Cleaning up after a flow that was killed outright:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

The label carries your uid, so this cannot reach past you on a machine several people share.

## The agent is still here

This is the same arrangement as [remote execution](/features/remote-execution), with the far end
being a container instead of a host. The agent **process** stays on this machine — keeping its
credentials and its link to its model provider — and everything it *does* happens in the
container.

Which means: the container needs no network access to a model provider, and no login.

## Isolation here is about environment, not permission

A container gives the agent a different toolchain and a different filesystem, and mounts your
workspace into it. It does **not** stop the agent editing that workspace.

To narrow what the agent may do at all, that is [permissions](/features/permissions) — a
different setting, and they compose:

```sh
hmz exec -f tested \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=workspace-write \
    "get the suite green on 3.12"
```

Read [Security](/guide/security).

## Requirements

`docker` on your `PATH` and a daemon to reach, plus what remote execution needs: Linux on x86-64
here, and a `python3` in the image.

## See also

- [Tutorial: a container of its own](/guide/tutorial-container)
- [Remote execution](/features/remote-execution)
- [Machines reference](/reference/machines)
