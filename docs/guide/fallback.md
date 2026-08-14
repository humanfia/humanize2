# Falling back — `/fallback`

Two things go wrong, and they are not the same thing.

An **account** goes down. A subscription runs out, a key is refused, a gateway answers 503.
The model is fine, the CLI is fine, and what the turn needs is another account of the same
backend. That happens **inside the conversation that was running** — the conversation is the
backend's own and is named by an id, so the next account picks it up mid-thought.

An **agent** has nowhere left to run. The model was retired this morning, the CLI will not
start, the region has gone dark, the whole account is rate-limited rather than one request. No
other account of that backend answers any of those. What answers them is **another agent** —
another CLI, another model, another effort — and the conversation cannot come with it, because
no backend takes another backend's session id.

`/fallback` is both, on two pages of one menu.

## Try it

```
/fallback
```

The first page is the steps between agents. `a` chooses the agent that cannot run, and then
the agent that takes its turns. `d` twice takes a step away. **tab** turns to the accounts,
where enter says which account one falls back to.

Nothing lands until the menu is saved on the way out, as on every menu.

## On the command line

```sh
hmz fallback add claude/claude-opus-5:high codex/gpt-5.6-sol:high
hmz fallback list
hmz fallback show claude/claude-opus-5:high
hmz fallback remove claude/claude-opus-5:high
```

An agent is named exactly the way [`-a`](/reference/cli) names one, account and all:

```sh
hmz fallback add claude@work/claude-opus-5:high codex@key/gpt-5.6-sol:high
```

`show` prints the whole walk rather than the one step, since the walk is what a failed turn
actually does:

```
1. claude@work/claude-opus-5:high
2. codex@key/gpt-5.6-sol:high
3. dsh/deepseek-v4-flash:high
```

The accounts are still [`hmz providers falls-back`](/reference/providers#hmz-providers) on the
command line, because there they are a thing about an account.

## What a turn actually does

In order, and it stops at the first thing that works:

1. **Takes the turn.** If it lands, none of the rest happens — nothing is looked up, and no
   stand-in is started.
2. **Tries again under the same account**, as many times and with whatever wait that account
   was [told to use](/guide/providers). Nothing is retried unless you asked for it.
3. **Walks the account chain**, in the conversation that was running. An agent that has moved
   stays moved: the account that went down is not one to try again each turn.
4. **Walks the agent chain**, once there is no account left. The turn is taken in a new session
   of the agent it moved to, carrying the skills the flow gave the agent it left.

The flow sees one turn either way. The events come back through the session it asked, between
the same `begins` and `ends`, and the transcript says which agent picked it up.

## What it costs you to have one

Nothing until it is needed. The stand-in agent is built the first time a turn has nowhere left
to go — a chain of four agents all started when the run was would be three CLIs held open for a
failure that never came.

## What it will not do

- **Carry the conversation across the move.** Step 4 opens a session on the other side, and
  the agent arrives reading the repository rather than a history. It is lost once rather than
  every turn, though: that session is held for as long as the one that asked for it, so a
  stateful loop that moved is one conversation on the other side and not one a round.
- **Come round on itself.** A chain ends at the second sight of an agent, and an agent cannot
  fall back to itself — either would be a turn that never ran out of places to go.
- **Fork.** One agent has one place to go. Writing a step again says the new thing and not both.
- **Rescue a turn that failed for a reason another try cannot fix.** A prompt longer than the
  context window is that long on the next agent too. Those are `Unrecoverable`, and are
  [taken once](/reference/agents#when-an-account-goes-down) whatever any chain says.

## See also

- [Providers](/guide/providers) — the accounts an agent runs as, and the chain between them
- [Unattended runs](/guide/unattended) — where having somewhere to fall back to earns its keep
- [TUI › `/fallback`](/reference/tui#where-a-turn-goes-when-it-cannot-be-taken)
