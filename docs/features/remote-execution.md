# Remote execution

An agent runs on **this** machine, unchanged. Everything it *does* — reading and writing project
files, running commands, reaching the network from those commands — happens on the **target**.

The agent needs no plugin, no configuration and no cooperation. It is told none of this and takes
part in none of it.

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

The workspace the agent works in is a **local mirror** of the target's copy. It reads and writes
the mirror at local speed and humanize keeps the two in step. The mirror lives at the workspace's
own path by default, so the paths the agent sees are the target's own.

## Try it

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

Then run something:

```sh
hmz anchor --target ssh://build-box claude
hmz anchor --target ssh://gpu-01 codex exec "run the test suite"
```

Everything after the agent's name is the agent's own.

## Targets

| `--target` | |
| --- | --- |
| `ssh://HOST[:PORT]` | Bootstraps the target half over ssh and speaks to it on that connection's pipes. Uses your ssh config, agent and keys. **Nothing listens.** |
| `docker://CONTAINER` | Runs the target half inside a running container over `docker exec`. No port and no secret. |
| `tcp://HOST:PORT` | Connects to a target [left listening](/reference/remote-execution#serving-a-target). Cheap to reconnect, which matters for a loop of short turns. |
| `local[:DIR]` | Another directory on this machine, standing in for a remote one. Used for development and by the test suite. |

The target half is a zipapp humanize ships to the target and caches there by digest. It needs no
installation, and the two halves refuse to run against each other if their versions disagree.

## What crosses, and what does not

**Reaches the target**

- File contents — pushed in full before any command runs, and again when the session ends.
- Structural changes — create, remove, rename, link, chmod — replayed there *first*, so the
  target's own error is what the agent sees.
- Commands, including helpers bundled with the agent itself, in the target's copy of the working
  directory.
- Whatever those commands reach on the network.

**Stays here**

- The agent's own executable and its re-execs.
- Its state directory. All ten known CLIs are known by name — `agy`, `claude`, `codex`, `dsh`,
  `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen` — as is humanize's own `~/.humanize`; any
  other agent keeping state inside the workspace has to be named with `--local-path`.
- Anything named `--local-path` or `--local-exec`.
- The agent's own network connections, so it can still reach its model provider. `--net remote`
  sends them to the target instead; `--net-allow HOST[:PORT]` keeps named hosts local anyway.

Commands the agent spawns **always** use the target's network, whatever `--net` says.

## Anchoring a flow

Give an agent's config an anchored machine and its turns land there, with no other change to the
flow:

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

Every option of `hmz anchor` is a field of `AnchorConfig` and every field is an option — a flow
spawns what an operator would have typed. Settings no session could run under are refused where
they are *written*, so a flow that misspells a target hears about it as it configures its agents
rather than hours into the loop.

**Which agents may be moved at all is the flow's to say.** A place declared plain `AgentBase`
works here and cannot be pointed anywhere; only `Annotated[AgentBase, Remote]` may be:

```python
class Agents(NamedTuple):
    builder: Annotated[AgentBase, Remote]   # may be pointed at a machine
    reviewer: AgentBase                     # here, and nowhere else
```

At the prompt, that is the third step of `/agents` — offered only for a `Remote` place, listing
the containers running and the hosts in your `~/.ssh/config`, with anything else typed.

## A session works in a directory the target names

For an anchored agent, `agent.new(cwd)` takes **the target's** path, and it must be inside the
workspace the anchor names. humanize puts the agent in this machine's mirror of it and tells the
anchor to run the work in the directory itself — so a flow says where the work happens in the only
names the far end has.

```text
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

## Serving a target

Where there is no ssh and no container:

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

Needs only a POSIX system and a recent `python3` — no root, no compiler, nothing installed.

::: danger An open port is a shell on that machine
`--export` bounds which files a request may **name**. It does not confine the commands that
request can run. Give `--token` a real secret; listening on anything but loopback without one is
refused outright. Prefer `ssh://` or `docker://`, which need no port at all. See
[Security](/guide/security).
:::

## Requirements

Linux on x86-64 **here**; a POSIX system with a recent `python3` **there**. No root, no compiler,
no kernel module, nothing installed on the far end.

## See also

- [Tutorial: another machine](/guide/tutorial-remote)
- [Containers](/features/containers) — the same arrangement, with a container as the target
- [Remote execution reference](/reference/remote-execution) — what is and is not guaranteed
- [CLI › `hmz anchor`](/reference/cli#hmz-anchor)
