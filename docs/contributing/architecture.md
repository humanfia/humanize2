# Architecture

How the package is laid out, what each layer is for, and the rules that keep it that way. For
contributors; nothing here is needed to *use* humanize.

## The tree

```
src/hmz/
├── __init__.py       home() — where humanize keeps what outlives one run
├── __main__.py       python -m hmz
├── backends.py       every fact about a coding agent CLI that is not code
├── models.py         what each backend runs, asked of it and kept per account
├── cycle.py          what one run of one flow was, written down as it happens
├── fallbacks.py     where a turn goes when the place taking it cannot take it at all
├── runner.py         finding a flow, checking it, driving it, reading the `hmz exec` line
├── sdk/              humanize as one object: Hmz, which every way in goes through
├── cli/              the command line: one module per command that has a parser
├── daemon/           a run held where a terminal closing cannot end it
├── agents/           the contract, and the driver for each backend
├── flows/            what a flow is called, where it is found, what it brings, and the three it ships
├── machines/         where an agent's turns land
├── providers/        which account an agent runs as, kept apart from which CLI it is
├── coganchor/        running an agent here whose work lands elsewhere
├── tracing/          trajectories back out as a Chrome trace
└── tui/              the terminal interface
```

There are four ways in and one thing under them. `sdk/` is humanize as one object, and `cli/`,
`daemon/` and `tui/` are each a way of reaching it rather than a second copy of what it does: a
command line reads a line and prints what came of it, a daemon holds a run where a terminal
closing cannot end it, and the interface draws. What two of them would otherwise each have
written is written in `sdk/` instead, so that a thing that can be done one way can be done every
way and is refused the same way whichever way it was asked.

Every name says what it holds. `coganchor` is the one exception — it is a program that ships to
a target and could be lifted out whole, so it has a name of its own.

## The layers

| Layer | Is | Entry points |
| --- | --- | --- |
| `backends.py` | Names, aliases, efforts, home directories, log globs, credential paths, ways in and skill directories for all twelve backends. Facts, not code — standard library only, and no model id anywhere in it. | `PROFILES`, `named()`, `profiles()`, `read()`, `remember()` |
| `models.py` | What each backend runs, asked of that backend the way it offers being asked, and kept per account. Nothing here is a list: a CLI ships models without asking anybody. | `ask`, `offered`, `asked`, `where` |
| `agents/` | The drivers: one per backend, plus the vocabulary a turn is described in (`Event`, `Question`, `Moment`). `AgentBase` and `SessionBase` answer to the interface `flows/` declares, structurally — this layer never names a flow. | everything in `__init__` |
| `machines/` | The setting that says which machine, and the machine it brings up. | `MachineConfig`, `MachineBase`, `AnchoredConfig`, `DockerConfig` |
| `coganchor/` | Syscall interposition: a seccomp-filtered ptrace supervisor here, a replaying server there, a wire protocol between. | `AnchorConfig`, `connect`, `check` |
| `flows/` | What a flow is: the interface it drives, the mark, what it says it drives, the skills it brings, calling one from another, and where flowverses are fetched to. The one import a flow writes — what it needs from another layer is handed through from here. `builtin/` beside it is the three humanize ships. | `Agent`, `Session`, `Person`, `flow`, `load`, `drives`, `wanted`, `found`, `find`, `held`, `fork`, `flowverses` |
| `fallbacks.py` | The layer between an agent and its accounts: where a turn goes when the place taking it cannot take it at all, and how many times over it is taken again first. A step is written between two places — `CLI[@ACCOUNT]/MODEL` — rather than on the account, which `providers` already answers for. Names `backends` and nothing else. | `Falls`, `falls`, `points`, `retrying`, `tried`, `clear`, `chain`, `spec`, `reads`, `waits`, `POLICIES` |
| `cycle.py` | One run of one flow as a directory: the journal, the links to each session's log, and what a flow that can be picked up left behind. Written by `runner`, read by `tracing`, `cli` and `tui`. | `Cycle`, `cycles`, `read`, `opened`, `state`, `resumed` |
| `runner.py` | Handing a flow the agents it declared, naming them, and running it under a cycle. Also reads the `hmz exec` line, which the interface starts a flow from too. What the flow says it drives is `flows/`'s to answer. | `Runner`, `flow_and_agents`, `read_agent`, `set_up_from` |
| `tracing/` | Reading the backends' logs back — and, for a profiled run, sampling the programs its agents start — and rendering both as one Chrome trace. | `collect`, `profile.Profiler` |
| `sdk/` | humanize as one object. A workspace, what is remembered about it, the flows there are, the agents and accounts they run as, the runs already made and the run being made now. It composes the layers and restates none of them, and it reaches each of them from inside the call that needs it — which is what lets `hmz exec` name it without paying for the tracer. | `Hmz`, `Run`, `Session` |
| `tui/` | The terminal interface. | `Humanize` |
| `daemon/` | A run held where a terminal closing cannot end it, and the terminals that come and go from it. A leaf: what it holds is a callable that opens a run and returns when it is over, so it knows nothing of what a run is. | `Daemon`, `Held`, `running`, `daemons`, `start` |
| `proctitle.py` | What this process is called to every other process. `hmz exec` renames itself to just that once it has read its line — the command, and nothing typed after it — so an agent's `pkill -f` on a path the task names cannot reach the run. A leaf. | `named` |
| `cli/` | The one command line, over layers that have none of their own. | `main`, `COMMANDS` |

### Inside the bigger ones

```
agents/
├── event.py      Event, Question, Stopped, say — values, no behaviour, imported by every driver
├── hooks.py      Moment, Occasion, Verdict, Hooks — the same, for what a turn stops at
├── base.py       AgentBase and SessionBase: two halves of one object, declared in one file
├── config.py     AgentConfig, anchored
└── claude.py agy.py codex.py dsh.py grok.py kimi.py pi.py qwen.py opencode.py mimo.py
    zcode.py acp.py human.py

flows/
├── agent.py      Agent, Session, Person — what a flow drives, as interfaces and nothing else
├── driving.py    what a flow says it drives, read off its own entry point, and load()
├── __init__.py   the mark, finding one by name, and the one import a flow writes
├── skills.py     the skills a flow brings, its own and the ones it named
├── verses.py     where flows come from when they come from somewhere else
└── builtin/      the three humanize ships

coganchor/
├── anchor.py     AnchorConfig, connect, check — the front door
├── argv.py       the `hmz anchor` line, all three directions: parse, settle, render
├── proto.py      the wire, shared by both halves
├── linux/        ptrace, seccomp, procfs, syscall numbers (x86-64)
├── serve/        the target half — imports nothing but proto
└── supervisor.py handlers.py policy.py shadow.py standin.py execproxy.py netproxy.py
                  remote.py transport.py statepaths.py — the half beside the agent

tracing/
├── collector.py  what to gather, and naming each session's agent
├── session.py    the model every reader produces
├── chrome.py     the Chrome trace rendering
├── profile.py    the sampler a profiled run's programs are read off the process tree by
└── readers/      claude.py codex.py dsh.py kimi.py — one log format apiece
```

## The dependency graph

```
coganchor        backends
    │                │
machines            │
    │                │
 agents ────────────┤
    │                │
 cycle   flows       │
    └──┬───┘         │
       │             │
    runner ──────────┤
       │             │
      sdk ── tracing ┘
       │
      tui        daemon   ← a leaf: it holds a callable, not a run
       │
      cli ── proctitle   ← a leaf: what `hmz exec` is called
       ↑
       may name anything; it is what joins them
```

<HmzStack />

It is a DAG with no exceptions. Nothing points both ways. The diagram above is the same table
drawn: hover a layer and it lights up exactly what that layer is allowed to name.

Two edges are worth explaining:

- **`agents → machines`** rather than the other way round, because an agent's config says which
  machine, and a machine hands back an anchor without knowing what will run on it.
- **`tracing → backends` only.** `tracing` does not know how to *drive* anything; it needs the
  home directories and log globs, and nothing else.

And one edge deliberately absent: **`agents` does not name `cycle`.** A run is written out of
the agents it drove, so naming the run from an agent would be a circle. What an agent needs of
one — somewhere to write down a session it opened — is a `Journal` protocol declared in
`agents/base.py`, which `Cycle` happens to satisfy.

## Rules that are checked

`tests/test_layering.py` holds the table and four tests. It is the only place these can be
checked at all.

1. **Every layer imports only what it may.** The table lists what each may name besides its own
   subtree and `hmz` itself. Relative spellings are resolved, so
   `from ..supervisor import Supervisor` counts exactly as the absolute form would.
2. **No two layers name each other.** A pair that points both ways is two things put in one
   place, not one above another.
3. **Every top-level module is in the table.** One left out is unchecked, and reads exactly like
   one deliberately exempt. `cli` is the only exemption, and it is checked differently:
4. **Serving loads only what it may** — against a real target half, not statically. The bundle
   is built, `hmz anchor serve` is run out of it with an empty `PYTHONPATH`, and what it loaded
   is compared with the table.

That last one is why `coganchor/serve/` may import nothing but `proto`. The serving half runs on
the target, which may be any architecture, while `coganchor/linux/` picks a register map at
import time and refuses anything but x86-64.

The same discipline is why **every command imports what it needs when it is the one asked for,
and no earlier** — `hmz exec` must not pay for a date parser it will not use. Ruff's
`PLC0415` is off for exactly this reason.

## Two design decisions worth knowing

**An agent and its session are two halves of one object, declared in one file.** They are
mutually recursive by nature — a session registers itself with its agent, and an agent's turns
run through its sessions — so splitting them would create a two-way dependency and spread the
`SLF001` exemption across two files. `agents/base.py` is long on purpose.

**The setting and the machine are two classes.** `MachineConfig.create()` builds a
`MachineBase`. One config drives as many agents as it is given to, and each gets a machine of
its own — two agents sharing a `DockerConfig` get a container each, which is what you want and
what a single class could not express.

## Naming

Module names come from the product's own vocabulary — the same words `hmz` and `docs/` use.
`docs/agents.md` documents `agents/`, `docs/tracing.md` documents `tracing/`, and so on.

A name of its own is for something that could be its own repository: its own SPEC, its own wire
protocol, its own architecture requirement, shippable on its own. Exactly one thing qualifies,
and it is `coganchor` — an abbreviation, and an easter egg.

## SPEC.md

Beside the code, and normative. Where this documentation says what humanize *does*, a SPEC says
what it *must* do, in MUST/MUST NOT terms, for whoever is changing it.

| | |
| --- | --- |
| `src/hmz/SPEC.md` | The tree, the top-level modules, and every command line |
| `src/hmz/agents/SPEC.md` | The agent and session contract every backend keeps |
| `src/hmz/flows/SPEC.md` | What a flow is, how one is found, what it brings, and what a flowverse holds |
| `src/hmz/machines/SPEC.md` | What a machine is |
| `src/hmz/providers/SPEC.md` | Which account an agent runs as, and how a turn is run under it |
| `src/hmz/coganchor/SPEC.md` | What you are entitled to under an anchor, and what you deliberately are not |
| `src/hmz/tracing/SPEC.md` | The collect API and how a trace is built |
| `src/hmz/sdk/SPEC.md` | `Hmz` and everything it hands back |
| `src/hmz/daemon/SPEC.md` | Holding a run apart from a terminal, and the terminals that read one |
| `src/hmz/tui/SPEC.md` | Every behaviour the interface must have |

`AGENTS.md` says not to modify a SPEC unless you were told to. Change the code to match the
SPEC; propose the SPEC change separately.

## Adding things

**A backend.** A `Profile` in `backends.py`, a driver in `agents/`, an entry in the `DRIVEN`
table in `agents/__init__.py`, which `runner.py` and the interface both read, a way of asking
it what it runs in `models.py`'s `_READING` table, and its state paths in
`coganchor/statepaths.py`. Subclass `CommandSessionBase` if a turn is one run of a command
line, or `StreamSessionBase` if it is one long-lived process spoken to a line at a time —
`agents/SPEC.md` says which and why.

Then whatever its logs allow, and nothing more: a reader in `tracing/readers/` where a session
of it can be gathered afterwards, and a branch in `tui/tally.py`'s `_spent` where a row of them
says what one request cost, which is what a tally moving during a turn is read out of. A
backend that writes neither gets neither, and says so rather than being left out.

And the documentation. Several pages count the backends and several tables name every one of
them, so one added without them is a site that says there are fewer than there are.

**A machine.** Two classes in `machines/`, per [Machines](/reference/machines#writing-a-machine-of-your-own).

**A command.** A module under `cli/` if it takes a parser of its own, a thin wrapper in
`cli/__init__.py`, and an entry in `COMMANDS`. Import your layer *inside* the function, not at
the top of the module.

**A flow.** Just a directory: one in `flows/builtin/` for one humanize ships, one in a
[flowverse](/reference/flows#flowverses)'s own `flows/` for one it offers, one in
`.humanize/flows/` for one of your own. Its `__init__.py` is the flow, whatever it imports
lives beside it, and its `skills/` is what it brings. They are content and import nothing of
humanize but `hmz.agents` — and `hmz.flows.flow`, where one holds several.

## The checks

```sh
uv sync
uv run pre-commit install     # then every commit is checked before it is made

uv run pre-commit run --all-files   # format, lint, types
uv run pytest                       # the tests
uv run pytest --run-agents          # also drives the real coding agent CLIs
```

Run them through `uv run`, not `uvx`: the lockfile pins the versions the hooks and CI enforce.

- **ruff** with `select = ["ALL"]`, less what this codebase has a reason to be without. Every
  exemption in `pyproject.toml` carries the reason it is there.
- **pyright** in strict mode, with `# type: ignore` comments disabled — a suppression names a
  pyright rule or it does not exist.
- Google-style docstrings, and type annotations everywhere.

CI runs all of it over every file, and the tests on each Python the package claims.
