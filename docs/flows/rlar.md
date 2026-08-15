---
pageClass: hmz-feature
---

# official/rlar

An actor works in one session and a fresh reviewer reads its work. The actor must remember and
the reviewer must not — and the review **is** the actor's next prompt, word for word, so what
the reviewer noticed is what the actor hears.

```sh
hmz exec -f official/rlar \
    -a claude/claude-opus-5:high -a claude/claude-opus-5:high "$(cat TASK.md)"
```

<HmzFlowShape flow="rlar" />

## The reviewer answers two things at once

Both are read off the [shape](/features/shapes) the reviewer is held to rather than off a
marker at the end of a paragraph, so a review that says the work is done and a review that says
the words "it is done" are not the same thing:

```python
class Review(BaseModel):
    done: bool   # True only if everything asked for is implemented, works, and nothing was faked
    notes: str   # the review itself, written as a message to the coding agent
```

`notes` becomes the actor's next prompt verbatim. `done` is what ends the run — this is the one
flow here whose stopping condition is a judgement rather than a budget.

The reviewer's prompt tells it to be skeptical, and to treat reward hacking — tests weakened or
special-cased, work stubbed out or faked — as the thing it is most there to catch. How to read
a round of work against the repository it landed in, and how to write the review the actor is
then handed, is the flow's own skill: `skills/review-notes`, mounted onto every session either
agent opens. A fork of this flow that wants its reviews written differently edits that file and
runs. See [Skills](/guide/skills).

## Give the two the same model, if you like

They are still two agents. The actor holds one session across the rounds; every review is a
session that has just started, reads the repository itself, and is told nothing about how the
work was arrived at. That asymmetry is the flow.

## What it keeps

`rounds`, and `notes` — the one review nobody has acted on.

The review is kept word for word, and this is the only place in these flows where an agent's
own prose is written into a file that outlives the run. It earns that: it is what the next
round is owed, the reviewer wrote it as the actor's next prompt, it was never answered, and
nothing can write it again.

The actor's session is not picked up with it. So a picked-up round opens on **both** — the task,
because the actor has never been told it, and under it the review, marked as an earlier round's
reading of work this session did not do. Marked that way because it may not even be this task's:
humanize keeps one state per flow per workspace, and neither this flow nor humanize knows what
the run that left it was started on.

A run the reviewer agreed with keeps nothing at all. What is over is not carried on.

## See also

- [Answers in a shape](/features/shapes) — how the reviewer is held to that model
- [official/flame_chase](/flows/flame-chase) — two agents both working, rather than one reviewing
- [official/humanize1](/flows/humanize1) — the same idea, with the review hung on a hook
