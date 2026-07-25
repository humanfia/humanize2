# amflows

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat-square)](LICENSE)

Orchestrate, execute, and observe agent flows

A flow is a coding agent driven in a loop. amflows is the three pieces that takes:

- **`amflows.janus`** runs Claude Code, Codex and Kimi Code behind one interface, as agents that
  hand out sessions.
- **`amflows.exomyth`** turns the trajectories they leave behind into a Chrome JSON trace.
- **`amflows.coganchor`** runs an agent on one machine and has it act on another.

## Table of Contents

- [Install](#install)
- [Usage](#usage)
- [Documentation](#documentation)
- [Security](#security)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Install

```sh
pip install git+https://github.com/humanfia/amflows.git
```

From source, with [uv](https://docs.astral.sh/uv/), which is also how you get
[examples/](examples/):

```sh
git clone git@github.com:humanfia/amflows.git
cd amflows
uv sync
```

### Dependencies

Python ≥ 3.12, and the coding agent CLIs you intend to drive (`claude`, `codex`, `kimi`) on your
PATH. [Isolation](docs/isolation.md) and [remote execution](docs/remote-execution.md) ask for more.

## Usage

Drive an [agent](docs/agents.md):

```python
from amflows.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))
agent.launch().run("Read TASK.md and get started.")
```

### CLI

Run a [flow](docs/flows.md) over the agents you name:

```sh
janus -f examples/ralph_loop.py -a claude/claude-opus-4-8/high "fix the build"
```

Collect what it left behind, and open the file in [ui.perfetto.dev](https://ui.perfetto.dev):

```sh
exomyth collect
```

Anchor an agent onto [another machine](docs/remote-execution.md):

```sh
coganchor --target ssh://build-box claude
```

## Documentation

- [Flows](docs/flows.md) — writing a flow and running it (`janus`)
- [Agents](docs/agents.md) — sessions, goals, models and efforts, names (`janus`)
- [Isolation](docs/isolation.md) — a container of the agent's own (`janus`)
- [Remote execution](docs/remote-execution.md) — acting on another machine (`coganchor`)
- [Tracing](docs/tracing.md) — trajectories into a trace (`exomyth`)

## Security

**A `coganchor serve` port is equivalent to a shell on that machine.** An export bounds which files
a request may name; it does not confine the commands that request can run. Give `--token` a real
secret, and prefer `ssh://` or `docker://`, which need no open port at all.

**janus runs every agent with permission prompts disabled**, as flowbench does, and there is no
setting that turns them back on. Drive one only in a workspace you are willing to have rewritten —
including under [isolation](docs/isolation.md), which confines the agent to a container of its own
but mounts that workspace into it.

## Maintainers

[@futrime](https://github.com/futrime)

## Contributing

PRs accepted. Ask a question or discuss a substantial change first in
[issues](https://github.com/humanfia/amflows/issues). A change must pass:

```sh
uvx ruff format && uvx ruff check && uv run pytest
uv run pytest --run-agents  # also drives claude, codex and kimi for real
```

If you edit this README, please conform to the
[standard-readme](https://github.com/RichardLitt/standard-readme) specification.

## License

[Apache-2.0](LICENSE) © Zijian Zhang
