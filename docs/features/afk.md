# Being away — `/afk`

An agent may stop mid-turn to ask you something. `/afk` is where you say there is nobody to ask.

An agent that wants to ask, with `/afk` on, is told **nobody answered** and carries on — rather
than waiting on a reply that is not coming.

## What it is not

`/afk` governs whether an agent may ask you a **question**. It does not govern whether an agent
may **act**: humanize runs every agent with permission prompts disabled, and there is no setting
that turns them back on. See [Security](/guide/security) and
[Permissions](/features/permissions).

## At the prompt

```
/afk            flips it
/afk on         you are not here
/afk off        you are
```

Asking starts **allowed**. An agent that really needs a person gets one unless it has been said
that none is there.

While a question is up, the status line says `enter answer`, and the next line you type is the
answer rather than a word put into the turn. What the agent offered is shown with it; an answer
is not held to those options — every backend that offers them takes something else too.

A question still up when the flow ends or is stopped ends with it, so stopping a flow is never
blocked on one.

## On a command line

There is nothing to switch. `hmz exec` has nobody at a prompt, so it behaves as `/afk on`
always: an agent that asks is told nobody answered and carries on.

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
```

This is the whole reason the setting exists. A nine-hour unattended loop that blocked forever on
`Which approach would you prefer?` is a run that did nothing.

## From Python

`agent.ask` is the hook. Set it and questions reach you; leave it unset and the backend is told
nobody answered:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

```python
agent.ask = None          # /afk on, in other words
```

A `Question` has `text` and `options`. Whatever happens, the question also reaches anything
[watching](/reference/agents#watching-a-turn-as-it-happens) the agent, as an `asks` event — so a
flow can log that its agent wanted to ask without answering it.

## When to turn it on

- Overnight, or over a weekend.
- Any run started from a script, a cron entry or CI — though there it is already the case.
- When you are watching the transcript but do not want to be interrupted; the agent gets on with
  it and you read what it decided afterwards.

## When to leave it off

- The [`chat`](/reference/flows#the-flows-humanize-ships) flow, where a question is the point.
- A flow that drives [the person as an agent](/features/human-agent) — that side of it is you,
  and `/afk` makes it answer nothing, which ends the conversation.
- Any flow that asks you for [an answer in a shape](/features/shapes): a questionnaire nobody
  filled in comes back as `None`.

## See also

- [Questions](/features/questions) — what an agent asking actually looks like
- [The person as an agent](/features/human-agent)
- [TUI › Questions, and being away](/reference/tui#questions-and-being-away)
