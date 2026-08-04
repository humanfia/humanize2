# Providers

Which account an agent runs as. A provider is one named set of credentials for one coding agent
CLI, kept apart from the CLI's own — so two agents driving the same CLI can be two different
accounts at the same time.

Nothing needs one. An agent with no provider runs its CLI exactly as you run it yourself, signed
in the way you already signed in.

## One CLI, two accounts

A coding agent CLI signs in once. Claude Code keeps its account under `~/.claude`, and every
`claude` started on this machine is whoever is signed in there — so a flow that wants two of
them on two accounts has two accounts wanting one directory.

A provider is the second directory. [flame_chase](/reference/flows.md#the-official-flowverse) hands
the same task to two agents in turn; here both are Claude Code — one on the Anthropic
subscription running Opus, one on a DeepSeek endpoint running DeepSeek's own model:

```sh
hmz providers add claude/anthropic -w login          # runs `claude auth login`, here
hmz providers add claude/deepseek -w gateway \
    -s ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic   # then asks for the token

hmz exec -f official/flame_chase \
    -a claude@anthropic/claude-opus-5:max \
    -a claude@deepseek/deepseek-chat:high "fix the build"
```

Both agents run the same `claude`. The first reads the subscription's tokens and refreshes them;
the second dials the endpoint with the token you typed; neither can read the other's credential
file, and neither can read yours.

## Where the credentials are kept

One directory per provider, under `~/.humanize/providers/<cli>/<name>/` — `$HUMANIZE_HOME` where
that is set:

```
~/.humanize/providers/claude/deepseek/
├── provider.json      what it was made by, and what a turn under it runs with
├── home/              the credential files the CLI keeps under its own home
│   ├── .credentials.json
│   └── .claude.json
└── user/              and the ones it keeps outside it
    └── .claude.json
```

The files keep the names the CLI gave them, because it is the CLI that writes them: a login run
for a provider is the CLI's own login, with those paths pointed here.

**Only the credential files are kept here.** Sessions, settings and skills stay in the CLI's own
home, which is why a turn under a provider still shows up in a [trace](/reference/tracing.md), still counts
towards the [cost readout](/reference/agents.md#what-it-has-cost-and-how-fast), and still has the skills you
installed.

What each backend keeps an account in, and so what a provider of it holds:

| Backend | The credential files |
| --- | --- |
| `claude` | `~/.claude/.credentials.json`, `~/.claude/.claude.json`, and `~/.claude.json` outside the home |
| `codex` | `~/.codex/auth.json` — the subscription's tokens and an API key land in the same file |
| `kimi` | `~/.kimi-code/credentials/` and `~/.kimi-code/oauth/`, each a directory and everything in it |
| `pi` | `~/.pi/agent/auth.json`, and the lock its own processes refresh under |
| `opencode` | `~/.local/share/opencode/auth.json` and `mcp-auth.json` |
| `mimo` | `~/.local/share/mimocode/auth.json` and `mcp-auth.json` |

Each follows the variable that moves that CLI's home — `CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
`KIMI_CODE_HOME`, `PI_CODING_AGENT_DIR`, `XDG_DATA_HOME`. See
[Environment variables](/reference/cli.md#environment-variables).

## The ways in

A way is one kind of account: a subscription signed into, a key, a gateway, an account on
somebody's cloud. `hmz providers ways <cli>` prints the list on this machine, which is the one to
trust; these are the ways as they stand.

An answer in parentheses is what a question takes when you say nothing. A way with a command of
its own runs it on this terminal, under the provider's paths, and what it writes is the provider;
a way that is only answers keeps them as the variables the backend reads them under.

**claude**

| Way | | Asks for |
| --- | --- | --- |
| `login` | Sign in to an Anthropic account. Runs `claude auth login`. | — |
| `token` | A long-lived token, as `claude setup-token` prints one. | `CLAUDE_CODE_OAUTH_TOKEN` |
| `key` | An Anthropic API key, from the console. | `ANTHROPIC_API_KEY` |
| `gateway` | An endpoint speaking Claude Code's own protocol — a proxy, a router, another vendor. | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` |
| `bedrock` | Anthropic's models on an AWS account of yours. Also sets `CLAUDE_CODE_USE_BEDROCK=1`. | `AWS_PROFILE`, `AWS_REGION` (`us-east-1`) |
| `vertex` | Anthropic's models on a Google Cloud project of yours. Also sets `CLAUDE_CODE_USE_VERTEX=1`. | `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` (`us-east5`) |

**codex**

| Way | | Asks for |
| --- | --- | --- |
| `login` | Sign in to a ChatGPT account, in a browser. Runs `codex login`. | — |
| `device` | The same, from a machine with no browser on it. Runs `codex login --device-auth`. | — |
| `key` | An OpenAI API key, which codex keeps in its own store. Runs `codex login --with-api-key` and feeds it in. | `OPENAI_API_KEY` |
| `token` | An access token, which is how an organisation hands one out. Runs `codex login --with-access-token` and feeds it in. | `CODEX_ACCESS_TOKEN` |
| `gateway` | An endpoint speaking codex's own protocol. | `CODEX_PROVIDER_URL`, `CODEX_PROVIDER_KEY`, `CODEX_PROVIDER_WIRE` (`chat`) |

Codex takes a provider as settings rather than as variables, so a turn under `gateway` is given
`-c model_provider=humanize` and the four settings under it on the command line. Nobody's
`config.toml` is written. The key of the `key` way is read by `codex login` off its standard
input and kept in codex's own store, so it is not kept a second time as a variable.

**kimi**

| Way | | Asks for |
| --- | --- | --- |
| `login` | Sign in to a Kimi account, by the code it prints. Runs `kimi login`. | — |
| `model` | An endpoint speaking Kimi Code's own protocol, made its default in memory. | `KIMI_MODEL_NAME`, `KIMI_MODEL_API_KEY`, `KIMI_MODEL_BASE_URL`, `KIMI_MODEL_PROVIDER_TYPE` (`openai`) |

**pi**

| Way | | Asks for |
| --- | --- | --- |
| `login` | pi's own `/login`, in a session opened for it. Runs `pi`, and hands you the terminal: `/login`, whichever provider, then `/exit`. | — |

**opencode**

| Way | | Asks for |
| --- | --- | --- |
| `login` | opencode's own provider list, and whichever way that one takes. Runs `opencode auth login`. | — |
| `wellknown` | A provider that hands out its own credential, by URL. Runs `opencode auth login <url>`. | `OPENCODE_WELLKNOWN`, the URL answering at `/.well-known/opencode` |
| `zen` | An OpenCode Zen key, which its own models run on. | `OPENCODE_API_KEY` |

**mimo**

| Way | | Asks for |
| --- | --- | --- |
| `login` | mimocode's own provider list, and whichever way that one takes. Runs `mimo auth login`. | — |
| `key` | A MiMo key, which its own models run on. | `XIAOMI_API_KEY` |

**Every backend but `dsh`, as well as its own:**

| Way | | Asks for |
| --- | --- | --- |
| `env` | Variables of your own: whatever this CLI reads a key or an endpoint under. | the `NAME=VALUE` lines you give it |

DeepSeek Harness is the exception: it is driven through an SDK that takes an API key and
nothing else, so `hmz providers ways dsh` offers only its own `key` way.

The names are typed rather than chosen because there is no list worth keeping: pi has a variable
for each provider it knows and opencode one for each of a hundred and eighty, across six vendors
that move. One variable a line, and shift+enter — or ctrl+j — is what breaks the line, enter
being what takes the form.

## `hmz providers`

```
hmz providers list [<cli>]
hmz providers ways <cli>
hmz providers add <cli>/<name> [-w <way>] [-s VAR=VALUE]... [--no-login]
hmz providers login <cli>/<name> [-s VAR=VALUE]...
hmz providers show <cli>/[<name>]
hmz providers falls-back <cli>/[<name>] [<name>]
hmz providers retry <cli>/[<name>] [-n <tries>] [-p <policy>] [-t <seconds>]
hmz providers remove <cli>/<name>
```

A provider is named `<cli>/<name>` everywhere the command line asks for one. The name is a
directory, so it is letters, digits, dot, dash and underscore, starting with a letter or a digit.

`<cli>/` — a backend and no name at all — is **the account this machine is already signed
into**: an account of every backend, which humanize did not make and keeps no credentials for.
`show`, `falls-back` and `retry` take it; `add`, `login` and `remove` refuse it, there being
nothing to make, sign in or take away.

| Command | |
| --- | --- |
| `list` | What providers there are, or one backend's. The line is the name, the way it was made by, and the variables it sets. |
| `ways` | How that backend can be signed into: each way, what it asks for, and what it runs. |
| `add` | Makes one. `-w` chooses the way — the backend's first when nothing says otherwise, which is `login` for the CLIs that sign in and `key` for `dsh` — and `-s` answers one of its questions on the line rather than being asked. Then it runs the way's own command, unless `--no-login` says only to write it down. |
| `login` | Signs an existing one in again, by the way it was made with. For a way that has nothing to run, `add` it again instead. |
| `show` | What one holds: the way, when it was made, where it is kept, what it falls back to, how a failed turn under it is tried again, the **names** of the variables it sets, and which paths a turn under it is given instead of which. |
| `falls-back` | Says which account of that CLI a turn carries on under when this one fails, or — with nothing after it — that this one is the end of the line. |
| `retry` | Says how a failed turn under it is tried again before the chain moves on: `-n` how many times over, `-p` which wait, `-t` the longest the whole of it may go on for. |
| `remove` | Takes it away, credentials and all. |

Whatever a way asks that the line did not answer is asked at the terminal, and a secret is not
echoed. A line run where nobody is at a terminal has to answer everything itself — a question
with no answer and no default is reported rather than waited on.

```console
$ hmz providers add claude/deepseek -w gateway
where it is, as a URL: https://api.deepseek.com/anthropic
the token it takes:
claude/deepseek is written down at /home/you/.humanize/providers/claude/deepseek

$ hmz providers list
claude/anthropic  login      -  falls back to deepseek
claude/deepseek  gateway    ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
claude/  as local   -  2 tries, exponential-jitter
codex/work  login      -

$ hmz providers show claude/deepseek
provider    claude/deepseek
way         gateway
made        2026-08-11T15:01:01Z
kept in     /home/you/.humanize/providers/claude/deepseek
falls to    nowhere
tried       once
sets        ANTHROPIC_AUTH_TOKEN
sets        ANTHROPIC_BASE_URL
answers     /home/you/.claude/.credentials.json -> …/providers/claude/deepseek/home/.credentials.json
answers     /home/you/.claude/.claude.json -> …/providers/claude/deepseek/home/.claude.json
answers     /home/you/.claude.json -> …/providers/claude/deepseek/user/.claude.json

$ hmz providers ways claude
login      sign in to an Anthropic account, as `claude auth login` does
           asks: -
           runs: claude auth login
token      a long-lived token, as `claude setup-token` prints one
           asks: CLAUDE_CODE_OAUTH_TOKEN
           runs: -
…

$ hmz providers remove claude/deepseek
claude/deepseek is gone, credentials and all
```

Making a provider that is already there replaces what it holds and leaves its credentials alone:
a key corrected is not a reason to sign in again.

In the interface, `/providers` walks the same list, with the account this machine is signed
into last under each CLI's heading. Six things can happen to one there: **a** makes one,
**enter** corrects what it holds, **l** signs it in again, **f** says what it falls back to,
**t** says how a failed turn under it is tried again, and **d** twice takes it away.

## When an account goes down

An account says what happens when it is the one that fails, and both halves are written down
beside it: it is the account that goes down, and whichever agent was running under one when it
did is the agent that needs somewhere else to run.

**Tried again.** Nothing is retried by default — a prompt the model refused is the same refusal
every time, and only you know which of your accounts fails the other way. The waits are the
ones everybody uses, `BASE` being one second and no single wait longer than a minute:

| Policy | The waits before the 2nd, 3rd, 4th… try |
| --- | --- |
| `none` | none at all |
| `constant` | 1s, 1s, 1s |
| `linear` | 1s, 2s, 3s |
| `exponential` | 1s, 2s, 4s, 8s |
| `exponential-jitter` | anywhere up to the exponential wait — the default, and what keeps a flow's agents from all coming back on the same second |
| `fibonacci` | 1s, 1s, 2s, 3s, 5s |

`-t` is checked **before** a wait rather than after it, so a turn is never started knowing the
time it was given is already spent.

**Then the chain.** Each account names the one to carry on under, and that one names the next:

```sh
hmz providers falls-back claude/subscription key
hmz providers falls-back claude/key gateway
hmz providers falls-back claude/ subscription   # where an agent with no account starts
```

A turn walks it inside the conversation that was running, and the agent stays where it landed.
A chain that comes round on itself ends at the second sight of an account; one naming an
account that is not there ends there. Nothing may fall back *to* the machine's own account:
an agent that is to try it is an agent given no account, which is where its chain already
starts.

From Python:

```python
from hmz import providers

held = providers.find("claude", "subscription")
providers.chain(held)                       # [subscription, key, gateway]
providers.points("claude", "", "subscription")   # "" is the machine's own account
providers.retrying("claude", "key", 3, "exponential-jitter", 120.0)
providers.alone("claude")                   # where what is said about the machine's own is kept
```

## Choosing one for an agent

It is a setting of the [agent](/reference/agents.md), because it is the agent that signs in.

In Python, by name:

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", provider="deepseek")
```

On a command line, after the CLI and an `@`:

```sh
hmz exec -f official/flame_chase -a claude@deepseek/claude-opus-5:max "fix the build"
hmz exec -f ralph_loop -a cli=claude,model=claude-opus-5,effort=max,provider=deepseek "…"
```

In the interface it is the `provider` row of the sheet an agent is set up on — which
CLI, and which of its accounts — because an account belongs to a backend and everything after it
is about how that backend runs. See [TUI › What each agent
is](/reference/tui.md#what-each-agent-is).

**`a` on that row makes one there and then**, so finding out you have no account for this
CLI is not a reason to leave the question: it asks how to sign in and what that way needs, hands
the terminal to the CLI's own login where the way has one, and comes back with the new account
chosen for that agent. It is the same walk `/providers` runs without the question already
answered — which backend.

`""` — the default — is the CLI as you already run it. A name no provider of that backend
answers to raises the first time that agent needs it, saying which agent and what it was called:
an agent that cannot find the account it was told to run as must not quietly run as yours.

## What a turn under one runs as

Two things, and nothing else:

- **Its variables** are added to the environment the turn inherits, which is how a key, an
  endpoint or an account on somebody's cloud reaches the CLI. A way that adds arguments — codex's
  `gateway` — adds them to the CLI's own command line.
- **Its credential paths are answered.** The CLI still opens `~/.claude/.credentials.json`; what
  it gets is the one under the provider's directory. A token refreshed mid-turn is written back
  where it was read from.

Both happen whichever way the provider was made, so an agent on a gateway never reads the account
your CLI is signed into either.

The paths are answered by a seccomp-filtered ptrace supervisor — the technique
[`hmz anchor`](/reference/remote-execution.md) runs a whole session under, here handling only the handful of
syscalls that name one of those files. Everything else the agent does is untouched and runs at
native speed, and the agent is told none of it. That supervisor is a process humanize spawns
for itself: a supervisor forks the program it watches, and a flow pumping turns from threads
of its own has no signal handling to lend one.

## Requirements and limits

- **Linux on x86-64**, as running an agent under an anchor needs. There is nothing to install.
- **A turn that is also [anchored](/reference/machines.md) is supervised once, not twice.** A process has
  one tracer, so the anchor is told which paths to answer and answers them itself.
- **Only the paths listed [above](#where-the-credentials-are-kept) are answered.** A CLI that
  keeps a credential somewhere else keeps it where it always did.
- **A credential that is not a file is not covered.** A macOS keychain is not a path, and nothing
  here reaches it. Neither is one kept in a database: an opencode or mimocode **console account**
  lives in that CLI's SQLite file, which holds the sessions too and is therefore not answered —
  a provider of one of those is its `auth.json`, which is every provider it signs into.
- **A path that could not be answered fails**, with `EIO`, rather than falling through to the
  real one: a turn taken as the wrong account is worse than a turn that did not run. So is a turn
  that could not be supervised at all, which is refused rather than run unsupervised.
- **A 32-bit process below the agent is not intercepted**, as it is not under an
  [anchor](/reference/remote-execution.md): the filter passes another architecture's syscalls through
  untouched. Every one of these CLIs is 64-bit.

## What a turn under one is run without

A CLI takes an account from a variable in preference to the credentials it was signed in with,
so a key left in a shell profile would outrank a provider and nothing about the turn would look
wrong. A turn under a provider is therefore run **without** every variable its backend reads an
account from — unless that provider set it:

```console
$ export ANTHROPIC_API_KEY=sk-mine          # what you use by hand
$ hmz exec -f ralph_loop -a claude@work/claude-opus-5:high "..."
                                            # the turn runs as `work`, not as that key
```

`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_OAUTH_TOKEN`,
`CLAUDE_CODE_USE_BEDROCK`, `OPENAI_API_KEY`, `CODEX_API_KEY`, `KIMI_MODEL_*`,
`OPENCODE_AUTH_CONTENT`, `XIAOMI_API_KEY` and the rest of each backend's own — `hmz providers
ways <cli>` names the ones its ways use. Everything else in the environment is left exactly as
it was found, and an agent with **no** provider is not touched at all.

## Security

**A provider directory holds real credentials.** It is made at `0700` and `provider.json` at
`0600`, which is what these CLIs keep their own at. `remove` deletes it, credentials and all —
that is what taking away an account this machine can run turns as means.

**Nothing prints a secret.** `show` and `list` print the names of the variables a provider sets
and never their values; a secret answered at the terminal is not echoed. One given with `-s` is
in your shell's history, so leave it to be asked for.

**The credentials stay on this machine.** An agent runs here however its
[machine](/reference/machines.md) is configured, so a provider's files do not cross to a target — what
crosses is the work. Neither do its variables: everything an agent exports is otherwise
inherited by every command it runs there, so a provider's are named as the agent's own and
dropped on the way over.

## API summary

```python
from hmz.providers import (
    Provider,   # cli, name, way, env, args, made; .at, .swaps(), .command(argv)
    providers,  # every provider there is, or one backend's
    find,       # one of a backend, by name, or None
    add,        # write one down, and make the directory its credentials go in
    remove,     # take one away, credentials and all
    ways,       # every way in one backend offers, and `env` last
    where,      # the directory one is kept in
    environ,    # what a turn under one is run with
)

from hmz.providers.login import (
    way_of,     # the way one backend offers under a name
    asked,      # what a way still has to be told
    make,       # a provider out of what its way was answered with
    sign_in,    # the backend's own way in, run under that provider's paths
)
```

And on the agent side:

```python
agent.provider      # Provider | None -- which account its turns run as
agent.environment() # what those turns are run with, on top of what they inherit
```
