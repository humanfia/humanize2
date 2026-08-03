# Installation

## What you need

| | |
| --- | --- |
| **Python 3.12 or newer** | 3.12, 3.13 and 3.14 are the ones CI runs the tests on. |
| **At least one supported backend** | `claude`, `codex`, `kimi`, `pi`, `opencode` or `mimo` on your `PATH`, or the optional DeepSeek Harness Python SDK. |
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

```sh [pip + DeepSeek Harness]
pip install 'hmz[dsh] @ git+https://github.com/humanfia/humanize2.git'
```

```sh [uv tool + DeepSeek Harness]
uv tool install 'hmz[dsh] @ git+https://github.com/humanfia/humanize2.git'
```

```sh [from a checkout]
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync
```

```sh [checkout + DeepSeek Harness]
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync --extra dsh
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

### Add DeepSeek Harness to an existing install

An extra is chosen when a package is installed; upgrading an installation that did not include
`dsh` does not add it. For an existing pip installation, run the **pip + DeepSeek Harness**
command above. For an existing uv tool installation, replace it in place with:

```sh
uv tool install --force 'hmz[dsh] @ git+https://github.com/humanfia/humanize2.git'
```

For a checkout, sync the extra into that checkout's `.venv`:

```sh
uv sync --extra dsh
```

Then reopen `hmz`. Before the SDK is installed, the `dsh` tab in `/agents` also prints a
command that targets the exact Python environment running `hmz`.

The Python extra is all humanize needs to run DeepSeek Harness. DeepSeek's own `dsh` launcher
is useful for its Web configuration UI and is installed separately with Node.js:

```sh
npm install --global @deepseek-ai/dsh
dsh web
```

For a one-off run without a global install, use `npx @deepseek-ai/dsh web`.

## Check what you have

humanize can run the backends installed in its environment. Check the CLI backends with:

```sh
command -v claude codex kimi pi opencode mimo
```

A CLI backend that is not on your `PATH` is simply not offered. The `dsh` tab remains visible
in `/agents` when its SDK is missing so it can show the installation command; it becomes
selectable when this import succeeds:

```sh
python -c 'import deepseek_harness; print("dsh installed")'
```

If none of the CLI backends or the SDK is installed,
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
| DeepSeek Harness | a DeepSeek API key saved by dsh, stored from `/agents`, or supplied as `DEEPSEEK_API_KEY` |

DeepSeek Harness is currently a developer preview. The `dsh` extra installs
`deepseek-harness-sdk>=0.1.0rc6,<0.2` and its bundled runtime; the published runtime wheels
support Linux on x86-64 or arm64 and macOS on arm64. It does not require the `dsh` CLI.

DeepSeek Harness supports API-key login only. To use dsh's own credential store, run `dsh web`,
open **Settings -> Models**, enter the DeepSeek key, and save it. In humanize, type `/agents`,
switch to `dsh`, and choose `as installed`. That choice uses dsh's normal configuration sources:
the saved key and any `llm-deepseek.baseURL` in `$DSH_HOME/settings.yaml`, then its environment
layers. `$DSH_HOME` defaults to `~/.dsh`.

To keep a separate key in humanize's provider store instead, press **ctrl+n** on the `dsh` tab,
choose `key`, and enter an account name and the key. The same account can be made from a
terminal; this command asks for the key without putting it in the command itself:

```sh
hmz providers add dsh/deepseek -w key
```

An agent using that stored account is written with `@deepseek`:

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

The other official model is `deepseek-v4-pro`; the efforts are `max`, `high` and `off`.
The current SDK exposes no per-session permission or skill controls, so dsh agents must use
the default `permission="bypass"` and `skills=None`.

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
