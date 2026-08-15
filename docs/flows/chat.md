---
pageClass: hmz-feature
---

# chat

One agent, one session, and every line typed between turns is a turn of it. This is talking to
a coding agent with no loop around it: the flow does what it is told and then waits to be told
again. It is what the terminal interface opens on, so that saying something is all it takes to
start.

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
while said:
    answered = conversation(said, suppress=True)
    said = agents.human(answered)
```

Which is why the same flow works with nobody at a prompt. Run from a command line the person
answers with nothing, the loop ends, and `chat` has done the one thing it was given. `/afk` and
a shell script are the same thing to it, and that is deliberate.

A line typed **while a turn is running** goes into that turn rather than becoming another one —
that is true under any flow, and [Steering](/features/steering) is how.

## What it keeps

Nothing. What was said is the conversation, and the backend that ran it logged it turn by turn.
A session is opened rather than reopened, so starting this again is another conversation rather
than the last one carried on. To read one back, [collect the trace](/guide/tracing) or
[export the transcript](/guide/export).

## See also

- [Many conversations at once](/guide/conversations) — `chat` is one of them; the interface holds several
- [The person as an agent](/guide/human-agent) — what `agents.human` is, and what it does unattended
- [ralph_loop](/flows/ralph-loop) — the same one agent, with a loop around it
