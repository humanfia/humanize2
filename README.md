# humanize

![humanize](https://socialify.git.ci/humanfia/humanize2/image?description=1&font=Raleway&forks=1&issues=1&logo=https%3A%2F%2Fgithub.com%2Fhumanfia%2Fhumanize2%2Fraw%2Frefs%2Fheads%2Fmain%2Fdocs%2Fpublic%2Flogo.svg&name=1&owner=1&pattern=Circuit+Board&pulls=1&stargazers=1&theme=Auto)

[![CI](https://github.com/humanfia/humanize2/actions/workflows/ci.yml/badge.svg)](https://github.com/humanfia/humanize2/actions/workflows/ci.yml)
[![docs](https://github.com/humanfia/humanize2/actions/workflows/build-docs.yml/badge.svg)](https://humanfia.github.io/humanize2/)
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
[Security](https://humanfia.github.io/humanize2/guide/security):

- humanize runs every agent with **permission prompts disabled**, and nothing turns them back on.
- **A flow is a Python file, and reading one means running it**, so adding a flowverse is trusting
  that repository with this machine.
- **An `hmz anchor` port is equivalent to a shell on that machine.**

## Install

```sh
pip install git+https://github.com/humanfia/humanize2.git
```

Needs Python ≥ 3.12 and at least one of the coding agent CLIs it drives — `claude`, `codex`,
`kimi`, `pi`, `opencode`, `mimo` — on your PATH. See
[Installation](https://humanfia.github.io/humanize2/guide/installation).

## Usage

To use the TUI:

```sh
hmz
```

To run a flow over the agents you name, one `-a` apiece:

```sh
hmz exec -f official/flame_chase \
    -a claude/claude-opus-4-8:high -a codex/gpt-5.6-sol:high "fix the build"
```

To collect what a run left behind, and open it in [ui.perfetto.dev](https://ui.perfetto.dev):

```sh
hmz collect
```

[Getting started](https://humanfia.github.io/humanize2/guide/getting-started) goes from here to a
run you can read back.

## Documentation

**[humanfia.github.io/humanize2](https://humanfia.github.io/humanize2/)** — tutorials, a page per
feature, and the complete CLI, TUI and Python reference. Its source is under [docs/](docs/).

## Maintainers

[@futrime](https://github.com/futrime)

## Contributing

PRs accepted. Ask a question or discuss a substantial change first in
[issues](https://github.com/humanfia/humanize2/issues), and see
[Contributing](https://humanfia.github.io/humanize2/contributing/) for the checks a commit has to
pass.

```sh
uv sync
uv run pre-commit install
```

If you edit this README, please conform to the
[standard-readme](https://github.com/RichardLitt/standard-readme) specification.

## License

[Apache-2.0](LICENSE) © Zijian Zhang
