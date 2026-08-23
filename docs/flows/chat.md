---
pageClass: hmz-feature
---

# chat

One agent, one session, and every line typed between turns is a turn of it — a coding agent
with no loop around it, doing what it is told and then waiting to be told again. It is what the
terminal interface opens on, so that saying something is all it takes to start.

```sh
hmz exec -f chat -a claude/claude-opus-5:high "what does this repository do?"
```

<HmzFlowShape flow="chat" />

## Two agents, and the second is you

`chat` drives an assistant and a [person](/features/human). Saying something to the person is
asking what to say next, and what they answer with is what they typed:

```python
conversation = agents.assistant.new()
said = task
opening = True
while said:
    answered = conversation(said, suppress=not opening)
    opening = False
    said = agents.human(answered)
```

Which is why the same flow works with nobody at a prompt: the person answers with nothing, the
loop ends, and `chat` has done the one thing it was given. `/afk` and a shell script are the
same thing to it, and that is deliberate.

**The first turn is the one that fails out loud.** A conversation that could not be started at
all — an account the backend refused, a model it will not run for that account — ends the run
with what the backend said about it. Suppressed, it would answer with nothing, which the loop
above reads as a conversation that is over, and the run would exit as though it had done what
it was asked. Every turn after the first is forgiving: by then there is a conversation to carry
on.

A line typed **while a turn is running** goes into that turn rather than becoming another one —
true under any flow, and [Steering](/features/steering) is how.

## What it keeps

Nothing. What was said is the conversation, logged turn by turn by the backend that ran it, and
a session is opened rather than reopened — so starting this again is another conversation
rather than the last one carried on. To read one back, [collect the trace](/user/tracing) or
[export the transcript](/user/export).

## See also

- [Many conversations at once](/user/conversations) — the interface holds several of these
- [The person as an agent](/weaver/human-agent) — what `agents.human` is, and what it does unattended
- [ralph_loop](/flows/ralph-loop) — the same one agent, with a loop around it
