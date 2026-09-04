# Installation

## What you need

| | |
| --- | --- |
| **Python 3.12 or newer** | 3.12, 3.13 and 3.14 are the ones CI runs the tests on. |
| **At least one supported backend** | `agy`, `claude`, `codex`, `cursor-agent`, `grok`, `kimi`, `mimo`, `opencode`, `pi`, `qwen` or `zcode` on your `PATH` — or nothing at all, since DeepSeek Harness arrives with humanize and needs only a DeepSeek API key. |
| **A project you are willing to have rewritten** | Read [Security](/user/security) first. |

Nothing else, and no tutorial needs more. Two features do: [a container of the agent's
own](/user/containers) wants `docker`, and [remote execution](/user/remote-execution) wants
Linux on x86-64 here plus `python3` on the far machine.

## Install humanize

::: code-group

```sh [pip]
pip install git+https://github.com/humanfia/humanize2.git
```

```sh [uv tool]
uv tool install git+https://github.com/humanfia/humanize2.git
```

```sh [from a checkout]
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync
```

:::

Either way the command is `hmz`:

```sh
hmz --version
```

```console
hmz 0.1.0
```

![hmz --version and hmz --help, listing the commands there are](/demo/cli.gif)

From a checkout with `uv sync`, the command lives in that checkout's environment. Run `uv run
hmz`, or activate `.venv` first.

### DeepSeek Harness

Nothing to add: its SDK and the runtime its turns are taken on are ordinary dependencies, so
any install that has humanize has them. It still needs an API key — see [Signing each backend
in](#signing-each-backend-in).

## Check what you have

humanize can run the backends installed in its environment. Check the CLI backends with:

```sh
command -v agy claude codex grok kimi pi qwen opencode mimo zcode
```

A CLI backend humanize cannot find is not offered. It looks on your `PATH` first, then where an
installer would have put one — `~/.local/bin`, `/usr/local/bin`, `/opt/homebrew/bin`,
`/usr/bin`, `/bin` — so a backend installed on this machine is offered even when whatever
started `hmz` handed it a `PATH` of its own, as a notebook kernel, a service or a runtime
platform's launcher does.

DeepSeek Harness stays in the list of CLIs an agent may be set to when its SDK is missing, so
that it can show the installation command. It becomes selectable when this import succeeds:

```sh
python -c 'import deepseek_harness; print("dsh installed")'
```

If none of the CLI backends or the SDK is installed, `hmz` says `no coding agent is installed
here` and does nothing else — see
[Troubleshooting](/user/troubleshooting#no-coding-agent-is-installed-here).

## Signing each backend in

Each CLI logs in its own way. humanize never sees the credential:

| Backend | Signing in |
| --- | --- |
| Claude Code | `claude auth login` |
| Codex | `codex login` |
| Kimi Code | `kimi login` |
| pi | `/login`, inside `pi` |
| opencode | `opencode auth login` |
| mimocode | `mimo auth login` |
| ZCode | `zcode login` |
| DeepSeek Harness | a DeepSeek API key saved by dsh, stored from an agent's `provider` row, or supplied as `DEEPSEEK_API_KEY` |

DeepSeek Harness is a developer preview and **arrives with humanize**:
`deepseek-harness-sdk>=0.1.0rc6,<0.2` and its bundled runtime are ordinary dependencies rather
than an extra, because a backend humanize drives is not a thing an install should be able to
have half of. The runtime wheels are published for Linux on x86-64 or arm64 and macOS on arm64.
The `dsh` CLI is not required.

It supports API-key login only, and there are two places to keep that key. For dsh's own
credential store, run `dsh web`, open **Settings -> Models**, enter the DeepSeek key and save
it; then set an agent's `cli` row to `dsh` and leave its `provider` row on `as local`. That
reads dsh's normal configuration sources — the saved key and any `llm-deepseek.baseURL` in
`$DSH_HOME/settings.yaml`, then its environment layers. `$DSH_HOME` defaults to `~/.dsh`.

For a separate key in humanize's provider store, choose `dsh` on the `cli` row, press enter on
the `provider` row and **a** in the list of accounts, choose `key`, and enter an account name
and the key. The same account is one command from a terminal, which asks for the key rather
than taking it in the command itself:

```sh
hmz providers add dsh/deepseek -w key
```

An agent that uses that stored account is written with `@deepseek`:

```sh
hmz exec -f chat -a dsh@deepseek/deepseek-v4-flash:high "hello"
```

Alternatively, set the key and optional endpoint in the environment before starting `hmz`:

```sh
export DEEPSEEK_API_KEY=sk-…
export DEEPSEEK_BASE_URL=https://api.deepseek.com
hmz
```

Use either official model id at one of its three efforts:

```sh
DEEPSEEK_API_KEY=sk-… hmz exec -f ralph_loop \
    -a dsh/deepseek-v4-flash:high "fix the failing tests"
```

The other official model is `deepseek-v4-pro`. The efforts are `max`, `high` and `off`. The
current SDK exposes no per-session permission or skill controls, so DeepSeek Harness agents
must use the default `permission="bypass"`.

To run one CLI as **more than one** account at a time, use [providers](/user/providers). It is
a separate store, made with `hmz providers add` rather than by signing the CLI in twice.

## Where humanize keeps things

Nothing is written until something needs it.

| Path | |
| --- | --- |
| `~/.humanize/epics/` | one directory per run: the flow, the agents, every session opened, and the [trace](/user/tracing) gathered of it afterwards |
| `~/.humanize/settings.yaml` | what each project was last set up to run |
| `~/.humanize/history.jsonl` | what has been typed at the prompt |
| `~/.humanize/flowverses/` | the [flowverses](/weaver/flowverses) fetched here |
| `~/.humanize/providers/` | the [accounts](/user/providers), `0600` in a `0700` directory |
| `.humanize/` in a project | exported transcripts, and this project's own flows |

`HUMANIZE_HOME` moves the first five somewhere else. The full list is in the [CLI
reference](/reference/cli#files).

## Uninstall

```sh
pip uninstall hmz          # or: uv tool uninstall hmz
rm -rf ~/.humanize         # everything it remembered, accounts included
```

Removing `~/.humanize` removes the provider credential stores with it. It does not touch the
coding agent CLIs or their own logins.

## Next

The [quickstart](/#run-a-flow) goes from here to a run you can read back.
