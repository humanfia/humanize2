# Providers

A **[provider](/reference/providers)** is one named set of credentials for one CLI, kept apart
from the CLI's own. Reach for one when two agents need to run the same CLI as two different
accounts at once. An agent with no provider runs its CLI exactly as you run it yourself.

A coding agent CLI signs in once. Claude Code keeps its account under `~/.claude`, so every
Claude Code on this machine runs as whoever is signed in there, and a flow that wants two of
them on two accounts has two accounts wanting one directory. A provider is the second
directory.

## Try it

Accounts are made at `/providers`, which is a page of the terminal interface: `hmz` in the
project, then `/providers` at the prompt.

1. **Make one from your existing subscription.** **a** asks which CLI — Claude Code here — and
   then how to sign in, which is that backend's own list of ways. Choose `login`, call the
   account `anthropic`, and `claude auth login` runs on this terminal with the paths pointed at
   that account's own directory. The CLI's own login owns the screen until it is done, and what
   it writes lands under `~/.humanize/providers/claude/anthropic/`.

2. **Make a second from somebody else's endpoint.** **a** again, Claude Code again, and this
   time `gateway`, which asks where the endpoint is and then for the token. A secret is drawn
   as bullets and never shown back.

3. **Read what you made.** One line each, under a heading per CLI: the account, the way it was
   made by, and the variables it sets. Names, never values.

![making an account at /providers: a, which backend, how that backend signs in, and what the
list says about the account afterwards](/demo/accounts.gif)

4. **Run one flow as both accounts at the same time.**

```sh
hmz exec -f official/flame_chase \
    -a claude@anthropic/claude-opus-5:max \
    -a claude@deepseek/deepseek-chat:high \
    "fix the build"
```

`flame_chase` hands the same task to two agents in turn, and both run the same Claude Code. The
first reads the subscription's tokens and refreshes them; the second dials the endpoint with
the token you typed. Neither can read the other's credential file, and neither can read yours.

## Naming one on an agent

An `@` after the CLI names the account an agent's turns run as:

```
claude@deepseek/claude-opus-5:max
```

It is the account and never the model, whatever comes after the slash. A CLI is never spelled
with an `@` in it, so the CLI and the account are told apart wherever an
agent is written. An `@` with nothing after it is refused: it was typed to name an account, and
running as whoever is at this machine is not that.

In Python the account is a field of the config:

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", provider="deepseek")
```

At the prompt it is the **account** row of the sheet an agent is set up on, which is the second
page of `/flow`. It sits under the `cli` row, because an account belongs
to one backend: what signs in to Claude Code is not what signs in to codex. Opening it lists
that CLI's own accounts with `as local` first:

```
   Select the account its turns run as

   ❯ 1. as local                  signed in as you signed it in
     2. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     3. work                      login

   a to make one · Enter to choose · Esc to cancel · s to search
```

`as local` is always the first row, and it is what every agent ran as before there were any
accounts. **a** makes one without leaving the question: the same walk `/providers` runs, minus
the question the `cli` row has already answered, coming back with the new account chosen.

## What moves, and what does not

**Only the credential files move.** Sessions, settings and skills stay in the CLI's own home. A
turn under a provider still shows up in a [trace](/user/tracing), still counts towards the
[cost readout](/user/tally), and still has the skills you installed.

```
~/.humanize/providers/claude/deepseek/
├── provider.json      what it was made by, and what a turn under it runs with
├── home/              the credential files the CLI keeps under its own home
│   ├── .credentials.json
│   └── .claude.json
├── user/              the ones it keeps outside it
│   └── .claude.json
└── config/            and the ones it keeps where every program keeps its configuration
    └── anthropic/
```

Files are `0600` in a directory at `0700`, and they keep the names the CLI gave them, because
the CLI writes them: a login run for a provider is the CLI's own login with those paths pointed
here.

**A credential is read out of memory and written to disk.** These CLIs ask about their token
hundreds of times in a single turn — pi asks about its `auth.json` six to eight hundred times —
and change it once in a while. So the file is copied once into memory when the turn first reads
it, and every read after that is answered there; a write goes straight to the file above, where
a refreshed token is durable the moment it lands, and the copy is dropped so the next read makes
a new one. The copy is the turn's own, at `0600` in a directory at `0700` that goes away when the
turn does.

**A turn under a provider is run with the other accounts' variables unset.** An
`ANTHROPIC_API_KEY` left in a shell profile is a key the CLI would rather have than the
credential file it was signed in with, and the turn would be taken as the wrong account with
nothing looking wrong. So every variable that backend would read an account out of is cleared
unless *this* provider set it.

## The ways in

A **way** is one kind of account. **a** at `/providers`, once it has been told which CLI, offers
that backend's ways as they are on this machine, and this machine is the one to trust.

| CLI | Ways |
| --- | --- |
| `claude` | `login`, `token`, `key`, `gateway`, `bedrock`, `vertex` |
| `codex` | `login`, `device`, `key`, `token`, `gateway` |
| `kimi` | `login`, `model` |
| `pi` | `login` |
| `opencode` | `login`, `wellknown`, `zen` |
| `mimo` | `login`, `key` |
| `zcode` | `login`, `device`, `key`, `gateway` |
| all of them | `env` — variables of your own |

A way with a command of its own is **handed the terminal**: its browser or its device code owns
the screen until it is done, and what it writes lands in that account's directory rather than
in the CLI's. A way that is only answers keeps them as the variables the backend reads them
under. What each way asks for is in [Providers › The ways
in](/reference/providers#the-ways-in).

## Never the values

**What is drawn of an account is the names of the variables it sets**, never what they are. A
secret typed at the prompt is bullets and is never shown back — it is on its way into a
credential store — and correcting an account starts its secrets blank for the same reason: you
type one again, or you leave it as it was.

::: tip With nobody at a terminal
Every question the walk asks is a call on `Hmz().accounts`, which is the object the walk itself
goes through:

```python
from hmz.sdk import Hmz

accounts = Hmz().accounts
way = accounts.way("claude", "gateway")
accounts.make("claude", "deepseek", way, {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": token,
})
```

`make` writes one down out of what its way was answered with; `sign_in` is what runs the
backend's own way in for a way that has one, so a script may do either without doing both. See
[SDK › Accounts](/reference/sdk#accounts).
:::

## Which models it may name

The models an account can run belong to that account, so it is asked as soon as one is made:
which models a turn may name depends on which subscription, key or gateway it runs under.
The answer is kept in `~/.humanize/providers/claude/deepseek/models.json`. Something that will
not say does not fail the line; the account was made. **r** on the models sheet asks it again,
and it is where you find out that the model you came for is not in the list.

**A gateway account is asked the gateway.** A coding agent pointed at somebody's endpoint lists
the models it ships with — it never goes and looks at the other end — so its answer is a list
your key will refuse, however recently it was taken. Where an account sets the base URL its
backend routes turns by, `GET {base}/v1/models` under that account's own credentials is what
gets written down, so the list is the ids that endpoint actually serves:

```
   claude/nvidia
     1. azure/anthropic/claude-haiku-4-5
     2. azure/anthropic/claude-opus-5
     3. azure/openai/gpt-5.6-sol
```

The credential goes into that one request and nowhere else — not into `models.json`, not into
a log, not into the message you get when the endpoint refuses, and not to another host: a
redirect off the address you gave is refused rather than followed, since the headers would go
with it. An endpoint that is down, that refuses, or that answers something other than a model
list leaves the CLI to answer as before.

## Every account there is

`/providers` lists all of them, grouped by CLI, with the way each was made by and the variables
it sets:

```
   claude
   ❯ 1. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     2. work                      login
     3. as local                  the CLI as this machine is already signed in · falls back to work

   codex
     4. personal                  key
     5. as local                  the CLI as this machine is already signed in
```

| Key | |
| --- | --- |
| **enter** | What there is to do with the account under the cursor |
| **a** | Make one: which CLI, then how to sign in, then what that way asks |
| **d** **d** | Take it away, credentials and all |

**enter** opens a menu of three rather than one letter apiece on the list:

| | | |
| --- | --- | --- |
| **correct what it holds** | the answers its way in was made with, asked again | held until saved |
| **sign in again** | its own way in, run again; it owns the terminal while it does | at once |
| **falls back to** | which account a turn carries on under when this one fails | held until saved |

How many times over a failed turn is taken again is not one of them: that is a thing about the
place a turn runs at rather than about the credentials it runs with, and
[`/fallback`](/user/fallback) is the menu it is said on. An account written down before it moved
there says so under the list — the tries it still holds are no longer read, and the line names
where they are said now.

Making an account and signing one in happen as they are asked for, because a login owns the
terminal while its browser or its device code has it, and something that has already happened
is not a draft. The other two are held with the removals until the menu is saved, as on every
other menu.

The account this machine is already signed into is `as local`, last under each CLI, and the one
thing it is offered is where it falls back to. The line under that says why rather than leaving
rows that do nothing: humanize did not make that account and keeps no credentials for it, so
there is nothing to correct and nothing to sign in.

**a** asks which CLI first, because a backend's ways in are its own and the second question is
only answerable once the first has been. The last row of that list is not a backend at all: [a
CLI of your own](/reference/agents#a-cli-of-your-own) that speaks ACP, a backend from there on
in this project and every other. Someone who cannot find their agent in the list finds that out
while answering the question *which CLI*, which is where it is answered.

![the backends a new account may be for, each with its ways in, and "a CLI of your own" last on
the list](/demo/account-backends.png)

Nothing here is refused while a flow is running. An agent reads the account it was configured
with **once**, so one made or taken away now is one the next run sees.

## One account, several CLIs

A vendor's credential is the vendor's rather than the CLI's. An Anthropic key is an Anthropic
key whether Claude Code, pi, opencode, mimocode or ZCode is holding it, and a subscription
token is one under whatever name each of them reads it under: `CLAUDE_CODE_OAUTH_TOKEN` on
Claude Code, `ANTHROPIC_OAUTH_TOKEN` on pi. So an account made for one backend is often one
several others could be run as, and making the same key four times by hand is four places to
correct when it is rotated.

That is why it is asked at the moment the account exists. Making one that others could be run
as asks which of them to write it down for as well, with the backends installed here already
ticked and the rest listed and off. An account is worth writing down before the CLI that will
use it is on this machine.

![the question after claude/shared is made: pi, opencode, mimo and zcode, each marked not
installed here yet and each switched off](/demo/alike.png)

A copy is written down **under the same name** and **over one already there**, spelled as that
backend reads it: that backend's own way where one asks for exactly those variables, and
variables of your own where it has none. So `claude/shared` made by `key` is `pi/shared` and
`opencode/shared` made by `env` — the same key under three names.

Correcting an account asks the same question again, of the account as corrected. So a rotated
key is a key rotated in several places at once: typed once, into the account it was first made
on, and written over the copies that are **ticked**.

What is ticked is the backends **installed here**, and it does not read which backends already
hold a copy. A copy on a CLI that is not on this machine is therefore one still holding the old
key, and nothing marks it as one. Which is worth a look before a rotation is trusted, a copy
left behind being an account that is still there and still works: `/providers` is where the
copies are, the same name under another backend's heading, and ticking one is what writes the
new key over it.

**What travels is variables.** An account that is a subscription signed into travels nowhere —
it is the CLI's own credential store in that CLI's own format, and nothing else can read it.
Neither does one holding a credential the other backend has no name for: every variable has to
land somewhere, or that backend is not offered the account at all.

From Python it is two calls — what else this account could run, and writing it down there:

```python
accounts = Hmz().accounts

one = accounts.find("claude", "shared")
accounts.serves(one)              # ('pi', 'opencode', 'mimo', 'zcode')
accounts.copies(one, "pi")        # pi/shared, the same key under the name pi reads it under
```

`serves` answers what an account **could** be copied to rather than what it has been copied to,
a backend already holding a copy reading the same as one holding none. Full detail in
[Providers › One account, several CLIs](/reference/providers#one-account-several-clis).

## Failing loudly

`agent.provider` raises `ValueError` the first time a turn needs an account that is not there,
naming the agent and what it was called. An agent that cannot find the account it was told to
run as **does not quietly run as yours**:

```console
$ hmz exec -f ralph_loop -a claude@gone/claude-opus-5:max "…"
… ValueError: NeiKos496: no claude provider called 'gone'
```

In the interface, an agent given an account that has since been taken away is a red line when
the flow is started, before any turn has run.

## When one goes down

An account says one thing about failing, and that one thing is written down beside the account
rather than on any agent: it is the account that goes down, and whichever agent was running
under one then is the agent that needs somewhere else to run.

**Tried again first, though not from here.** How many times a failed turn is taken again is a
thing about the place the turn runs at rather than about the credentials it runs with, so it is
said against the place, on [`/fallback`](/user/fallback), and never on the account. Nothing is
retried unless you say so.

**Then the chain.** Each account names the one to carry on under, and that one names the next.
It is *falls back to* on the menu **enter** opens, which offers that backend's other accounts;
from Python it is one call apiece:

```python
accounts.points("claude", "subscription", "key")
accounts.points("claude", "key", "gateway")
```

The account this machine is already signed into is one of them — last under each CLI's heading,
and `""` from Python, a backend and no name at all. It is where the chain of an agent nobody
gave an account begins:

```python
accounts.points("claude", "", "subscription")
```

So a flow you never configured an account for still has somewhere to go. Nothing may fall back
*to* it: an agent that is to try it is an agent given no account.

A turn walks the chain inside the conversation that was running. The session is the backend's
own and is named by an id, so the next account picks it up where the last left off, and the
agent stays where it landed. See [Agents › When an account goes
down](/reference/agents#when-an-account-goes-down).

## See also

- [Providers reference](/reference/providers)
- [TUI › The accounts themselves](/reference/tui#the-accounts-themselves) — the page itself
- [SDK › Accounts](/reference/sdk#accounts) — the same accounts as one object
- [Publish a flowverse](/weaver/flowverses)
- [A container of its own](/user/containers)
