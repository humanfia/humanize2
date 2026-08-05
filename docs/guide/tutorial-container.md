# 17 · A container of its own

**Fifteen minutes.** Give an agent a toolchain that is not yours, without giving up your
workspace.

::: tip Before you start
[Two accounts of one CLI](/guide/tutorial-providers). This one needs `docker` on your `PATH` and a
daemon to reach, plus Linux on x86-64.
:::

## What you get

A container of the image you name, holding **this project directory at the path it already has**
and running as **you**. So the work it leaves behind is yours, in your own workspace, and
everything else is the image's.

The agent process stays on this machine — keeping its credentials and its link to its model
provider. Everything it *does* happens in the container. Which means the container needs no
network access to a model provider, and no login.

## Step 1 — the flow declares it

The usual way. The flow writes the image beside the place, and nobody is asked anything:

```python
# .humanize/flows/tested/__init__.py
"""Build here; run the suite in a container that has the right Python."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated
from hmz.flows import flow


class Agents(NamedTuple):
    """The two this drives, and the two places they work."""

    builder: AgentBase                                    # here, and nowhere else
    tester: Annotated[AgentBase, Isolated("python:3.12")] # a container of the flow's own


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

## Step 2 — run it

```sh
hmz exec -f tested -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "get the suite green"
```

The container is **brought up on the tester's first turn**, not when the agent is constructed —
so a flow that configures more agents than it drives pulls no image for the ones it does not.

At the prompt, the agents page of `/flow` reads it back on that agent's `where` row as `in a
container of python:3.12`, with `the flow settled this` beside it: the image is the flow's, and
nothing can point that agent anywhere else — including you.

## Step 3 — watch it come and go

While it runs, in another terminal:

```sh
docker ps --filter label=humanize=$(id -u)
```

The container:

- runs as **your uid and gid**, so files it writes are yours;
- has `HOME=/tmp`, away from the workspace, so what a command caches is not the project's;
- is reached as a `docker://` target, and needs no port and no secret;
- is labelled `humanize=<your uid>`.

It is taken down when the agent is collected, or at exit for one held to the end. **The workspace
is left behind** either way — it is the directory itself, mounted, not a copy.

::: details Cleaning up after a flow that was killed outright
```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```
The label carries your uid, so this cannot reach past you on a machine several people share.
:::

## Step 4 — choose the image properly

```python
Isolated("python:3.12")
```

The image needs:

1. **a `python3`** — for the target half. An image without one is refused as the container starts,
   rather than a turn later.
2. **whatever the agent is expected to reach for.** An agent told to run `pytest` in an image with
   no pytest will spend a turn discovering that.

A good image for this is one you already build for CI.

## Step 5 — an agent you point yourself

Where the flow says a place may be pointed anywhere — `Annotated[AgentBase, Remote]` — you can
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

| `DockerConfig` field | Default | |
| --- | --- | --- |
| `image` | `python:3.12` | the image to run |
| `workspace` | this directory | the directory **itself**, mounted |

Both refusals land before the first turn:

```text
onbox: reviewer runs on this machine -- this flow does not say it works anywhere else, so it cannot be pointed at one
onbox: tester works in a container of this flow's own, so there is nothing to point it at
```

## Step 6 — know what it does not do

::: warning Isolation here is about environment, not permission
A container gives the agent a different toolchain and a different filesystem, and **mounts your
workspace into it**. It does not stop the agent editing that workspace.
:::

To narrow what the agent may **do**, that is a different setting — and they compose:

```sh
hmz exec -f tested \
    -a claude/claude-opus-5:max \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "get the suite green"
```

Now the tester is in a container *and* cannot write anything. See
[Permissions](/features/permissions) and [Security](/guide/security).

## Step 7 — collecting a trace afterwards

A flow that ran in a container worked in a **mirror** rather than in this directory, so its
trajectories are not found by workspace:

```sh
hmz trace collect --session 0a1b2c3d
```

The run itself is still written down here — a [cycle](/features/tracing#what-a-run-writes-down)
belongs to the directory the flow ran in, and it is a directory of its own with a `sessions/` in
it. Each of those is named for whose session it was, what took its turns, which account they ran
as and what the backend called it:

```sh
run=$(ls -dt ~/.humanize/cycles/*/*/ | head -1)   # the run that just finished
ls "$run"sessions
```

```console
builder-claude@local-5f6e7d8c-1a2b-3c4d-5e6f-708192a3b4c5
tester-codex@local-0a1b2c3d-1a2b-3c4d-5e6f-708192a3b4c5
```

The id is the end of the name, and a leading part of it is enough — so the line above collects
the tester's, which is the session that worked in the container. At the prompt the same thing is
`/cycles`: enter on the run, then **where it is**.

## What you now know

- `Isolated("image")` beside the place is the flow's own container; nobody configures it.
- `DockerConfig` is the hand-built version, for a `Remote` place.
- Brought up on the first turn, taken down with the agent, workspace left behind.
- Environment, not permission.

## Next

[Another machine](/guide/tutorial-remote).
