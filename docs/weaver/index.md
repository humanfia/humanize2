# Weaver Guide

A **weaver** is whoever — or whatever — writes a flow: the directory of Python that says which
agents are driven, what each is asked, in what order, and when to stop. This section is
everything that role needs. The [User Guide](/user/) is for whoever runs what a weaver made.

If you have not run humanize at all yet, the front page has a quickstart per role: [run a
flow](/#run-a-flow) is the basics of running one, and [weave a flow](/#weave-a-flow) is the
shortest flow there is.

## Tutorials

Taken in order, each a whole flow written from scratch.

| | |
| --- | --- |
| [Build under test](/weaver/tutorials/checked-build) | The shortest useful flow there is: a writer, `pytest` between turns, a reviewer |
| [Four agents on a maths problem](/weaver/tutorials/prove) | Several turns at once, answers held to a shape, and nothing to compile |

## Writing a flow

| | |
| --- | --- |
| [Writing a flow](/weaver/writing-a-flow) | The dozen lines that make a directory a flow |
| [Loops](/weaver/loops) | Ralph, stateful ralph, and the shapes a loop takes |
| [Settings of its own](/weaver/flow-settings) | A pydantic model that becomes a settings sheet |
| [Many turns at once](/weaver/async-flows) | `async def run`, and awaiting several turns |
| [A flow that calls a flow](/weaver/calling-flows) | Composition, and whose agents the inner one gets |
| [An atlas](/weaver/atlas) | Restricted Python compiled into a typed, resumable prophecy |

## What an agent can be asked

| | |
| --- | --- |
| [Goals](/weaver/goals) | The backend's own goal feature: it decides when it is done |
| [Answers in a shape](/weaver/shapes) | A turn that answers with a pydantic model instead of prose |
| [Hooks](/weaver/hooks) | Python callables hung on the moments of a turn |
| [Callbacks as tools](/weaver/tools) | Functions of the flow's own, put in front of the agent |
| [The person as an agent](/weaver/human-agent) | You, driven by a flow like any other agent |
| [Worktrees](/weaver/worktrees) | One agent working in several directories at once |

## Checking and publishing

| | |
| --- | --- |
| [Checking a flow](/weaver/checking-flows) | Static findings and executable proof before a real turn |
| [Testing a flow](/weaver/testing-flows) | Checking the loop without spending a turn |
| [Flowverses](/weaver/flowverses) | A git repository of flows, offered by name |

## From the User Guide

A flow sets up the agents it drives, so five pages written for whoever runs one are pages a
weaver writes against.

| | |
| --- | --- |
| [Concepts](/user/concepts) | The vocabulary the rest of this uses |
| [Security](/user/security) | A flow is Python, and reading one means running it |
| [Skills](/user/skills) | What an agent carries: its CLI's own, and the ones the flow brings |
| [Permissions](/user/permissions) | Four rungs, from `read-only` to `bypass` |
| [Efforts](/user/efforts) | How hard to think — and moving it while the flow runs |

---

Eleven flows already exist, and reading one is the shortest way to see what a twelfth could be:
[Flows](/flows/). For the contract in full — every argument, every refusal, every return —
[Reference › Flows](/reference/flows).
