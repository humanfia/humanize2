# AGENTS.md

For code:

- MUST pass `uv run pre-commit run --all-files` and `uv run pytest`.
- PREFER use popular and well-maintained libraries rather than custom implementations.
- MUST also update `humanfia/flowverse` to ensure them working if any changes affect flow impl.

For `specs/*.md`:

- MUST read a package's SPEC at `specs/`, in a file named for the package: `specs/agents.md`
  binds `src/hmz/agents`. A package no file is named for is bound by the nearest one above it
  that has a file, and `specs/SPEC.md` binds `src/hmz` itself.
- MUST NOT modify any SPEC UNLESS explicitly instructed to do so.
- MUST keep code minimal while strictly adhering to the SPEC.

For commits:

- MUST adhere to [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

For docs:

- MUST update docs once any impl changes lead to misalignment between code and docs.
- MUST adhere to the minimal spec of [Standard Readme](https://raw.githubusercontent.com/RichardLitt/standard-readme/refs/heads/main/spec.md) for all `README.md`.
