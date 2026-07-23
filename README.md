# amflows

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat-square)](LICENSE)

> Orchestrate, execute, and observe agent flows.

A flow is a coding agent driven in a loop. amflows is the three pieces that takes:

- **`amflows.janus`** runs Claude Code, Codex and Kimi Code behind one interface, as agents that
  hand out sessions.
- **`amflows.exomyth`** turns the trajectories they leave behind into a Chrome JSON trace.
- **`amflows.coganchor`** runs an agent on one machine and has it act on another.

Each is importable on its own; nothing pulls in the others.

## Table of Contents

- [Install](#install)
- [Usage](#usage)
  - [janus](#janus)
  - [exomyth](#exomyth)
  - [coganchor](#coganchor)
- [Security](#security)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Install

Python ≥ 3.12, and the coding agent CLIs you intend to drive (`claude`, `codex`, `kimi`) on your
PATH. `coganchor` additionally needs Linux x86-64 locally, and nothing but `python3` on the target.

```sh
pip install git+https://github.com/humanfia/amflows.git
```

From source, with [uv](https://docs.astral.sh/uv/):

```sh
git clone git@github.com:humanfia/amflows.git
cd amflows
uv sync
```

## Usage

### janus

An agent runs at a model and an effort; a session is one conversation with it. Which of the two a
loop holds decides what the flow remembers.

```python
from amflows.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))

agent.launch().run(
    "Read TASK.md and get started."
)  # a new session: nothing carries over

session = agent.launch()
session.run("Read TASK.md and get started.")  # opens the session
session.run("continue")  # resumes it, task still in context
```

`CodexAgent` and `KimiCodeCLIAgent` take the same calls. Both streams of a turn are passed through
as they arrive, and a turn that fails raises `subprocess.CalledProcessError` without opening the
session, so the next call retries it.

Two agents at one model and one effort are still two agents — an executor and the reviewer that
judges it. Name them, and each reports the sessions it opened, which is what tells a trace apart:

```python
config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
executor = ClaudeCodeAgent(config, name="executor")
reviewer = ClaudeCodeAgent(config, name="reviewer")
...
exomyth.collect(agents={a.id: a.opened for a in (executor, reviewer)})
```

`opened` is the backend's id for every session the agent ever opened, including the ones a Ralph
loop dropped a turn later — ids, so a flow running for days remembers them in a list of strings.

[examples/](examples/) has the flow loops from flowbench written this way: `ralph_loop`, `goal`,
`flame_chase`, `stateful_ralph`, `continue_loop` and `rlar`.

### exomyth

```sh
exomyth collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects the trajectories recorded for a workspace and writes `.amflows/<datetime>.trace.json`.
Load it in [ui.perfetto.dev](https://ui.perfetto.dev) or `chrome://tracing`: sessions and
sub-agents become tracks, one slice per action, with prompt, reasoning, tool input and tool
output attached.

Each **agent** is one process. An agent is a configuration — a backend at a model at an effort —
together with every sub-agent it started, so a loop of one-shot sessions reads as one agent
rather than a hundred. A flow that drove the sessions itself knows better, and says so by passing
`agents=`, which is what tells two agents run at the same configuration apart.

```sh
exomyth collect                                   # current workspace, all history
exomyth collect ~/myproject --start "3 days ago"  # another workspace, recent history only
exomyth collect --session 0a1b2c3d,5f6e           # two sessions, wherever they ran
```

Trajectories are read from the backends' own home directories, named by `CLAUDE_CONFIG_DIR`,
`CODEX_HOME` and `KIMI_CODE_HOME` and falling back to `~/.claude`, `~/.codex` and `~/.kimi-code`;
a missing one is skipped. `amflows.exomyth.collect` takes the same arguments plus `agents`,
returns the trace document, and writes a file only when `output` is given.

### coganchor

```sh
coganchor --target ssh://build-box claude
coganchor --target ssh://gpu-01 codex exec "run the test suite"
```

The agent process stays here, keeping its credentials, its state directory and its link to its
model provider. Everything it *does* — reading and writing files, running commands, reaching the
network from them — happens on the target. It needs no plugin and no cooperation from the agent.

`--target` takes `ssh://HOST`, `tcp://HOST:PORT` or `local[:DIR]`; `--workspace` names the project
directory as it exists on the target; `--check` connects, reports what it found, and exits;
`--shadow` puts the local mirror somewhere other than the workspace path. Instead of reconnecting
over ssh each time, a target can be left listening:

```sh
# on the target
coganchor serve --listen 0.0.0.0:7777 --export /srv/project --token "$SECRET"
# on this machine
COGANCHOR_TOKEN=$SECRET coganchor --target tcp://build-box:7777 --workspace /srv/project claude
```

## Security

**A `coganchor serve` port is equivalent to a shell on that machine.** An export bounds which files
a request may name; it does not confine the commands that request can run. Give `--token` a real
secret, and prefer `ssh://`, which needs no open port at all.

The agent flows in [examples/](examples/) run their agents with permission prompts disabled, as
flowbench does. Run them only in a workspace you are willing to have rewritten.

## Maintainers

[@futrime](https://github.com/futrime)

## Contributing

PRs accepted. Open an issue to discuss a substantial change first.

```sh
uvx ruff format && uvx ruff check && uv run pytest
uv run pytest --run-agents  # also drives claude, codex and kimi for real
```

If you edit this README, please conform to the
[standard-readme](https://github.com/RichardLitt/standard-readme) specification.

## License

[Apache-2.0](LICENSE) © Zijian Zhang
