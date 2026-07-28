# AGENTS.md

- MUST pass `uv run ruff format`, `uv run ruff check` and `uv run pyright` without errors or
  warnings. Run through `uv run`, not `uvx`: the lockfile is what pins the versions the hooks
  and CI enforce, and `uvx` fetches whatever is newest instead.
- MUST adhere to the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) for Python code UNLESS enforced by Ruff.
- MUST add type annotations everywhere and not violate them.
- MUST inline functions with less than 25 lines and used in less than 3 places.
- MUST NOT roll your own; always use existing libraries if it is well-maintained and widely used.

- MUST adhere to [Standard Readme](https://raw.githubusercontent.com/RichardLitt/standard-readme/refs/heads/main/spec.md) for Markdown files.
- MUST NOT introduce how it works in README.md; only describe what it does and how to use it.

- MUST NOT modify SPEC.md UNLESS explicitly instructed to do so.
- MUST keep code minimal while strictly adhering to SPEC.md.
