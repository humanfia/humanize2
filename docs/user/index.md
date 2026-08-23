# User Guide

One page per thing humanize does, each answering "how do I use this?" — for the person who runs
flows rather than writes them. Where a page here shows Python, it is to say what the weaver on
the other side of the feature did; writing a flow yourself is the [Weaver Guide](/weaver/).

Never run one before? Start at the [quickstart](/#run-a-flow). The tutorials below each take a
whole piece of work start to finish; everything under them is for looking up.

## Tutorials

| | |
| --- | --- |
| [Beat a benchmark](/user/tutorials/take-home) | Two agents take turns optimising a kernel |
| [Port a project](/user/tutorials/port-a-project) | An agent works, a reviewer reads it back |
| [Build a coding agent](/user/tutorials/build-an-agent) | Idea, plan, then build under review |

## Start here

| | |
| --- | --- |
| [Installation](/user/installation) | Python, a backend, and what each one needs |
| [Concepts](/user/concepts) | The twelve words the rest of this uses |
| [Security](/user/security) | Read this before pointing an agent at a repository you care about |
| [Troubleshooting](/user/troubleshooting) | When it goes wrong |

## At the prompt

| | |
| --- | --- |
| [Talking to a running turn](/user/steering) | A line typed mid-turn goes *into* it, not after it |
| [Side questions](/user/btw) | `/btw`: ask about progress without steering the flow |
| [Many conversations at once](/user/conversations) | One transcript, **tab** between the agents that are working |
| [Showing the working](/user/details) | `/details`: tool calls and thinking, or only what the agent says |
| [The shape of a run](/user/status) | `/status`: who is working, who handed to whom, what it cost |
| [The mission board](/user/board) | Lines you and the flow both write on, and neither waits at |
| [Being away](/user/afk) | `/afk`: whether an agent may stop and ask you something |
| [Falling back](/user/fallback) | `/fallback`: where a turn goes when what was taking it cannot |
| [Completion](/user/completion) | What a half-typed line could become, under the editor |
| [History](/user/history) | Everything typed here before, on ↑ and ↓ |
| [Exporting a transcript](/user/export) | `/export` writes what is on screen, as it was written |
| [What a project remembers](/user/settings) | Reopening finds it set up the way you left it |
| [Stopping](/user/stopping) | **ctrl+c** twice ends the flow; what that does to a turn |

## Setting an agent up

| | |
| --- | --- |
| [Efforts](/user/efforts) | How hard to think — and moving it while the flow runs |
| [Permissions](/user/permissions) | Four rungs, from `read-only` to `bypass` |
| [Skills](/user/skills) | What an agent carries: its CLI's own, and the ones the flow brings |
| [Questions](/user/questions) | An agent stopping mid-turn to ask its user something |
| [Cost and rate](/user/tally) | What has been spent, how fast, and how hard it is thinking |
| [Reporting](/user/reporting) | What humanize sends its developers, and how to say no |

## Where the work lands

| | |
| --- | --- |
| [Providers](/user/providers) | One CLI, two accounts, at the same time |
| [Containers](/user/containers) | A container of the agent's own, up on the first turn |
| [Remote execution](/user/remote-execution) | The agent here; its commands on the build box |

## Running it, and reading it back

| | |
| --- | --- |
| [Unattended](/user/unattended) | `hmz exec` from a script, with nobody watching |
| [humanize in CI](/user/ci) | The same flows on a build machine |
| [Tracing](/user/tracing) | The whole run as one timeline you can open in Perfetto |
| [Picking a run up](/user/resuming) | A loop stopped on Thursday, carried on from where it stopped |

## If you write flows too

Three pages live here and matter either way. [Concepts](/user/concepts) is the vocabulary the
whole site uses, **weaver** included; [Security](/user/security) is why reading a flow means
running it; [Skills](/user/skills) is what an agent carries into a turn, and what a flow may
add. The rest of that job is the [Weaver Guide](/weaver/).

---

Looking for the exhaustive list of flags and keys instead? [CLI](/reference/cli) and
[TUI](/reference/tui).
