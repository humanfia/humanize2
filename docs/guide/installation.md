# Installation

## What you need

| | |
| --- | --- |
| **Python 3.12 or newer** | 3.12, 3.13 and 3.14 are the ones CI runs the tests on. |
| **At least one coding agent CLI**, already logged in | `claude`, `codex`, `kimi`, `pi`, `opencode` or `mimo`, on your `PATH`. |
| **A project you are willing to have rewritten** | Read [Security](/guide/security) first. |

Nothing else. Two features want more, and neither is needed for anything in the tutorials:
[a container of the agent's own](/features/containers) wants `docker`, and
[remote execution](/features/remote-execution) wants Linux on x86-64 here plus `python3` on the
far machine.

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

From a checkout with `uv sync`, the command lives in that checkout's environment — `uv run hmz`,
or activate `.venv` first.

## Check what you have

humanize offers you exactly the backends that are installed, so this is the list you will see:

```sh
command -v claude codex kimi pi opencode mimo
```

A backend that is not on your `PATH` is simply not offered. If none of them is,
`hmz` says `no coding agent is installed here` and does nothing else — see
[Troubleshooting](/guide/troubleshooting#no-coding-agent-is-installed-here).

Each CLI is logged into its own way. humanize never sees the credential:

| Backend | Signing in |
| --- | --- |
| Claude Code | `claude auth login` |
| Codex | `codex login` |
| Kimi Code | `kimi login` |
| pi | `/login`, inside `pi` |
| opencode | `opencode auth login` |
| mimocode | `mimo auth login` |

To run one CLI as **more than one** account at a time, that is
[providers](/features/providers) — and it is a separate store, made with `hmz providers add`
rather than by signing the CLI in twice.

## Where humanize keeps things

Nothing is written until something needs it.

| Path | |
| --- | --- |
| `~/.humanize/cycles/` | one file per run: the flow, the agents, every session opened |
| `~/.humanize/settings.yaml` | what each project was last set up to run |
| `~/.humanize/history.jsonl` | what has been typed at the prompt |
| `~/.humanize/flowverses/` | the [flowverses](/features/flowverses) fetched here |
| `~/.humanize/providers/` | the [accounts](/features/providers), `0600` in a `0700` directory |
| `.humanize/` in a project | traces, exported transcripts, and this project's own flows |

`HUMANIZE_HOME` moves the first five somewhere else. The full list is in the
[CLI reference](/reference/cli#files).

## Uninstall

```sh
pip uninstall hmz          # or: uv tool uninstall hmz
rm -rf ~/.humanize         # everything it remembered, accounts included
```

Removing `~/.humanize` removes the provider credential stores with it. It does not touch the
coding agent CLIs or their own logins.

## Next

[Getting started](/guide/getting-started) goes from here to a run you can read back.
