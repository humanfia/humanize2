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
hmz --version        # prints the installed version
hmz --help           # lists the commands
```

There is no command that opens the interface. Naming nothing at all is how it opens.

It opens on a run [held apart from this terminal](/reference/daemon), so that closing the
terminal is not what ends a day's work: a line naming no command reads whichever run is already
being held in this directory and starts one where none is. It opens it in this
process instead, which is also what happens with no terminal to hand over to — output going to
a file, a suite driving the interface itself — and what happens if a run cannot be held at all,
which is said on stderr and then done without.

It opens on whatever this workspace was [last set up to run](/reference/tui#what-it-remembers).
The line says nothing about that: which flow, what drives it and what it is set up with are
[chosen at the prompt](/reference/tui#setting-a-flow-up), and what was chosen there is what the
next `hmz` here opens on — so a run that is always the same run is set up once rather than
spelled out again by every line that reads it.

Nothing is started either: the interface opens ready, and the first thing you say is still what
starts it.

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

## `hmz anchor`

Runs a coding agent on this machine whose work lands on another one. See
[Remote execution](/reference/remote-execution).

**Not one of the commands the listing shows.** humanize spawns it for every turn whose work
lands on another machine, and the zipapp bootstrapped onto a target runs `hmz anchor serve` to
answer one — the same reason `hmz tools` is a command line. It still runs when it is typed,
which is what `--check` is for.

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
| `--native` | off | Run the CLI already installed **on the target** instead of supervising one here. No mirror, nothing traced: this process starts it there and carries its three streams, its signals and its exit status. The flags above that describe a mirror say nothing under it. |
| `--hush NAME` | — | With `--native`, run the CLI on the target without this variable, whoever left it there. The other half of `--private`: a key in the target's own shell profile outranks the account the turn was given, and merely not sending one does not remove it. Repeatable. |
| `--project NAME=DIR` | — | With `--native`, put this directory of credentials on the target for the length of the turn and set `NAME` to where it landed. Written where only the target's user may read it, and removed when the turn is over. Repeatable. |
| `--carry DIR=PATH` | — | With `--native`, put this directory into the target's copy of the workspace at `PATH` for the length of the turn — which is how a flow's own [skills](/reference/flows#the-skills-a-flow-brings) get there. Nothing already at `PATH` is written over. Repeatable. |
| `--installs LINE` | — | With `--native`, the line that installs this CLI, said where the target has nothing to run. |
| `--check` | off | Connect, report what was found, and exit without running anything. |
| `--log-level {debug,info,warning,error}` | `$HUMANIZE_LOG`, else `warning` | Logging verbosity. The log goes to stderr. |

Settings no session could run under — a target nobody can read, a `--net` that is neither, a
credential bound for something that is not a variable — exit 2 the way argparse's own
rejections do. A `--native` session whose CLI the target has not got exits **127**, the status
every shell uses for a command it could not find, so that whatever spawned it reads it as a CLI
that is not installed.

```sh
hmz anchor --target ssh://build-box claude
hmz anchor --target ssh://gpu-01 codex exec "run the test suite"
hmz anchor --target docker://build-container --workspace /srv/project claude
hmz anchor --native --target docker://build-container --remote-path /srv/project claude
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
| `HUMANIZE_DAEMON` | `hmz` with no command | `off`, `0` or `no` opens the interface in this terminal rather than [holding the run apart from it](/reference/daemon). Anything else — including empty — is silence, and silence holds the run. |
| `HUMANIZE_SENTRY` | everything | `on` or `off`, answering the [reporting](/user/reporting) question for one process without writing anything down. Nothing else is looked at while it is set. |
| `HUMANIZE_WATCHDOG` | everything that runs a turn | How long a turn may say nothing before [the watchdog looks at it](/reference/agents#when-a-cli-stops-answering), in seconds, overriding each backend's own. `0` turns it off. |
| `HUMANIZE_SHADOWS` | `hmz anchor`, a container or a machine an agent works on | Where the mirrors coganchor has been pointed at are recorded. Defaults to `~/.cache/humanize/shadows`. |
| `CLAUDE_CONFIG_DIR` | the traces `/epics` gathers, the TUI's cost readout | Claude Code's home. Defaults to `~/.claude`. |
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
| `~/.humanize/epics/<workspace>/<datetime>-<hex>/traces/export.trace.json` | exporting on `/epics` | The trace of that run, gathered as it was exported. One gathered by hand is named for the moment instead. |
| `~/.humanize/providers/<cli>/<name>/provider.json` | **a** in `/providers` | What a [provider](/reference/providers) was made by, and what a turn under it runs with. `0600`, in a directory at `0700`. |
| `~/.humanize/providers/<cli>/<name>/{home,user}/...` | the CLI's own login | That provider's credentials, at the names the CLI keeps its own under. |
| `~/.humanize/providers/<cli>/<name>/models.json` | **a** in `/providers`, **r** | What that account may name: what its endpoint serves where it has one, and what the CLI said where it has not. Never the credential either was asked under. Goes when the account does. |
| `~/.humanize/local/<cli>.json` | what enter opens in `/providers` | What the account this machine is signed into does when it fails: where it falls back to, and how a turn under it is tried again. |
| `~/.humanize/acp.json` | a CLI of your own, added where `/providers` asks which CLI | The CLIs of your own that speak the [Agent Client Protocol](/reference/agents#a-cli-of-your-own), as `{name: [argv…]}`. A backend from the moment it is written. |
| `~/.humanize/models/<cli>.json` | the TUI, **r** | The same, for the CLI as you already run it. |
| `~/.humanize/settings.yaml` | the TUI | What each workspace was last set up to run and whether its runs are profiled, and the settings that are not a workspace's — `enable_sentry`, the answer to the [reporting](/user/reporting) question. |
| `~/.humanize/history.jsonl` | the TUI | What has been typed at the prompt before, and where. |
| `~/.humanize/daemons/<project>-<digest>/daemon.sock` | `hmz` with no command | The socket a terminal reaches a [held run](/reference/daemon) through. `0600`. |
| `~/.humanize/daemons/<project>-<digest>/daemon.json` | the same | Which process is holding it, which workspace, and since when. |
| `~/.humanize/daemons/<project>-<digest>/daemon.log` | the same | Whatever could not be said through a terminal about that run — what the daemon itself could not say, and what went wrong in a process reaching for its socket. |
| `.humanize/<run>.epic.tar.gz` | `/export` | One whole run, packaged up to send: its records, its session logs in full, the transcript, and a manifest. `0600`. |
| `~/.humanize/flowverses/<name>/` | **a** in `/flowverses` | A [flowverse](/weaver/flowverses), cloned. Every flow in it is offered as `<name>/<flow>`. |
| `~/.humanize/skills/<owner>-<repo>-<digest>/` | a flow that named one | A repository of [skills a flow brings](/reference/flows#the-skills-a-flow-brings), cloned. The digest is of the URL, so two repositories of one name on two hosts are two directories. Fetched again the next time a run asks for it. |
| `.humanize/flows/*/` | you | This project's own flows, offered as `local/<flow>`. |
| `~/.humanize/flows/*/` | you | Your flows in every project, offered as `user/<flow>`. |

`~/.humanize` is `$HUMANIZE_HOME` where that is set. The directories are made by whatever writes
into them.

## Exit statuses

| | |
| --- | --- |
| `0` | It did what it was asked. |
| `1` | It could not: the target could not be reached, the listener could not be started, a turn could not be supervised. |
| `2` | The command line was wrong — argparse's own rejections, a flow that is not there or takes other agents, a malformed listen address, a non-loopback listener with no token. |
| `130` | Interrupted. |
| *the agent's own* | `hmz anchor` exits with the status of the program it ran, and `hmz cred` with that of the program it supervised. |

## Python entry points

Every way in — the command, and every sheet of the interface — is a shell around a call you
can make yourself. The layer each lives in is named in
[Architecture](/contributing/architecture).

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
from hmz.runtime.runner import Runner          # hmz exec
from hmz.runtime.tracing import collect        # the trace /epics gathers
from hmz.coganchor import connect      # hmz anchor
from hmz.coganchor import check        # hmz anchor --check
from hmz.daemon import running, start  # the run hmz holds apart from the terminal
```

- `Runner(flow, agents).run(task)` — [Flows](/reference/flows)
- `collect(workspace, *, sessions=…, agents=…, output=…, start=…, end=…, profile=…)` — [Tracing](/reference/tracing)
- `connect(command, config)` / `check(config)` — [Remote execution](/reference/remote-execution)
- `running(workspace)` / `start(opens)` — [Daemon](/reference/daemon)
