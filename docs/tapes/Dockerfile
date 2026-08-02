# The world the demo GIFs are recorded in: VHS, humanize built out of this checkout, and a
# stand-in for the coding agent CLIs.
#
# Nothing in here signs in to anything, and nothing in here is yours: the demos run in this
# container's own scratch home, in a throwaway project, so a recording cannot pick up an
# account, a path or a hostname. See README.md beside this file.
#
# Built and run by ./render.sh, from the repository root as its context.

FROM ghcr.io/charmbracelet/vhs:v0.11.0

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# humanize out of this checkout rather than out of a release, so a demo is of the code beside
# it. Only what the build backend reads, so editing a tape does not rebuild the environment.
COPY pyproject.toml README.md LICENSE /src/
COPY src /src/src
RUN uv venv /opt/hmz \
    && uv pip install --python /opt/hmz/bin/python /src \
    && rm -rf /root/.cache

COPY docs/tapes/standin /opt/standin
COPY docs/tapes/stage.py /opt/stage.py

ENV PATH=/opt/hmz/bin:/opt/standin:$PATH \
    HUMANIZE_HOME=/root/.humanize \
    CLAUDE_CONFIG_DIR=/root/.claude \
    CODEX_HOME=/root/.codex \
    TERM=xterm-256color

# Staged at build time so a tape spends its frames on humanize rather than on `mkdir`.
RUN /opt/hmz/bin/python /opt/stage.py
