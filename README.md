# flowjanus

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

> Treat any coding agent as one interface, hiding which CLI actually runs.

flowjanus is a tiny library that puts a uniform face on coding-agent CLIs. A caller programs against
one `run(prompt)` method; whether that dispatches to `claude`, `codex`, `kimi`, or an agent you add
yourself is a detail behind the class. It is pure standard-library Python (≥ 3.12) with **zero
third-party dependencies**.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [API](#api)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Background

The concrete agents (`claude --print`, `codex exec`, `kimi --prompt`) differ in how they take a
prompt and which flags they expect. flowjanus hides that: `AgentBase` owns the subprocess call and
error handling, and each backend is a small subclass that only builds its command. Swapping the
backend is swapping the class — the calling code does not change.

## Install

flowjanus is pure Python (≥ 3.12) with zero third-party dependencies.

From source, with [uv](https://docs.astral.sh/uv/):

```sh
git clone git@github.com:humanfia/flowjanus.git
cd flowjanus
uv sync
```

Or vendor it: copy `src/flowjanus/` into your project and `from flowjanus import ClaudeCodeAgent`
works with no install.

The agents shell out to the backend CLIs, so the ones you use must be installed and authenticated on
`PATH`.

## Usage

```python
from flowjanus import ClaudeCodeAgent, CodexAgent, KimiCodeCLIAgent

agent = ClaudeCodeAgent(model="claude-opus-4-8", effort="high")
print(agent.run("Summarize CHANGELOG.md in 5 bullets"))  # -> str

# same interface, different backend
print(CodexAgent(model="gpt-5-codex").run("Write a pytest for utils.slugify"))
print(KimiCodeCLIAgent(model="kimi-code/k3").run("Explain this repo"))
```

Add your own agent by subclassing `AgentBase` and building its command:

```python
from flowjanus import AgentBase


class AcmeAgent(AgentBase):
    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        argv = ["acme-bot", "--json"]
        if self.model:
            argv += ["--model", self.model]
        return argv, prompt  # (argv, stdin); stdin=None => prompt is inside argv


AcmeAgent(model="large").run("hello")
```

## API

Everything is re-exported from the `flowjanus` package.

- **`AgentBase(*, model=None, effort=None, timeout=None, cwd=None)`** — base class.
  - **`run(prompt: str) -> str`** — run one turn, return the agent's final text, raise `AgentError`
    on a nonzero exit.
  - **`_command(prompt: str) -> tuple[list[str], str | None]`** — the one method a subclass
    implements: return `(argv, stdin)`, where `stdin=None` means the prompt is already in `argv`.
- **`ClaudeCodeAgent`**, **`CodexAgent`**, **`KimiCodeCLIAgent`** — the built-in backends.
- **`AgentError`** — raised when the underlying CLI exits nonzero.

## Maintainers

[@futrime](https://github.com/futrime)

## Contributing

PRs accepted. Open an issue to discuss a substantial change first.

```sh
uv run python -m pytest        # base is tested with a `cat`-backed fake agent; no real CLI needed
uvx ruff check && uvx ruff format --check
```

If you edit this README, please conform to the
[standard-readme](https://github.com/RichardLitt/standard-readme) specification.

## License

[MIT](LICENSE) © Zijian Zhang
