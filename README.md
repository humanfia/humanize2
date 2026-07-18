# flowjanus

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

> Treat any coding agent as one interface, hiding which CLI actually runs.

flowjanus is a tiny library that puts a uniform face on coding-agent CLIs. An **agent** is
structure — a model at an effort level. A **session** is the conversation it runs on. A caller
programs against one `run(prompt)` method and picks per flow whether turns share context; whether
that dispatches to `claude`, `codex`, `kimi`, or an agent you add yourself is a detail behind the
class. It is pure standard-library Python (≥ 3.12) with **zero third-party dependencies**.

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
prompt, which flags they expect, and — most of all — how they name and reopen a conversation.
Claude lets you pin a session id up front; Codex prints one in its header; Kimi prints one in a
closing resume hint. Each of them also offers a "continue the newest session here" shortcut that
silently breaks the moment a second agent runs in the same directory.

flowjanus hides all of that. `SessionBase` owns the subprocess call, the stream teeing, and the
error handling; each backend is a small pair of subclasses that build their own command and read
their own session id back. Swapping the backend is swapping the class — the calling code does not
change.

Splitting the agent from the session is what makes both loop shapes expressible. A Ralph loop
wants a fresh session per turn, so the agent rereads the repository instead of its own history. A
stateful loop wants one session across every turn. Same agent, different session lifetime.

## Install

flowjanus is pure Python (≥ 3.12) with zero third-party dependencies.

From source, with [uv](https://docs.astral.sh/uv/):

```sh
git clone git@github.com:humanfia/flowjanus.git
cd flowjanus
uv sync
```

Or vendor it: copy `src/flowjanus/` into your project and
`from flowjanus.agents import ClaudeCodeAgent` works with no install.

The agents shell out to the backend CLIs, so the ones you use must be installed and authenticated
on `PATH`.

## Usage

```python
from flowjanus.agents import ClaudeCodeAgent, CodexAgent, KimiCodeCLIAgent

agent = ClaudeCodeAgent(model="claude-opus-4-8", effort="high")

# One turn in a throwaway session: nothing carries over to the next call.
print(agent.run("Summarize CHANGELOG.md in 5 bullets"))  # -> str

# Or a conversation that remembers, resumed under the hood on every turn after the first.
session = agent.start()
session.run("Refactor foo.py")
session.run("Now write tests for what you just changed")
print(session.session_id)  # the backend's id for that conversation

# same interface, different backend
print(CodexAgent(model="gpt-5-codex", effort="high").run("Write a pytest for utils.slugify"))
print(KimiCodeCLIAgent(model="kimi-code/k3", effort="high").start().run("Explain this repo"))
```

Two independent sessions never steal each other's history, so an executor can keep working while
a reviewer audits it from a clean slate — see [examples/arar.py](examples/arar.py).

Add your own backend by subclassing `SessionBase` and `AgentBase`:

```python
from flowjanus.agents import AgentBase, SessionBase


class AcmeSession(SessionBase):
    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        resume = ["--resume", self.session_id] if self.session_id else []
        argv = ["acme-bot", *resume, "--model", self.agent.model, "--effort", self.agent.effort]
        return argv, prompt  # (argv, stdin); stdin=None => the prompt is already inside argv

    def _read_session_id(self, transcript: str) -> str:
        return transcript.split("session=")[1].split()[0]


class AcmeAgent(AgentBase):
    def start(self) -> AcmeSession:
        return AcmeSession(self)


AcmeAgent(model="large", effort="high").start().run("hello")
```

## API

Everything is exported from the `flowjanus.agents` package.

- **`AgentBase(*, model: str, effort: str)`** — structure, and no history.
  - **`start() -> SessionBase`** — the one method a backend implements: create a new session,
    which stays unopened until its first turn.
  - **`run(prompt: str) -> str`** — one turn in a throwaway session, dropped on return.
- **`SessionBase(agent: AgentBase)`** — one conversation, across as many turns as you send it.
  - **`run(prompt: str) -> str`** — send one turn and return the agent's final text. The first
    call opens the backend session; every later one resumes it. Both of the agent's streams are
    teed through to yours as they arrive. A nonzero exit raises
    `subprocess.CalledProcessError` with both streams attached, and leaves the session unopened
    so the next call retries rather than resuming a session that may not exist.
  - **`session_id: str | None`** — the backend's id for this conversation, `None` until the
    first turn lands.
  - **`_turn(prompt) -> (argv, stdin)`** — what a backend implements: the command for one turn,
    which opens a session while `session_id` is `None` and resumes it once set.
  - **`_read_session_id(transcript) -> str`** — what a backend implements: read the session id
    out of everything the opening turn printed, on stdout and stderr alike.
- **`ClaudeCodeAgent`**, **`CodexAgent`**, **`KimiCodeCLIAgent`** and their
  **`ClaudeCodeSession`**, **`CodexSession`**, **`KimiCodeCLISession`** — the built-in backends.
  `kimi` has no effort knob, so `KimiCodeCLIAgent` ignores `effort`.

[examples/](examples) rewrites the flow loops from flowbench on this API.

## Maintainers

[@futrime](https://github.com/futrime)

## Contributing

PRs accepted. Open an issue to discuss a substantial change first.

```sh
uv run python -m pytest        # the plumbing is tested with `sh`-backed fakes; no real CLI needed
uvx ruff check && uvx ruff format --check
uv run python -m mypy
```

If you edit this README, please conform to the
[standard-readme](https://github.com/RichardLitt/standard-readme) specification.

## License

[MIT](LICENSE) © Zijian Zhang
