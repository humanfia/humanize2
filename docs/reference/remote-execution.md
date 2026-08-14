# Remote execution

`hmz anchor` runs a coding agent on this machine whose work lands on another one. The agent
needs no plugin, no configuration and no cooperation: it is told none of this and takes part in
none of it.

## The model

An agent runs on this machine, unchanged. Everything it *does* — reading and writing project
files, running commands, reaching the network from those commands — happens on the target.

The workspace the agent works in is a **local mirror** of the target's copy. It reads and writes
the mirror at local speed; humanize keeps the two in step. The mirror lives at the workspace's
own path by default, so the paths the agent sees are the target's own.

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

## Quick start

```sh
hmz anchor --target ssh://build-box claude
hmz anchor --target ssh://gpu-01 codex exec "run the test suite"
```

Everything after the agent's name is the agent's own. Before running anything, ask the target
what it is:

```console
$ hmz anchor --check --target ssh://build-box
target      ssh://build-box
hostname    build-box
python      3.12.3 (pid 41207)
export      /home/me/code/myproject -> /home/me/code/myproject
workspace   /home/me/code/myproject (184 entries)
```

Every flag is in the [CLI reference](/reference/cli#hmz-anchor).

## Targets

| `--target` | |
| --- | --- |
| `ssh://HOST` or `ssh://HOST:PORT` | Bootstraps the target half over ssh and speaks to it on that connection's pipes. Uses your ssh config, agent and keys. |
| `docker://CONTAINER` | Runs the target half inside a running container over `docker exec`, as whoever that container runs as. No port and no secret. |
| `tcp://HOST:PORT` | Connects to a target [left listening](#serving-a-target). Cheap to reconnect, which matters for a loop of short turns. |
| `local` or `local:DIR` | Another directory on this machine, standing in for a remote one. Used for testing, and by the container machines. |

The target half is a zipapp humanize ships to the target and caches there by digest. It needs no
installation, and the two halves refuse to run against each other if their versions disagree.

## What the agent observes

Inside the workspace it sees the target: the same file names, contents, sizes, modes and
timestamps, at the same paths. A failure answers with the target's own error, not a local
approximation of it.

Every program it spawns behaves like an ordinary local child — the same descriptors, the same
output, the same exit status — and its parent is released as soon as it starts, so commands run
concurrently and a long-lived one can be talked to while it runs.

Signals travel both ways: one aimed at a running command reaches the real process on the target,
and a command killed there kills its local counterpart the same way.

A command never reports a success it did not achieve: one that cannot be started, or that
humanize loses track of, fails visibly. What a command changes on the target becomes visible to
the agent once it exits, and when the session ends nothing it started is left running.

## What reaches the target

- **File contents.** A file the agent modifies is pushed in full before any command runs on the
  target, and again when the session ends.
- **Structural changes.** Creating, removing, renaming, linking and changing permissions are
  replayed on the target first, so the target's error is what the agent sees.
- **Commands.** Everything the agent spawns, including bundled work helpers such as ripgrep, in
  the target's copy of the working directory.
- **Network.** Whatever those commands reach.

## What stays on this machine

- The agent's own runtime executables and re-execs. For an npm-installed Codex, that includes
  Node, the native CLI and its code-mode host.
- Its state directory. All ten known CLIs are known by name — `agy`, `claude`, `codex`, `dsh`,
  `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen` — as is humanize's own `~/.humanize`; any
  other agent keeping state inside the workspace has to be named with `--local-path`.
- Anything named as a local path (`--local-path`) or a local program (`--local-exec`).
- The agent's own network connections, so that it can still reach its model provider. `--net
  remote` sends them to the target instead, and `--net-allow HOST[:PORT]` keeps named hosts
  local anyway.

Commands the agent spawns always use the target's network, whatever `--net` says.

## Anchoring a flow

Give an agent's config an anchored [machine](/reference/machines) and its turns land there, without any
other change to the [flow](/reference/flows):

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

Every option of `hmz anchor` is a field of `AnchorConfig` and every field is an option, so the
two spellings mean exactly the same thing — a flow spawns what an operator would have typed.
Settings no session could run under are refused where they are *written* rather than where they
are used, so a flow that misspells a target hears about it as it configures its agents, not
hours into the loop.

**How often the target is reached depends on the backend.** A turn that runs as its own process
is anchored on its own, so a loop of short turns reaches the target once per turn — a `tcp://`
target makes that a socket rather than an ssh session to bootstrap. A backend that holds one
process across turns is anchored once for the agent instead.

There is a trade-off worth knowing: an anchored **Claude** ends its process with each turn, so
the turn's work reaches the target before the turn says it landed — at the cost of not being
able to hear you *during* a turn. An anchored **Codex** keeps one app server for the life of the
agent and can be steered throughout, at the cost of that guarantee: its work reaches the target
whenever a command runs there, which for a coding agent is constantly, rather than at the end of
every turn.

## Serving a target

Instead of bootstrapping over ssh each time, a target can be left listening:

```sh
# on the target
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"

# on this machine
HUMANIZE_TOKEN=$SECRET hmz anchor --target tcp://build-box:7777 --workspace /srv/project claude
```

`--export VIRTUAL[:REAL]` says which directory to expose, and under what path the agent believes
it is using. Repeat it for more than one.

Listening on anything but loopback **without** `--token` is refused. Read
[Security](#security) before opening one.

The same program serves both ends — the bundle shipped to a target runs `hmz anchor serve
--stdio`, which is one session over a pipe.

## From Python

```python
from hmz.coganchor import AnchorConfig, check, connect

config = AnchorConfig(target="ssh://build-box", workspace="/srv/project")

found = check(config)              # what the target says about itself; runs nothing there
status = connect(["claude", "--print"], config)   # the agent's own exit status
```

`connect` returns once the agent has exited and everything it wrote has been pushed.

`AnchorConfig` fields map one-to-one onto the flags in the
[CLI reference](/reference/cli#hmz-anchor): `target`, `workspace`, `chdir`, `remote_path`,
`shadow`, `local_paths`, `local_execs`, `redirects`, `private`, `net`, `net_allow`, `token`,
`force`.

## Requirements

**Running an agent** needs Linux on x86-64 and a recent Python. Any other architecture is
refused at start-up.

**Serving** needs only a POSIX system with a Python of the same vintage — no root, no compiler,
no kernel module, nothing installed.

## What is not guaranteed

Each of these is deliberate, and each looks like a defect if you meet it cold.

- **Serving is not a sandbox.** An export bounds which files a request may name. It does not
  confine the commands that request can run, and it does not stop a symlink pointing out of the
  tree from being followed. A listening port is equivalent to a shell on that machine.
- **Mirrored directories are the mirror's, not the target's.** A directory in the mirror carries
  this machine's permissions and the time the mirror was made.
- **Only file contents are pushed.** A permission change made through an already-open descriptor
  never reaches the target, and ownership, device nodes and extended attributes never leave the
  mirror.
- **A request that goes unanswered is abandoned here, not there.** It may still take effect on
  the target after the agent has been told it failed.
- **Losing the connection does not stop the agent.** Work needing the target fails,
  already-mirrored files still read, and the agent exits with its own status.
- **Only the common signals are reproduced faithfully.** A repeat of a signal already delivered,
  and the rarer signals, do not reach the command.
- **The mirror is authoritative.** Anything in it the target does not have is deleted. humanize
  refuses a mirror directory holding unrelated files, or one last used against a different
  target, unless `--force` says otherwise.

## Limits

- **Whole files.** A file crosses in full, in both directions.
- **One writer.** The target's workspace must not be edited by anyone else at the same time.
- **No privilege escalation.** `sudo` does not work below the agent on this machine. Commands
  run on the target, where it is unaffected.
- **No crossing.** Renaming or linking between the workspace and a path kept on this machine
  fails.
- **64-bit only.** A 32-bit process below the agent is not intercepted and runs against the
  mirror with nothing replayed.
- **Names resolve here** and are dialled from the target, so split-horizon DNS can disagree.

## Security

**An `hmz anchor` port is equivalent to a shell on that machine.** Give `--token` a real secret,
and prefer `ssh://` or `docker://`, which need no open port at all.

The full statement, including what running any agent under humanize means, is in
[Security](/guide/security).
