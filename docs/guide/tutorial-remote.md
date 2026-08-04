# 18 · Another machine

**Twenty minutes.** The agent runs here. Its commands run on the build box.

::: tip Before you start
[A container of its own](/guide/tutorial-container). You need Linux on x86-64 **here**, and a host
you can `ssh` to with a recent `python3` on it. Nothing is installed on the far end.
:::

## The model

```
     this machine                              the target
┌────────────────────┐                   ┌────────────────────┐
│  claude / codex …  │                   │                    │
│        ↓ syscalls  │                   │                    │
│  ┌──────────────┐  │   one channel     │  hmz anchor serve  │
│  │  supervisor  │──┼──────────────────▶│         ↓          │
│  └──────────────┘  │  ssh / docker /   │  files, processes, │
│   local mirror     │  tcp / a pipe     │  the network       │
└────────────────────┘                   └────────────────────┘
     credentials,                             the work
   the model provider
```

The agent needs **no plugin, no configuration and no cooperation**. It is told none of this and
takes part in none of it.

The workspace it works in is a **local mirror** of the target's copy, living at the workspace's own
path — so the paths the agent sees are the target's own.

## Step 1 — ask the target what it is

Before running anything:

```sh
hmz anchor --check --target ssh://build-box
```

```console
target      ssh://build-box
hostname    build-box
python      3.12.3 (pid 41207)
export      /home/me/code/myproject -> /home/me/code/myproject
workspace   /home/me/code/myproject (184 entries)
```

::: details It cannot connect
`ssh build-box` yourself first — `hmz anchor` uses your own ssh config, agent and keys and adds
nothing. Then check `python3 --version` there. See
[Troubleshooting](/guide/troubleshooting#the-target-cannot-be-reached).
:::

## Step 2 — run an agent against it

```sh
hmz anchor --target ssh://build-box claude
```

Everything after the agent's name is the agent's own:

```sh
hmz anchor --target ssh://gpu-01 codex exec "run the test suite"
```

Inside the workspace the agent sees the target: the same file names, contents, sizes, modes and
timestamps, at the same paths. A failure answers with the target's own error, not a local
approximation of it.

## Step 3 — know what crosses

**Reaches the target**

- File contents — pushed in full before any command runs, and again when the session ends.
- Structural changes — create, remove, rename, link, chmod — replayed there **first**, so the
  target's own error is what the agent sees.
- Commands, including helpers bundled with the agent itself, in the target's copy of the working
  directory.
- Whatever those commands reach on the network.

**Stays here**

- The agent's own executable and its re-execs.
- Its state directory. The ten known CLIs are known by name; any other agent keeping state inside
  the workspace has to be named with `--local-path`.
- Anything named `--local-path` or `--local-exec`.
- The agent's own network connections, so it can still reach its model provider.

```sh
hmz anchor --target ssh://build-box \
    --local-path /home/me/code/myproject/.venv \
    --local-exec /usr/bin/rg \
    claude
```

`--net remote` sends the agent's own connections to the target instead; `--net-allow HOST[:PORT]`
keeps named hosts local anyway. **Commands the agent spawns always use the target's network**,
whatever `--net` says.

## Step 4 — the workspace as the target has it

Where the project lives at a different path there:

```sh
hmz anchor --target ssh://build-box \
    --workspace /home/me/code/myproject \
    --remote-path /srv/build/myproject \
    claude
```

| Flag | |
| --- | --- |
| `--workspace` | the project directory as the agent should see it |
| `--remote-path` | where that workspace really lives on the target |
| `--shadow` | the local mirror directory — defaults to the workspace path, which is what makes the paths the agent sees the target's own |
| `--chdir` | where inside the workspace the agent starts, as the target names it |

## Step 5 — anchor a flow

The same thing from a flow: give the agent's config an anchored machine, and its turns land there
with no other change.

```python
# .humanize/flows/onbox/__init__.py
"""Build on the box, review here."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    builder: Annotated[AgentBase, Remote]   # may be pointed at a machine
    reviewer: AgentBase                     # here, and nowhere else


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.builder.new()
    working(task, suppress=True)
    for _ in range(5):
        working(agents.reviewer("Read the diff and say what is wrong.", suppress=True),
                suppress=True)
```

Then point the builder somewhere. At the prompt that is the **third step** of `/agents`, offered
only for a `Remote` place. It lists what this machine can see — each container running, each host
in your `~/.ssh/config` — and anything else is typed:

| Typed | Where the work goes |
| --- | --- |
| *(nothing)* | this machine |
| `docker://<container>` | a container that is already running |
| `ssh://<host>` | a host you can reach |
| `tcp://<host>:<port>` | a target listening there |

In Python:

```python
from hmz.coganchor import AnchorConfig
from hmz.machines import AnchoredConfig

machine = AnchoredConfig(
    anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")
)
```

**Every option of `hmz anchor` is a field of `AnchorConfig` and every field is an option** — a flow
spawns what an operator would have typed. Settings no session could run under are refused where
they are *written*, so a misspelled target is reported as the agents are configured rather than
hours into the loop.

## Step 6 — a session works in a directory the target names

For an anchored agent, `agent.new(cwd)` takes the **target's** path, and it must be inside the
workspace the anchor names:

```text
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

humanize puts the agent in this machine's mirror of that directory and tells the anchor to run the
work in the directory itself.

## Step 7 — where there is no ssh: serve a target

On the far machine:

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

Here:

```sh
hmz anchor --target tcp://build-box:7777 --workspace /srv/project --token "$SECRET" claude
```

A `tcp://` target is **cheap to reconnect**, which matters for a loop of short turns: a backend
whose turn runs as its own process reaches the target once per turn, and a socket is a great deal
less than an ssh session to bootstrap.

::: danger An open port is a shell on that machine
`--export` bounds which files a request may **name**. It does not confine the commands that
request can run. Give `--token` a real secret; listening on anything but loopback without one is
refused outright. Prefer `ssh://` or `docker://`, which need no port at all.
:::

## What is not guaranteed

Read [Remote execution › What is not
guaranteed](/reference/remote-execution#what-is-not-guaranteed) before you rely on this for
anything expensive. The short version: what a command changes on the target becomes visible to the
agent once the command **exits**, and a command that ran while the agent was writing the same file
may have run against what was there before.

## What you now know

- `--check` first, always.
- Four targets: `ssh://`, `docker://`, `tcp://`, `local`.
- The flow says which agents may be moved; `Remote` is the only kind that may.
- `--local-path` / `--local-exec` for what must stay here.

## Next

[humanize in CI](/guide/tutorial-ci).
