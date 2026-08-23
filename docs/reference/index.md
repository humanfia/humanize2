# Reference

Complete and dry. Every command, flag, key, argument and return, for a reader who already
knows what they are looking for.

If you do not yet: [Features](/features/) is what humanize does and [Flows](/flows/) is what
there is to run, and then there is a section per role — the [User Guide](/user/) for running
flows, the [Weaver Guide](/weaver/) for weaving them, [Contributing](/contributing/) for
working on humanize itself. Each of the three opens with tutorials, and the home page carries
a quickstart apiece: [run a flow](/#run-a-flow), [weave a flow](/#weave-a-flow),
[work on humanize](/#work-on-humanize).

## Command line

| | |
| --- | --- |
| [CLI](/reference/cli) | Every command and flag, and the environment variables, files and exit statuses |
| [TUI](/reference/tui) | The screen `hmz` opens with no command: its keys, its commands, its menus |
| [Daemon](/reference/daemon) | The run held where a terminal closing cannot end it, and the terminals that come and go |

## Python

| | |
| --- | --- |
| [SDK](/reference/sdk) | `Hmz`: humanize as one object, which every way in goes through |
| [Flows](/reference/flows) | The directory a flow is, what `@flow` takes, and what the loop it holds may do |
| [Agents](/reference/agents) | Driving a coding agent from Python: an agent is settings, a session is memory |
| [Machines](/reference/machines) | Where an agent's turns land — here, a container, or a machine already running |
| [Providers](/reference/providers) | Which account an agent runs as, kept apart from the CLI's own |
| [Remote execution](/reference/remote-execution) | `hmz anchor`: an agent on this machine whose work lands on another |
| [Tracing](/reference/tracing) | `hmz trace collect`, and the one timeline it makes of a run |
