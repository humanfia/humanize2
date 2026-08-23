---
pageClass: hmz-feature
---

# Two accounts of one CLI

A coding agent CLI signs in once. Every copy of it started on this machine is whoever is signed
in there — which is fine until a flow drives two agents of one CLI as two accounts, and the two
want the same directory.

humanize gives the second one a directory of its own, and then makes the CLI open it without
telling the CLI anything. The same technique the [anchor](/features/anchor) runs a whole
session under, aimed at four or five paths instead of a workspace.

<HmzAccounts />

## An account is a directory, written by the CLI itself

One account is one directory, holding what it was made by and what a turn under it runs with —
and, beside those, the files the CLI wrote when it signed in, under the names that CLI gave
them. It is the CLI that wrote them and the CLI that will read them back.

Nothing here reimplements a login. A login is a browser opened, a code read out, a token
exchanged and refreshed on a schedule nobody else knows, so the CLI's own login is what is run:
its own command, on this terminal, under the account's paths. What it writes when it succeeds
*is* the account.

**Only the credentials are answered.** The sessions, the settings and the skills are the ones
the CLI already has, so a turn under an account still leaves a [trace](/features/tracing),
still counts what it spends, and still loads what you installed.

## Three shapes, and why the third one matters

A redirect answers the file itself, everything under it where it names a directory, and
anything beside it under the same name and another suffix.

That third one is not a nicety. These CLIs rotate a token by writing a `.tmp` file and renaming
it over the old one — so a temp file left unanswered writes the *new* token into the store you
were redirecting away from, and the account you were not using quietly becomes the one that
works.

Two rules hold the rest of it up, because a turn taken as the wrong account is worse than a
turn that did not run:

- **A path that is answered but cannot be rewritten fails the call** rather than running
  against the path it named.
- **A run that cannot be supervised at all is refused** rather than run unsupervised.

An account that is only variables costs no supervisor at all — the backend's own command line
runs unchanged. And two supervisors cannot be nested, since a process has one tracer, so a turn
that is also [anchored](/features/anchor) hands its redirects to the anchor instead of wrapping
it.

## The environment is part of the account

A CLI reads a key, a token or an endpoint out of the environment, and it does not care whether
you exported it or an account did. An `ANTHROPIC_API_KEY` left in somebody's shell profile
outranks the credentials file the account was signed into — and nothing about that reads as
wrong until the bill arrives.

So every variable a backend would take an account from is written down, and a turn under an
account runs with all of them unset unless that account set them.

## The same credential, under everybody else's name for it

A vendor's key is the vendor's rather than the CLI's. An Anthropic key is an Anthropic key
whether Claude Code, pi, opencode, mimocode or ZCode is holding it, and
`CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_OAUTH_TOKEN` are one subscription under two names.

So an account made for one backend is an account several others could be run as, and copying it
spells it the way the other backend reads it. What cannot travel is an account that is not
variables at all: a subscription signed into writes the CLI's own credential store, in that
CLI's own format, and nothing else reads it.

## When an account goes down

Where a turn goes next is said on the **account**, not on the agent: it is the account that
fails, and whichever agent was running under it is the one that needs somewhere else to run.
Each account names the next, so what a turn walks is a chain — a subscription that runs out
falling to a key, and a key that is refused falling to a gateway.

- **The chain is walked inside the session that was running.** The conversation is the
  backend's own and is named by an id, so it carries on under the next account rather than
  coming back to the flow as a failure.
- **An agent that has moved stays moved.** The account that went down is not one to try again
  every turn.
- **A chain that comes round on itself ends at the second sight of an account**, and one naming
  an account that is not there ends there. Either would otherwise be a run that never stopped.
- **The machine's own account is the start of a chain and never the end of one.** An agent that
  is to try that account is an agent given no account, which is where its chain already begins.

## When there is no account left

Some failures no account answers. The model was retired this morning; the CLI will not start;
the region has gone dark; the rate limit is on the whole account rather than on one request.
Another key for the same backend is another way of asking the same thing that is not there.

What answers those is another **place** — another CLI, another account, another model — written
between the two places rather than on either, because it is about neither on its own: it is
what to do when *this* CLI, at *this* model, as *this* account, cannot run. How hard the agent
thinks and what it may reach for are what that agent *is*, and come across the step unchanged.

It is the second thing tried and not the first, and the reason is the conversation. No backend
takes another backend's session id, so a turn that leaves its backend leaves the conversation
and is taken in a new session on the other side. The account chain keeps the conversation and
is walked to its end first; this is what is left after that. The flow sees one turn either way.

## How it waits

Before either chain moves, the turn is taken again: how many times over, how long between
tries, and how long the whole of it may go on for. That is written against the **place** — the
CLI, the account and the model together — rather than against the credentials, because it and
where the turn goes next are answers to the one thing that happened.
[`/fallback`](/user/fallback) is where both are said.

- **Nothing is retried by default.** A turn is taken once, as it always was: a prompt the model
  refused is the same refusal every time, and only the caller knows which of its places fails
  the other way.
- **No wait is invented here.** They are the ones everybody uses, under the names everybody
  uses them by, and the default is exponential backoff with full jitter — which is what keeps a
  flow's agents from all coming back on the same second.
- **No single wait is longer than a minute**, however far the backoff has climbed.
- **The time a place was given is checked *before* a wait**, not after it, so a turn is never
  started knowing it is already spent.

## The account nobody made

The CLI as whoever is at this machine already runs it is an account here too, named by the
empty string. humanize did not make it, keeps no credentials for it, cannot sign it in and
cannot take it away — so the only thing written down about it is which account a turn under it
carries on under when it fails.

It answers no redirects and no variables, so a turn under it is exactly the turn an agent with
no account has always taken: nothing added to the environment, nothing taken out of it, no path
answered by another, and no supervisor at all.

## Where the detail is

- [Providers](/user/providers) — making one, signing it in, pointing it somewhere
- [Falling back](/user/fallback) — the chain, the second place, and the waits
- [Providers reference](/reference/providers) — every way in, every field, and adding a CLI
- [The anchor](/features/anchor) — the same interception, over a whole session
