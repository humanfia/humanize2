# humanize

![humanize](https://socialify.git.ci/humanfia/humanize2/image?description=1&font=Raleway&forks=1&issues=1&logo=https%3A%2F%2Fraw.githubusercontent.com%2Fhumanfia%2Fhumanize2%2Frefs%2Fheads%2Fmain%2Fdocs%2Fpublic%2Flogo.svg&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Auto)

[![CI](https://github.com/humanfia/humanize2/actions/workflows/ci.yml/badge.svg)](https://github.com/humanfia/humanize2/actions/workflows/ci.yml)
[![docs](https://github.com/humanfia/humanize2/actions/workflows/build-docs.yml/badge.svg)](https://docs.humanfia.ai/humanize2/)
[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat-square)](LICENSE)

Orchestrate, execute, and observe agent flows

humanize runs flows over coding agents; whoever writes a flow is a **weaver**.

## Table of Contents

- [Security](#security)
- [Install](#install)
- [Usage](#usage)
- [Documentation](#documentation)
- [Maintainers](#maintainers)
- [Contributing](#contributing)
- [License](#license)

## Security

Three things to know before pointing one at a repository you care about. Each is explained in
[Security](https://docs.humanfia.ai/humanize2/user/security):

- humanize runs every agent with **permission prompts disabled**, and nothing turns them back on.
- **A flow is a directory of Python, and reading one means running it**, so adding a flowverse
  is trusting that repository with this machine.
- **An `hmz anchor` port is equivalent to a shell on that machine.**
- humanize asks, once, whether to **report what goes wrong** to its developers, and says what
  a report carries before you answer. Nothing is sent by a machine that has not answered yes:
  `HUMANIZE_SENTRY=off` settles it for a scripted install, and `/settings` changes it later.

## Install

```sh
pip install git+https://github.com/humanfia/humanize2.git
```

DeepSeek Harness arrives with humanize: its Python SDK and the runtime its turns are taken on
are ordinary dependencies, so there is nothing extra to install for it.

To install DeepSeek's own `dsh` launcher and configuration UI (Node.js required):

```sh
npm install --global @deepseek-ai/dsh
dsh web
```

Needs Python ≥ 3.12 and at least one supported backend: `agy`, `claude`, `codex`,
`cursor-agent`, `grok`, `kimi`, `pi`, `qwen`, `opencode`, `mimo` or `zcode` on your PATH — or
none of them, since DeepSeek Harness arrives with humanize. See
[Installation](https://docs.humanfia.ai/humanize2/user/installation).

## Usage

To use the TUI:

```sh
hmz
```

The run is held apart from the terminal, so closing the terminal does not end it: `/detach`
lets go of the terminal and leaves the flow running, `hmz` in the same directory opens it
again, and `hmz daemon list` says what is being held where.

DeepSeek Harness takes an API key and no subscription login. Run `dsh web`, save the key
under **Settings -> Models**, then open `/flow` in humanize, turn to its agents, set one to
`dsh` and leave its account row on `as local` — which uses the key and the base URL saved in
dsh. Alternatively, press **a** on that row to make a humanize `key` account, or set the key
before opening humanize:

```sh
export DEEPSEEK_API_KEY=sk-…
hmz
```

To run a flow over the agents you name, one `-a` apiece:

```sh
hmz exec -f official/flame_chase \
    -a claude/claude-opus-4-8:high -a codex/gpt-5.6-sol:high "fix the build"
```

To run DeepSeek Harness unattended with that environment variable:

```sh
DEEPSEEK_API_KEY=sk-… hmz exec -f ralph_loop \
    -a dsh/deepseek-v4-flash:high "fix the build"
```

To collect what a run left behind, and open it in [ui.perfetto.dev](https://ui.perfetto.dev):

```sh
hmz trace collect
```

The [quickstart](https://docs.humanfia.ai/humanize2/#run-a-flow) goes from here to a run you can
read back. The home page has one for each role: running a flow, weaving one, and working on
humanize itself.

## Documentation

**[docs.humanfia.ai/humanize2](https://docs.humanfia.ai/humanize2/)**, in six parts. Its source is under
[docs/](docs/).

- **[Features](https://docs.humanfia.ai/humanize2/features/)** — what humanize does, a diagram each.
- **[Flows](https://docs.humanfia.ai/humanize2/flows/)** — every flow it can run, from `chat` to seven
  agents in three isolated lanes, with the shape of each one drawn.
- **[User Guide](https://docs.humanfia.ai/humanize2/user/)** — running flows. Tutorials first, then a
  page per feature, each opening with something you can paste.
- **[Weaver Guide](https://docs.humanfia.ai/humanize2/weaver/)** — weaving them. Tutorials first, then a
  page per thing a flow may be written to do.
- **[Contributing](https://docs.humanfia.ai/humanize2/contributing/)** — working on humanize itself: the
  checks a commit has to pass, the layers of the code, and these docs.
- **[Reference](https://docs.humanfia.ai/humanize2/reference/)** — the complete CLI, TUI and Python API.

## Maintainers

[@futrime](https://github.com/futrime), [@SihaoLiu](https://github.com/SihaoLiu), [@lyken17](https://github.com/lyken17).

This project was initiated by Sihao Liu at UCLA [PolyArch/humanize](https://github.com/PolyArch/humanize), then contributed
by NVIDIA Research, MIT HAN LAB, NUNCHAKU and many community members.

## Contributing

PRs accepted. Ask a question or discuss a substantial change first in
[issues](https://github.com/humanfia/humanize2/issues), and see
[Contributing](https://docs.humanfia.ai/humanize2/contributing/) for the checks a commit has to
pass.

```sh
uv sync
uv run pre-commit install
```

If you edit this README, please conform to the
[standard-readme](https://github.com/RichardLitt/standard-readme) specification.

## License

[Apache-2.0](LICENSE)
