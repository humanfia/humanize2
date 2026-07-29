# Concepts

Eight words carry the whole of humanize. This page defines them once, in the order they build
on each other, so the rest of the documentation can use them without redefining them.

## Table of Contents

- [The one-sentence version](#the-one-sentence-version)
- [Backend](#backend)
- [Agent](#agent)
- [Session](#session)
- [Turn](#turn)
- [Flow](#flow)
- [Cycle](#cycle)
- [Machine](#machine)
- [Trace](#trace)
- [How they fit](#how-they-fit)
- [Two distinctions worth getting right](#two-distinctions-worth-getting-right)

## The one-sentence version

A **flow** drives **agents**, each of which holds **sessions** with a coding-agent **backend**;
a session is made of **turns**; one run of a flow is a **cycle**; an agent's turns land on a
**machine**; and what the whole thing did is read back as a **trace**.

## Backend

A coding agent CLI that is installed on this machine and that humanize knows how to drive.
There are three: `claude` (Claude Code), `codex`, and `kimi` (Kimi Code).

humanize does not talk to a model provider. It drives the CLI you already have, logged in the
way you already log in, so your credentials never pass through it. A backend that is not on
your `PATH` is simply not offered.

Each backend is driven through whichever of its own interfaces can express what an agent is
configured with — its command line where that is enough, and the app server it serves its own
client from where it is not. That choice is humanize's business, not yours; the consequences
that do reach you are listed in [Agents](agents.md#what-each-backend-can-do).

## Agent

**A backend, a model, and an effort — plus, optionally, where its work lands and what to call
it.** That is the whole definition.

```
claude / claude-opus-4-8 : high
  │           │            └── effort: how hard to think
  │           └── model
  └── backend
```

An agent holds no conversation. It is *structure*: the settings every conversation it opens
will run at.

Two consequences that surprise people:

- **Two agents at the same model and effort are two agents.** An actor and the reviewer that
  reads its work are not one thing because they happen to be configured alike. A [flow](#flow)
  that drives both drives two.
- **An agent has an id.** Either the name you gave it, the name the flow calls it, or one
  nothing else answers to. That id is what a [trace](#trace) groups its sessions under.

**Effort** is the backend's own word, not humanize's, so the values differ: Claude Code takes
`low`/`medium`/`high`/`xhigh`/`max` and also `ultracode`; Codex's models each take their own
subset; Kimi Code's effort also says how *wide* to run, where `swarmmax` is `max` thinking at
the width of a fleet. See [Agents](agents.md#efforts).

## Session

**One conversation with one agent, kept alive across turns.**

The first turn opens the session with the backend; every later one resumes it, so the agent
still has the earlier turns in context. Discarding the session is how a flow forgets — a new
one starts from nothing.

This is the single most important choice a flow makes:

```python
agent("do the task")          # a session of its own, dropped straight after: nothing carries over
session = agent.new()
session("do the task")        # opens it
session("keep going")         # resumes it, the first turn still in context
```

Every session the backend opened is written down under an id, which is how its transcript is
found again later.

## Turn

**One exchange with the model.** You say something; the agent thinks, uses tools, and answers.
A turn can run for minutes and do a great deal.

A turn is the unit that:

- **can be watched** — everything the agent says arrives as it says it, not at the end;
- **can be talked to** — a line said while a turn is running goes *into* that turn rather than
  starting another;
- **can be hooked** — it passes through named [moments](agents.md#hooks) a flow may hang a
  callable on, and take down again while the flow is running;
- **can fail** — a failed turn raises, and leaves the session unopened so the next attempt
  retries it rather than resuming something that may not exist.

## Flow

**A Python file with a `run(agents, task)` in it.** It is the loop: what each agent is asked,
in what order, and when to stop.

```python
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    while True:
        agent(task, suppress=True)
```

The annotation on `agents` is load-bearing. Its length is how many agents the flow drives —
the one thing about a flow that the command line starting it cannot otherwise know — so it is
checked before the first turn rather than hours into a loop. A `NamedTuple` says what each one
is *for* as well as how many there are, and an `Annotated[AgentBase, Moment.…]` says what that
one has to be able to do, which is checked at the same moment.

A flow is ordinary Python and may branch any way it likes. Nothing asks it what it is doing;
what a run looks like is read off the turns going past.

See [Flows](flows.md).

## Cycle

**One run of one flow, written down as it happens.**

It opens when the flow starts and closes when the flow stops — finished, failed, or
interrupted. It records the flow, the agents, and the backend's id for every session each of
them opened. It does *not* record what the sessions said: the backend's own log is the
turn-by-turn record, and a cycle is not a second copy of it.

It exists because the backends log a session under an id and never say whose it was. Without
the cycle, two agents at one configuration are indistinguishable afterwards. With it, a
[trace](#trace) can say `builder` and `reviewer`.

Cycles live under `~/.humanize/cycles/`. See [Tracing](tracing.md#cycles).

## Machine

**Where an agent's turns land.** One setting with three answers:

| | |
| --- | --- |
| **This machine** | the default. Nothing to configure. |
| **One that is already running** | an ssh host, a container, a listening port. The agent process stays here — keeping its credentials and its link to its model provider — and everything it *does* happens there. |
| **One started for the agent** | a container of an image you name, brought up on the first turn and removed with the agent. |

It is one setting because it is one question. See [Machines](machines.md).

## Trace

**Everything a run left behind, as one timeline.**

`hmz collect` reads the backends' own transcripts, names each session by the agent that opened
it (using the cycle), and writes a Chrome JSON trace. Load it in
[ui.perfetto.dev](https://ui.perfetto.dev): each agent is a process, each session a track, each
slice one thing the agent did.

It works on sessions no flow ever drove, too — a trace of yesterday's `claude` session is
`hmz collect` away. See [Tracing](tracing.md).

## How they fit

```
cycle ─── one run of one flow, written down
  │
flow ──── the loop, a Python file
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
agent, opposite behaviour — and the flow decides, not the agent.

**Turn failing vs. agent stopping — what a loop should do.** A turn that failed is ordinary;
`suppress=True` turns it into an empty answer and the loop goes round again. An agent that has
been *told to stop* — esc in the interface, or `agent.stop()` — raises `Stopped`, which
`suppress` deliberately does not catch, because a loop that carried on past it would never end.

---

Next: [Flows](flows.md) to write one, [Agents](agents.md) for the Python API,
[TUI](tui.md) or [CLI](cli.md) to look something up.
