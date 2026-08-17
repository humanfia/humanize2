# Containers

A container gives an agent a toolchain that is not yours, without giving up your workspace.
Reach for it when the agent needs a toolchain or a filesystem you do not have. You name an
image, and humanize brings it up on the agent's first turn and removes it with the agent,
holding **this project directory at the path it already has** and running as you, so the work
it leaves behind is yours and everything else is the image's.

## Try it

1. Declare the container beside the tester's place in a flow, so the flow can run the suite in
   an image that has the right Python:

```python
# .humanize/flows/tested/__init__.py
"""Build here; run the suite in a container that has the right Python."""

from typing import Annotated, NamedTuple

from hmz.flows import Agent, Isolated, flow


class Agents(NamedTuple):
    """The two this drives, and the two places they work."""

    builder: Agent                                    # here, and nowhere else
    tester: Annotated[Agent, Isolated("python:3.12")]  # a container of the flow's own


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.builder.new()
    working(task, suppress=True)
    for _ in range(5):
        said = agents.tester("Run `python -m pytest -q` and report exactly what failed.",
                             suppress=True)
        if "passed" in said and "failed" not in said:
            return
        working(f"The suite says:\n\n{said}\n\nFix it.", suppress=True)
```

2. Run the flow:

```sh
hmz exec -f tested -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "get the suite green"
```

The container comes up on the tester's first turn, not when the agent is constructed.

3. While it runs, in another terminal:

```sh
docker ps --filter label=humanize=$(id -u)
```

You see the container, labelled `humanize=<your uid>`. It is taken down when the agent is
collected, and the workspace is left behind.

The tester runs the suite in its own container, the builder fixes what it reports, and
everything they produce lands in your workspace.

## The whole run in one container

The section above puts **one agent** in a container, which is what a flow says when only one
place needs a toolchain of its own. When the answer is *all of them*, say it once from outside
instead:

```sh
hmz exec -f ralph_loop --container python:3.12 -a claude/claude-opus-5:max "get the suite green"
```

One container is started for the run, **every** agent's turns land in it, and it goes when the
run ends. One container rather than one apiece, which is the point: the agents are working on
one thing, so what one of them writes is what the next one reads.

The project directory is mounted at the path it already has, so the flow's own `open()` reads
the same bytes a turn wrote. What a mounted directory does **not** answer for is a command: one
the flow runs is run by this machine's shell against this machine's tools, which is the thing a
container was reached for to avoid. So the flow asks:

```python
from hmz.flows import container, flow


@flow
def run(agents, task):
    agents[0](task)
    if (held := container()) is not None:
        said = held.run(["python", "-m", "pytest", "-q"])   # in the container
        held.write_text("last-run.txt", said.output)        # on the container's filesystem
```

`container()` answers `None` for a run on this machine, where a flow does what it always did.
What it answers otherwise reads and writes and runs on the far end: `read_text`, `write_text`,
`listdir`, `exists`, `mkdir`, `remove`, and `run`, which answers a `Ran` with `status`, `output`
and `ok`. See [Machines › The workspace as the flow reaches it](/reference/machines).

A place the **flow** declared `Isolated` is left where the flow put it — where an agent works is
the flow's to say, and this is a convenience rather than a way round that. The person at the
prompt is left alone too, taking no turn anywhere.

## From a flow

This is the usual way for one agent. The flow writes the image beside the place, and nobody is
asked anything:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, Isolated

class Agents(NamedTuple):
    """The two this drives."""

    tester: Annotated[Agent, Isolated("python:3.12")]  # a container of the flow's own
    reviewer: Agent                                    # here, and nowhere else
```

The image is the flow's, and the workspace is the directory the flow is running in. Nothing can
point that agent anywhere else, including you. The agents page of `/flow` reads it back on that
agent's `where` row as `in a container of python:3.12`, with `the flow settled this` beside it
— a row to read rather than one to open.

## From Python

Use this for an agent you build yourself, or for a place the flow declared `Remote`:

```python
from hmz.machines import DockerConfig

ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

| Field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | Needs a `python3` for the target half, plus whatever the agent will reach for. |
| `workspace` | this directory | The directory **itself**, mounted — not a copy — so the work outlives the container. |

An image with no `python3` in it is refused as the container starts, rather than a turn later.
The image also needs whatever the agent is expected to reach for: an agent told to run `pytest`
in an image with no pytest spends a turn discovering that. A good image is one you already
build for CI.

Where the flow says a place may be pointed anywhere (`Annotated[Agent, Remote]`), you can
hand it a container instead:

```python
from hmz.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.machines import DockerConfig
from hmz.runner import Runner

config = ClaudeCodeAgentConfig(
    model="claude-opus-5",
    effort="high",
    machine=DockerConfig(image="node:22", workspace="/home/me/code/myproject"),
)

Runner("movable", [ClaudeCodeAgent(config, name="builder")]).run("upgrade the toolchain")
```

Both refusals land before the first turn:

```text
onbox: reviewer runs on this machine -- this flow does not say it works anywhere else, so it cannot be pointed at one
onbox: tester works in a container of this flow's own, so there is nothing to point it at
```

## What the container is

- runs as **your uid and gid**, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` [target](/guide/remote-execution), and needs no port and no
  secret;
- is labelled `humanize=<your uid>`.

## When it comes up, and when it goes

- **On the agent's first turn**, not when the agent is constructed. Configuring an agent pulls
  no image and starts no container, so a flow that configures more agents than it drives pulls
  no image for the ones it does not.
- **Shared by every session that agent opens**, so its sessions find the workspace as the last
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

This is the same arrangement as [remote execution](/guide/remote-execution), with the far end a
container instead of a host. The agent **process** stays on this machine, keeping its
credentials and its link to its model provider. Everything it *does* happens in the container,
so the container needs no network access to a model provider and no login.

Because the work happens in a **mirror** rather than in this directory, the backend logs the
agent's turns under a path this project has never heard of. It makes no difference: the run
wrote down the ids of the sessions it opened, and that is what its trace is gathered by.

```sh
hmz trace collect
```

The run itself is still written down here. A [cycle](/guide/tracing#what-a-run-writes-down)
belongs to the directory the flow ran in, and it is a directory of its own with a `sessions/`
in it. Each session is named for whose it was, what took its turns, which account it ran as and
what the backend called it:

```sh
run=$(ls -dt ~/.humanize/cycles/*/*/ | head -1)   # the run that just finished
ls "$run"sessions
```

```console
builder-claude@local-5f6e7d8c-1a2b-3c4d-5e6f-708192a3b4c5
tester-codex@local-0a1b2c3d-1a2b-3c4d-5e6f-708192a3b4c5
```

The id is the end of the name, and a leading part of it is enough, so the line above collects
the tester's, which is the session that worked in the container. At the prompt the same thing
is `/cycles`: enter on the run, then **where it is**.

## Isolation here is about environment, not permission

A container gives the agent a different toolchain and a different filesystem, and mounts your
workspace into it. It does **not** stop the agent editing that workspace.

To narrow what the agent may do at all, that is [permissions](/guide/permissions) — a different
setting, and they compose:

```sh
hmz exec -f tested \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=workspace-write \
    "get the suite green on 3.12"
```

With `permission=read-only`, the tester is in a container *and* cannot write anything:

```sh
hmz exec -f tested \
    -a claude/claude-opus-5:max \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "get the suite green"
```

Read [Security](/guide/security).

## Requirements

You need `docker` on your `PATH` and a daemon to reach, plus what remote execution needs: Linux
on x86-64 here, and a `python3` in the image.

## See also

- [Remote execution](/guide/remote-execution)
- [Machines reference](/reference/machines)
- [Permissions](/guide/permissions)
- [Security](/guide/security)
