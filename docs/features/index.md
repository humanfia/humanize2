---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Features

humanize runs **flows**: directories of Python that drive one or more coding agents in a loop
and write down everything they did. Most backends drive a coding agent you already have under
its existing login; the bundled DeepSeek Harness is the SDK-backed exception.

This is the front of the documentation: one way to install it, then what the system is rather
than how to operate each part. The [tutorials](/tutorials/) teach it in order starting with the
[Quickstart](/tutorials/quickstart), the [guides](/guide/) answer "how do I use this?", and
[Flows](/flows/) is what it can run out of the box.

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

## How the capabilities fit together

A run crosses five systems: the flow that describes the work, the control plane that drives
agents, the execution fabric that decides where work lands, the run record that keeps it
continuous and readable, and the surfaces through which people start and inspect it. Hover or
focus a group to read the guarantee it owns; follow it to the best explanation.

<HmzMap />

<p class="hmz-note">
The complete map adds the boundaries, related guides and reference for every group:
<a :href="withBase('/features/capabilities')">Capability map</a>.
</p>

## Feature deep dives

The map is broad. These pages take one mechanism far enough that its trade-offs make sense,
each around a diagram you can push.

### Flow system

| | |
| --- | --- |
| [Python becomes a prophecy](/features/prophecy) | A deliberately narrow flow becomes a typed graph that can be checked, compared and resumed node by node. |
| [A flow is Python](/features/flows) | Ordinary Python and compiled atlases live side by side, chosen by how much of the work must be knowable before it runs. |
| [Many turns at once](/features/concurrency) | Turns are sequential inside one session; concurrency comes from having several conversations to run. |
| [Picked up where it stopped](/features/resuming) | Ordinary flows preserve explicit state; atlases preserve completed node visits. Neither recreates a conversation. |

### Agent control plane

| | |
| --- | --- |
| [Many backends, one agent](/features/backends) | Native servers, streaming CLIs and Agent Client Protocol backends meet one session contract. |
| [Two accounts of one CLI](/features/accounts) | Credentials, model catalogues and failure chains stay isolated while a session changes where it runs. |
| [A line typed mid-turn](/features/steering) | Acknowledged queues put guidance into the turn that is working rather than behind it. |
| [Answers in a shape](/features/shapes) | A pydantic model is both the question and the contract the answer must satisfy. |
| [It decides when it is done](/features/goals) | A backend-owned pursuit loop continues until the model settles the objective. |
| [The moments of a turn](/features/hooks) | Typed lifecycle moments let a flow react without teaching the backend about the flow. |
| [You, as one of the agents](/features/human) | Questions, the mission board and a person-shaped agent put human decisions on the same run. |

### Execution fabric

| | |
| --- | --- |
| [The anchor](/features/anchor) | A local agent can work against a remote target while paths, processes, networks and ownership keep their meaning. |

### Run continuity and observability

| | |
| --- | --- |
| [The terminal can leave](/features/daemon) | A workspace daemon owns the PTY, so watchers may disconnect and return without owning the run. |
| [One timeline](/features/tracing) | Agent events, sub-agents and sampled processes are reconstructed on one calibrated clock. |

### Product surfaces

| | |
| --- | --- |
| [One system, four ways in](/features/surfaces) | Local discovery, schema-driven setup, Python, CLI, TUI and the daemon all reach the same run and session model. |

## The flows it comes with

Between the package and the official flowverse are a ralph loop and a stateful one, two agents
alternating, an actor with a reviewer between its rounds, a loop the model itself decides is
over, and isolated lanes with a coordinator over them. Each has a page with its own loop
played on it.

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

## Where to go next

<div class="hmz-paths">
  <a :href="withBase('/features/capabilities')">
    <strong>Map the whole system</strong>
    <span>Five domains, every capability group, and the right explanation for each.</span>
  </a>
  <a :href="withBase('/tutorials/quickstart')">
    <strong>Never used it</strong>
    <span>Nothing installed to a run you can open in Perfetto, in fifteen minutes.</span>
  </a>
  <a :href="withBase('/flows/')">
    <strong>What it can run</strong>
    <span>The flows it ships, with the shape of each one drawn and played.</span>
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
flow is trusted Python: loading or running it may execute its code, even though static checks
can inspect selected structure without doing so. Read
[Security](/guide/security).
:::
