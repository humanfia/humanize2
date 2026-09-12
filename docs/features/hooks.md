---
pageClass: hmz-feature
---

# The moments of a turn

A coding agent has hooks of its own: a table of shell commands to run before a tool, after a
prompt, when a turn stops. They live in a settings file, written before anything starts and
read by the backend rather than by whatever is driving it.

humanize holds the same moments here instead. A hook is **Python a weaver hangs on a moment** —
hung on a live agent, and taken down again, while it runs. A flow says what to do at a moment
in the language it is written in, and says it to the agent it is holding rather than to a file
somewhere under a home directory.

<HmzMoments />

## Named as the agents name them

`PreToolUse` here is `PreToolUse` there, so a flow written against one backend reads against
the others and against their own documentation.

Not every backend reaches every moment. Three differ: the one about a permission being asked
for, which only the backends that wait to be told have, and the two about a **fleet** — the
agents an agent starts of its own, Claude's `Task`, Codex's collab agent, Cursor's task tool —
which only the backends that say so on the stream a turn is read from have. So an agent says
which moments it runs, and a flow says which it needs where it declares its agents.

The two about a fleet are told rather than answered: no backend here waits to be told whether
it may start one, so a refusal would be a verdict that goes nowhere. What they carry is what
that agent is called, what it was asked to do, and the backend's own id for it — which is what
pairs the one that started with the one that came back.

## What a hook is told

One shape for every moment, and a hook reads the fields its moment fills. A tool hook reads
what was reached for and with what; a stop hook reads what the agent said last, and how many
times this turn has already been sent on. The rest are empty rather than absent, so a hook hung
on two moments is not two hooks.

## What it may say back

Nothing at all, usually. Otherwise one of two things:

- **refused** — what was about to happen may not. A refusal carries what to say about it, which
  is what the agent is told; at the moment a turn ends, that is what the agent is sent on to
  *do*, so a refusal with nothing to say is not one.
- **adds** — something to add to what the agent was about to be told.

Everything hung on one moment is asked, and the answers come back as one verdict: refused if
any of them refused, with the first reason there was, and adding everything any of them added,
in the order they were hung.

## Refusing a tool, and where the refusal lands

`PreToolUse` is the moment a flow most wants to refuse, and it is the one that cannot be read
off the stream a turn is read from: a CLI says what it reached for and *then* reaches for it, so
a refusal read there would be describing a tool that had already run.

So on the backends whose CLI takes a hook table meant for a single run — Claude Code among them
— humanize puts the moment in that table instead, pointed at a relay that carries it straight
back to the hooks hung on the agent. The CLI stops and waits for the answer, and a refusal means
the tool **does not run**:

```python
def no_shell(occasion: Occasion) -> Verdict | None:
    if occasion.tool == "Bash":
        return Verdict(refused=True, because="this flow does not shell out")
    return None

with agent.hooks.on(Moment.PRE_TOOL_USE, no_shell):
    agent(task)
```

Nothing of your own configuration is read, written or replaced to do it. The table reaches the
CLI on its own command line, or through a settings file this run alone is pointed at, for the
length of the run — your own hooks stay yours, and a flow that ends leaves the machine as it
found it.

On a backend with no such seam, and on a turn whose work lands on [another
machine](/features/anchor) — where the relay is not — the moment is still told to every hook
hung on it, and a refusal there is a flow watching a tool rather than stopping one.

## Hung on the agent, not on the session

A hook hung on an agent is on every conversation that agent holds — and hanging one is
something a weaver does to a flow that is **already running**, which is the whole point of
these being callables rather than a file.

A hook hung on a moment the agent does not run is refused **where it is hung**, rather than
hours into a loop. A hook that quietly never runs is a flow that quietly does not do what it
says.

## A hook is a word in the turn, not a note about it

It is called on the thread the turn is running on — or, for the moment the CLI itself asks
about, on the thread serving that question, which is the CLI's own turn waiting at the other
end of a socket. Either way, whatever called it waits. A hook that takes a while is a turn that
takes a while — which is what lets it decide something, and also what makes a slow one
expensive.

One agent's hooks run **one at a time** whichever way they arrive, so a CLI that reaches for
three tools at once still puts them to your hook one after another.

A hook that raises has **said nothing**, the way a watcher that raises has: a flow must not
fail because something hung off it did. The one exception is a run ended by hand, which is
allowed out of the turn — swallowing that would let the turn end quietly and the flow report
that it finished.

## What this is enough to build

- a permission rung of your own, on top of the four there are
- a house rule added to every prompt, without touching anybody's settings file
- a [goal written by hand](/features/goals): a refused stop, decided by code
- a watcher that writes down what the agent reached for, alongside the
  [trace](/features/tracing)

## Where the detail is

- [Hooks](/weaver/hooks) — hanging one, and each moment's fields
- [It decides when it is done](/features/goals) — the refused stop, and what it costs
- [Agents reference](/reference/agents#hooks)
