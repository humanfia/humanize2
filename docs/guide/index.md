# Guides

One page per thing humanize does, each answering "how do I use this?". Every guide opens with a
worked example you can paste, then explains the rest.

These are for looking things up. If you have not used humanize before, the
[tutorials](/tutorials/) teach it in order, starting with the
[Quickstart](/tutorials/quickstart).

## Start here

| | |
| --- | --- |
| [Installation](/guide/installation) | Python, a backend, and what each one needs |
| [Concepts](/guide/concepts) | The ten words the rest of this uses |
| [Security](/guide/security) | Read this before pointing an agent at a repository you care about |
| [Troubleshooting](/guide/troubleshooting) | When it goes wrong |

## At the prompt

| | |
| --- | --- |
| [Talking to a running turn](/guide/steering) | A line typed mid-turn goes *into* it, not after it |
| [Side questions](/guide/btw) | `/btw`: ask about progress without steering the flow |
| [Many conversations at once](/guide/conversations) | One transcript, **tab** between the agents that are working |
| [Showing the working](/guide/details) | `/details`: tool calls and thinking, or only what the agent says |
| [The shape of a run](/guide/status) | `/status`: who is working, who handed to whom, what it cost |
| [Being away](/guide/afk) | `/afk`: whether an agent may stop and ask you something |
| [Falling back](/guide/fallback) | `/fallback`: where a turn goes when what was taking it cannot |
| [Completion](/guide/completion) | What a half-typed line could become, under the editor |
| [History](/guide/history) | Everything typed here before, on ↑ and ↓ |
| [Exporting a transcript](/guide/export) | `/export` writes what is on screen, as it was written |
| [What a project remembers](/guide/settings) | Reopening finds it set up the way you left it |
| [Stopping](/guide/stopping) | **ctrl+c** twice ends the flow; what that does to a turn |

## Setting an agent up

| | |
| --- | --- |
| [Efforts](/guide/efforts) | How hard to think — and moving it while the flow runs |
| [Permissions](/guide/permissions) | Four rungs, from `read-only` to `bypass` |
| [Skills](/guide/skills) | What an agent carries: its CLI's own, and the ones the flow brings |
| [Goals](/guide/goals) | The backend's own goal feature: it decides when it is done |
| [Questions](/guide/questions) | An agent stopping mid-turn to ask its user something |
| [Answers in a shape](/guide/shapes) | A turn that answers with a pydantic model instead of prose |
| [Hooks](/guide/hooks) | Python callables hung on the moments of a turn |
| [Cost and rate](/guide/tally) | What has been spent, how fast, and how hard it is thinking |
| [The person as an agent](/guide/human-agent) | You, driven by a flow like any other agent |
| [Reporting](/guide/reporting) | What humanize sends its developers, and how to say no |

## Writing flows

| | |
| --- | --- |
| [Writing a flow](/guide/writing-a-flow) | The dozen lines that make a directory a flow |
| [Loops](/guide/loops) | Ralph, stateful ralph, and the shapes a loop takes |
| [Settings of its own](/guide/flow-settings) | A pydantic model that becomes `/config` fields |
| [Many turns at once](/guide/async-flows) | `async def run`, and awaiting several turns |
| [A flow that calls a flow](/guide/calling-flows) | Composition, and whose agents the inner one gets |
| [Testing a flow](/guide/testing-flows) | Checking the loop without spending a turn |
| [Flowverses](/guide/flowverses) | A git repository of flows, offered by name |

## Where the work lands

| | |
| --- | --- |
| [Providers](/guide/providers) | One CLI, two accounts, at the same time |
| [Containers](/guide/containers) | A container of the agent's own, up on the first turn |
| [Remote execution](/guide/remote-execution) | The agent here; its commands on the build box |
| [Worktrees](/guide/worktrees) | One agent working in several directories at once |

## Running it, and reading it back

| | |
| --- | --- |
| [Unattended](/guide/unattended) | `hmz exec` from a script, with nobody watching |
| [humanize in CI](/guide/ci) | The same flows on a build machine |
| [Tracing](/guide/tracing) | The whole run as one timeline you can open in Perfetto |
| [Picking a run up](/guide/resuming) | A loop stopped on Thursday, carried on from where it stopped |

---

Looking for the exhaustive list of flags and keys instead? [CLI](/reference/cli) and
[TUI](/reference/tui).
