# CLI reference

Every command, flag, environment variable, exit status and file. For a walk through rather than
a lookup, start at the [quickstart](/#run-a-flow).

```
hmz [<command> [<args>...]]
```

A line naming no command opens the [terminal interface](/reference/tui). A line naming something that
is not a command is a usage error listing the commands there are. Everything after the command
name reaches that command untouched — `--help` included — so each answers for its own
arguments.

`python -m hmz` is the same command line, which is how a turn spawns itself under an
[anchor](/reference/remote-execution).

## Who is reading

Every command is written twice over: for somebody at a terminal, and for a program.

- **A terminal** gets colour and layout. `hmz exec` draws the run as it happens — which agent
  is working and in which conversation, what it says, the tools it runs, the sub-agents it
  starts, a clock at the foot while it thinks, and what the turn cost when it lands.
- **A pipe or a file** gets exactly the same lines with no escape sequences in them. What each
  turn answered still goes to stdout and the run itself to stderr, so `hmz exec … > answer.txt`
  and `hmz exec … 2>/dev/null` mean what they always did.
- **A program** gets `--json`: one JSON object per line, flushed as it is written, and nothing
  else on stdout at all — anything the flow prints is put on stderr for the duration, so a
  stray line cannot break the stream.

`NO_COLOR`, `FORCE_COLOR` and `TERM=dumb` are honoured, in that order of authority. See
[environment variables](#environment-variables).

## `hmz`

```
hmz                  # opens the terminal interface
hmz --no-daemon      # opens it in this terminal, with the run going when the terminal does
hmz --version        # prints the installed version
hmz --help           # lists the commands
```

There is no command that opens the interface. Naming nothing at all is how it opens.

It opens on a run [held apart from this terminal](/reference/daemon), so that closing the
terminal is not what ends a day's work: a line naming no command reads whichever run is already
being held in this directory and starts one where none is. `--no-daemon` opens it in this
process instead, which is also what happens with no terminal to hand over to — output going to
a file, a suite driving the interface itself — and what happens if a run cannot be held at all,
which is said on stderr and then done without.

It opens on whatever this workspace was [last set up to run](/reference/tui#what-it-remembers) — or on
what the line says, for a run that is always the same run:

```
hmz -f|--flow <flow> [-c|--config <path>] [-a|--agent <spec>]...
```

| Argument | |
| --- | --- |
| `-f`, `--flow <flow>[:<name>]` | The flow to open on. |
| `-c`, `--config <path>` | A YAML file of what to set that flow up with, as [choosing the flow](/reference/tui#setting-a-flow-up) would have asked for it. Needs `-f`. |
| `-a`, `--agent <spec>` | What each of that flow's agents runs, in the order it takes them — as many as it drives. Needs `-f`. |

Nothing is started: the interface opens ready, and the first thing you say is still what starts
it. What the line says is checked before the interface opens — a flow that will not load, a
config the flow refuses, the wrong number of agents — so a line that is wrong is a line, not a
sheet to walk back out of.

A line that says what to run while a run is already being held here is a line to correct: a run
that is set up is set up, and two answers to how it is set up would be one of them silently
losing. `hmz` on its own reads it, and `hmz daemon stop` ends it.

```sh
hmz -f official/humanize1:rlcr -c setup.yaml
```

## `hmz exec`

Runs a [flow](/reference/flows) in the current directory, on the agents it is given.

```
hmz exec -f|--flow <flow> -a|--agent <spec>[,<spec>...] [-a ...] [-c|--config <path>] [--json] <task>

<spec> := [<name>=]<cli>[@<provider>]/<model>:<effort>
```

| Argument | |
| --- | --- |
| `-f`, `--flow <flow>[:<name>]` | **Required.** The flow to drive: the name of one humanize ships, `<where>/<flow>` for one any other place holds — a [flowverse](/reference/flows#flowverses), or `local`/`user` for your own — or the path to a flow anywhere else. A file that holds [several flows](/reference/flows#several-flows-in-one-file) is said which, after a colon. See [where flows live](/reference/flows#where-flows-live). |
| `-c`, `--config <path>` | A YAML file of what to set the flow up with, one field per line, under the names the flow declared — only for a flow that says it [can be set up](/reference/flows#settings-of-the-flow-s-own). The flow's own model checks it before the first turn. |
| `-a`, `--agent <spec>[,<spec>...]` | **One for each agent the flow drives** — several to an option, separated by commas, and the option repeated as often as suits. Unnamed they fill the flow's places in the order it takes them; `<name>=` fills the place the flow calls that. None at all for a flow whose only side is you, since nobody chooses what the person runs. |
| `--json` | Write the run for a program: one JSON object on stdout per thing an agent says, as it says it. See [Watching a run](#watching-a-run). |
| `<task>` | **Required.** What the flow is to have the agents do, as the text itself. Put `--` before it if it starts with a dash. |

### Watching a run

At a terminal, the run is drawn as it happens:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-5:high -a codex/gpt-5.6-sol:high "fix the build"
● builder is working
● Bash(pytest -q tests/)
● I fixed add() and the tests pass.
✻ input 40.0k · output 1.2k · $0.61 · claude-opus-5 · builder
✻ Worked for 74s · builder
```

The star under a turn says what it cost: the tokens by kind, then what those came to in money
where the model is one [somebody lists](/user/tally#the-money), then which model and which
agent. A model nobody lists shows the tokens and no figure at all — `$0.00` beside a turn that
cost something would be a claim about a bill, and a wrong one.

While a turn is thinking — which is most of a turn — a clock sits at the foot of the screen
saying which agent is working and for how long, or how many turns are open where there are
several. It is drawn only where a terminal is reading **and** escapes are wanted — a clock is
written in them, cursor and all, so `NO_COLOR` and `TERM=dumb` mean no clock — and it is gone
when the run is.

Piped or redirected, the same lines are written with no escape sequences in them. The run goes
to **stderr** and what each turn answered to **stdout**, which is where every script written
against `hmz exec` reads it:

```sh
hmz exec -f chat -a claude/claude-opus-5:high "summarise CHANGELOG.md" > summary.txt
```

`--json` writes the run for a program instead — [NDJSON](https://github.com/ndjson/ndjson-spec),
one object a line, flushed as each is written:

```console
$ hmz exec -f chat -a claude/claude-opus-5:high --json "say hello" | jq -c 'select(.kind == "result")'
{"at":1789026740.6,"agent":"assistant","cli":"claude","model":"claude-opus-5","session":"1d1ff959","kind":"result","text":"Hello.","whose":"","tokens":{"claude-opus-5":2080},"spent":{"input":2000,"output":80}}
```

| Key | |
| --- | --- |
| `at` | When it was said, as a Unix timestamp. |
| `agent` | Which agent said it, by the name the flow gave it. |
| `cli`, `model` | Which backend and model it was said on. |
| `session` | The backend's own id for the conversation, or `""` before the backend has named one. |
| `kind` | `begins` and `ends` bracket a turn; `text` is the agent talking, `reasoning` it thinking aloud, `tool` it using one, `subagent`/`subagent-ends` an agent it started of its own, `asks` it stopping to ask, `failed` a turn that went wrong, `result` the answer it ends on. |
| `text` | The words themselves. |
| `whose` | Which of a turn's several things it is about — the backend's id for a sub-agent — and `""` for everything else. |
| `tokens` | What the turn cost, per model. Only a `result` carries it, and only from a backend that says. |
| `spent` | The same cost by the kind of token it went on. |

Every object carries every key, whether or not it has anything to put in it. While `--json` is
on, **nothing else reaches stdout**: whatever the flow prints goes to stderr instead, so one
stray line cannot break the stream.

### Writing an agent

```
claude/claude-opus-4-8:high
claude@deepseek/claude-opus-4-8:high
builder=claude/claude-opus-4-8:high
claude/claude-opus-4-8:high,codex/gpt-5.6-sol:max
```

One `-a` is one agent or a list of them separated by commas, and every `-a` on the line adds to
the same list in the order they were written — so a flow of four agents is one option or four,
whichever reads better.

- `<cli>` is `agy`, `claude`, `codex`, `dsh`, `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen`
  or `zcode` — or any CLI of your own [added at `/providers`](/reference/agents#a-cli-of-your-own).
  Several also answer to the longer name they are installed under: `antigravity`,
  `claude-code`, `deepseek-harness`, `grok-build`, `kimi-code`, `qwen-code`, `mimocode`,
  `mimo-code` and `zcode-cli`.
- `<model>` and `<effort>` are whatever that CLI is asked for — humanize does not check them
  against a list, so a model your account has and this documentation does not still works.
- A model may hold slashes of its own — Kimi Code's are `kimi-code/k3`, and pi, opencode,
  mimocode and ZCode name every model as `provider/id` — so the CLI is read from the front and
  the effort from after the last colon.
- An `@` after the CLI names the [provider](/reference/providers) that agent's turns run as — the
  account, not the model: `claude@deepseek`. A CLI is never spelled with an `@` in it, so the
  two are told apart wherever an agent is written. An agent that names none runs its CLI as you
  already run it.
- A `<name>=` before the CLI says which of the flow's agents this one is — the field name from
  the [named tuple](/weaver/writing-a-flow#the-contract-in-three-rules) the flow declares, so
  `builder=claude/claude-opus-4-8:high`. Name every agent on the line or none of them: an agent
  with no name fills the flow's next place, which cannot be counted while the others are filled
  by name. A name the flow has not got, one given twice, a place left unnamed, and a name given
  to a flow that declared a plain `tuple` are each refused before anything runs, saying what the
  flow does declare.
- `permission=` and `web_search=` are **not** settings of `-a`. What an agent may do and
  whether it may read the internet are the flow's, declared beside the agent it drives, and a
  line that writes one is refused before anything runs, saying where it is said instead. See
  [Permissions](/user/permissions) and
  [Writing a flow](/weaver/writing-a-flow#say-what-each-agent-is-allowed).
- `cli=`, `model=`, `effort=`, `provider=`, `service_tier=` and `config.KEY=` are **gone**. `=`
  and `,` say which place an agent fills now, so the two spellings cannot both be read, and a
  line that writes one of those is refused saying so. A latency tier and a backend-native
  override are still an agent's to carry — they are set where the agent is made, from the
  [SDK](/reference/sdk) or by the flow, rather than on the line that names one.

**Names beat position.** A line that names its agents is put in the flow's order whatever order
you wrote them in; a line that names none fills the places in the order the flow takes them.
Two agents of one spelling are two agents either way, which is what makes a flow of an actor and
a reviewer at one configuration what it says it is.

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
hmz exec -f official/rlar -a claude/claude-opus-4-8:high,codex/gpt-5.6-sol:high "$(cat TASK.md)"
hmz exec -f official/rlar -a actor=claude/claude-opus-4-8:high -a reviewer=codex/gpt-5.6-sol:high "$(cat TASK.md)"
hmz exec -f official/flame_chase -a claude@anthropic/claude-opus-5:max -a claude@deepseek/deepseek-chat:high "fix the build"
hmz exec -f ./flows/mine -a kimi/kimi-code/k3:swarmmax "port this to asyncio"
hmz exec -f ralph_loop -a pi/openai-codex/gpt-5.5:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a opencode/opencode/big-pickle:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high -- "--force is not a flag here"
hmz exec -f official/humanize1:rlcr -c setup.yaml -a claude/claude-opus-5:max \
    -a codex/gpt-5.6-sol:xhigh "add undo"
```

Nobody is at a prompt, so an agent that stops to ask is told nobody answered and carries on.

## `hmz trace`

What a run left behind, gathered into something that can be read. One command with what there
is to do to a trace under it: `collect` is what there is today.

### `hmz trace collect`

Reads the trajectories the coding agents recorded -- and the programs they ran, where the run
was profiled -- and writes them out as one Chrome JSON trace. Works whether or not a flow drove
them. See [Tracing](/reference/tracing).

```
hmz trace collect [<workspace>] [--epic <epic> | --session <session>[,<session>]... | --all]
                  [--output <output>] [--start <start>] [--end <end>] [--json]
```

| Argument | |
| --- | --- |
| `<workspace>` | The directory to collect for. Defaults to this one, unless sessions are named. |
| `--epic <name>` | Which run to trace, by the name of its directory or a leading part of it. Defaults to the last run of the workspace. |
| `--session <s>[,<s>...]` | Sessions to trace instead of a run, comma separated and repeatable. |
| `--all` | Every session of the workspace instead of a run, whichever run opened them and whether any did. |
| `--output <path>` | Where to write. Defaults to `traces/<datetime>.trace.json` inside the run it is a trace of, and beside that workspace's runs for a trace that is of none; the directory is created if it is not there. |
| `--start <when>` | Earliest record to include, in any wording [dateparser](https://dateparser.readthedocs.io/) understands. |
| `--end <when>` | Latest record to include, same wording. |
| `--json` | Say where it went and what it holds as one JSON object, for a program to read. |

A trace is of a run and holds the sessions that run opened and no others, asked for by the ids
the run wrote down rather than by the directory it ran in -- so a run that worked in a
[machine's](/reference/machines) mirror is in its own trace, and a run that opened nothing is a
trace of nothing. `--session` and `--all` are the other thing a trace can be of: what a directory
holds whoever opened it. Naming a run as well is a usage error, and neither is offered in the
interface, `/epics` being a list of runs.

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either, and the sub-agents it started come with it. Named sessions are collected wherever they
were recorded, and are then cut down to the workspace when one is given.

A trace goes with the run it is a trace of: an epic already holds what happened, what each
session was logged to and what the flow left behind. One that is of no run goes beside that
workspace's runs instead. The default name is the UTC moment it was collected, so collecting
twice keeps both traces rather than writing over the first -- and `--output` still wins, a trace
being also a thing to attach to an issue.

Prints the output path, which run it is a trace of, and what it holds:

```console
$ hmz trace collect
~/.humanize/epics/-home-you-code/20260809T014455.212Z-9f21ab/traces/20260809T014455Z.trace.json of 20260809T014455.212Z-9f21ab: 3 sessions, 412 slices
```

### Examples

```sh
hmz trace collect                                    # the last run here
hmz trace collect --epic 20260809T0144               # a run of this workspace, by name
hmz trace collect ~/code/other --start "3 days ago"  # another workspace's last run, recent part
hmz trace collect --all                              # every session here, run or no run
hmz trace collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz trace collect --end "yesterday 18:00" --output /tmp/before.json
```

## `hmz export`

One whole run, packaged up to send to somebody who was not there: what it did, what every
session of every agent was logged as, and what this machine was running — with every credential
taken out. See [Exporting a run](/user/export).

```
hmz export [<epic>] [-o|--output <output>]
```

| Argument | |
| --- | --- |
| `<epic>` | Which run, by the name of its directory, a leading part of that name, or the path to it. Defaults to the last run of this directory. |
| `-o`, `--output <path>` | Where to write it: a file, or a directory to write it into under its own name. Defaults to `.humanize/<run>.epic.tar.gz` here; the directory is created if it is not there. |

A run points at each backend's own session log by a symlink rather than copying it, which is
right on the machine that ran it and worth nothing anywhere else. An export follows every one
of those links and carries what is behind it, beside the run's own records, the state a
resumable flow left, the profile of a profiled run, every trace gathered of it, and a
`manifest.json` saying which run this was, which agents drove it — CLI, model, effort, and the
account **by name** — the workspace and the commit it is on, and per backend the version it
reports and the SHA-256 of the executable that took the turns.

Every byte of every file is scrubbed on the way in: the values of every account's variables,
keys in the shapes the vendors mint them, anything signed into a URL, and any value a log named
as a token, a secret, a key or a password. What a turn cost is left alone.

A session the archive holds no log for says why — opencode and mimocode keep their sessions in
a database of their own and write nothing humanize can read.

Prints where it landed, which run it is of, what is in it and how big it came out:

```console
$ hmz export
/home/you/code/.humanize/20260809T014455.212Z-9f21ab.epic.tar.gz of 20260809T014455.212Z-9f21ab: 3 sessions, 4 logs, 812 kB
```

### Examples

```sh
hmz export                                   # the last run here
hmz export 20260809T0144                     # a run of this directory, by name
hmz export ~/.humanize/epics/-home-you-x/20260809T014455.212Z-9f21ab
hmz export -o /tmp/for-the-issue.tar.gz      # somewhere to attach it from
```

## `hmz anchor`

Runs a coding agent on this machine whose work lands on another one. See
[Remote execution](/reference/remote-execution).

```
hmz anchor [options] AGENT [ARGS...]
```

Everything after the agent's name is the agent's own.

| Flag | Default | |
| --- | --- | --- |
| `--target URL` | `$HUMANIZE_TARGET`, else `local` | `ssh://HOST`, `docker://CONTAINER`, `tcp://HOST:PORT`, or `local[:DIR]`. |
| `--workspace PATH` | this directory | The project directory as it exists on the target. |
| `--chdir PATH` | `--workspace` | Where inside that workspace the agent starts, as the target names it. What a [session opened at a directory](/reference/agents#the-directory-a-session-works-in) comes to: the agent is put in this machine's mirror of it. |
| `--remote-path PATH` | `--workspace` | Where that workspace really lives on the target, if not at the same path. |
| `--shadow PATH` | `--workspace` | The local mirror directory. Defaulting to the workspace path is what makes the paths the agent sees the target's own. |
| `--local-path PATH` | — | Keep this path on this machine even when it is inside the workspace. Repeatable. |
| `--local-exec PATH` | — | Run programs under this path here rather than on the target. Repeatable. |
| `--redirect FROM=TO` | — | Answer this path with that one — the file it names, or everything under the directory it names — and keep what it is answered with local. What a turn under a [provider](/reference/providers) is given. Repeatable. |
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
to a shell on that machine — read [Security](/user/security).

```sh
hmz anchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
```

## `hmz check`

```
hmz check [--static] [--strict] [--json] [--prophecy | --ship] FLOW [FLOW...]
```

Reads a flow for what will not run — before anything runs it. Two readings, in their order: a
static one over every file the flow holds, which executes nothing and is safe to point at a
flow nobody has read, and then the flow loaded — in a subprocess held to a clock — so its live
config model is read too. A flow is named the way `-f` names one: `chat`, `official/rlar`, a
path of your own.

| Argument | |
| --- | --- |
| `--static` | Only the reading that executes nothing: do not load the flow at all. |
| `--strict` | Exit non-zero on warnings too. |
| `--json` | One JSON object per finding, one a line, for a script to read. |
| `--prophecy` | Print what each [atlas](/weaver/atlas) compiles to instead of what is wrong with it. |
| `--ship` | Write each atlas's prophecy into its own directory, for runs of it to walk. |

Each finding prints as `file:line: severity: code: what is wrong`, with a count under them.
An error is a flow that cannot run, cannot be answered or cannot end — a loop nothing inside
can end, a name the interfaces do not answer to, an import of humanize's own internals — and
a warning is a flow that runs and may be regretted: a loop whose only way out is an agent's
verdict, a shaped answer read without a guard, a config that takes anything.

It exits `0` for flows with nothing blocking (warnings print and pass), `1` where any error
was found — or any warning, under `--strict` — and `2` for a line to correct or a name no
flow answers to.

An [atlas](/weaver/atlas) gets the stricter reading of the two automatically, its body being a
declaration rather than a program. `--prophecy` prints the graph that reading compiled, one
line of canonical JSON; `--ship` writes it to `<flow>/prophecy.pkl`, which every run of that
flow walks from then on. The two cannot be given together, and a name that is not an atlas
that compiles exits non-zero.

```sh
hmz check official/rlar          # one warning: a loop only its reviewer ends
hmz check --strict local/mine    # hold a flow of your own to the whole bar
hmz check --prophecy local/mine  # the graph it compiles to, for a diff to read
hmz check --ship local/mine      # and beside the flow, for runs of it to walk
```

## `hmz flowverses`

Where flows come from: a git repository with a `flows/` directory apiece, cloned under
humanize's home, and the flows of your own read where they lie. Each is offered under the name
it is listed here under. See [Flowverses](/weaver/flowverses).

```
hmz flowverses list [-q|--quiet] [--json]
hmz flowverses show <name> [--json]
hmz flowverses add <url> [<name>]
hmz flowverses fetch <name>
hmz flowverses remove <name>
```

The same places the interface's [`/flowverses`](/reference/tui#where-flows-come-from) is the
list of — a machine being set up, a CI job that runs somebody else's flow, or a line in a script
is not always a moment you are sitting in the interface. Naming no command at all lists them.

| Command | |
| --- | --- |
| `list` | Every place flows come from, in the order they are offered: the name, whether it has been fetched, and where from. `-q` prints just the names, one a line, for a script to read, and `--json` one object a place. |
| `show <name>` | What one is — where from, where kept, whether fetched — and the name each flow in it is offered under, which is what `-f` takes, with the line each says about itself. `--json` says the whole of it as one object, the flows in a `holds` list. |
| `add <url> [<name>]` | Fetches one. `<url>` is a URL, a path, or `owner/repo` for one on GitHub; `<name>` is what to keep it under, defaulting to the repository's own name as `git clone` does. |
| `fetch <name>` | Fetches it again, or for the first time — which is what `official` usually has done to it. What the repository says now, not a merge into what you have. |
| `remove <name>` | Takes it away, flows and all. |

`local` and `user` are your own flows — `.humanize/flows` here, and the one in your home
directory — listed as places like the rest. Nothing fetches them, so `add`, `fetch` and
`remove` refuse all three.

What was added is findable by `-f` at once — it is the same store, reached another way:

```sh
hmz flowverses add you/my-flowverse mine
hmz exec -f mine/review -a claude/claude-opus-5:high "the payments module"
```

**One that has not been fetched says so** where it would have said what it holds, rather than
saying it holds nothing — `official` is listed from the start, and what there is to run is not
the same question as what has been downloaded.

**`show` is the line that reads them, and the only one.** What a file holds is not a fact its
name carries — one file may hold [several flows](/reference/flows#several-flows-in-one-file), and the
file beside them may hold none — so the only way to say what `-f` would take is to import them,
as `/flow` does for the same question. `list`, `add` and `fetch` read nothing: a repository that
has just been cloned off the internet is not one to import unasked, and asking which places
there are is not asking about any of them.

So the name `show` prints is always a name `-f` takes — `official/humanize1:gen-plan`, not the
`official/humanize1` its filename would suggest, and never a `conftest.py` that holds no flow at
all. Adding one is still trusting that repository with this machine, exactly as installing a
package is. See [Security](/user/security).

## `hmz providers`

The accounts an agent may be run as: one named set of credentials per provider, kept apart from
the CLI's own. See [Providers](/reference/providers).

```
hmz providers list [<cli>] [--json]
hmz providers ways <cli> [--json]
hmz providers add <cli>/<name> [-w|--way <way>] [-s|--set VAR=VALUE]... [--no-login]
                               [--also <cli>[,<cli>...]]
hmz providers login <cli>/<name> [-s|--set VAR=VALUE]...
hmz providers show <cli>/[<name>] [--json]
hmz providers falls-back <cli>/[<name>] [<name>]
hmz providers remove <cli>/<name>
```

A provider is named `<cli>/<name>` — `claude/deepseek` — wherever one is asked for, and
`<cli>/` with no name is the account this machine is already signed into: an account of every
backend, which nobody made and which `show` and `falls-back` take. Naming no command at all
lists them.

| Command | |
| --- | --- |
| `list [<cli>]` | What providers there are, or one backend's: the name, the way it was made by, the variables it sets, and — where it is set — what it falls back to. The account this machine is signed into is listed as `<cli>/  as local` wherever it has one. A `<cli>` no backend answers to exits 1 rather than listing everybody's. |
| `ways <cli>` | How that backend can be signed into: each way, what it asks for, and what it runs. |
| `add <cli>/<name>` | Makes one, signs it in, and asks what it runs as it — the endpoint the account points that CLI at, where it names one, and the CLI itself where it does not. `-w` chooses the way and defaults to the backend's first — `login` for the CLIs that sign in, `key` for `dsh`; `-s` answers one of the way's questions on the line rather than being asked, and repeats; `--no-login` writes it down without running the backend's own way in, and so without asking it anything either. `--also` writes the same account down for the backends it names, comma separated, under the same name and over one already there — or `all` for [every one it could be run as](/reference/providers#one-account-several-clis). A line that did not ask says it could have. |
| `login <cli>/<name>` | Signs an existing one in again, by the way it was made with, and asks again what it runs. Takes the same `-s`. |
| `show <cli>/<name>` | What one holds: the way, when it was made, where it is kept, what it falls back to, the names of the variables it sets, which paths a turn under it is given instead of which, and an `also runs` line per [other backend](/reference/providers#one-account-several-clis) that could be run as it. |
| `falls-back <cli>/<name> [<name>]` | Says which account of that CLI a turn carries on under when this one fails, or, with nothing after it, that this one is the end of the line. Each account naming the next is what makes a chain. |
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
hmz providers add claude/shared -w key --also pi,opencode      # or --also all
hmz providers ways codex
hmz providers falls-back claude/anthropic deepseek
hmz providers show claude/deepseek
hmz providers remove claude/deepseek
```

## `hmz fallback`

```sh
hmz fallback list [-q|--quiet] [--json]
hmz fallback show <cli>[@<account>]/<model> [--json]
hmz fallback add <cli>[@<account>]/<model> <cli>[@<account>]/<model>
hmz fallback retry <cli>[@<account>]/<model> <tries> [-p|--policy <policy>] [-t|--timeout <seconds>]
hmz fallback remove <cli>[@<account>]/<model>
```

Where a turn goes when the **place** taking it cannot take it at all — a model retired, a CLI
that will not start, a rate limit on the whole account rather than one request. The layer
between an agent and its accounts: an account's chain is a thing about an account, and this is
about neither of the two places it names.

A place is three things and no more — the CLI, the account it runs as, and the model it runs.
How hard the agent thinks and what it may reach for are what that agent *is*, and they come
across a step unchanged. `show` prints the whole walk rather than the one step, since the walk
is what a failed turn does.

| Command | |
| --- | --- |
| `list` | Every step: the place, how often a failed turn there is taken again, and where it goes once those are spent. `-q` prints the place alone, `--json` one object a step. |
| `show <place>` | The whole walk from that place, in the order a turn tries them. `--json` says one object a place of the walk. |
| `add <place> <place>` | Says where the first one's turns go when it cannot run. |
| `retry <place> <tries>` | Says how many goes beyond the first a failed turn there gets before the step is taken: `-p` how long to wait between them (`none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci`), `-t` the longest the whole of it may go on for. Nothing is retried by default. |
| `remove <place>` | Takes the whole step away, tries and destination alike. |

```sh
hmz fallback add claude/claude-opus-5 codex/gpt-5.6-sol
hmz fallback add claude@work/claude-opus-5 codex@key/gpt-5.6-sol
hmz fallback retry claude/claude-opus-5 3 -p exponential-jitter -t 120
hmz fallback show claude/claude-opus-5
hmz fallback remove claude/claude-opus-5
```

A place cannot fall back to itself, one place has one place to go, and a chain that comes
round on itself ends at the second sight of a place. The same steps are in the interface at
[`/fallback`](/reference/tui#where-a-turn-goes-when-it-cannot-be-taken), and what they mean is
[Falling back](/user/fallback).

## `hmz daemon`

The runs being [held apart from a terminal](/reference/daemon): which there are, what one of them
is doing, and the two ways one ends. `hmz` on its own is how one is opened and read; this is
what is left to say about one from outside it.

```
hmz daemon [list [-q] [--json] | status [<workspace>] [--json] | start [-f <flow>] [-a <agent>]... | attach [<workspace>] | stop [<workspace>] [--kill]]
```

| | |
| --- | --- |
| `list` | Every run being held on this machine, oldest first: where, which process, since when, and how many terminals are reading. `-q` prints the directories alone, one a line, and `--json` one object a run. A line naming no command does this. |
| `status [<workspace>]` | What one of them is doing, without attaching to it: how many are reading, and which flows are running under it. `--json` says the whole of it as one object, which is what a monitor that cannot attach reads. |
| `start [-f <flow>] [-a <agent>]...` | Holds a run here without reading it, for a machine being set up rather than sat at. Takes `-f` and `-a` exactly as `hmz` does. |
| `attach [<workspace>]` | Reads one from this terminal, which is the long way round of what `hmz` already does. |
| `stop [<workspace>]` | Stops the flow and closes the interface, which is what `/exit` means, and waits for it to go. `--kill` ends the process holding both instead, for one that will not. |

A directory nothing is being held in says so and exits non-zero rather than starting one.

```console
$ hmz daemon list
/home/you/project   pid 41221  since 2026-08-28T09:12:04Z  1 terminal reading

$ hmz daemon status
workspace   /home/you/project
pid         41221
started     2026-08-28T09:12:04Z
socket      /home/you/.humanize/daemons/project-58036393b2f5
reading     1 terminal
running     official/rlar
```

## `hmz tools`

```sh
hmz tools --at <socket>
```

Carries the tool protocol between a coding agent and the flow whose
[callbacks](/weaver/tools) it is: it reads its stdin into the flow's socket and the flow's
answers back out to its stdout, and does nothing else.

**Not a command anybody types.** A CLI takes a tool by starting a program, so there is a
program — the same reason `hmz cred` exists. humanize spawns it and tells the backend to run
it; a socket that is not there exits 1, which the CLI reads as tools being unavailable rather
than as a turn that failed.

## Environment variables

| Variable | Read by | |
| --- | --- | --- |
| `HUMANIZE_HOME` | everything | Where humanize keeps what outlives one run. Defaults to `~/.humanize`. |
| `HUMANIZE_TARGET` | `hmz anchor` | Default for `--target`. |
| `HUMANIZE_TOKEN` | `hmz anchor`, `hmz anchor serve` | Default for `--token`. |
| `HUMANIZE_LOG` | `hmz anchor`, `hmz anchor serve` | Default for `--log-level`. |
| `HUMANIZE_DAEMON` | `hmz` with no command | `off`, `0` or `no` opens the interface in this terminal rather than [holding the run apart from it](/reference/daemon), which is what `--no-daemon` says on the line. Anything else — including empty — is silence, and silence holds the run. |
| `HUMANIZE_SENTRY` | everything | `on` or `off`, answering the [reporting](/user/reporting) question for one process without writing anything down. Nothing else is looked at while it is set. |
| `HUMANIZE_WATCHDOG` | everything that runs a turn | How long a turn may say nothing before [the watchdog looks at it](/reference/agents#when-a-cli-stops-answering), in seconds, overriding each backend's own. `0` turns it off. |
| `HUMANIZE_SHADOWS` | `hmz anchor`, a container or a machine an agent works on | Where the mirrors coganchor has been pointed at are recorded. Defaults to `~/.cache/humanize/shadows`. |
| `CLAUDE_CONFIG_DIR` | `hmz trace collect`, the TUI's cost readout | Claude Code's home. Defaults to `~/.claude`. |
| `CODEX_HOME` | same | Codex's home. Defaults to `~/.codex`. |
| `DSH_HOME` | same | DeepSeek Harness's home. Defaults to `~/.dsh`. |
| `GROK_HOME` | the model list, the cost readout | Grok Build's home. Defaults to `~/.grok`. |
| `KIMI_CODE_HOME` | same | Kimi Code's home. Defaults to `~/.kimi-code`. |
| `PI_CODING_AGENT_DIR` | same | pi's home. Defaults to `~/.pi/agent`. |
| `QWEN_HOME` | same | Qwen Code's home. Defaults to `~/.qwen`. |
| `XDG_DATA_HOME` | the model list | Where opencode and mimocode keep their data. Defaults to `~/.local/share`. |
| `NO_COLOR` | every command, the TUI | Honoured. Set to anything non-empty, nothing writes an escape sequence — and it wins over `FORCE_COLOR`. |
| `FORCE_COLOR` | every command | Set to anything but `0`, a command writes colour into something that is not a terminal — which is what a CI log wants. It does not make a run believe somebody is watching it: a piped run is still written plainly in shape, just in colour. |
| `TERM` | every command | `dumb` is a terminal saying it could not read escapes, and is honoured as `NO_COLOR` is. |
| `TEXTUAL_THEME` | the TUI | Names a Textual theme to use instead of humanize's own, which is your terminal's sixteen colours. A name no theme answers to is ignored. |

Antigravity CLI and ZCode are the two backends whose homes cannot be moved: neither reads a
variable of its own, so their state is always `~/.gemini/antigravity-cli` and `~/.zcode`.

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
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/epic.jsonl` | every run of a flow | What the run was: the flow, the agents, every session opened and as which account, how it ended. See [Epics](/reference/tracing#epics). |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/epic.<flow>_<hex>.jsonl` | the same, per flow that run [called](/reference/flows#a-flow-that-calls-another-flow) | What that call was, written the same way: a called flow opens sessions and calls flows of its own. The run's own record says which file each call is in. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/sessions/<session>/` | the same | A link per file each session was logged to, for reading a run back. humanize reads and writes the logs where the backend keeps them. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/state.json` | a [resumable](/reference/flows) flow | What that flow left behind, which the next run of it picks up. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/profile.jsonl` | a run of a workspace that asked to be profiled | The programs the run started, sampled while it ran. |
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/traces/<datetime>.trace.json` | `hmz trace collect`, `/epics` | The trace of that run. |
| `~/.humanize/providers/<cli>/<name>/provider.json` | `hmz providers add` | What a [provider](/reference/providers) was made by, and what a turn under it runs with. `0600`, in a directory at `0700`. |
| `~/.humanize/providers/<cli>/<name>/{home,user}/...` | the CLI's own login | That provider's credentials, at the names the CLI keeps its own under. |
| `~/.humanize/providers/<cli>/<name>/models.json` | `hmz providers add`, **r** | What that account may name: what its endpoint serves where it has one, and what the CLI said where it has not. Never the credential either was asked under. Goes when the account does. |
| `~/.humanize/local/<cli>.json` | `hmz providers falls-back`, `retry`, and what enter opens in `/providers` | What the account this machine is signed into does when it fails: where it falls back to, and how a turn under it is tried again. |
| `~/.humanize/acp.json` | a CLI of your own, added where `/providers` asks which CLI | The CLIs of your own that speak the [Agent Client Protocol](/reference/agents#a-cli-of-your-own), as `{name: [argv…]}`. A backend from the moment it is written. |
| `~/.humanize/models/<cli>.json` | the TUI, **r** | The same, for the CLI as you already run it. |
| `~/.humanize/settings.yaml` | the TUI | What each workspace was last set up to run and whether its runs are profiled, and the settings that are not a workspace's — `enable_sentry`, the answer to the [reporting](/user/reporting) question. |
| `~/.humanize/history.jsonl` | the TUI | What has been typed at the prompt before, and where. |
| `~/.humanize/daemons/<project>-<digest>/daemon.sock` | `hmz` with no command | The socket a terminal reaches a [held run](/reference/daemon) through. `0600`. |
| `~/.humanize/daemons/<project>-<digest>/daemon.json` | the same | Which process is holding it, which workspace, and since when. |
| `~/.humanize/daemons/<project>-<digest>/daemon.log` | the same | Whatever could not be said through a terminal about that run — what the daemon itself could not say, and what went wrong in a process reaching for its socket. |
| `.humanize/<run>.epic.tar.gz` | `/export`, `hmz export` | One whole run, packaged up to send: its records, its session logs in full, the transcript, and a manifest. `0600`. |
| `~/.humanize/flowverses/<name>/` | `hmz flowverses add`, **a** in `/flowverses` | A [flowverse](/weaver/flowverses), cloned. Every flow in it is offered as `<name>/<flow>`. |
| `~/.humanize/skills/<owner>-<repo>-<digest>/` | a flow that named one | A repository of [skills a flow brings](/reference/flows#the-skills-a-flow-brings), cloned. The digest is of the URL, so two repositories of one name on two hosts are two directories. Fetched again the next time a run asks for it. |
| `.humanize/flows/*/` | you | This project's own flows, offered as `local/<flow>`. |
| `~/.humanize/flows/*/` | you | Your flows in every project, offered as `user/<flow>`. |

`~/.humanize` is `$HUMANIZE_HOME` where that is set. The directories are made by whatever writes
into them.

## Exit statuses

| | |
| --- | --- |
| `0` | It did what it was asked. |
| `1` | It could not: the target could not be reached, the listener could not be started, there is no such provider, a turn could not be supervised, `hmz check` found something blocking. |
| `2` | The command line was wrong — argparse's own rejections, a flow that is not there or takes other agents, a malformed listen address, a non-loopback listener with no token. |
| `130` | Interrupted. |
| *the agent's own* | `hmz anchor` exits with the status of the program it ran, and `hmz providers add` with that of the login it ran. |

## Python entry points

Every command is a shell around a call you can make yourself. The layer each lives in is named
in [Architecture](/contributing/architecture).

Every one of them is [`Hmz`](/reference/sdk), which is the same object the command line holds:

```python
from hmz.sdk import Hmz

hmz = Hmz()
hmz.exec(["-f", "ralph_loop", "-a", "claude/claude-opus-5:high", "fix the build"])
hmz.epics.trace(output="run.trace.json")
hmz.accounts.all("claude")
hmz.verses.add("humanfia/flowverse")
```

- `hmz.exec(argv)` / `hmz.run(flow, agents, task)` — [Flows](/reference/flows)
- `hmz.epics.trace(...)` — [Tracing](/reference/tracing)
- `hmz.accounts` — [Providers](/reference/providers)
- `hmz.verses` — [Flowverses](/weaver/flowverses)

The layers under it are reachable directly where that is what you want — the SDK composes them
and restates none of them:

```python
from hmz.runner import Runner          # hmz exec
from hmz.tracing import collect        # hmz trace collect
from hmz.coganchor import connect      # hmz anchor
from hmz.coganchor import check        # hmz anchor --check
from hmz.daemon import running, start  # hmz daemon
```

- `Runner(flow, agents).run(task)` — [Flows](/reference/flows)
- `collect(workspace, *, sessions=…, agents=…, output=…, start=…, end=…, profile=…)` — [Tracing](/reference/tracing)
- `connect(command, config)` / `check(config)` — [Remote execution](/reference/remote-execution)
- `running(workspace)` / `start(opens)` — [Daemon](/reference/daemon)
