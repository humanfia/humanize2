# 16 · Two accounts of one CLI

**Fifteen minutes.** One flow driving `claude` twice — once on a subscription, once on somebody
else's endpoint — at the same time.

::: tip Before you start
[Publish a flowverse](/guide/tutorial-flowverse). You need a second account or endpoint to point
at; the walkthrough uses a gateway, which is the easiest to try.
:::

## The problem

A coding agent CLI signs in **once**. Claude Code keeps its account under `~/.claude`, and every
`claude` on this machine is whoever is signed in there. A flow that wants two of them on two
accounts has two accounts wanting one directory.

A provider is the second directory.

## Step 1 — see what ways in there are

```sh
hmz providers ways claude
```

This prints the list **on this machine**, which is the one to trust. For `claude` it is `login`,
`token`, `key`, `gateway`, `bedrock`, `vertex` — plus `env`, which every backend has.

## Step 2 — make one from your existing subscription

```sh
hmz providers add claude/anthropic -w login
```

This runs `claude auth login` **here**, with the paths pointed at the provider's own directory. The
CLI's own login owns the terminal until it is done, and what it writes lands under
`~/.humanize/providers/claude/anthropic/`.

## Step 3 — make one from an endpoint

```sh
hmz providers add claude/deepseek -w gateway \
    -s ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
```

`-s` answers one of the way's questions on the line rather than being asked. Whatever the line did
not answer is asked at the terminal, and a **secret is not echoed** — here, the token.

::: tip Non-interactive
A line with nobody at a terminal has to answer everything itself:
```sh
hmz providers add claude/deepseek -w gateway \
    -s ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic \
    -s ANTHROPIC_AUTH_TOKEN="$TOKEN"
```
`--no-login` writes one down without running the backend's own way in at all.
:::

## Step 4 — look at what you made

```sh
hmz providers list
```

```console
claude/anthropic  login      -
claude/deepseek  gateway    ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
codex/personal  key        -
```

One line each: the account, the way it was made by, and the variables it sets — `-` for a way
that sets none. `hmz providers list claude` narrows it to one backend.

```sh
hmz providers show claude/deepseek
```

**Values are never printed.** `show` and `list` say which variables a provider sets and not what
they are.

![hmz providers ways, add, list and show — naming variables and never their values](/demo/providers.gif)

<small>Recorded with `--no-login` against an invalid endpoint, so nothing here is signed in to
anything.</small>

## Step 5 — run one flow as both

```sh
hmz exec -f official/flame_chase \
    -a claude@anthropic/claude-opus-5:max \
    -a claude@deepseek/deepseek-chat:high \
    "fix the build"
```

`flame_chase` hands the same task to two agents in turn. Both run the same `claude`. The first
reads the subscription's tokens and refreshes them; the second dials the endpoint with the token
you typed; **neither can read the other's credential file, and neither can read yours.**

Two spellings, meaning the same thing:

```
claude@deepseek/claude-opus-5:max
cli=claude,model=claude-opus-5,effort=max,provider=deepseek
```

A CLI is never spelled with an `@` in it, so the two are told apart wherever an agent is written.

## Step 6 — the same at the prompt

`/agents`, **first step**. A tab per CLI that is installed, and under it that CLI's own accounts —
an account belongs to one backend, since what signs in to Claude Code is not what signs in to
codex:

```
   claude · codex · kimi · mimo · opencode · pi   ←/→ to switch

   ❯ 1. as installed              ✔ signed in as you signed it in
     2. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     3. work                      login
```

`as installed` is what every agent ran as before there were any accounts.

**a makes one without leaving the question** — the same walk `/providers` runs, minus the
question this tab has already answered — and comes back with the new account chosen.

## Step 7 — the models are the account's

Which models a turn may name depends on which subscription, key or gateway it runs under. So the
CLI is asked as soon as an account is made, and the answer is kept:

```
~/.humanize/providers/claude/deepseek/models.json
```

**r** on the models sheet asks it again, which is where you find out that the model you came
for is not in the list. A CLI that will not say does not fail the line — the account was made.

## What actually moves

Only the credential files:

```
~/.humanize/providers/claude/deepseek/
├── provider.json      what it was made by, and what a turn under it runs with
├── home/              the credential files the CLI keeps under its own home
│   ├── .credentials.json
│   └── .claude.json
└── user/              and the ones it keeps outside it
    └── .claude.json
```

`0600` in a directory at `0700`. **Sessions, settings and skills stay in the CLI's own home** —
which is why a turn under a provider still shows up in a [trace](/features/tracing), still counts
towards the [cost readout](/features/tally), and still has the skills you installed.

And a turn under a provider is run with the **other** accounts' variables unset. An
`ANTHROPIC_API_KEY` left in a shell profile is a key the CLI would rather have than the credential
file it was signed in with — the turn would be taken as the wrong account with nothing looking
wrong.

## When it goes wrong

```console
$ hmz exec -f ralph_loop -a claude@gone/claude-opus-5:max "…"
… ValueError: ClaudeCodeAgent#859ee5b7: no claude provider called 'gone'
```

An agent that cannot find the account it was told to run as **does not quietly run as yours**. In
the interface it is a red line when the flow is started, before any turn has run.

## Tidying up

```sh
hmz providers login claude/deepseek     # sign it in again, by the way it was made with
hmz providers remove claude/deepseek    # take it away, credentials and all
```

Nothing here is refused while a flow is running. An agent reads the account it was configured with
**once**, so one made or taken away now is one the next run sees.

## What you now know

- `hmz providers ways <cli>` first; then `add`, `login`, `show`, `remove`.
- `cli@account/model:effort` on an agent, or `provider=` written out.
- Only credentials move; sessions, settings and skills stay put.
- The model list belongs to the account.

## Next

[A container of its own](/guide/tutorial-container).
