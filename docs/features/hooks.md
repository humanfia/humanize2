---
pageClass: hmz-feature
---

# The moments of a turn

A coding agent has hooks of its own: a table of shell commands to run before a tool, after a
prompt, when a turn stops. They live in a settings file, written before anything starts and
read by the backend rather than by whatever is driving it.

humanize holds the same moments here instead. A hook is a **Python callable**, hung on a live
agent and taken down again while it runs — so a flow says what to do at a moment in the
language it is written in, and says it to the agent it is holding rather than to a file
somewhere under a home directory.

<HmzMoments />

## Named as the agents name them

`PreToolUse` here is `PreToolUse` there. A flow written against one backend reads against the
others and against their own documentation.

Not every backend reaches every moment — the one about a permission being asked for is the one
that differs — so an agent says which it runs, and a flow says which it needs where it declares
the agents it drives.

## What a hook is told

One shape for every moment, because a hook is written against a moment and reads the fields
that moment fills. A tool hook reads what was reached for and what it was reached for with; a
stop hook reads what the agent said last, and how many times this turn has already been sent
on. The rest are empty rather than absent, so a hook hung on two moments is not two hooks.

## What it may say back

Nothing at all, unless it says otherwise. Otherwise one of two things:

- **refused** — what was about to happen may not. The turn does not run, the tool does not run,
  the turn does not stop. A refusal carries what to say about it, which is what the agent is
  told; at the moment a turn ends, that is what the agent is sent on to *do*, so a refusal with
  nothing to say is not one.
- **adds** — something to add to what the agent was about to be told.

Everything hung on one moment is asked, and the answers come back as one verdict: refused if
any of them refused, with the first reason there was, and adding everything any of them added,
in the order they were hung.

## Hung on the agent, not on the session

So a hook hung on an agent is on every conversation that agent holds — and so that hanging one
is something you do to a flow that is **already running**, which is the whole point of these
being callables rather than a file.

A hook hung on a moment the agent does not run is refused **where it is hung**, rather than
hours into a loop. A hook that quietly never runs is a flow that quietly does not do what it
says.

## A hook is a word in the turn, not a note about it

It is called on the thread the turn is running on, and that thread waits for it. A hook that
takes a while is a turn that takes a while — which is what makes it able to decide something,
and also what makes a slow one expensive.

A hook that raises has **said nothing**, in the way a watcher that raises has: a flow must not
fail because something hung off it did. The one exception is a run ended by hand, which is
allowed out of the turn — a run stopped by a person has to read as stopped by a person, and
swallowing that would let the turn end quietly and the flow report that it finished.

## What this is enough to build

- a permission rung of your own, on top of the four there are
- a house rule added to every prompt, without touching anybody's settings file
- a [goal written by hand](/features/goals): a refused stop, decided by code
- a watcher that writes down what the agent reached for, alongside the
  [trace](/features/tracing)

## Where the detail is

- [Hooks](/guide/hooks) — hanging one, and each moment's fields
- [It decides when it is done](/features/goals) — the refused stop, and what it costs
- [Agents reference](/reference/agents#hooks)
