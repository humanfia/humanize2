# Documentation

Everything there is to read about humanize, grouped by what you came for.

## Table of Contents

- [Start here](#start-here)
- [Guides](#guides)
- [Reference](#reference)
- [Contributing](#contributing)
- [Reading order](#reading-order)

## Start here

| | |
| --- | --- |
| [Getting started](getting-started.md) | Install it, open the prompt, run a flow, read the trace it left. Half an hour, nothing memorised. |
| [Concepts](concepts.md) | The ten words the rest of this uses — flow, flowverse, agent, session, turn, cycle, machine, provider, backend, trace — and how they fit. |

## Guides

For doing a particular thing, once you know what the words mean.

| | |
| --- | --- |
| [Flows](flows.md) | Writing a flow: the entry point, how many agents it drives, what to call them, and the patterns that come with humanize. |
| [Agents](agents.md) | Driving a coding agent from Python: sessions, turns, streaming, goals, questions, interruption. |
| [Machines](machines.md) | Where an agent's turns land — this machine, one that is already running, or a container started for the agent. |
| [Providers](providers.md) | Which account an agent runs as, so that one flow can drive one CLI as two accounts at once. |
| [Remote execution](remote-execution.md) | `hmz anchor` in depth: targets, transports, serving, and exactly what does and does not cross. |
| [Tracing](tracing.md) | What a run leaves behind, and turning it into a timeline you can read. |
| [Troubleshooting](troubleshooting.md) | What each thing that goes wrong looks like, and what to do about it. |

## Reference

Complete, and organised for looking things up rather than reading through.

| | |
| --- | --- |
| [CLI](cli.md) | Every command, every flag, every environment variable, every file humanize writes. |
| [TUI](tui.md) | Every key and every `/command` the terminal interface takes. |

## Contributing

| | |
| --- | --- |
| [Architecture](architecture.md) | How the package is laid out, what each layer is for, and the rules that keep it that way. |

The [README](../README.md#contributing) has the checks a commit has to pass.

## Reading order

Never used it: [Getting started](getting-started.md) → [Concepts](concepts.md) → [TUI](tui.md).

Automating something: [Concepts](concepts.md) → [Flows](flows.md) → [CLI](cli.md).

Writing a flow of your own: [Flows](flows.md) → [Agents](agents.md) → [Tracing](tracing.md).

Running agents somewhere other than this machine: [Machines](machines.md) →
[Remote execution](remote-execution.md).

Running two accounts of one CLI at once: [Providers](providers.md).

Changing humanize itself: [Architecture](architecture.md), then the `SPEC.md` beside whatever
you are changing.
