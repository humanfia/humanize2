# Features

What humanize does, described in one page. Every entry links to a [guide](/guide/) that shows
you how to use it, and to the [reference](/reference/cli) that spells it out completely.

If you have not run it yet, start with the [Quickstart](/tutorials/quickstart) instead.

## The idea

humanize runs **flows**: directories of Python that drive one or more coding agents in a loop
and write down everything they did.

It does not talk to a model provider. It drives the coding agent CLI you already have — nine of
them, plus anything that speaks the Agent Client Protocol — logged in the way you already log
in. There is no API key for it to hold. The one exception is DeepSeek Harness, which ships
inside humanize and does take a key, because it has no subscription login to use instead.

Two ways in, and they run the same flows and leave the same records behind. `hmz` opens a
terminal interface. `hmz exec` runs a flow with nobody watching, which is what a script, a cron
entry or a CI job wants.

## At the prompt

The interface is a transcript, an editor under it and a status line under that. The status
line's right-hand end lists the keys that do something right now, which is the whole of what you
have to remember.

**A line typed mid-turn goes into the turn.** Not after it. "Actually, use pathlib" arriving
four minutes into a refactor reaches the agent that is doing the refactoring.
[Guide](/guide/steering)

**One transcript, several conversations.** A flow driving four agents is four conversations,
and **tab** steps between the ones that are working. [Guide](/guide/conversations)

**Showing the working.** `/details` toggles between every tool call and thought, or only what
the agent says. It changes the screen and nothing about the run. [Guide](/guide/details)

**The shape of a run.** `/status` says who is working, who handed to whom, and what it has cost
so far. [Guide](/guide/status)

**Being away.** `/afk` decides what happens when an agent stops to ask you something: wait, or
tell it nobody is there and let it carry on. [Guide](/guide/afk)

**Everything you typed here before,** on ↑ and ↓, kept per project.
[Guide](/guide/history) · **What a half-typed line could become,** under the editor.
[Guide](/guide/completion) · **`/export`** writes the transcript out as it was written.
[Guide](/guide/export)

**Reopening finds it as you left it.** The flow, the agents, the efforts and the accounts are
remembered per project. [Guide](/guide/settings)

**esc stops the flow** — the whole flow, not just the turn. **ctrl+c** takes back something
smaller. [Guide](/guide/stopping)

## What an agent is

An agent is a CLI, a model, an effort and an account, written `cli/model:effort`.

**Efforts.** How hard to think: `off`, `low`, `medium`, `high`, `max`, mapped onto whatever
each backend calls the same idea. A flow can move an agent's effort between turns.
[Guide](/guide/efforts)

**Permissions.** Four rungs from `read-only` to `bypass`. The default is `bypass`, and there is
no setting that turns permission prompts back on. [Guide](/guide/permissions)

**Skills.** Two kinds: the ones that CLI has installed, which humanize reads and never changes,
and the ones a flow carries in its own `skills/` and mounts onto every session it opens.
[Guide](/guide/skills)

**Goals.** The backend's own goal feature — the agent decides for itself when the objective is
met, and until it does, a turn that would have ended starts another. [Guide](/guide/goals)

**Questions.** An agent stopping mid-turn to ask its user something, answered by whoever is at
the prompt or by the flow. [Guide](/guide/questions)

**Answers in a shape.** A turn given a pydantic model answers with that model instead of prose,
so a flow reads a field rather than searching a paragraph for a phrase.
[Guide](/guide/shapes)

**Hooks.** Python callables hung on the moments of a turn — before a tool runs, when one asks
permission, when the agent tries to stop. [Guide](/guide/hooks)

**Cost and rate.** What has been spent, how fast the tokens are arriving, and how hard the model
is currently thinking. [Guide](/guide/tally)

**The person as an agent.** You, driven by a flow like any other agent, so a flow can ask a
human the same way it asks a model. [Guide](/guide/human-agent)

**Reporting.** humanize asks once whether to send crash reports to its developers, and says what
one carries before you answer. [Guide](/guide/reporting)

## Where the work lands

**Providers.** An agent may name the account it runs as, so one flow can drive one CLI as your
subscription and as somebody else's endpoint at the same time. [Guide](/guide/providers)

**Containers.** Give an agent a container of its own, brought up on its first turn and taken
down with it. [Guide](/guide/containers)

**Remote execution.** Moor an agent to an ssh host so its commands land there while the process
stays here. [Guide](/guide/remote-execution)

**Worktrees.** One agent working in several directories at once, one session per directory.
[Guide](/guide/worktrees)

## Flows

A flow is a directory whose `__init__.py` holds a function marked `@flow`, taking the agents and
the task. Everything else is ordinary Python — a loop, a `subprocess.run`, a file read between
turns.

**Writing one.** The shortest useful flow is about a dozen lines.
[Guide](/guide/writing-a-flow) · **Loops.** Ralph, stateful ralph, actor-and-reviewer: the
shapes a loop over one or two agents takes. [Guide](/guide/loops)

**Settings of its own.** A third argument annotated with a pydantic model becomes fields on
`/config` and lines in a `-c setup.yaml`. [Guide](/guide/flow-settings)

**Many turns at once.** Write `async def run` and a flow can have as many turns going as it
likes. [Guide](/guide/async-flows)

**A flow that calls a flow.** Composition, with the inner flow's agents supplied by the outer
one. [Guide](/guide/calling-flows)

**Testing one.** Without spending a turn. [Guide](/guide/testing-flows)

**Flowverses.** A git repository with a `flows/` directory in it, offered under its own name.
`official` is there from the start. [Guide](/guide/flowverses)

## What a run leaves behind

**Cycles.** Every run of a flow is a directory under `~/.humanize/cycles/`, holding what the
run was and what happened in it.

**Tracing.** `hmz trace collect` turns a run plus the backends' own transcripts into a Chrome
trace: one process per agent, one track per row of its sessions, one slice per thing it did.
Open it in Perfetto. [Guide](/guide/tracing)

**Picking a run up.** A loop stopped on Thursday — by esc, or by a machine going down — carried
on from where it stopped. [Guide](/guide/resuming)

**Unattended.** The same flows from a script. [Guide](/guide/unattended) · **In CI.**
[Guide](/guide/ci)

## Where the detail is

| | |
| --- | --- |
| [CLI](/reference/cli) | Every command and flag |
| [TUI](/reference/tui) | Every key and `/command` |
| [Flows](/reference/flows) | The `@flow` contract, settings, composition, flowverses |
| [Agents](/reference/agents) | Turns, sessions, hooks, shapes, efforts, permissions, skills, and what each backend can do |
| [Machines](/reference/machines) | Containers, worktrees, where a session works |
| [Providers](/reference/providers) | Accounts, and adding a CLI of your own |
| [Remote execution](/reference/remote-execution) | `hmz anchor`, and what lands where |
| [Tracing](/reference/tracing) | Cycles, the trace format, what a slice carries |
