# Providers

Which account an agent runs as. A provider is **one named set of credentials for one CLI**, kept
apart from the CLI's own — so two agents driving the same CLI can be two different accounts at
the same time.

Nothing needs one. An agent with no provider runs its CLI exactly as you run it yourself.

## The problem it solves

A coding agent CLI signs in once. Claude Code keeps its account under `~/.claude`, and every
`claude` started on this machine is whoever is signed in there. A flow that wants two of them on
two accounts has two accounts wanting one directory.

A provider is the second directory.

```sh
hmz providers add claude/anthropic -w login          # runs `claude auth login`, here
hmz providers add claude/deepseek -w gateway \
    -s ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic   # then asks for the token

hmz exec -f official/flame_chase \
    -a claude@anthropic/claude-opus-5:max \
    -a claude@deepseek/deepseek-chat:high "fix the build"
```

Both agents run the same `claude`. The first reads the subscription's tokens and refreshes them;
the second dials the endpoint with the token you typed. Neither can read the other's credential
file, and neither can read yours.

## Naming one on an agent

```
claude@deepseek/claude-opus-5:max
cli=claude,model=claude-opus-5,effort=max,provider=deepseek
```

A CLI is never spelled with an `@` in it, so the two are told apart wherever an agent is written.
An `@` with nothing after it is refused — it was typed to name an account, and running as
whoever is at this machine is not that.

In Python it is a field of the config:

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", provider="deepseek")
```

At the prompt it is the **first** step of `/agents`: a tab per CLI that is installed, and under it
that CLI's own accounts, with `as installed` as the first row. **ctrl+n** there makes one without
leaving the question.

## What moves, and what does not

**Only the credential files move.** Sessions, settings and skills stay in the CLI's own home —
which is why a turn under a provider still shows up in a [trace](/features/tracing), still counts
towards the [cost readout](/features/tally), and still has the skills you installed.

```
~/.humanize/providers/claude/deepseek/
├── provider.json      what it was made by, and what a turn under it runs with
├── home/              the credential files the CLI keeps under its own home
│   ├── .credentials.json
│   └── .claude.json
└── user/              and the ones it keeps outside it
    └── .claude.json
```

`0600` in a directory at `0700`. The files keep the names the CLI gave them, because it is the CLI
that writes them: a login run for a provider is the CLI's own login with those paths pointed here.

**A turn under a provider is run with the other accounts' variables unset.** An
`ANTHROPIC_API_KEY` left in a shell profile is a key the CLI would rather have than the credential
file it was signed in with — and the turn would be taken as the wrong account with nothing looking
wrong. So every variable that backend would read an account out of is cleared unless *this*
provider set it.

## The ways in

A way is one kind of account. `hmz providers ways <cli>` prints the list on this machine, which is
the one to trust.

| CLI | Ways |
| --- | --- |
| `claude` | `login`, `token`, `key`, `gateway`, `bedrock`, `vertex` |
| `codex` | `login`, `device`, `key`, `token`, `gateway` |
| `kimi` | `login`, `model` |
| `pi` | `login` |
| `opencode` | `login`, `wellknown`, `zen` |
| `mimo` | `login`, `key` |
| all of them | `env` — variables of your own |

A way with a command of its own is **handed the terminal**: its browser or its device code owns
the screen until it is done, and what it writes lands in that account's directory rather than in
the CLI's. A way that is only answers keeps them as the variables the backend reads them under.

Full table, with what each way asks for, in
[Providers › The ways in](/reference/providers#the-ways-in).

## The commands

```sh
hmz providers list [<cli>]           # what there is
hmz providers ways <cli>             # how that backend can be signed into
hmz providers add <cli>/<name>       # make one: -w <way>, -s VAR=VALUE, --no-login
hmz providers login <cli>/<name>     # sign an existing one in again
hmz providers show <cli>/<name>      # what it holds — never what the values are
hmz providers remove <cli>/<name>    # take it away, credentials and all
```

**Values are never printed.** `show` and `list` say which variables a provider sets and not what
they are. A secret typed at the prompt is drawn as bullets and never shown back.

![hmz providers ways, add, list and show — naming variables and never their values](/demo/providers.gif)

**What an account runs is that account's**, so the CLI is asked as soon as one is made: which
models a turn may name depends on which subscription, key or gateway it runs under. A CLI that
will not say does not fail the line — the account was made — and **ctrl+r** on the models sheet
asks it again.

## In the interface

`/providers` is all of them, grouped by CLI, with the way each was made by and the variables it
sets:

```
   claude
   ❯ 1. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     2. work                      login

   codex
     3. personal                  key
```

| Key | |
| --- | --- |
| **enter** or **a** | Make one: which CLI, then how to sign in, then what that way asks |
| **l** | Sign the one under the cursor in again |
| **r** | Take it away, credentials and all |

Nothing here is refused while a flow is running. An agent reads the account it was configured
with **once**, so one made or taken away now is one the next run sees.

## Failing loudly

`agent.provider` raises `ValueError` the first time a turn needs an account that is not there,
naming the agent and what it was called. An agent that cannot find the account it was told to run
as **does not quietly run as yours**.

In the interface, an agent given an account that has since been taken away is a red line when the
flow is started, before any turn has run.

## See also

- [Tutorial: two accounts of one CLI](/guide/tutorial-providers)
- [Providers reference](/reference/providers)
- [CLI › `hmz providers`](/reference/cli#hmz-providers)
