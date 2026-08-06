# Being away — `/afk`

`/afk` tells humanize that nobody is there to answer an agent's questions. Turn it on for long
or unattended runs, so an agent that asks is told **nobody answered** and carries on instead of
waiting for a reply that will not come.

## Try it

At the prompt, type:

```
/afk on
```

Now an agent that asks is told nobody answered and carries on. Type `/afk off` to take
questions again.

## What it is not

`/afk` controls whether an agent may ask you a **question**. It does not control whether an
agent may **act**. humanize runs every agent with permission prompts disabled, and no setting
turns them back on. See [Security](/guide/security) and [Permissions](/guide/permissions).

## At the prompt

```
/afk            flips it
/afk on         you are not here
/afk off        you are
```

Asking starts **allowed**. An agent that really needs a person gets one, unless you have said
that nobody is there.

While a question is up, the status line shows `enter answer`. The next line you type becomes
the answer, rather than a word in the turn. The agent's offer appears with it, but an answer is
not limited to those options — every backend that offers them also takes something else.

A question still up when the flow ends or is stopped ends with it, so stopping a flow is never
blocked on a question.

## On a command line

You do not switch anything. `hmz exec` has nobody at a prompt, so it always behaves as `/afk
on`. An agent that asks is told nobody answered and carries on.

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
```

This is the whole reason the setting exists. A nine-hour unattended loop that blocked forever
on `Which approach would you prefer?` is a run that did nothing.

## From Python

`agent.ask` is the hook. Set it and questions reach you. Leave it unset and the backend is told
nobody answered:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

```python
agent.ask = None          # /afk on, in other words
```

A `Question` has `text` and `options`. Either way, the question also reaches anything
[watching](/reference/agents#watching-a-turn-as-it-happens) the agent, as an `asks` event. A
flow can therefore log that its agent wanted to ask, without answering it.

## When to turn it on

- Overnight, or over a weekend.
- Any run started from a script, a cron entry or CI — there it is already the case.
- When you are watching the transcript but do not want to be interrupted. The agent gets on
  with it, and you read what it decided afterwards.

## When to leave it off

- The [`chat`](/reference/flows#the-flows-humanize-ships) flow, where a question is the point.
- A flow that drives [the person as an agent](/guide/human-agent). That side of it is you, and
  `/afk` makes it answer nothing, which ends the conversation.
- Any flow that asks you for [an answer in a shape](/guide/shapes). A questionnaire nobody
  filled in comes back as `None`.

## See also

- [Questions](/guide/questions) — what an agent asking actually looks like
- [The person as an agent](/guide/human-agent)
- [TUI › Questions, and being away](/reference/tui#questions-and-being-away)
