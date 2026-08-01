# Troubleshooting

What each thing that goes wrong looks like, and what to do about it. Grouped by where you were
when it happened.

## Table of Contents

- [Starting a flow](#starting-a-flow)
- [In the interface](#in-the-interface)
- [Driving agents from Python](#driving-agents-from-python)
- [Collecting a trace](#collecting-a-trace)
- [Remote execution](#remote-execution)
- [Containers](#containers)
- [Still stuck](#still-stuck)

## Starting a flow

### `run() drives 2 agents, 1 given`

The flow declares more agents than `-a` named, or fewer. One `-a` per agent, in the order the
flow takes them:

```sh
hmz exec -f rlar -a claude/claude-opus-4-8:high -a claude/claude-opus-4-8:high "fix the build"
```

Ask a flow how many it wants without running it:

```python
from humanize.runner import drives

print(drives("rlar"))   # ('actor', 'reviewer')
```

A `HumanAgent` place does **not** count — nobody chooses what the person runs.

### `no Python file to read a flow from`

`-f` named something that is not there. A name is looked for in `.humanize/flows`, then
`~/.humanize/flows`, then among the ones humanize came with; anything with a slash or an
extension in it is taken as a path. See [where flows live](flows.md#where-flows-live).

### `a flow is a run(agents, task) whose agents are annotated with a tuple of a fixed length`

The file has no `run`, or its `agents` parameter is annotated with something that does not say
how many. `tuple[AgentBase, ...]` is any number, which is no answer.

```python
def run(agents: tuple[AgentBase], task: str) -> None:          # one agent
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:  # two
def run(agents: Agents, task: str) -> None:                     # a NamedTuple of them
```

### `run()'s agents cannot be read here (…)`

The annotation names something that only exists for a type checker:

```python
if TYPE_CHECKING:                     # ← this is the problem
    from humanize.agents import AgentBase
```

Import it at runtime instead. The count has to be readable where the flow runs, not only where
pyright looks.

### `bad agent 'claude:high': expected CLI[@PROVIDER]/MODEL:EFFORT or cli=CLI,…`

An `-a` that is missing a part. All three are required:

```sh
-a claude/claude-opus-4-8:high
-a cli=claude,model=claude-opus-4-8,effort=high
```

The CLI is read from the front and the effort from after the **last** colon, so a model with
slashes in it — `kimi/kimi-code/k3:high` — is fine.

### `bad agent '…': foo is not cli, model, effort, provider or permission`

A key in the written-out form that is not one of the five it takes: `cli`, `model`, `effort`,
`provider` and `permission`.

### `permission must be one of read-only, workspace-write, auto, bypass`

The `permission=` value is misspelled or empty. It is matched exactly and is refused rather than
silently replaced with the default:

```sh
-a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only
```

### The agent starts and immediately fails

Run the backend's own command line by hand first. humanize passes `model` and `effort` through
untouched, so a model your account cannot run fails the same way it would anywhere:

```sh
claude --help
codex --version
```

## In the interface

### `no coding agent is installed here`

None of `claude`, `codex` or `kimi` is on your `PATH`. humanize drives the CLI you already have
— it holds no API key and talks to no model provider itself.

```sh
command -v claude codex kimi pi opencode mimo
```

### `no choosing a flow while a flow is running: esc stops it first`

Or `no switching flow while a flow is running`. Choosing a flow is done in order to run it, so
it stops whatever was running — and it says so rather than doing it behind your back. Press esc
first.

### `a flow is already running`

Same cause, from a `/flow` that named a path.

### `say on or off, not 'yes'`

`/details` and `/afk` flip when given nothing, and take exactly `on` or `off` when told which.

### `no such command: /foo`

Type `/` to see the list. `hmz collect` and `hmz anchor` are deliberately not commands here:
neither is a thing to do to a flow that is running.

### A line I typed did not reach the agent

Look at whether it is still [pinned above the prompt](tui.md#talking-to-a-running-flow): a line
sits there, rather than in the transcript, until somebody has actually taken it — the next turn
if none was open, or the running turn saying the words are in front of it. A line to a running
flow is never dropped, and one nothing ever took is written down as never sent rather than
left to look like it went. It reaches whichever agent has a turn *open*, not whichever was
named last.

Several lines typed in a row go one at a time, so the ones behind the first sit pinned for a
turn or two before their own answer comes back. That is deliberate: handed over together they
would be run together and answered once.

If the agent is anchored and is Claude, it hears you **between** turns rather than during one:
an anchored Claude ends its process with each turn so that its work reaches the target before
the turn says it landed. See [Remote execution](remote-execution.md#anchoring-a-flow).

### The screen is unreadable in my terminal

The interface uses only your terminal's own sixteen colours and never asks what they are, so
this is usually a theme with too little contrast between two of them. `NO_COLOR=1 hmz` drops to
no colour at all.

### The token count sits still, then jumps

It should not — the cost readout tails the logs the backends write as they go rather than
waiting for a turn to end. If it does sit still, the backend's home is somewhere humanize is
not looking: check `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `KIMI_CODE_HOME`.

## Driving agents from Python

### `RuntimeError: session has not run a turn yet`

`session.id` is the backend's id, and the backend has not named the session yet. Use
`session.named`, which answers `None` instead, if you need it before a turn has landed.

### `NotImplementedError: … cannot be talked to mid-turn`

That backend takes a turn's whole prompt up front, so there is nowhere for a later word to go.
See [what each backend can do](agents.md#what-each-backend-can-do).

### `RuntimeError: no turn is running to be talked to`

`interject` on a backend that *can* be talked to, but with no process up to hear it. Open the
session with a turn first.

### `NotImplementedError: … has no goal feature`

`pursue` is the backend's own goal feature, not a prompt asking for one. `suppress=True` does
not catch this, deliberately: asking for a feature that is not there is a flow to correct.

### My loop never ends after I press esc

It is catching the stop. `Stopped` is not a `CalledProcessError`, and `suppress=True` does not
catch it — but a bare `except Exception` in your flow will. Let it propagate.

### A turn raises `subprocess.CalledProcessError` and I want the loop to continue

```python
agent(task, suppress=True)
```

Whatever the turn was actually run through, a failed turn raises this one type, so a flow
catches turns rather than transports.

## Collecting a trace

### `cannot parse time: …`

`--start` and `--end` take anything [dateparser](https://dateparser.readthedocs.io/)
understands. Quote it: `--start "3 days ago"`.

### `session id cannot be empty`

A `--session` with an empty entry — usually a trailing comma.

### `0 sessions, 0 slices`

Nothing matched. In order of likelihood:

1. **The backend's home is elsewhere.** Check `CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
   `KIMI_CODE_HOME`. A home that does not exist is skipped silently.
2. **The workspace does not match.** Sessions are matched against the path the flow ran under,
   as it was given rather than what it links to. Try `hmz collect --session <id>`, which looks
   everywhere.
3. **The run worked in a mirror.** A flow on a [machine of its own](machines.md) did not work in
   this directory, so find it by `--session`.
4. **The time window excludes it.** Drop `--start`/`--end`.

### Two agents show up as one

They ran at the same configuration and nothing said they were two. `hmz collect` reads that
from the last [cycle](tracing.md#cycles) in the workspace; driving agents by hand, pass
`agents={a.id: a.opened for a in …}`. See
[what counts as one agent](tracing.md#what-counts-as-one-agent).

## Remote execution

### `humanize supports x86_64 only; this host reports 'aarch64'`

The half that runs *beside the agent* needs an architecture-specific register map. The
**target** may be any architecture — only this end is restricted.

### `unsupported target '…'`

```
expected ssh://HOST, docker://CONTAINER, tcp://HOST:PORT or local[:PATH]
```

Those four, and nothing else. See [Targets](remote-execution.md#targets).

### `refusing to listen on a non-loopback address without --token`

An open port is equivalent to a shell on that machine. Give `--token` a real secret, or prefer
`ssh://` or `docker://`, which need no open port at all.

### The target cannot be reached

Ask it what it is, which runs nothing there:

```sh
hmz anchor --check --target ssh://build-box
```

That exercises the whole path — bootstrapping the target half, opening the channel, and reading
the workspace back — without starting an agent. `--log-level debug` says more; the log goes to
stderr, which is the one stream a session never speaks the protocol on.

### The target refuses the mirror directory

The mirror is authoritative: anything in it the target does not have is deleted. humanize
therefore refuses a mirror directory holding unrelated files, or one last used against a
different target. Point `--shadow` somewhere empty, or pass `--force` if you are sure.

### `the target speaks protocol …`

The two halves are different versions. The bundle is cached on the target by digest; a stale one
is replaced by a new connection, so this usually means two different humanize installations are
both driving that target.

### The agent can no longer reach its model provider

`--net remote` sends the agent's *own* connections to the target. Leave it at `local` — the
default — or keep the provider local with `--net-allow api.anthropic.com:443`.

### A command ran against stale files

Only file *contents* cross. A permission change made through an already-open descriptor never
reaches the target, and ownership, device nodes and extended attributes never leave the mirror.
The full list is [What is not guaranteed](remote-execution.md#what-is-not-guaranteed).

## Containers

### `could not start a container of python:3.12: …`

Whatever docker said is attached. The usual causes are no daemon to reach, an image that is not
pulled, and an image with no `python3` in it — which is refused as the container starts rather
than a turn later.

### `no directory to give the container`

The workspace is not there. It is refused rather than mounted into being: docker would create
it for you, owned by root, inside directories you own.

### Containers left behind after a flow was killed

They are labelled with the uid that started them:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

That cannot reach past you on a machine several people share.

## Still stuck

- `--log-level debug` on `hmz anchor`, both ends.
- The `SPEC.md` beside the code says what it is *supposed* to do, normatively —
  `src/humanize/coganchor/SPEC.md` is the one worth reading when a remote session behaves
  strangely.
- [Architecture](architecture.md) says which layer to look in.
- Ask in [issues](https://github.com/humanfia/humanize/issues).
