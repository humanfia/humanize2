---
pageClass: hmz-feature
---

# One system, four ways in

humanize has a Python SDK, a command line, a terminal interface and a daemon, but none of
them is a second orchestration engine. They reach the same workspace stores, flow loader and
runner. What changes is how the question is asked and how long the caller stays attached.

The route starts before a run does: find the nearest flow, fork it when it should become
yours, let its own pydantic model describe its setup, then enter through whichever surface
fits the job.

<HmzSurfaces />

## A flow starts near you

A flowverse is one place flows come from. A fetched flowverse is a Git repository whose
flows directory is the only part offered to humanize; the built-in flows are read from the
package instead. The project flow directory and the flow directory in your home are places
too, called local and user, even though nothing fetches either of them.

That gives a name two different orders. The catalogue opens with the flows humanize ships,
then the official flowverse, added flowverses, and finally the local places where either has
something to show. Resolution is deliberately different: an unqualified name looks in this
project first, then your home, then everywhere else. What is nearest wins.

A qualified name names its flowverse outright and bypasses that precedence. This is why the
catalogue can show the original and a local variant beside each other, while an unqualified
name quietly picks the one meant for this project.

Discovery is also a trust boundary. Listing the files in a repository is cheap, but finding
the marked flows and the lines they say about themselves means loading their entry points.
Only the flows directory is considered; what is in that directory is still Python code. A
flowverse should be trusted the way a package that will run on this machine is trusted.

## Forking changes ownership, not ancestry

Forking copies a flow into this project's local flow directory. A directory flow arrives
whole: its entry point, the modules it imports beside itself and every skill it brings. A
single-file flow remains a single file. The fetched source stays untouched, so refreshing
its flowverse later cannot erase the local edits.

The copy is staged beside its destination and then moved into place. If copying fails, no
half-flow is left under the name; if a local file or directory already owns that name,
forking refuses to write over it. Once the copy lands, nearest-first resolution makes the
unqualified name mean the local copy. The qualified source name still reaches the original.

This is a source decision, not a runtime capability switch. Forking a flow does not add a
goal feature to a backend, make an unsupported hook available or change where an agent can
work. The flow's declared requirements are checked separately against the agents chosen for
the run.

## The model is the setup surface

A flow that needs settings declares a pydantic model as its third argument. The model is the
complete vocabulary of that setup: field names, annotations, defaults, descriptions, bounds
and validators. Optional section metadata lets a large model group related fields without
teaching the terminal interface what any of them mean.

The interface reads those declarations directly. A boolean becomes a switch, a fixed set of
literal values becomes a list to step through, numbers move one at a time or accept typed
input, and other values are written. The description appears beside the field. When the
reader accepts the sheet, the model validates the whole set, including relationships between
fields, and returns its own refusal when the combination cannot run.

The command line and Python surface do not get a weaker contract. Values read from a setup
file or handed to the SDK are validated by the same model. Loading a flow runs its file
again, so the earlier model class is not trusted as the current one: its fields are read back
through the class the flow declares now. A remembered setup that no longer fits starts over;
a bad setup presented to a run is refused before its first turn.

## Shared core does not mean identical interfaces

The SDK's workspace object is the composition point. It reaches the same settings, flows,
agents, accounts and epics that the other surfaces show, and loads each of them only when it
is asked for. Adding a flowverse through one surface and seeing it in another is not a sync
operation. Both are reading the same store.

Python and the execution command both use the SDK Run: a loaded runner plus its task, with
one lifecycle for running here, starting in the background, waiting, stopping and closing
the agent conversations. The command line chooses the blocking path; Python may choose
either.

The terminal interface has a different job. It keeps the same workspace object and runner in
hand so it can configure the flow, watch several conversations, accept questions and steer a
turn while the run is live. It does not need to wrap that runner in a second orchestration
engine merely to draw it.

The daemon is narrower still. It does not interpret flows at all. It holds the same terminal
interface in a detached process and carries its screen through a pseudoterminal. The interface
sees only the SDK Session boundary: how many terminals are reading and how to detach them
without stopping the run. That protocol keeps daemon machinery out of the interface while a
closed terminal leaves the work going on the same host.

So unified means common state, validation and runtime semantics where the surfaces overlap.
It does not mean feature parity or identical interaction. The SDK is composable, the command
line is scriptable, the terminal interface is conversational, and the daemon owns
continuity. Each remains small because none has to redefine what a flow, setup, run or
session means.

## Where the detail is

- [Flowverses and forking](/guide/flowverses) · [Flow settings](/guide/flow-settings)
- [Python SDK](/reference/sdk) · [CLI](/reference/cli) · [TUI](/reference/tui) ·
  [Daemon](/reference/daemon)
