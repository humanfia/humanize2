---
pageClass: hmz-feature
---

# It decides when it is done

A session can be given a **goal** instead of a prompt. The agent decides for itself whether the
objective has been met, and until it decides that it has, a turn that would have ended starts
another.

This is the backend's own goal feature — the one its own goal command reaches — and not a
prompt that asks for one. The extra turns are started by the backend, and humanize follows the
goal across all of them.

<HmzGoal />

## What "until it says so" means

A goal takes as many turns of the model as the objective takes. What comes back is the last of
them.

A session that has gone quiet is not the same as a goal that has stopped: the goal has stopped
only once the goal itself says so. That is why a flow looping over a goal runs the objective
again rather than nudging an agent that stopped early — it is starting a new goal, not
continuing one.

## Asked for before the first turn, not an hour in

A flow built on a goal says so where it declares its agents, and an agent whose backend has
none is refused before anything runs. Where agents are chosen at the prompt, only the CLIs that
have one are offered — so there is no wrong choice to make.

On a backend without one, asking for a goal raises rather than quietly running the objective as
an ordinary turn, and suppression does not catch it: a missing feature is a flow to correct,
not a turn to retry.

## Turning it off

Goals are on or off per agent, explicitly, with no third state and nothing inherited. A flow
may suggest the initial value where it declares a place, but the value is resolved before the
agent is built and the flow does not change it afterwards.

An agent with goals off is one whose flow owns every continuation. Beyond refusing the goal
itself, humanize refuses the tools that would carry work past the turn it is holding — the
backend's own switch where it has one, and a refusal before the CLI is invoked where it has
none. Everything else the agent may reach for is what its [permission](/user/permissions) rung
says it may, exactly as before, and neither path touches your global configuration of that
backend.

## The same shape, written by hand

A goal written by hand is a refused `Stop` [hook](/features/hooks): the turn is not over until
the hook lets it be, and the hook is told how many times it has already sent this turn on, so
one that keeps refusing can decide to stop.

The difference is who judges, and what it costs:

| | Decides it is done | Costs |
| --- | --- | --- |
| a goal | the **model**, against the objective in its own words | turns you did not ask for, until it says so |
| a refused stop | **your code**, against whatever it can read | one extra turn per refusal, bounded by the count it is given |

Reach for the first when the stopping condition is something the model should judge, and the
second when it is something a Python function can check — an unticked box in a file, a test
that still fails, a diff that still touches the wrong directory.

## Where the detail is

- [Goals](/weaver/goals) — the calls, the marker, and which backends have one
- [The moments of a turn](/features/hooks) — the refused stop, in full
- [Agents reference](/reference/agents#goals)
