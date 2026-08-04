# What humanize is

humanize runs **flows**: directories of Python that drive one or more coding agents in a loop, and write
down everything they did so it can be read back afterwards.

It does not talk to a model provider. It drives the coding agent CLI you already have — `claude`,
`codex`, `kimi`, `pi`, `opencode`, `mimo` — logged in the way you already log in. There is no API
key to give it and none for it to hold.

## What it is for

A single conversation with a coding agent is a chat window. Most work is not that shape:

| You want | humanize's answer |
| --- | --- |
| The agent to keep going until the job is done, starting fresh each time | A [Ralph loop](/guide/tutorial-ralph-loop) |
| One agent building and another reading its work | A [two-agent flow](/guide/tutorial-actor-reviewer) |
| Two hundred files fixed at once | A [fan-out](/guide/tutorial-async-flow) |
| The same run twice, unattended, in CI | [`hmz exec`](/guide/tutorial-unattended) and [CI](/guide/tutorial-ci) |
| To know what a nine-hour run actually did | [`hmz collect`](/guide/tutorial-trace) |
| One CLI driven as two accounts at once | [Providers](/guide/tutorial-providers) |
| The work to land in a container, or on the build box | [Containers](/guide/tutorial-container), [remote execution](/guide/tutorial-remote) |

## Two ways in

**A terminal interface.** `hmz` with nothing after it opens a transcript, an editor, and a status
line. Pick a flow with `/flow`, say what you want done, and watch it. There is no `hmz tui`: one
way in is one way in.

**A command line.** `hmz exec -f <flow> -a <agent> "<task>"` runs the same flows with nobody
watching — which is what a script, a cron entry or a CI job wants.

Both write the same [cycle](/guide/concepts#cycle), and both are read back the same way.

## What to read

- **Never used it.** [Installation](/guide/installation) → [Getting started](/guide/getting-started)
  → [Concepts](/guide/concepts).
- **Want a feature.** [Features](/features/) has a page each — `/afk`, skills, goals, containers,
  providers, tracing — and each says how to reach it from the prompt, the command line and Python.
- **Automating something.** The [tutorials](/guide/tutorial-first-run) go from your first run to
  publishing a flowverse, in order.
- **Looking something up.** [CLI](/reference/cli) and [TUI](/reference/tui) are complete.
- **Changing humanize itself.** [Architecture](/contributing/architecture).

Before you point one at a repository you care about, read [Security](/guide/security). humanize
runs every agent with permission prompts disabled, and there is no setting that turns them back
on.
