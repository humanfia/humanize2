# CLI reference

Every command, flag, environment variable, exit status and file. For a walk through rather than
a lookup, start at [Getting started](/guide/getting-started.md).

```
hmz [<command> [<args>...]]
```

A line naming no command opens the [terminal interface](/reference/tui.md). A line naming something that
is not a command is a usage error listing the commands there are. Everything after the command
name reaches that command untouched — `--help` included — so each answers for its own
arguments.

`python -m hmz` is the same command line, which is how a turn spawns itself under an
[anchor](/reference/remote-execution.md).

## `hmz`

```
hmz                  # opens the terminal interface
hmz --version        # prints the installed version
hmz --help           # lists the commands
```

There is no command that opens the interface. Naming nothing at all is how it opens.

It opens on whatever this workspace was [last set up to run](/reference/tui.md#what-it-remembers) — or on
what the line says, for a run that is always the same run:

```
hmz -f|--flow <flow> [-c|--config <path>] [-a|--agent <spec>]...
```

| Argument | |
| --- | --- |
| `-f`, `--flow <flow>[:<name>]` | The flow to open on. |
| `-c`, `--config <path>` | A YAML file of what to set that flow up with, as [choosing the flow](/reference/tui.md#setting-a-flow-up) would have asked for it. Needs `-f`. |
| `-a`, `--agent <spec>` | What each of that flow's agents runs, in the order it takes them — as many as it drives. Needs `-f`. |

Nothing is started: the interface opens ready, and the first thing you say is still what starts
it. What the line says is checked before the interface opens — a flow that will not load, a
config the flow refuses, the wrong number of agents — so a line that is wrong is a line, not a
sheet to walk back out of.

```sh
hmz -f official/humanize1:rlcr -c setup.yaml
```

## `hmz exec`

Runs a [flow](/reference/flows.md) in the current directory, on the agents it is given.

```
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...] <task>
```

| Argument | |
| --- | --- |
| `-f`, `--flow <flow>[:<name>]` | **Required.** The flow to drive: the name of one humanize ships, `<flowverse>/<flow>` for one a [flowverse](/reference/flows.md#flowverses) holds, or the path to a file — which is what a flow of your own is called. A file that holds [several flows](/reference/flows.md#several-flows-in-one-file) is said which, after a colon. See [where flows live](/reference/flows.md#where-flows-live). |
| `-c`, `--config <path>` | A YAML file of what to set the flow up with, one field per line, under the names the flow declared — only for a flow that says it [can be set up](/reference/flows.md#settings-of-the-flow-s-own). The flow's own model checks it before the first turn. |
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
- An `@` after the CLI names the [provider](/reference/providers.md) that agent's turns run as — the
  account, not the model: `claude@deepseek`. Written out, it is `provider=`. A CLI is never
  spelled with an `@` in it, so the two are told apart wherever an agent is written. An agent
  that names none runs its CLI as you already run it.
- `permission=` names [what that agent may do](/reference/agents.md#what-an-agent-may-do): `read-only`,
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
$ hmz exec -f official/rlar -a claude/claude-opus-4-8:high "fix the build"
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given
```

Whatever else a flow does as it is imported is the flow's own, and fails as it would anywhere.

### Examples

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
hmz exec -f official/flame_chase -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max "fix the build"
hmz exec -f official/rlar -a claude/claude-opus-4-8:high -a claude/claude-opus-4-8:high "$(cat TASK.md)"
hmz exec -f official/rlar -a claude/claude-opus-4-8:high -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only "$(cat TASK.md)"
hmz exec -f official/flame_chase -a claude@anthropic/claude-opus-5:max -a claude@deepseek/deepseek-chat:high "fix the build"
hmz exec -f ./flows/mine -a kimi/kimi-code/k3:swarmmax "port this to asyncio"
hmz exec -f ralph_loop -a pi/openai-codex/gpt-5.5:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a opencode/opencode/big-pickle:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high -- "--force is not a flag here"
hmz exec -f official/humanize1:rlcr -c setup.yaml -a claude/claude-opus-5:max \
    -a codex/gpt-5.6-sol:xhigh "add undo"
```

Nobody is at a prompt, so an agent that stops to ask is told nobody answered and carries on.

## `hmz collect`

Reads the trajectories the coding agents recorded and writes them out as one Chrome JSON trace.
Works whether or not a flow drove them. See [Tracing](/reference/tracing.md).

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
[Remote execution](/reference/remote-execution.md).

```
hmz anchor [options] AGENT [ARGS...]
```

Everything after the agent's name is the agent's own.

| Flag | Default | |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT`, or `local[:DIR]`. |
| `--workspace PATH` | this directory | The project directory as it exists on the target. |
| `--chdir PATH` | `--workspace` | Where inside that workspace the agent starts, as the target names it. What a [session opened at a directory](/reference/agents.md#the-directory-a-session-works-in) comes to: the agent is put in this machine's mirror of it. |
| `--remote-path PATH` | `--workspace` | Where that workspace really lives on the target, if not at the same path. |
| `--shadow PATH` | `--workspace` | The local mirror directory. Defaulting to the workspace path is what makes the paths the agent sees the target's own. |
| `--local-path PATH` | — | Keep this path on this machine even when it is inside the workspace. Repeatable. |
| `--local-exec PATH` | — | Run programs under this path here rather than on the target. Repeatable. |
| `--redirect FROM=TO` | — | Answer this path with that one — the file it names, or everything under the directory it names — and keep what it is answered with local. What a turn under a [provider](/reference/providers.md) is given. Repeatable. |
| `--private NAME` | — | Keep this variable out of what the agent's commands are run with on the target: a credential it was given to reach its model provider is its own. Repeatable. |
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
to a shell on that machine — read [Security](/guide/security.md).

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## `hmz flowverses`

Where flows come from: a git repository with a `flows/` directory apiece, cloned under
humanize's home and offered under the name it is kept there. See
[Flowverses](/features/flowverses.md).

```
hmz flowverses list [-q|--quiet]
hmz flowverses show <name>
hmz flowverses add <url> [<name>]
hmz flowverses fetch <name>
hmz flowverses remove <name>
```

The same places the interface's [`/flow`](/reference/tui.md) walks a tab at a time — a machine being set
up, a CI job that runs somebody else's flow, or a line in a script is not always a moment you
are sitting in the interface. Naming no command at all lists them.

| Command | |
| --- | --- |
| `list` | Every place flows come from, in the order they are offered: the name, whether it has been fetched, and where from. `-q` prints just the names, one a line, for a script to read. |
| `show <name>` | What one is — where from, where kept, whether fetched — and the name each flow in it is offered under, which is what `-f` takes, with the line each says about itself. |
| `add <url> [<name>]` | Fetches one. `<url>` is a URL, a path, or `owner/repo` for one on GitHub; `<name>` is what to keep it under, defaulting to the repository's own name as `git clone` does. |
| `fetch <name>` | Fetches it again, or for the first time — which is what `official` usually has done to it. What the repository says now, not a merge into what you have. |
| `remove <name>` | Takes it away, flows and all. |

What was added is findable by `-f` at once — it is the same store, reached another way:

```sh
hmz flowverses add you/my-flowverse mine
hmz exec -f mine/review -a claude/claude-opus-5:high "the payments module"
```

**One that has not been fetched says so** where it would have said what it holds, rather than
saying it holds nothing — `official` is listed from the start, and what there is to run is not
the same question as what has been downloaded.

**`show` is the line that reads them, and the only one.** What a file holds is not a fact its
name carries — one file may hold [several flows](/reference/flows.md#several-flows-in-one-file), and the
file beside them may hold none — so the only way to say what `-f` would take is to import them,
as `/flow` does for the same question. `list`, `add` and `fetch` read nothing: a repository that
has just been cloned off the internet is not one to import unasked, and asking which places
there are is not asking about any of them.

So the name `show` prints is always a name `-f` takes — `official/humanize1:gen-plan`, not the
`official/humanize1` its filename would suggest, and never a `conftest.py` that holds no flow at
all. Adding one is still trusting that repository with this machine, exactly as installing a
package is. See [Security](/guide/security.md).

## `hmz agents`

The agents written down under a name, to be reached for from any flow. The same store
[`/agents`](/reference/tui.md#agents-kept-under-a-name) keeps, said as arguments instead — for a machine
being set up, a CI job, or anywhere the interface is not open.

```
hmz agents list [-q|--quiet]
hmz agents show <name>
hmz agents add <name> <cli>[@<provider>]/<model>:<effort> [--anchor <target>] [--no-goals] [--force]
hmz agents remove <name>
```

| Line | |
| --- | --- |
| `list` | Every one written down, by name and by what it runs. `-q` prints just the names, one a line, for a script to read. |
| `show <name>` | What one of them is: its CLI, its model at an effort, the account it runs as, what it may do, and where it works. Its skills are its CLI's own and are not written down here. |
| `add <name> <agent>` | Writes one down. The agent is spelled exactly as [`-a`](#hmz) spells one, so `claude@work/claude-opus-5:high` names the account too, and the written-out form may name a permission rung. |
| `remove <name>` | Takes it away. |

What it wrote down is there to be imported the next time a flow's agent is set up — **import**
on the agent sheet takes a copy of it, so tuning one inside a flow does not rewrite the one it
came from.

A name already written down is refused rather than quietly written over; `--force` is the line
that means it. Naming no command at all lists them.

```sh
hmz agents add reviewer codex@work/gpt-5.6-sol:high --no-goals
hmz agents add builder claude/claude-opus-5:max --anchor ssh://build-box
hmz agents list -q
```

Whose agents they are is not a question here: these are agents kept under a name, not the
agents of a flow. Which agent drives which flow is remembered per workspace — that is `hmz -f
<flow> -a <agent>`, or the second page of `/flow`.

## `hmz providers`

The accounts an agent may be run as: one named set of credentials per provider, kept apart from
the CLI's own. See [Providers](/reference/providers.md).

```
hmz providers list [<cli>]
hmz providers ways <cli>
hmz providers add <cli>/<name> [-w|--way <way>] [-s|--set VAR=VALUE]... [--no-login]
hmz providers login <cli>/<name> [-s|--set VAR=VALUE]...
hmz providers show <cli>/[<name>]
hmz providers falls-back <cli>/[<name>] [<name>]
hmz providers retry <cli>/[<name>] [-n|--tries <n>] [-p|--policy <policy>] [-t|--timeout <seconds>]
hmz providers remove <cli>/<name>
```

A provider is named `<cli>/<name>` — `claude/deepseek` — wherever one is asked for, and
`<cli>/` with no name is the account this machine is already signed into: an account of every
backend, which nobody made and which `show`, `falls-back` and `retry` take. Naming no command
at all lists them.

| Command | |
| --- | --- |
| `list [<cli>]` | What providers there are, or one backend's: the name, the way it was made by, and the variables it sets. |
| `ways <cli>` | How that backend can be signed into: each way, what it asks for, and what it runs. |
| `add <cli>/<name>` | Makes one, signs it in, and asks that CLI what it runs as it. `-w` chooses the way and defaults to the backend's first, which is `login`; `-s` answers one of the way's questions on the line rather than being asked, and repeats; `--no-login` writes it down without running the backend's own way in, and so without asking it anything either. |
| `login <cli>/<name>` | Signs an existing one in again, by the way it was made with, and asks it again what it runs. Takes the same `-s`. |
| `show <cli>/<name>` | What one holds: the way, when it was made, where it is kept, what it falls back to, how it is tried again, the names of the variables it sets, and which paths a turn under it is given instead of which. |
| `falls-back <cli>/<name> [<name>]` | Says which account of that CLI a turn carries on under when this one fails, or, with nothing after it, that this one is the end of the line. Each account naming the next is what makes a chain. |
| `retry <cli>/<name>` | Says how a failed turn under it is tried again before the chain moves on: `-n` how many times over, `-p` how long to wait between tries (`none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci`), `-t` the longest the whole of it may go on for. Nothing is retried by default. |
| `remove <cli>/<name>` | Takes it away, credentials and all. |

Whatever a way asks that the line did not answer is asked at the terminal, and a secret is not
echoed. A line with nobody at a terminal has to answer everything itself.

**What an account runs is that account's**, so it is asked for as soon as one is made: which
models a turn may name depends on which subscription, key or gateway it runs under. A CLI that
will not say does not fail the line — the account was made — and **r** on the models sheet
asks it again.

**Values are never printed** — `show` and `list` say which variables a provider sets and not
what they are.

```sh
hmz providers add claude/anthropic -w login
hmz providers add claude/deepseek -w gateway -s ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
hmz providers ways codex
hmz providers falls-back claude/anthropic deepseek
hmz providers retry claude/anthropic -n 3 -p exponential-jitter -t 120
hmz providers show claude/deepseek
hmz providers remove claude/deepseek
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
| `~/.humanize/cycles/<workspace>/<datetime>-<hex>.jsonl` | every run of a flow | What the run was: the flow, the agents, every session opened, how it ended. See [Cycles](/reference/tracing.md#cycles). |
| `~/.humanize/providers/<cli>/<name>/provider.json` | `hmz providers add` | What a [provider](/reference/providers.md) was made by, and what a turn under it runs with. `0600`, in a directory at `0700`. |
| `~/.humanize/providers/<cli>/<name>/{home,user}/...` | the CLI's own login | That provider's credentials, at the names the CLI keeps its own under. |
| `~/.humanize/providers/<cli>/<name>/models.json` | `hmz providers add`, **r** | What that CLI said it runs as that account. Goes when the account does. |
| `~/.humanize/local/<cli>.json` | `hmz providers falls-back`, `retry`, **f**, **t** | What the account this machine is signed into does when it fails: where it falls back to, and how a turn under it is tried again. |
| `~/.humanize/models/<cli>.json` | the TUI, **r** | The same, for the CLI as you already run it. |
| `~/.humanize/settings.yaml` | the TUI | What each workspace was last set up to run. |
| `~/.humanize/agents.yaml` | `hmz agents`, `/agents` | The agents written down under a name, to be reached for from any flow. |
| `~/.humanize/history.jsonl` | the TUI | What has been typed at the prompt before, and where. |
| `.humanize/<datetime>.trace.json` | `hmz collect` | The trace. Relative to the current directory, not to the workspace named. |
| `.humanize/<datetime>.session.md` | `/export` | The transcript on screen. |
| `~/.humanize/flowverses/<name>/` | `hmz flowverses add`, **a** | A [flowverse](/features/flowverses.md), cloned. Every flow in it is offered as `<name>/<flow>`. |
| `~/.humanize/skills/<owner>-<repo>/` | a flow that named one | A repository of [skills a flow brings](/reference/flows.md#the-skills-a-flow-brings), cloned. Fetched again the next time a run asks for it. |
| `.humanize/flows/*/` | you | This project's own flows. |
| `~/.humanize/flows/*/` | you | Your flows, in every project. |

`~/.humanize` is `$HUMANIZE_HOME` where that is set. The directories are made by whatever writes
into them.

## Exit statuses

| | |
| --- | --- |
| `0` | It did what it was asked. |
| `1` | It could not: the target could not be reached, the listener could not be started, there is no such provider, a turn could not be supervised. |
| `2` | The command line was wrong — argparse's own rejections, a flow that is not there or takes other agents, a malformed listen address, a non-loopback listener with no token. |
| `130` | Interrupted. |
| *the agent's own* | `hmz anchor` exits with the status of the program it ran, and `hmz providers add` with that of the login it ran. |

## Python entry points

Every command is a shell around a call you can make yourself. The layer each lives in is named
in [Architecture](/contributing/architecture.md).

```python
from hmz.runner import Runner          # hmz exec
from hmz.tracing import collect        # hmz collect
from hmz.coganchor import connect      # hmz anchor
from hmz.coganchor import check        # hmz anchor --check
from hmz import providers              # hmz providers
from hmz.flows import verses           # hmz flowverses
```

- `Runner(flow, agents).run(task)` — [Flows](/reference/flows.md)
- `collect(workspace, *, sessions=…, agents=…, output=…, start=…, end=…)` — [Tracing](/reference/tracing.md)
- `connect(command, config)` / `check(config)` — [Remote execution](/reference/remote-execution.md)
- `providers.providers(cli)` / `providers.find(cli, name)` / `providers.remove(cli, name)` —
  [Providers](/reference/providers.md)
- `verses.flowverses()` / `verses.add(url, name)` / `verses.fetch(name)` / `verses.remove(name)` —
  [Flowverses](/features/flowverses.md)
