---
pageClass: hmz-feature
---

# You, as one of the agents

A flow can drive the person at the prompt the way it drives a model: ask them something, wait
for the answer, and carry on. Given a [shape](/features/shapes), it asks them a question per
field and builds the model out of what they typed.

<HmzPerson />

## The person is handed over, not chosen

They are made by whatever is driving the flow rather than by the flow, and they are not among
the agents a flow is configured with — nobody chooses what the person runs. A flow that talks
to a person is a flow with one fewer agent to pick.

Their turn is also not a turn of a model, and is not bracketed by the events that say whose
turn it is. The person takes no turn of a model, and counting it would put them in the graph of
who handed to whom and spin a clock at them while they thought.

## A schema is not a question

Shown a JSON Schema, a person is being asked to be a parser. So they are asked a question per
field instead, and the field is what makes the question:

| In the model | What they are asked |
| --- | --- |
| the line the field was declared with | the question itself, or the field's name where it has none |
| a fixed few possibilities | those words, as the answers it offers |
| a true-or-false | yes and no |
| a default | "or a dash for that" — and a dash takes it |
| a list | one line, separated by commas |

**What the model refuses is put back on the field it was refused for, in the model's own
words.** The flow that declared the field is the only thing that knows what it will take, so
its refusal is the only wording worth showing. It is put back a bounded number of times: a
person who keeps typing something the model will not accept ends the questionnaire rather than
living in it.

Each of those questions goes the road [a coding agent's own question](/guide/questions) goes,
so it is a real question wherever the run is being watched, options and all.

## Nobody there is an answer

A flow run from a command line, or an interface told its user is away, answers with nothing —
and the backend is *told* that rather than left waiting. A turn waiting on an answer that is
not coming is a flow that has stopped.

So the flow gets nothing back, under the same suppression it would use for a turn that failed,
and takes the same branch it takes for [an answer that was not the shape it asked
for](/features/shapes). One branch, three reasons to take it.

## Which is why it is one feature and not two

An agent stopping mid-turn to ask its user something and a flow asking a person something are
the same road. Both are answered by whoever is at the prompt or by the flow; both say what was
asked to whatever is watching the agent, since the one place a run is visible is the turns
going past; and both are answered with nothing where nobody is there.

The difference is only that a flow states the shape of the whole answer once, in the model it
is about to use.

## Where the detail is

- [The person as an agent](/guide/human-agent) — driving one from a flow
- [Questions](/guide/questions) — an agent asking its user
- [Being away](/guide/afk) — deciding what happens when nobody is at the prompt
