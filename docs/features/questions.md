# Questions

An agent may stop mid-turn to ask its user something — which approach, which file, is this what
you meant.

## At the prompt

The question and whatever it offered are shown. The next line you type is **the answer** rather
than a word put into the turn, and the status line says `enter answer` while that is so.

An answer is not held to the options. Every backend that offers them takes something else too —
they are what the agent expects, and what an interface has to show for the question to read as
one.

A question still up when the flow ends or is stopped ends with it, so stopping a flow is never
blocked on one.

## When nobody is there

`hmz exec` has nobody at a prompt, and [`/afk`](/features/afk) says so deliberately. In both
cases the backend is told **nobody answered** and the agent carries on.

A turn waiting on an answer that is not coming is a flow that has stopped, so this is the
default everywhere except an interface with `/afk` off.

## From Python

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

```python
@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[str, ...]
```

Return a string to answer, or `None` for "nobody answered". Leave `ask` unset and it is `None`
every time.

Whatever happens, the question also reaches anything
[watching](/reference/agents#watching-a-turn-as-it-happens) the agent, as an `asks` event — so a
flow can record that its agent wanted to ask without answering it:

```python
def looking(agent, session, event):
    if event.kind == "asks":
        Path("questions.log").open("a").write(f"{agent.id}: {event.text}\n")

agent.watch(looking)
```

The session on an `asks` event is `None`, whichever backend asked: a question is the agent's
rather than one conversation's — `ask` is set on the agent, and it is the agent a stopped turn
reaches. So a watcher can say which agent wanted to ask, as the one above does, but not which
of its conversations did.

## The other direction: a flow asking you

The reverse — the *flow* asking the person — is [the person as an agent](/features/human-agent):

```python
said = agents.human("Here is what I did. What next?")
```

And with a [schema](/features/shapes), it is a questionnaire: a question per field, and the model
built out of what they typed.

```python
settled = agents.human("How should I do this?", schema=Settled, suppress=True)
```

Each of those goes the same road a coding agent's own question takes, so `/afk` answers it the
same way: nobody is there.

## The moment, for a hook

`NOTIFICATION` is the [moment](/features/hooks) that fires when the agent has stopped to ask its
user something. A hook on it cannot answer — a verdict does nothing there — but it can log,
notify, or wake something up:

```python
agent.hooks.on(Moment.NOTIFICATION, lambda occasion: ring_a_bell(occasion.said))
```

## See also

- [Being away](/features/afk)
- [Answers in a shape](/features/shapes)
- [The person as an agent](/features/human-agent)
