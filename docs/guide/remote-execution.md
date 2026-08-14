# Remote execution

Remote execution runs an agent on **this** machine while everything it does happens on a
**target**. The agent needs no plugin, no configuration and no cooperation: it is told none of
this and takes part in none of it. Reach for it when the work must happen on another machine
but the agent and its model credentials stay where you are.

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

The workspace the agent works in is a **local mirror** of the target's copy. The agent reads
and writes the mirror at local speed, and humanize keeps the two in step. The mirror lives at
the workspace's own path by default, so the paths the agent sees are the target's own.

## Try it

Ask the target what it is before you run anything against it:

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

The output names the target and shows the workspace it will mirror. Then run an agent against
it:

```sh
hmz anchor --target ssh://build-box claude
```

The agent runs here while its commands run on the build box. Inside the workspace it sees the
target: the same file names, contents, sizes, modes and timestamps, at the same paths. A
failure answers with the target's own error, not a local approximation of it.

Everything after the agent's name is the agent's own:

```sh
hmz anchor --target ssh://gpu-01 codex exec "run the test suite"
```

## Targets

| `--target` | |
| --- | --- |
| `ssh://HOST[:PORT]` | Bootstraps the target half over ssh and speaks to it on that connection's pipes. Uses your ssh config, agent and keys. **Nothing listens.** |
| `docker://CONTAINER` | Runs the target half inside a running container over `docker exec`. No port and no secret. |
| `tcp://HOST:PORT` | Connects to a target [left listening](/reference/remote-execution#serving-a-target). Cheap to reconnect, which matters for a loop of short turns. |
| `local[:DIR]` | Another directory on this machine, standing in for a remote one. Used for development and by the test suite. |

humanize ships the target half as a zipapp and caches it there by digest. It needs no
installation. The two halves refuse to run against each other if their versions disagree.

::: details It cannot connect
Run `ssh build-box` yourself first. `hmz anchor` uses your own ssh config, agent and keys, and
it adds nothing. Then check `python3 --version` there. See
[Troubleshooting](/guide/troubleshooting#the-target-cannot-be-reached).
:::

## What crosses, and what does not

**Reaches the target**

- File contents are pushed in full before any command runs, and again when the session ends.
- Structural changes — create, remove, rename, link, chmod — are replayed there *first*, so the
  target's own error is what the agent sees.
- Commands run in the target's copy of the working directory, including work helpers such as
  ripgrep that are bundled with the agent itself.
- Whatever those commands reach on the network.

**Stays here**

- The agent's own runtime executables and re-execs. For an npm-installed Codex, that includes
  Node, the native CLI and its code-mode host.
- Its state directory. humanize knows the ten known CLIs by name — `agy`, `claude`, `codex`,
  `dsh`, `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen` — and its own `~/.humanize`. Any
  other agent that keeps state inside the workspace has to be named with `--local-path`.
- Anything named `--local-path` or `--local-exec`.
- The agent's own network connections, so it can still reach its model provider. `--net remote`
  sends them to the target instead. `--net-allow HOST[:PORT]` keeps named hosts local anyway.

Name what must stay here with `--local-path` or `--local-exec`:

```sh
hmz anchor --target ssh://build-box \
    --local-path /home/me/code/myproject/.venv \
    --local-exec /usr/bin/rg \
    claude
```

Commands the agent spawns **always** use the target's network, whatever `--net` says.

Before you rely on this for anything expensive, read [Remote execution › What is not
guaranteed](/reference/remote-execution#what-is-not-guaranteed). The short version: what a
command changes on the target becomes visible to the agent once the command exits, and a
command that ran while the agent was writing the same file may have run against what was there
before.

## Anchoring a flow

Give an agent's config an anchored machine and its turns land there, with no other change to
the flow:

```python
from hmz.agents import ClaudeCodeAgentConfig
from hmz.coganchor import AnchorConfig
from hmz.machines import AnchoredConfig

config = ClaudeCodeAgentConfig(
    model="claude-opus-4-8",
    effort="high",
    machine=AnchoredConfig(
        anchor=AnchorConfig(target="ssh://build-box", workspace="/srv/project")
    ),
)
```

Every option of `hmz anchor` is a field of `AnchorConfig`, and every field is an option. A flow
spawns what an operator would have typed. Settings no session could run under are refused where
they are *written*, so a flow that misspells a target hears about it as it configures its
agents rather than hours into the loop.

**The flow says which agents may be moved at all.** A place declared plain `Agent` works
here and cannot be pointed anywhere. Only `Annotated[Agent, Remote]` may be:

```python
# .humanize/flows/onbox/__init__.py
"""Build on the box, review here."""

from typing import Annotated, NamedTuple

from hmz.flows import Agent, Remote, flow


class Agents(NamedTuple):
    builder: Annotated[Agent, Remote]  # may be pointed at a machine
    reviewer: Agent                    # here, and nowhere else


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.builder.new()
    working(task, suppress=True)
    for _ in range(5):
        working(agents.reviewer("Read the diff and say what is wrong.", suppress=True),
                suppress=True)
```

At the prompt, that is the `where` row of the agent's own sheet on the agents page of `/flow`.
The row appears only for a `Remote` place. It lists the containers running and the hosts in
your `~/.ssh/config`, and anything else is typed:

| Typed | Where the work goes |
| --- | --- |
| *(nothing)* | this machine |
| `docker://<container>` | a container that is already running |
| `ssh://<host>` | a host you can reach |
| `tcp://<host>:<port>` | a target listening there |

## A session works in a directory the target names

For an anchored agent, `agent.new(cwd)` takes **the target's** path, and it must be inside the
workspace the anchor names. humanize puts the agent in this machine's mirror of that directory
and tells the anchor to run the work in the directory itself. A flow says where the work
happens in the only names the far end has.

```text
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

The same paths are flags on `hmz anchor`. Where the project lives at a different path there,
name both:

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
| `--shadow` | the local mirror directory; it defaults to the workspace path, so the paths the agent sees are the target's own |
| `--chdir` | where inside the workspace the agent starts, as the target names it |

## Serving a target

Where there is no ssh and no container, run the target half on the far machine:

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

It needs only a POSIX system and a recent `python3`. No root, no compiler, nothing installed.

Then connect from here:

```sh
hmz anchor --target tcp://build-box:7777 --workspace /srv/project --token "$SECRET" claude
```

A `tcp://` target is **cheap to reconnect**, which matters for a loop of short turns. A backend
whose turn runs as its own process reaches the target once per turn, and a socket costs less to
open than an ssh session.

::: danger An open port is a shell on that machine
`--export` bounds which files a request may **name**. It does not confine the commands that
request can run. Give `--token` a real secret; listening on anything but loopback without one
is refused outright. Prefer `ssh://` or `docker://`, which need no port at all. See
[Security](/guide/security).
:::

## Requirements

Linux on x86-64 **here**. A POSIX system with a recent `python3` **there**. No root, no
compiler, no kernel module, nothing installed on the far end.

## See also

- [Containers](/guide/containers) — the same arrangement, with a container as the target
- [Remote execution reference](/reference/remote-execution) — what is and is not guaranteed
- [CLI › `hmz anchor`](/reference/cli#hmz-anchor)
- [Troubleshooting](/guide/troubleshooting#the-target-cannot-be-reached)
- [humanize in CI](/guide/ci)
