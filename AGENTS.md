# AGENTS.md

For code:

- MUST pass `uv run pre-commit run --all-files` and `uv run pytest`.
- PREFER use popular and well-maintained libraries rather than custom implementations.
- MUST also update `humanfia/flowverse` to ensure them working if any changes affect flow impl.

For `specs/*.md`:

- MUST strictly adhere to specs at `specs/`.
- MUST NOT modify any SPEC UNLESS explicitly instructed to do so.
- MUST keep code minimal while strictly adhering to the SPEC.

For version control:

- MUST adhere to [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
- MUST delete local branches or worktrees once merged.

For docs:

- MUST update docs once any impl changes to avoid misalignment between code and docs.
- MUST adhere to the minimal spec of [Standard Readme](https://raw.githubusercontent.com/RichardLitt/standard-readme/refs/heads/main/spec.md) for `README.md`.
