---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Features

humanize runs **flows**: directories of Python that drive one or more coding agents in a loop
and write down everything they did. It does not talk to a model provider — it drives the coding
agent CLI you already have, logged in the way you already log in.

This is the front of the documentation, and it is what there is rather than how to use it.
Nothing on this page is a command to type: the [tutorials](/tutorials/) teach it in order
starting with the [Quickstart](/tutorials/quickstart), the [guides](/guide/) answer "how do I
use this?", and [Flows](/flows/) is what it can run out of the box.

<HmzInstall />

## A run, as it happens

One flow, many agents, one trace. Every turn's tool calls land on the timeline as they are
made — every agent, every sub-agent and every program those turns ran, on one clock. Hover a
lane; change how many agents are on it.

<HmzOrchestra />

<p class="hmz-note">
A simulation of the shape of a run, not a recording. What the real screens look like is
<a href="#the-real-thing-recorded">further down</a>, and
<a :href="withBase('/features/tracing')">One timeline</a> is how the trace is built.
</p>

## What it does, one picture each

<HmzFeatures />

## The agent runs here. Its syscalls land there.

A seccomp-filtered ptrace supervisor decides every call the coding agent makes, one at a time.
No plugin, no configuration, no cooperation — the agent is told none of it.

<HmzAnchor />

<p class="hmz-note">
How it works, syscall by syscall: <a :href="withBase('/features/anchor')">The anchor</a>. What
you are deliberately not entitled to:
<a :href="withBase('/reference/remote-execution')">its reference</a>.
</p>

## Where each page sits

<HmzMap />

### The deep end

The five that are worth reading even if you never install it.

| | |
| --- | --- |
| [The anchor](/features/anchor) | The agent runs here. Every syscall it makes is decided one at a time — replayed on another machine, or answered on this one. It is told none of it. |
| [Two accounts of one CLI](/features/accounts) | A CLI signs in once. humanize runs it as an account it was never signed into, by answering the paths it opens with other paths. |
| [One timeline](/features/tracing) | Every agent, every sub-agent and every program those turns ran, on one clock, in one document you open in Perfetto. |
| [A line typed mid-turn](/features/steering) | It goes *into* the turn that is running. Not queued behind it, and never quietly counted as said. |
| [Answers in a shape](/features/shapes) | A turn given a pydantic model answers with that model. The model is the whole of the question, and the answer is read back through it. |

### The shape of a run

| | |
| --- | --- |
| [Eleven CLIs, one agent](/features/backends) | Eleven coding agents and anything speaking the Agent Client Protocol, each driven through whatever it actually offers. |
| [A flow is Python](/features/flows) | A loop, a subprocess call, a file read between turns. The agents are its arguments, and the shapes a loop takes are few. |
| [Many turns at once](/features/concurrency) | Turns are sequential only inside one session. Two hundred conversations are two hundred turns. |
| [Picked up where it stopped](/features/resuming) | A loop meant to run for a week is a loop that will be stopped. What it was keeping track of survives; the conversation does not. |

### Who is at the other end

| | |
| --- | --- |
| [It decides when it is done](/features/goals) | The backend's own goal feature: a turn that would have ended starts another, until the model says the objective is met. |
| [The moments of a turn](/features/hooks) | Seven points a turn passes through, and Python callables hung on them — and taken down again while it runs. |
| [You, as one of the agents](/features/human) | A flow puts a decision to a person the way it puts one to a model, in the same shape, with the same branch for an answer that never came. |

## The flows it comes with

Eleven of them, between the package and the flowverse humanize fetches: a ralph loop and a
stateful one, two agents alternating, an actor with a reviewer between its rounds, a loop the
model itself decides is over, and three isolated lanes with a coordinator over them. Each has a
page with its own loop played on it.

<p class="hmz-note">
Every one of them, with the shape of each: <a :href="withBase('/flows/')">Flows</a>. How to write
one of your own: <a :href="withBase('/guide/writing-a-flow')">Writing a flow</a>.
</p>

## The real thing, recorded

Hover to play, click to open.

<HmzGallery />

<p class="hmz-note">
Recorded against a stand-in coding agent, in a container of its own — see
<a :href="withBase('/contributing/docs#the-terminal-demos')">Working on these docs</a>.
</p>

## And the rest

Everything above is one page because it is unusual. The ordinary parts of humanize have a guide
apiece and no page here: [efforts](/guide/efforts) and [permissions](/guide/permissions),
[skills](/guide/skills) and [questions](/guide/questions), [containers](/guide/containers) and
[worktrees](/guide/worktrees), [cost and rate](/guide/tally), [flowverses](/guide/flowverses),
[history](/guide/history), [completion](/guide/completion) and [what a project
remembers](/guide/settings).

## Where to go next

<div class="hmz-paths">
  <a :href="withBase('/tutorials/quickstart')">
    <strong>Never used it</strong>
    <span>Nothing installed to a run you can open in Perfetto, in fifteen minutes.</span>
  </a>
  <a :href="withBase('/flows/')">
    <strong>What it can run</strong>
    <span>Eleven flows, the shape of each one drawn and played.</span>
  </a>
  <a :href="withBase('/guide/')">
    <strong>One feature</strong>
    <span>A page each, opening with something you can paste.</span>
  </a>
  <a :href="withBase('/reference/cli')">
    <strong>Looking it up</strong>
    <span>Every command, key, flag and Python call.</span>
  </a>
</div>

::: warning Before you point one at a repository you care about
humanize runs every agent with permission prompts disabled, and nothing turns them back on. A
flow is a directory of Python, and reading one means running it. Read
[Security](/guide/security).
:::
