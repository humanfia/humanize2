---
pageClass: hmz-feature
---

# Ten CLIs, one agent

humanize never talks to a model provider. It drives the coding agent CLI you already have,
logged in the way you already log in — ten of them, plus anything that speaks the Agent Client
Protocol. There is no API key for it to hold.

The one exception ships inside it: DeepSeek Harness arrives with humanize, because it has no
subscription login to use instead.

<HmzBackends />

## An agent is four things

A backend, a model, an effort, and the [account](/features/accounts) its turns run as. Two
agents of one spelling are two agents, so a flow of an actor and a reviewer at one
configuration is what it says it is.

## What it runs is asked, never written down

A model id is not a fact that keeps. These CLIs ship models without asking anybody, and which
of them your account may name is your account's business — so a list written down here would be
wrong the day the CLI ships one, and would say nothing about what you may actually run.

So the backend itself is asked, by whatever mechanism that backend offers for being asked, and
what it says is kept:

- **Asked as the account whose it would be** — under that account's own credential paths and
  variables, and without the ones its backend would otherwise take an account from. Which is
  exactly how a turn of that account is run. Two accounts of one CLI are two catalogues.
- **Kept with the account**, so taking the account away takes its catalogue with it.
- **Never asked at a prompt.** Asking is a coding agent starting up, which costs seconds a
  prompt does not have; reading what was kept costs one file read.
- **An account is asked as soon as it is made**, that being the first moment there is anything
  to ask. A backend that would not answer leaves the account made — an account whose models are
  not known yet is one to ask again, not one that failed.

Claude Code's subscription picker hides the `fable` alias even when the account can run it.
For subscription accounts, humanize uses Claude's official `ANTHROPIC_CUSTOM_MODEL_OPTION`
hook while asking for the catalogue, and keeps the `fable` alias so a turn can pass it through
as `--model fable`. Key, gateway and cloud accounts are left to their own catalogue.

## The efforts are a vocabulary, so they are written down

An effort is the backend's own word for how hard to think, and a ladder keeps in a way a
catalogue does not: `xhigh` means the same thing next release. So the ladders are written down,
hardest first, and a model narrows its backend's ladder to the rungs that model takes — in the
ladder's own order, and to the whole of it where the backend said nothing about that model.

Two of them are worth knowing about:

- **A rung a backend takes but does not document is written down as one.** Claude Code's
  `ultracode` is `xhigh` with the turn opted into orchestrating a fleet of its own. No listing
  the CLI answers with will ever name it, so a model asked about would otherwise lose it.
- **Width is not depth.** Kimi Code's `max` is one agent and `swarmmax` is the same thinking at
  the width of a fleet — a second thing to say about a turn rather than a harder version of the
  first, so it is chosen beside the effort rather than among the rungs.

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

- [Efforts](/guide/efforts) · [Permissions](/guide/permissions) · [Skills](/guide/skills)
- [Providers reference](/reference/providers) — adding a CLI, and every way into each one
- [Agents reference](/reference/agents) — turns, sessions, and what each backend can do
