---
pageClass: hmz-feature
---

# Many backends, one agent

Most humanize backends do not talk to a model provider. They drive a supported coding agent
under its existing login, through a built-in adapter or the Agent Client Protocol. humanize
does not need the provider's API key for those backends.

The exception ships inside it: DeepSeek Harness arrives as an SDK-backed agent and uses its
own DeepSeek provider credentials because it has no subscription login to reuse.

<HmzBackends />

## An agent is four things

A backend, a model, an effort, and the [account](/features/accounts) its turns run as. Two
agents of one spelling are two agents, so a flow of an actor and a reviewer at one
configuration is what it says it is.

## What it runs is discovered for the account

A model id is not usually a fact that keeps. Coding agents add models, and which of them an
account may name is the account's business. Wherever a backend can report its catalogue,
humanize asks it under that account and keeps the answer:

- **It is asked as the account whose it would be** — under that account's own credential paths and
  variables, and without the ones its backend would otherwise take an account from. Which is
  exactly how a turn of that account is run. Two accounts of one CLI are two catalogues.
- **Kept with the account**, so taking the account away takes its catalogue with it.
- **Never asked at a prompt.** Asking is a coding agent starting up, which costs seconds a
  prompt does not have; reading what was kept costs one file read.
- **An account is asked as soon as it is made**, that being the first moment there is anything
  to ask. A backend that would not answer leaves the account made — an account whose models are
  not known yet is one to ask again, not one that failed.

DeepSeek Harness and Qwen Code cannot list their models dynamically. Their adapters provide
small advisory catalogues instead: the official DeepSeek adapter's current models, and the
models Qwen Code ships pointed at. Those lists make initial setup possible; they are not proof
of what an account or compatible endpoint will accept.

For a discovered catalogue, nothing is added to what the backend answered. Claude Code may
report a custom alias without proving the account can run it, so humanize preserves the alias
exactly as that account supplied it rather than silently manufacturing another model entry.

## The efforts are a vocabulary, so they are written down

An effort is the backend's own word for how hard to think, and a ladder keeps in a way a
catalogue does not: `xhigh` means the same thing next release. So the ladders are written down,
hardest first, and a model narrows its backend's ladder to the rungs that model takes — in the
ladder's own order, and to the whole of it where the backend said nothing about that model.

Three of them are worth knowing about:

- **A rung a backend takes but does not document is written down as one.** Claude Code's
  `ultracode` is `xhigh` with the turn opted into orchestrating a fleet of its own. No listing
  the CLI answers with will ever name it, so a model asked about would otherwise lose it.
- **Width is not depth.** Kimi Code's `max` is one agent and `swarmmax` is the same thinking at
  the width of a fleet — a second thing to say about a turn rather than a harder version of the
  first, so it is chosen beside the effort rather than among the rungs.
- **One ladder can hold two vocabularies.** ZCode's models do not agree on what an effort is:
  the ones that take a thinking budget answer `max`, `high`, `low` and `nothink`, and the ones
  that only take thinking-or-not answer `enabled` and `disabled`. Both are rungs of the one
  ladder, and a model narrows it to the half that model speaks.

## Driven through whatever each one actually offers

A backend is driven through its command line where that can express what an agent is configured
with, and through the app server it serves its own client from where it cannot. A model, an
effort, a mode or a goal that has no flag is a setting of a session there — and asking the
model for it in the prompt is not the same feature.

A turn that has to stay open to be [talked to](/features/steering) is such a case: a command
line run per turn has ended by the time there is anything to say to it.

Where a server is needed it is started at most once per agent, only when a turn first needs
one, so a flow that needs none starts none. One server serves every session of its agent, so
calls on it are serialized: two turns interleaved on one stream would each take the other's
answers.

## Skills are read where that CLI reads them

Nothing is asked of the CLI. Starting one costs seconds, so the skills are found where that CLI
looks for them — its own home, the shared directory more than one of them has agreed to read,
the project's own — and each is named as the CLI names it.

**This is a reading and nothing else.** What you installed is yours: humanize does not rewrite,
override or switch off any of it, and offers no way to. What a *flow* brings is different — its
own skills are mounted into the directory that backend reads for the length of a session, and
taken away with it. A backend that reads none is a turn run without them rather than a run that
will not start.

## Adding a CLI of your own

Anything speaking the Agent Client Protocol is a backend from the moment it is written down: a
name and the command that starts it. The protocol says nothing about which models such an agent
runs or how hard it may be asked to think — both are the agent's own — so one rung is offered
and none is sent.

## Where the detail is

- [Efforts](/user/efforts) · [Permissions](/user/permissions) · [Skills](/user/skills)
- [Providers reference](/reference/providers) — adding a CLI, and every way into each one
- [Agents reference](/reference/agents) — turns, sessions, and what each backend can do
