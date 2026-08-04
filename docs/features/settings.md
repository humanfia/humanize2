# What a project remembers

Opening the interface again in the same project finds it set up the way you left it.

What is remembered:

- the flow that was last run there;
- for **each** flow that workspace has run — what each of its agents was running, where its
  turns landed, which [account](/features/providers) it ran as, and
  [what it may do](/features/permissions);
- and how the flow itself was [set up](/reference/tui#setting-a-flow-up).

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
| **This directory** | the directory itself, the flow it opens on with how many agents that flow was set up with, and a row that forgets the lot |

Nothing lands until the menu is left and saving is confirmed, as on every other menu. Forgetting
one directory leaves every other directory, and every setting, exactly as it was.

Two related files, for completeness:

| | |
| --- | --- |
| `~/.humanize/models/<cli>.json` | what each CLI said it runs, as you run it — refreshed with **r** on the models sheet |
| `~/.humanize/providers/<cli>/<name>/models.json` | the same, as that [account](/features/providers) |

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

`hmz exec` remembers nothing and reads nothing: an unattended run is the same run every time,
which is the point of it.

## The first time

With nothing remembered, the interface opens on the [`chat`](/reference/flows#the-flows-humanize-ships)
flow, on the first backend installed here that has said what it runs, at the first model it
named — that CLI's own idea of what it runs by default — and at `high`,
deliberately not the hardest setting, which is the one to reach for rather than the one to spend
before anybody has asked for anything.

## See also

- [History](/features/history) — the other thing kept between sessions
- [TUI › What it remembers](/reference/tui#what-it-remembers)
- [CLI › Files](/reference/cli#files)
