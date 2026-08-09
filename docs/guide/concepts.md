# Concepts

Ten words carry the whole of humanize. This page defines them once, in the order they build on
each other, so the rest of the documentation can use them without redefining them.

## The one-sentence version

A **flow** — one humanize ships, or one a **flowverse** holds — drives **agents**, each of
which holds **sessions** with a coding-agent **backend**; a session is made of **turns**; one
run of a flow is a **cycle**; an agent's turns land on a **machine** and may run as a
**provider**; and what the whole thing did is read back as a **trace**.

## Backend

A coding agent CLI that is installed on this machine and that humanize knows how to drive.
There are ten: `agy` (Antigravity CLI), `claude` (Claude Code), `codex`, `dsh` (DeepSeek
Harness), `grok` (Grok Build), `kimi` (Kimi Code), `mimo` (mimocode), `opencode`, `pi` and
`qwen` (Qwen Code). You can also add any CLI of your own that speaks the [Agent Client
Protocol](/reference/agents#a-cli-of-your-own), at `/providers`.

humanize does not talk to a model provider. It drives the CLI you already have, logged in the
way you already log in, so your credentials never pass through it. A backend that is not on
your `PATH` is not offered.

Each backend is driven through whichever of its own interfaces can express what an agent is
configured with: its command line where that is enough, and the app server it serves its own
client from where it is not. That choice is humanize's business, not yours. The consequences
that do reach you are listed in [Agents](/reference/agents#what-each-backend-can-do).

## Agent

**A backend, a model, and an effort — plus, optionally, where its work lands and what to call
it.** That is the whole definition.

```
claude / claude-opus-4-8 : high
  │           │            └── effort: how hard to think
  │           └── model
  └── backend
```

An agent holds no conversation. It is *structure*: the settings that every conversation it
opens will run at.

Two consequences that surprise people:

- **Two agents at the same model and effort are two agents.** An actor and the reviewer that
  reads its work are not one thing because they are configured alike. A [flow](#flow) that
  drives both drives two.
- **An agent has an id.** Either the name you gave it, the name the flow calls it, or one
  nothing else answers to. That id is what a [trace](#trace) groups its sessions under.

**Effort** is the backend's own word, not humanize's, so the values differ. Claude Code takes
`low`/`medium`/`high`/`xhigh`/`max` and also `ultracode`. Codex's models each take their own
subset. Kimi Code's effort also says how *wide* to run, where `swarmmax` is `max` thinking at
the width of a fleet. For `pi`, effort is a thinking level down to `off`. For `opencode` and
`mimocode`, it is the variant of the model. See [Agents](/reference/agents#efforts).

## Session

**One conversation with one agent, kept alive across turns.**

The first turn opens the session with the backend. Every later turn resumes it, so the agent
still has the earlier turns in context. Discarding the session is how a flow forgets: a new
session starts from nothing.

This is the single most important choice a flow makes:

```python
agent("do the task")          # a session of its own, dropped straight after: nothing carries over
session = agent.new()
session("do the task")        # opens it
session("keep going")         # resumes it, the first turn still in context
```

A session is also **rooted at a directory**, `agent.new(worktree)`. That is what a conversation
is to these backends: it opens somewhere and every turn of it happens there. If you leave the
directory unsaid, it is the directory the flow runs in. That is what lets one agent work in
several places at once: one session per worktree, their turns going together. See
[Agents](/reference/agents#the-directory-a-session-works-in).

Every session the backend opened is written down under an id. That id is how its transcript is
found again later.

## Turn

**One exchange with the model.** You say something. The agent thinks, uses tools and answers. A
turn can run for minutes and do a great deal.

A turn is the unit that:

- **can be watched** — everything the agent says arrives as it says it, not at the end;
- **can be talked to** — a line you say while a turn is running goes *into* that turn rather
  than starting another;
- **can be hooked** — it passes through named [moments](/reference/agents#hooks); a flow may
  hang a callable on one and take it down again while the flow is running;
- **can fail** — a failed turn raises and leaves the session unopened, so the next attempt
  retries it rather than resuming something that may not exist.

## Flow

**A directory whose `__init__.py` has a function marked `@flow` in it, taking the agents and
the task, beside the skills it brings.** It is the loop: what each agent is asked, in what
order, and when to stop.

```python
@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        agent(task, suppress=True)
```

The annotation on `agents` is load-bearing. Its length is how many agents the flow drives, and
it is the one thing about a flow that the command line starting it cannot otherwise know.
humanize checks it before the first turn rather than hours into a loop. A `NamedTuple` says
what each agent is *for* as well as how many there are. An `Annotated[Agent, Moment.…]`
says what that agent has to be able to do. An `Annotated[Agent, Remote]` or
`Annotated[Agent, Isolated(…)]` says where that agent may work. All of it is checked at the
same moment.

A flow is ordinary Python and may branch any way it likes. Nothing asks it what it is doing.
What a run looks like is read off the turns going past. It may be `async def`. That is how a
flow drives [many turns at once](/reference/flows#a-flow-that-waits-for-more-than-one-thing).
Starting one is the same either way. It may also [call another
flow](/reference/flows#a-flow-that-calls-another-flow) by name, and run it with the agents it
already has.

One file may hold several: `@flow` is the flow it holds under its own name, and each
`@flow(name="…")` is another, run as `<flow>:<name>`. Three phases of one thing are then one
thing to write and three to run. Each asks only for the agents it drives.

See [Flows](/reference/flows).

## Flowverse

**A git repository with a `flows/` directory in it.** One directory per flow holds an
`__init__.py`, what it imports and the `skills/` it brings. A flow that needs neither is a
single `.py`. The repository is cloned into `~/.humanize/flowverses/<name>/` and offered as
`<name>/<flow>`.

Two are always there: `builtin`, the handful in the package, and `official`, where the rest of
the flows humanize offers come from. `official` is listed whether or not it has been fetched,
because what there is to run is not the same question as what has been downloaded. Add as many
more as you like. `/flowverses` is where they are added, fetched and taken away. `/flow`'s
arrows step between them, because that is which list of flows is being read.

See [Flows › Flowverses](/reference/flows#flowverses).

## Cycle

**One run of one flow, written down as it happens — and one directory.**

It opens when the flow starts and closes when the flow stops, finished, failed or interrupted.
It is never reopened. Its `cycle.jsonl` records the flow, the agents and the backend's id for
every session each of them opened. Beside it are a record apiece for the flows this one
[called](/reference/flows#a-flow-that-calls-another-flow), a link per file each session was logged to, whatever a flow
that [can be picked up](/guide/resuming) left behind, the programs a
[profiled](/guide/tracing#profiling-a-run) run started and the traces gathered of it
afterwards. It does *not* record what the sessions said. The backend's own log is the
turn-by-turn record, and a cycle is not a second copy of it.

It exists because the backends log a session under an id and never say whose it was. Without
the cycle, two agents at one configuration are indistinguishable afterwards. With it, a
[trace](#trace) can say `builder` and `reviewer`.

Cycles live under `~/.humanize/cycles/<workspace>/`, one directory apiece. See
[Tracing](/reference/tracing#cycles).

## Machine

**Where an agent's turns land.** One setting with three answers:

| | |
| --- | --- |
| **This machine** | the default. Nothing to configure. |
| **One that is already running** | an ssh host, a container, a listening port. The agent process stays here — keeping its credentials and its link to its model provider — and everything it *does* happens there. |
| **One started for the agent** | a container of an image you name, brought up on the first turn and removed with the agent. |

It is one setting because it is one question. **Which agents it may be asked of is the flow's
to say.** An agent whose annotation says nothing about a machine runs here and cannot be
pointed anywhere. `Annotated[Agent, Remote]` is one that may be. `Annotated[Agent,
Isolated("python:3.12")]` is a container of the flow's own that nobody configures. See
[Machines](/reference/machines).

## Provider

**One named set of credentials for one backend.** It is a subscription signed into, a key or an
endpoint of somebody else's. It is kept apart from the CLI's own under
`~/.humanize/providers/<cli>/<name>/`.

An agent configured with one runs its turns as that account. It runs with the provider's
variables and reads its credentials from the provider's directory rather than the CLI's. Only
the credential files move; the sessions, the settings and the skills are the CLI's own.

It is a setting of the agent because it is the agent that signs in. That is what lets one flow
drive two agents of one CLI as two different accounts at once. Each refreshes its own token,
and neither can read the other's. See [Providers](/reference/providers).

## Trace

**Everything a run left behind, as one timeline.**

`hmz trace collect` reads the backends' own transcripts and names each session by the agent
that opened it (using the cycle). It writes a Chrome JSON trace into the cycle of the run it is
a trace of. Load it in [ui.perfetto.dev](https://ui.perfetto.dev). Each agent is a process,
each row of that agent's sessions is a track and each slice is one thing the agent did.

It works on sessions no flow ever drove, too. A trace of yesterday's `claude` session is `hmz
trace collect` away. See [Tracing](/reference/tracing).

## How they fit

```
cycle ─── one run of one flow, written down
  │
flow ──── the loop, a directory of Python
  │
  ├── agent "builder"  ── backend + model + effort + machine
  │     ├── session ── turn, turn, turn …      ─┐
  │     └── session ── turn                     │  every session's transcript
  │                                             ├─ is written by the backend,
  └── agent "reviewer" ── backend + model …     │  and read back as a trace
        └── session ── turn                    ─┘
```

## Two distinctions worth getting right

**Agent vs. session — what is remembered.** The agent is settings; the session is memory. A
flow that opens a session per turn is a Ralph loop: the agent starts from the task and the
repository every time. A flow that holds one session across turns is a conversation. Same
agent, opposite behaviour. The flow decides, not the agent.

**Turn failing vs. agent stopping — what a loop should do.** A turn that failed is ordinary;
`suppress=True` turns it into an empty answer and the loop goes round again. An agent that has
been *told to stop* (ctrl+c twice in the interface, or `agent.stop()`) raises `Stopped`. `suppress`
deliberately does not catch it, because a loop that carried on past it would never end. It does
not catch an `Unrecoverable` either, and for the same reason: a turn that failed for a reason
no other try could come out differently on is one the next round would meet again.

---

Next: [Flows](/reference/flows) to write one, [Agents](/reference/agents) for the Python API,
[TUI](/reference/tui) or [CLI](/reference/cli) to look something up.
