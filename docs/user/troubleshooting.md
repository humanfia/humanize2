---
# Every entry here is one h3, and there are dozens of them: an outline of the errors
# themselves is a wall of half-sentences, all cut off at the same width. The outline
# names the places a problem happens in; the page itself lists the errors.
outline: 2
---

# Troubleshooting

What a problem looks like, and what to do about it — grouped by where you were when it
happened.

## Starting a flow

### `the flow drives 2 agents, 1 given`

The flow declares more agents than `-a` named, or fewer. Give one `-a` per agent, in the order
the flow takes them:

```sh
hmz exec -f rlar -a claude/claude-opus-4-8:high -a claude/claude-opus-4-8:high "fix the build"
```

Ask a flow how many it wants without running it:

```python
from hmz.flows import drives

print(drives("official/rlar"))   # ('actor', 'reviewer')
```

A `Person` place does **not** count. Nobody chooses what the person runs.

### `<flow>: no flow to read: a flow is a directory with an __init__.py in it`

`-f` named something that is not there, or a directory with no flow in it. humanize looks for a
name in `.humanize/flows`, then `~/.humanize/flows`, then among the flows humanize ships and
every [flowverse](/reference/flows#flowverses) fetched here. A name no place answers to is taken
as a path — `flows/mine` and `flows/mine.py` both. See
[where flows live](/reference/flows#where-flows-live).

### `the official flowverse has not been fetched yet`

The name is right; the download has not happened. `/flow` fetches whatever has never been
fetched as it opens. Press `r` on it in `/flowverses` to fetch it again, or run `hmz flowverses
fetch official`.

### `nothing in it is marked @flow(), and it holds …`

The file holds [several flows](/reference/flows#several-flows-in-one-file), and none of them is
under its own name. Say which one you want with a colon: `-f official/humanize1:gen-plan`.

### `nothing in it is marked @flow()`

Nothing in the file says which of its functions is a flow. A function called `run` is not a
flow because it is called that. Mark it:

```python
from hmz.flows import flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    ...
```

### `a flow is a function marked @flow() taking (agents, task), whose agents are annotated …`

The `agents` parameter is annotated with a type that does not say how many agents there are.
`tuple[Agent, ...]` means any number, which is no answer.

```python
def run(agents: tuple[Agent], task: str) -> None:          # one agent
def run(agents: tuple[Agent, Agent], task: str) -> None:  # two
def run(agents: Agents, task: str) -> None:                     # a NamedTuple of them
```

(Each is marked `@flow`, which is what makes it a flow at all.)

### `the flow's agents cannot be read here (…)`

The annotation names something that exists only for a type checker:

```python
if TYPE_CHECKING:                     # ← this is the problem
    from hmz.flows import Agent
```

Import it at runtime instead. The count has to be readable where the flow runs, not only where
pyright looks.

### `bad agent 'claude:high': expected CLI[@PROVIDER]/MODEL:EFFORT or cli=CLI,…`

An `-a` is missing a part. All three are required:

```sh
-a claude/claude-opus-4-8:high
-a cli=claude,model=claude-opus-4-8,effort=high
```

The CLI is read from the front and the effort from after the **last** colon. A model with
slashes in it, such as `kimi/kimi-code/k3:high`, is fine.

### `bad agent '…': foo is not cli, model, effort, provider, permission or config.KEY`

The written-out form has a key that is not one of the five every backend takes — `cli`,
`model`, `effort`, `provider` and `permission` — or a `config.KEY` Codex override.

### `bad agent '…': permission must be one of read-only, workspace-write, auto, bypass, not '…'`

The `permission=` value is misspelled or empty. humanize matches it exactly and refuses it
rather than silently replacing it with the default:

```sh
-a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only
```

### The agent starts and immediately fails

Run the backend's own command line by hand first. humanize passes `model` and `effort` through
untouched. So a model your account cannot run fails the same way it would anywhere:

```sh
claude --help
codex --version
```

### `codex: this machine will not run an agent at bypass, so it runs at auto`

Not a failure: a note, said once per agent. This Codex was given requirements by somebody
else — an enterprise policy that arrives with the account, or a `requirements.toml` on a
machine whose platform packages Codex — forbidding the `danger-full-access` sandbox that
[`bypass`](/user/permissions) is. Codex refuses such a call outright, so humanize asks again a
rung down, at `auto`: the same freedom, with Codex asking before it reaches past the workspace
and humanize granting what it asks. Set the agent to `auto` in `/agents` to say it yourself and
skip the note. What the machine allows is its own to say:

```sh
cat /etc/codex/requirements.toml
```

## In the interface

### `no coding agent is installed here`

No backend was found, on your `PATH` or in the directories an installer puts one in. humanize
drives the CLI you already have; it holds no API key and talks to no model provider itself.

```sh
command -v claude codex kimi pi opencode mimo zcode
```

### `no choosing a flow while a flow is running: ctrl+c twice stops it first`

Or `no switching flow while a flow is running`. Choosing a flow means running it, which means
stopping whatever was running — and humanize says so rather than doing it behind your back.
Press ctrl+c twice first.

### `a flow is already running`

This has the same cause, from a `/flow` that named a path.

### `say on or off, not 'yes'`

`/details` and `/afk` flip when you give them nothing. When you tell them which, they take
exactly `on` or `off`.

### `no such command: /foo`

Type `/` to see the list. `hmz anchor` is deliberately not a command here: it is not a thing to
do to a flow that is running. `/epics` is where the runs of this directory are, and where one
of them is collected into a trace.

### A line I typed did not reach the agent

Look at whether it is still [pinned above the
prompt](/reference/tui#talking-to-a-running-flow). A line sits there, rather than in the
transcript, until somebody has actually taken it — the next turn if none was open, or the
running turn saying the words are in front of it. A line to a running flow is never dropped:
one that nothing ever took is written down as never sent rather than left looking like it went.
It reaches whichever agent has a turn *open*, not whichever was named last.

Several lines typed in a row go one at a time. The ones behind the first sit pinned for a turn
or two before their own answer comes back. That is deliberate: handed over together, they would
be run together and answered once.

If the agent is anchored and is Claude, it hears you **between** turns rather than during one.
An anchored Claude ends its process with each turn, so that its work reaches the target before
the turn says it landed. See [Remote execution](/reference/remote-execution#anchoring-a-flow).

### The screen is unreadable in my terminal

The interface uses only your terminal's own 16 colours and never asks what they are. So this is
usually a theme with too little contrast between two of them. `NO_COLOR=1 hmz` drops to no
colour at all.

### The token count sits still, then jumps

It should not: the cost readout tails the logs the backends write as they go rather than
waiting for a turn to end. If it does sit still, the backend's home is somewhere humanize is
not looking. Check `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `KIMI_CODE_HOME`. ZCode has no variable
of its own, so its home is `~/.zcode` under whatever `HOME` says.

## Driving agents from Python

### `RuntimeError: session has not run a turn yet`

`session.id` is the backend's id, and the backend has not named the session yet. Use
`session.named` instead. It answers `None` if you need it before a turn has landed.

### `NotImplementedError: … cannot be talked to mid-turn`

That backend takes a turn's whole prompt up front. So there is nowhere for a later word to go.
See [what each backend can do](/reference/agents#what-each-backend-can-do).

### `RuntimeError: no turn is running to be talked to`

You called `interject` on a backend that *can* be talked to, but no process is up to hear it.
Open the session with a turn first.

### `NotImplementedError: … has no goal feature`

`pursue` is the backend's own goal feature, not a prompt asking for one. `suppress=True` does
not catch this, deliberately. Asking for a feature that is not there is a flow to correct.

### My loop never ends after I stop it

Your loop is catching the stop. `Stopped` is not a `CalledProcessError`, and `suppress=True`
does not catch it. But a bare `except Exception` in your flow will. Let it propagate.

### A turn raises `subprocess.CalledProcessError` and I want the loop to continue

```python
agent(task, suppress=True)
```

Whatever the turn was actually run through, a failed turn raises this one type. So a flow
catches turns rather than transports.

## Collecting a trace

### `cannot parse time: …`

`--start` and `--end` take anything [dateparser](https://dateparser.readthedocs.io/)
understands. Quote it: `--start "3 days ago"`.

### `session id cannot be empty`

A `--session` with an empty entry. Usually a trailing comma.

### `0 sessions, 0 slices`

Nothing matched. In order of likelihood:

1. **The backend's home is elsewhere.** Check `CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
   `KIMI_CODE_HOME`. A home that does not exist is skipped silently.
2. **The run being traced opened nothing.** A trace is of a run and holds that run's own
   sessions. So a run that died before its first turn is a trace of nothing. `/epics` says how
   many sessions each run opened, and `--epic` names another.
3. **You are tracing the wrong directory.** Runs are kept per workspace. Without a
   `<workspace>`, the last run of *this* one is what is traced.
4. **Nothing here was ever run by a flow.** Then there is no run to trace. What you want is
   `hmz trace collect --all` or `--session <id>`.
5. **The time window excludes it.** Drop `--start`/`--end`.

### One of my agents is not in the trace at all

A trace is gathered by session id, and a session is opened by a turn that **landed**. An agent
whose every turn failed — a CLI that was never signed in, an account whose quota went overnight
— opened nothing, so the run's record names no session for it and a trace of that run has
nothing of it to collect. Two agents declared and one of them in the trace is that, rather than
a trace that lost one.

Where it is said is the run as it happened: a failed turn closes on a
[`failed`](/reference/agents#watching-a-turn-as-it-happens) carrying what the CLI said about it,
shown in the interface and put on stderr for a run nothing is watching. The flow cannot tell you
— a turn taken under `suppress=True`, which is every loop, is handed the same nothing whether it
failed or answered with nothing — so that event is the place to read it.

### Two agents show up as one

They ran at the same configuration, and nothing said they were two. `hmz trace collect` reads
that off the run it is a trace of. That run is the last [epic](/reference/tracing#epics) of
the workspace unless `--epic` names another. So a trace asked for by `--session` or `--all` is
of no run and has nothing to read it off. If you drive agents by hand, pass `agents={a.id:
a.opened for a in …}`. See [what counts as one
agent](/reference/tracing#what-counts-as-one-agent).

## Remote execution

### `humanize supports x86_64 only; this host reports 'aarch64'`

The half that runs *beside the agent* needs an architecture-specific register map. The
**target** may be any architecture. Only this end is restricted.

### `unsupported target '…'`

```
expected ssh://HOST, docker://CONTAINER, tcp://HOST:PORT or local[:PATH]
```

Those four, and nothing else. See [Targets](/reference/remote-execution#targets).

### `refusing to listen on a non-loopback address without --token`

An open port is equivalent to a shell on that machine. Give `--token` a real secret, or prefer
`ssh://` or `docker://`. Those need no open port at all.

### The target cannot be reached

Ask it what it is. This runs nothing there:

```sh
hmz anchor --check --target ssh://build-box
```

It bootstraps the target half, opens the channel and reads the workspace back — the whole path,
without starting an agent. `--log-level debug` says more, on stderr, the one stream a session
never speaks the protocol on.

### The target refuses the mirror directory

The mirror is authoritative: anything in it the target does not have is deleted. So humanize
refuses a mirror directory holding unrelated files, or one last used against a different
target. Point `--shadow` somewhere empty, or pass `--force` if you are sure.

### `the target speaks protocol …`

The two halves are different versions. The bundle is cached on the target by digest. A stale
one is replaced by a new connection. So this usually means two different humanize installations
are both driving that target.

### The agent can no longer reach its model provider

`--net remote` sends the agent's *own* connections to the target. Leave it at `local`, the
default, or keep the provider local with `--net-allow api.anthropic.com:443`.

### A command ran against stale files

Only file *contents* cross. A permission change made through an already-open descriptor never
reaches the target. Ownership, device nodes and extended attributes never leave the mirror. The
full list is [What is not guaranteed](/reference/remote-execution#what-is-not-guaranteed).

## Containers

### `could not start a container of python:3.12: …`

Whatever docker said is attached. The usual causes are no daemon to reach, an image that is not
pulled and an image with no `python3` in it. That image is refused as the container starts,
rather than a turn later.

### `no directory to give the container`

The workspace is not there. humanize refuses it rather than mounting it into being. Docker
would create it for you, owned by root, inside directories you own.

### Containers left behind after a flow was killed

They are labelled with the uid that started them:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

That cannot reach past you on a machine several people share.

## Still stuck

- `--log-level debug` on `hmz anchor`, both ends.
- The `SPEC.md` beside the code says what it is *supposed* to do, normatively.
  `src/hmz/coganchor/SPEC.md` is the one worth reading when a remote session behaves strangely.
- [Architecture](/contributing/architecture) says which layer to look in.
- Ask in [issues](https://github.com/humanfia/humanize2/issues).
