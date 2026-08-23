# Falling back — `/fallback`

Two things go wrong, and they are not the same thing.

An **account** goes down. A subscription runs out, a key is refused, a gateway answers 503.
The model is fine, the CLI is fine, and what the turn needs is another account of the same
backend. That happens **inside the conversation that was running** — the conversation is the
backend's own and is named by an id, so the next account picks it up mid-thought. It is a
thing about the account, and it is said in [`/providers`](/user/providers).

A **place** has nowhere left to run. The model was retired this morning, the CLI will not
start, the region has gone dark, the whole account is rate-limited rather than one request. No
other account of that backend answers any of those. What answers them is **another place** —
another CLI, another account, another model — and the conversation cannot come with it,
because no backend takes another backend's session id.

`/fallback` is the second. It is the layer between an agent and its accounts, and a place is
three things and no more:

```
CLI[@ACCOUNT]/MODEL
```

How hard the agent thinks, what it may reach for, whether it may search the web and which of a
flow's skills it carries are what that **agent** is, settled where it was made. They come
across the step unchanged. What failed was the place, so the place is what moves.

## Try it

```
/fallback
```

One page, one row per place. `a` chooses the place that cannot run — the CLI, then one of its
accounts, then one of the models it says it runs — and then the place that takes its turns.
Enter on a row asks the two things a step says: where its turns go, and how many times over a
failed turn is taken again first. `d` twice takes a step away.

Nothing lands until the menu is saved on the way out, as on every menu.

## On the command line

```sh
hmz fallback add claude/claude-opus-5 codex/gpt-5.6-sol
hmz fallback retry claude/claude-opus-5 3 --policy exponential --timeout 90
hmz fallback list
hmz fallback show claude/claude-opus-5
hmz fallback remove claude/claude-opus-5
```

An account is part of which place this is, after an `@`:

```sh
hmz fallback add claude@work/claude-opus-5 codex@key/gpt-5.6-sol
```

`show` prints the whole walk rather than the one step, since the walk is what a failed turn
actually does:

```
1. claude@work/claude-opus-5   [3 more tries, exponential]
2. codex@key/gpt-5.6-sol
3. dsh/deepseek-v4-flash
```

## Trying again

How many times over a failed turn is taken again is written here rather than on the account,
because it is a thing about the place a turn runs at rather than about the credentials it runs
with. One row says both, both being answers to the one thing that went wrong.

| | |
| --- | --- |
| `tries` | how many goes beyond the first; `0` is a failed turn that is a failed turn |
| `policy` | how long to wait between them — `none`, `constant`, `linear`, `exponential`, `exponential-jitter`, `fibonacci` |
| `timeout` | the longest the trying again may go on for, or `0` for as long as the tries take |

`exponential-jitter` is what to reach for when several agents are failing at once: full jitter
is what keeps a flow's agents from all coming back on the same second.

## What a turn actually does

In order, and it stops at the first thing that works:

1. **Takes the turn.** If it lands, none of the rest happens — nothing is looked up, and no
   stand-in is started.
2. **Tries again at the same place**, as many times and with whatever wait the step says.
   Nothing is retried unless you asked for it.
3. **Walks the account chain**, in the conversation that was running. An agent that has moved
   stays moved: the account that went down is not one to try again each turn.
4. **Walks the chain of places**, once there is no account left. The turn is taken in a new
   session of an agent at the next place, configured exactly as the agent it left — carrying
   its effort, its permission rung, the skills the flow gave it and the
   [callbacks](/weaver/tools) the agent is offering.

The flow sees one turn either way. The events come back through the session it asked, between
the same `begins` and `ends`, and the transcript says where it was picked up.

## What it costs you to have one

Nothing until it is needed. The agent standing in is built the first time a turn has nowhere
left to go — a chain of four places all started when the run was would be three CLIs held open
for a failure that never came.

## What it will not do

- **Carry the conversation across the move.** Step 4 opens a session on the other side, and
  the agent arrives reading the repository rather than a history. It is lost once rather than
  every turn, though: that session is held for as long as the one that asked for it, so a
  stateful loop that moved is one conversation on the other side and not one a round.
- **Come round on itself.** A chain ends at the second sight of a place, and a place cannot
  fall back to itself — either would be a turn that never ran out of places to go.
- **Fork.** One place has one place to go. Writing a step again says the new thing and not both.
- **Move a setting the CLI taking over cannot be told.** An agent told not to search the web
  does not fall back to a CLI with no way of being told: a setting quietly ignored would be a
  setting that lies, so the turn fails as it failed before anybody wrote a step down. The
  same goes for what is in front of the model rather than configured on it — a turn taken
  with the flow's own [callbacks](/weaver/tools) offered does not move to a backend that has
  no way of being given one.
- **Rescue a turn that failed for a reason another try cannot fix.** A prompt longer than the
  context window is that long at the next place too. Those are `Unrecoverable`, and are
  [taken once](/reference/agents#when-an-account-goes-down) whatever any chain says.

## See also

- [Providers](/user/providers) — the accounts an agent runs as, and the chain between them
- [Unattended runs](/user/unattended) — where having somewhere to fall back to earns its keep
- [TUI › `/fallback`](/reference/tui#where-a-turn-goes-when-it-cannot-be-taken)
