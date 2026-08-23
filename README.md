# humanize

![humanize](https://socialify.git.ci/humanfia/humanize2/image?description=1&font=Raleway&forks=1&issues=1&logo=https%3A%2F%2Fgithub.com%2Fhumanfia%2Fhumanize2%2Fraw%2Frefs%2Fheads%2Fmain%2Fdocs%2Fpublic%2Flogo.svg&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Auto)

[![CI](https://github.com/humanfia/humanize2/actions/workflows/ci.yml/badge.svg)](https://github.com/humanfia/humanize2/actions/workflows/ci.yml)
[![docs](https://github.com/humanfia/humanize2/actions/workflows/build-docs.yml/badge.svg)](https://docs.humanfia.ai/humanize2/)
[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg?style=flat-square)](LICENSE)

Orchestrate, execute, and observe agent flows

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
[Security](https://docs.humanfia.ai/humanize2/guide/security):

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

Needs Python ≥ 3.12 and at least one supported backend: `agy`, `claude`, `codex`, `grok`,
`kimi`, `pi`, `qwen`, `opencode` or `mimo` on your PATH — or none of them, since DeepSeek
Harness arrives with humanize. See
[Installation](https://docs.humanfia.ai/humanize2/guide/installation).

## Usage

To use the TUI:

```sh
hmz
```

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

[Quickstart](https://docs.humanfia.ai/humanize2/tutorials/quickstart) goes from here to a run you can
read back, in fifteen minutes.

## Documentation

**[docs.humanfia.ai/humanize2](https://docs.humanfia.ai/humanize2/)**, in four parts. Its source is under
[docs/](docs/).

- **[Tutorials](https://docs.humanfia.ai/humanize2/tutorials/)** — six, in order. A quickstart, three real
  pieces of work run end to end, and two flows written from scratch.
- **[Guides](https://docs.humanfia.ai/humanize2/guide/)** — a page per feature, each answering "how do I
  use this?" and opening with something you can paste.
- **[Features](https://docs.humanfia.ai/humanize2/features/)** — what humanize does, described in one page.
- **[Reference](https://docs.humanfia.ai/humanize2/reference/cli)** — the complete CLI, TUI and Python API.

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
