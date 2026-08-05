# What a project remembers

Opening the interface again in the same project finds it set up the way you left it.

What is remembered:

- the flow that was last run there;
- for **each** flow that workspace has run — what each of its agents was running, where its
  turns landed, which [account](/features/providers) it ran as, and
  [what it may do](/features/permissions);
- how the flow itself was [set up](/reference/tui#setting-a-flow-up);
- and whether the programs a run here starts are
  [profiled](#whether-a-run-here-is-profiled) as well as traced.

Beside those, in the same file, is the one setting that is not a workspace's at all:
`enable_sentry`, the answer to the [reporting](/features/reporting) question, which is asked
once and true wherever humanize is run from.

## Why it is kept per flow

What an agent runs is only meaningful against the flow driving it. A flow's second agent is its
reviewer; the flow before it had no second agent at all.

So it is keyed three ways:

| Keyed by | So that |
| --- | --- |
| the workspace | two projects are two setups |
| the flow — by name for humanize's own, **by path** for yours | a flow of yours cannot inherit the agents of the one it shares a name with |
| the name the flow calls each agent | a flow that grows an agent in the middle does not silently hand the reviewer's model to the builder |

What was set up is read back **through the flow's own model**, so a setting the flow has since
dropped or renamed is one it starts over from rather than one that quietly comes back.

## Where it lives

```
~/.humanize/settings.yaml
```

`$HUMANIZE_HOME/settings.yaml` where that is set. Delete it and every project starts over from
its defaults **and** the reporting question is asked again, that answer living in the same file.

## Reading it, and forgetting it

`/settings` is the menu over this file, in two pages:

| Page | |
| --- | --- |
| **Everywhere** | whether humanize [reports what goes wrong](/features/reporting), and a row that says what a report carries and what it never does |
| **This directory** | the directory itself, the flow it opens on with how many agents that flow was set up with, whether a run here is [profiled](#whether-a-run-here-is-profiled), and a row that forgets the lot |

Nothing lands until the menu is left and saving is confirmed, as on every other menu. Forgetting
one directory leaves every other directory, and every setting, exactly as it was.

Two related files, for completeness:

| | |
| --- | --- |
| `~/.humanize/models/<cli>.json` | what each CLI said it runs, as you run it — refreshed with **r** on the models sheet |
| `~/.humanize/providers/<cli>/<name>/models.json` | the same, as that [account](/features/providers) |

## Whether a run here is profiled

A workspace remembers one thing more: whether the programs its runs start are sampled as well as
[traced](/features/tracing), which is the **profile** row on the second page of `/settings` and is
off until somebody turns it on.

![/settings opening on what is true of this machine, then tab to this directory: workspace, flow,
profile and forget](/demo/profiling.gif)

It is the workspace's rather than the machine's, because what a
run costs in processes is a thing about the project being worked on: a repository whose tests take
an hour is a different question from one whose tests take a minute. The switch is read where a run
starts, so turning it on holds from the next run rather than the one under way, and a run started
in that directory by `hmz exec` is profiled too — it says nothing about what runs, only about
whether what runs is watched.

What is sampled, what that costs while the flow runs, and what a trace then makes of it are
[Tracing › Profiling a run](/features/tracing#profiling-a-run).

From Python it is one property and one call:

```python
from hmz.settings import Settings

Settings().profiling            # whether a run in this directory is profiled
Settings().profiles(on=True)    # written down for it, from now on
```

## Overriding it for one run

The line beats what was remembered, and starts nothing — the interface opens ready, and the first
thing you say is still what starts it:

```sh
hmz -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high
```

```sh
hmz -f official/humanize1:rlcr -c setup.yaml
```

What the line says is checked **before** the interface opens — a flow that will not load, a
config the flow refuses, the wrong number of agents — so a line that is wrong is a line, not a
sheet to walk back out of.

`hmz exec` is set up from none of this: what it runs is what the line names, so an unattended run
inherits nothing of what this project was last set up with, which is the point of it. Two things
it does read from outside the line: whether the runs of this directory are
[profiled](#whether-a-run-here-is-profiled), which is the workspace's rather than the run's, and
whether [reporting](/features/reporting) was answered yes. And a flow that says it [can be picked
up](/features/resuming) is handed what the last run of it here left behind, which is the run's own
doing rather than a setting — an unattended run of one is the next stretch rather than the same
stretch again.

## The first time

With nothing remembered, the interface opens on the [`chat`](/reference/flows#the-flows-humanize-ships)
flow, on the first backend installed here that has said what it runs, at the first model it
named — that CLI's own idea of what it runs by default — and at `high`,
deliberately not the hardest setting, which is the one to reach for rather than the one to spend
before anybody has asked for anything.

## See also

- [History](/features/history) — the other thing kept between sessions
- [Tracing](/features/tracing) — the trace a profiled run is drawn into
- [TUI › What it remembers](/reference/tui#what-it-remembers)
- [CLI › Files](/reference/cli#files)
