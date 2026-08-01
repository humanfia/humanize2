# CLI reference

Every command, flag, environment variable, exit status and file. For a walk through rather than
a lookup, start at [Getting started](getting-started.md).

```
hmz [<command> [<args>...]]
```

A line naming no command opens the [terminal interface](tui.md). A line naming something that
is not a command is a usage error listing the commands there are. Everything after the command
name reaches that command untouched — `--help` included — so each answers for its own
arguments.

`python -m humanize` is the same command line, which is how a turn spawns itself under an
[anchor](remote-execution.md).

## Table of Contents

- [`hmz`](#hmz)
- [`hmz exec`](#hmz-exec)
- [`hmz collect`](#hmz-collect)
- [`hmz anchor`](#hmz-anchor)
- [`hmz anchor serve`](#hmz-anchor-serve)
- [`hmz providers`](#hmz-providers)
- [`hmz cred`](#hmz-cred)
- [Environment variables](#environment-variables)
- [Files](#files)
- [Exit statuses](#exit-statuses)
- [Python entry points](#python-entry-points)

## `hmz`

```
hmz                  # opens the terminal interface
hmz --version        # prints the installed version
hmz --help           # lists the commands
```

There is no command that opens the interface. Naming nothing at all is how it opens.

It opens on whatever this workspace was [last set up to run](tui.md#what-it-remembers) — or on
what the line says, for a run that is always the same run:

```
hmz -f|--flow <flow> [-c|--config <path>] [-a|--agent <spec>]...
```

| Argument | |
| --- | --- |
| `-f`, `--flow <flow>` | The flow to open on. |
| `-c`, `--config <path>` | A YAML file of what to set that flow up with, as [`/config`](tui.md#setting-a-flow-up) would have asked for it. Needs `-f`. |
| `-a`, `--agent <spec>` | What each of that flow's agents runs, in the order it takes them — as many as it drives. Needs `-f`. |

Nothing is started: the interface opens ready, and the first thing you say is still what starts
it. What the line says is checked before the interface opens — a flow that will not load, a
config the flow refuses, the wrong number of agents — so a line that is wrong is a line, not a
sheet to walk back out of.

```sh
hmz -f humanize1 -c setup.yaml
```

## `hmz exec`

Runs a [flow](flows.md) in the current directory, on the agents it is given.

```
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...] <task>
```

| Argument | |
| --- | --- |
| `-f`, `--flow <flow>` | **Required.** The flow to drive: the name of one humanize came with, or the path to a file — which is what a flow of your own is called. See [where flows live](flows.md#where-flows-live). |
| `-c`, `--config <path>` | A YAML file of what to set the flow up with, one field per line, under the names the flow declared — only for a flow that says it [can be set up](flows.md#settings-of-the-flows-own). The flow's own model checks it before the first turn. |
| `-a`, `--agent <spec>` | **Repeated once for each agent the flow drives**, in the order it takes them — so none at all for a flow whose only side is you, since nobody chooses what the person runs. |
| `<task>` | **Required.** What the flow is to have the agents do, as the text itself. Put `--` before it if it starts with a dash. |

### Writing an agent

```
claude/claude-opus-4-8:high
cli=claude,model=claude-opus-4-8,effort=high
claude@deepseek/claude-opus-4-8:high
cli=claude,model=claude-opus-4-8,effort=high,provider=deepseek
cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only
```

The first two spellings mean the same thing. The written-out form exists because a model or an
effort may hold the punctuation the short form separates on, and is also where settings with no
unambiguous short spelling go.

- `<cli>` is `claude`, `codex`, `kimi`, `pi`, `opencode` or `mimo`. Each also answers to the
  longer name it is installed under: `claude-code`, `kimi-code`, `mimocode` and `mimo-code`.
- `<model>` and `<effort>` are whatever that CLI is asked for — humanize does not check them
  against a list, so a model your account has and this documentation does not still works.
- A model may hold slashes of its own — Kimi Code's are `kimi-code/k3`, and pi, opencode and
  mimocode name every model as `provider/id` — so the CLI is read from the front and the effort
  from after the last colon.
- An `@` after the CLI names the [provider](providers.md) that agent's turns run as — the
  account, not the model: `claude@deepseek`. Written out, it is `provider=`. A CLI is never
  spelled with an `@` in it, so the two are told apart wherever an agent is written. An agent
  that names none runs its CLI as you already run it.
- `permission=` names [what that agent may do](agents.md#what-an-agent-may-do): `read-only`,
  `workspace-write`, `auto` or `bypass`. It is available in the written-out form only and
  defaults to `bypass`. A misspelling is refused before any agent runs.

**One `-a` is one agent.** A list inside a single `-a` is not split into several. Two agents of
one spelling are two agents, which is what makes a flow of an actor and a reviewer at one
configuration what it says it is.

### What is refused before anything runs

A flow that is not there, has no `run`, does not say how many agents it drives, or drives a
different number than were given, is a usage error — reported before the first turn rather than
partway into a loop with a turn's work already behind it:

```console
$ hmz exec -f rlar -a claude/claude-opus-4-8:high "fix the build"
hmz exec: error: /.../rlar.py: run() drives 2 agents, 1 given
```

Whatever else a flow does as it is imported is the flow's own, and fails as it would anywhere.

### Examples

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
hmz exec -f flame_chase -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max "fix the build"
hmz exec -f rlar -a claude/claude-opus-4-8:high -a claude/claude-opus-4-8:high "$(cat TASK.md)"
hmz exec -f rlar -a claude/claude-opus-4-8:high -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only "$(cat TASK.md)"
hmz exec -f flame_chase -a claude@anthropic/claude-opus-5:max -a claude@deepseek/deepseek-chat:high "fix the build"
hmz exec -f ./flows/mine.py -a kimi/kimi-code/k3:swarmmax "port this to asyncio"
hmz exec -f ralph_loop -a pi/openai-codex/gpt-5.5:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a opencode/opencode/big-pickle:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high -- "--force is not a flag here"
hmz exec -f humanize1 -c setup.yaml -a claude/claude-opus-5:max -a claude/claude-opus-5:max \
    -a codex/gpt-5.6-sol:xhigh -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:xhigh "add undo"
```

Nobody is at a prompt, so an agent that stops to ask is told nobody answered and carries on.

## `hmz collect`

Reads the trajectories the coding agents recorded and writes them out as one Chrome JSON trace.
Works whether or not a flow drove them. See [Tracing](tracing.md).

```
hmz collect [<workspace>] [--session <session>[,<session>]...]
            [--output <output>] [--start <start>] [--end <end>]
```

| Argument | |
| --- | --- |
| `<workspace>` | The directory to collect for. Defaults to this one, unless sessions are named. |
| `--session <s>[,<s>...]` | Sessions to include, comma separated and repeatable. Defaults to every session of the workspace. |
| `--output <path>` | Where to write. Defaults to `.humanize/<datetime>.trace.json`; the directory is created if it is not there. |
| `--start <when>` | Earliest record to include, in any wording [dateparser](https://dateparser.readthedocs.io/) understands. |
| `--end <when>` | Latest record to include, same wording. |

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either, and the sub-agents it started come with it. Named sessions are collected wherever they
were recorded, and are then cut down to the workspace when one is given.

The default output is named after the UTC moment it was collected, so collecting twice keeps
both traces rather than writing over the first.

Prints the output path with the number of sessions and slices it holds:

```console
$ hmz collect
.humanize/20260809T014455Z.trace.json: 3 sessions, 412 slices
```

### Examples

```sh
hmz collect                                    # this workspace, all of its history
hmz collect ~/code/other --start "3 days ago"  # another workspace, recent history only
hmz collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz collect --end "yesterday 18:00" --output /tmp/before.json
```

## `hmz anchor`

Runs a coding agent on this machine whose work lands on another one. See
[Remote execution](remote-execution.md).

```
hmz anchor [options] AGENT [ARGS...]
```

Everything after the agent's name is the agent's own.

| Flag | Default | |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT`, or `local[:DIR]`. |
| `--workspace PATH` | this directory | The project directory as it exists on the target. |
| `--remote-path PATH` | `--workspace` | Where that workspace really lives on the target, if not at the same path. |
| `--shadow PATH` | `--workspace` | The local mirror directory. Defaulting to the workspace path is what makes the paths the agent sees the target's own. |
| `--local-path PATH` | — | Keep this path on this machine even when it is inside the workspace. Repeatable. |
| `--local-exec PATH` | — | Run programs under this path here rather than on the target. Repeatable. |
| `--net {local,remote}` | `local` | Where the agent's *own* TCP connections go. Local keeps its model provider reachable. Commands it spawns always use the target's network. |
| `--net-allow HOST[:PORT]` | — | With `--net remote`, keep connections to this host local. Repeatable. |
| `--token TOKEN` | `$HUMANIZE_TOKEN` | Shared secret a `tcp://` target expects. |
| `--force` | off | Use the mirror directory even if it already holds unrelated files. |
| `--check` | off | Connect, report what was found, and exit without running anything. |
| `--log-level {debug,info,warning,error}` | `$HUMANIZE_LOG`, else `warning` | Logging verbosity. The log goes to stderr. |

Settings no session could run under — a target nobody can read, a `--net` that is neither —
exit 2 the way argparse's own rejections do.

```sh
hmz anchor --target ssh://build-box claude
hmz anchor --target ssh://gpu-01 codex exec "run the test suite"
hmz anchor --target docker://build-container --workspace /srv/project claude
hmz anchor --check --target ssh://build-box
```

## `hmz anchor serve`

The other half of a session: replays on this machine what an `hmz anchor` elsewhere asks of it.
Needs only a POSIX system and a recent `python3` — no root, no compiler, nothing installed.

```
hmz anchor serve --export VIRTUAL[:REAL] (--stdio | --listen [HOST:]PORT) [--token TOKEN]
```

| Flag | |
| --- | --- |
| `--export VIRTUAL[:REAL]` | **Required, repeatable.** Expose a directory. `VIRTUAL` is the path the agent believes it is using; `REAL` is where it is here. |
| `--stdio` | Serve one session over stdin/stdout. This is what a bootstrapped target runs. |
| `--listen [HOST:]PORT` | Serve TCP connections on this address. A bare port listens on `127.0.0.1`. |
| `--token TOKEN` | Shared secret required from clients. Defaults to `$HUMANIZE_TOKEN`. |
| `--log-level` | As for `hmz anchor`. |

`--stdio` and `--listen` are mutually exclusive, and one is required.

**Listening on anything but loopback without `--token` is refused.** An open port is equivalent
to a shell on that machine — read [Security](../README.md#security).

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## `hmz providers`

The accounts an agent may be run as: one named set of credentials per provider, kept apart from
the CLI's own. See [Providers](providers.md).

```
hmz providers list [<cli>]
hmz providers ways <cli>
hmz providers add <cli>/<name> [-w|--way <way>] [-s|--set VAR=VALUE]... [--no-login]
hmz providers login <cli>/<name> [-s|--set VAR=VALUE]...
hmz providers show <cli>/<name>
hmz providers remove <cli>/<name>
```

A provider is named `<cli>/<name>` — `claude/deepseek` — wherever one is asked for. Naming no
command at all lists them.

| Command | |
| --- | --- |
| `list [<cli>]` | What providers there are, or one backend's: the name, the way it was made by, and the variables it sets. |
| `ways <cli>` | How that backend can be signed into: each way, what it asks for, and what it runs. |
| `add <cli>/<name>` | Makes one and signs it in. `-w` chooses the way and defaults to the backend's first, which is `login`; `-s` answers one of the way's questions on the line rather than being asked, and repeats; `--no-login` writes it down without running the backend's own way in. |
| `login <cli>/<name>` | Signs an existing one in again, by the way it was made with. Takes the same `-s`. |
| `show <cli>/<name>` | What one holds: the way, when it was made, where it is kept, the names of the variables it sets, and which paths a turn under it is given instead of which. |
| `remove <cli>/<name>` | Takes it away, credentials and all. |

Whatever a way asks that the line did not answer is asked at the terminal, and a secret is not
echoed. A line with nobody at a terminal has to answer everything itself.

**Values are never printed** — `show` and `list` say which variables a provider sets and not
what they are.

```sh
hmz providers add claude/anthropic -w login
hmz providers add claude/deepseek -w gateway -s ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
hmz providers ways codex
hmz providers show claude/deepseek
hmz providers remove claude/deepseek
```

## `hmz cred`

Runs a program with some of its paths answered by others. This is what a turn under a provider
is spawned as, and it is a command of its own for the reason `hmz anchor` is: the supervisor
forks the program and takes the process's signal handling with it.

```
hmz cred --map FROM=TO [--map FROM=TO]... -- COMMAND [ARGS...]
```

| Flag | |
| --- | --- |
| `--map FROM=TO` | **Required, repeatable.** Answer `FROM` with `TO` for everything below, as two absolute paths. A directory names everything inside it. |
| `COMMAND` | The program to run and its arguments, after `--`. |

Exits with the program's own status. A run that could not be supervised is **not** run
unsupervised — the program would read the credentials of whoever is at this machine, which is a
turn taken as the wrong account rather than a turn that failed.

Needs Linux on x86-64, as running an agent under an anchor does.

```sh
hmz cred --map /home/you/.claude/.credentials.json=/home/you/.humanize/providers/claude/deepseek/home/.credentials.json -- claude
```

## Environment variables

| Variable | Read by | |
| --- | --- | --- |
| `HUMANIZE_HOME` | everything | Where humanize keeps what outlives one run. Defaults to `~/.humanize`. |
| `HUMANIZE_TARGET` | `hmz anchor` | Default for `--target`. |
| `HUMANIZE_TOKEN` | `hmz anchor`, `hmz anchor serve` | Default for `--token`. |
| `HUMANIZE_LOG` | `hmz anchor`, `hmz anchor serve` | Default for `--log-level`. |
| `CLAUDE_CONFIG_DIR` | `hmz collect`, the TUI's cost readout | Claude Code's home. Defaults to `~/.claude`. |
| `CODEX_HOME` | same | Codex's home. Defaults to `~/.codex`. |
| `KIMI_CODE_HOME` | same | Kimi Code's home. Defaults to `~/.kimi-code`. |
| `PI_CODING_AGENT_DIR` | same | pi's home. Defaults to `~/.pi/agent`. |
| `XDG_DATA_HOME` | the model list | Where opencode and mimocode keep their data. Defaults to `~/.local/share`. |
| `NO_COLOR` | the TUI | Honoured. |

A backend home that does not exist is skipped rather than being an error.

**Set inside an anchored agent**, so that it and the commands it spawns can tell:

| Variable | |
| --- | --- |
| `HUMANIZE` | The version of the half that launched it. |
| `HUMANIZE_TARGET` | The target its work is landing on. |
| `HUMANIZE_WORKSPACE` | The workspace as the target has it. |

## Files

| Path | Written by | |
| --- | --- | --- |
| `~/.humanize/cycles/<workspace>/<datetime>-<hex>.jsonl` | every run of a flow | What the run was: the flow, the agents, every session opened, how it ended. See [Cycles](tracing.md#cycles). |
| `~/.humanize/providers/<cli>/<name>/provider.json` | `hmz providers add` | What a [provider](providers.md) was made by, and what a turn under it runs with. `0600`, in a directory at `0700`. |
| `~/.humanize/providers/<cli>/<name>/{home,user}/...` | the CLI's own login | That provider's credentials, at the names the CLI keeps its own under. |
| `~/.humanize/settings.yaml` | the TUI | What each workspace was last set up to run. |
| `~/.humanize/history.jsonl` | the TUI | What has been typed at the prompt before, and where. |
| `.humanize/<datetime>.trace.json` | `hmz collect` | The trace. Relative to the current directory, not to the workspace named. |
| `.humanize/<datetime>.session.md` | `/export` | The transcript on screen. |
| `.humanize/flows/*.py` | you | This project's own flows. |
| `~/.humanize/flows/*.py` | you | Your flows, in every project. |

`~/.humanize` is `$HUMANIZE_HOME` where that is set. The directories are made by whatever writes
into them.

## Exit statuses

| | |
| --- | --- |
| `0` | It did what it was asked. |
| `1` | It could not: the target could not be reached, the listener could not be started, there is no such provider, a turn could not be supervised. |
| `2` | The command line was wrong — argparse's own rejections, a flow that is not there or takes other agents, a malformed listen address, a non-loopback listener with no token. |
| `130` | Interrupted. |
| *the agent's own* | `hmz anchor` and `hmz cred` exit with the status of the program they ran, and `hmz providers add` with that of the login it ran. |

## Python entry points

Every command is a shell around a call you can make yourself. The layer each lives in is named
in [Architecture](architecture.md).

```python
from humanize.runner import Runner          # hmz exec
from humanize.tracing import collect        # hmz collect
from humanize.coganchor import connect      # hmz anchor
from humanize.coganchor import check        # hmz anchor --check
from humanize import providers              # hmz providers
```

- `Runner(flow, agents).run(task)` — [Flows](flows.md)
- `collect(workspace, *, sessions=…, agents=…, output=…, start=…, end=…)` — [Tracing](tracing.md)
- `connect(command, config)` / `check(config)` — [Remote execution](remote-execution.md)
- `providers.providers(cli)` / `providers.find(cli, name)` / `providers.remove(cli, name)` —
  [Providers](providers.md)
