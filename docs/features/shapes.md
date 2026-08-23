---
pageClass: hmz-feature
---

# Answers in a shape

A turn given a pydantic model answers with **that model** instead of with prose. A flow then
reads a field — `done`, `notes`, `approach` — rather than searching a paragraph for a phrase
and hoping the wording holds next time.

<HmzShape />

## The model is the question

The model is the whole of what the backend is asked. Its fields, their types, which of them are
required, and the line each was declared with are already in it, so nothing about the shape is
said twice in the prompt.

That also means the schema is **not** in what the hooks and the watchers are shown. What they
see is the flow's own words: a schema in the transcript is the plumbing showing through.

And it is asked afresh for every turn of the model a call takes. A [hook](/features/hooks) that
sends the agent on says what to say next, and a shape that was only on the first prompt is one
the last turn was never asked for.

## Two roads, one answer

A backend with a setting for this is held to it there — a flag of its command line, a setting
of the turn. A backend with none is asked in the prompt instead. Each backend records which of
the two it is, so a flow never has to know.

**Either way the answer is read back through the model.** The road only decides who refuses a
bad answer first.

## An answer that is not the shape is a turn that did not do what it was told

However cleanly the backend exited. So a turn asked for a shape that came back as something
else is caught the way a failed turn is caught: it answers with nothing rather than with an
empty string, and without suppression it raises.

The branch a flow writes for that is "take this round again", and it is almost always the right
one — the same branch it writes for [a person who was not there](/features/human).

## Why a loop wants one

A flow that has to decide something is a flow that has to read an answer. Is this finished?
Does this plan belong to this repository? Which of these two ways should it be built?

- **Booleans decide**, and steer the loop.
- **Strings carry**, and become the next prompt word for word.
- **A model with thirty fields is a form**, and a turn that fills in a form is a turn that did
  not do the work. Two or three fields is usually the whole of a decision.

## The same decision, put to a person

Given a shape, [the person at the prompt](/features/human) is not shown a JSON Schema. They are
asked a question per field — the description is the question, a `Literal` becomes the words it
offers, a `bool` becomes yes and no — and the model is built out of what they typed.

Which is the point of stating the shape once, in the model the flow is going to use: the same
decision goes to a model or to a person, in the same shape, with the same branch for an answer
that never came.

## One more thing a shape moves

On a backend that takes the schema as an argument of the process rather than of the turn,
asking a session for a shape it was not started with ends that process and starts one that
**resumes** the conversation. The conversation is not restarted; only the process is. It is the
same thing [moving an effort](/user/efforts) does.

## Where the detail is

- [Answers in a shape](/weaver/shapes) — writing the model, and the failing branch
- [Agents reference](/reference/agents#answering-in-a-shape) — every call that takes one
- [You, as one of the agents](/features/human) — the same shape, asked of a person
