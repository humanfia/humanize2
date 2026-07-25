"""Knowing which files belong to the agent rather than to the project.

An agent's own binary, its bundled helpers and its state directory live on
this machine and must keep working here: rerouting ``~/.codex`` to the target
would lose the session, and rerouting the agent's own executable would make it
impossible to start.  Everything else the agent touches belongs to the target.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

__all__ = ["PROFILES", "AgentProfile", "ResolvedAgent", "profile_for", "resolve"]


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """What coganchor knows about one coding agent."""

    name: str
    #: Paths holding the agent's own state; always served from this machine.
    state_paths: tuple[str, ...] = ()


PROFILES: tuple[AgentProfile, ...] = (
    AgentProfile(
        name="claude",
        state_paths=(
            "~/.claude",
            "~/.claude.json",
            "~/.local/share/claude",
            "~/.cache/claude-cli-nodejs",
        ),
    ),
    AgentProfile(
        name="codex",
        state_paths=("~/.codex",),
    ),
    AgentProfile(
        name="kimi",
        state_paths=("~/.kimi-code", "~/.kimi"),
    ),
)

_BY_NAME = {profile.name: profile for profile in PROFILES}

#: Directories that hold per-user state for *any* agent and should never be
#: mirrored, even when the workspace happens to contain them.
COMMON_STATE_PATHS: tuple[str, ...] = (
    "~/.cache/amflows",
    "~/.config/amflows",
)


@dataclass(slots=True)
class ResolvedAgent:
    """A launchable agent plus the paths that stay on this machine."""

    profile: AgentProfile
    program: str
    argv: list[str]
    local_paths: list[str] = field(default_factory=list)
    local_programs: list[str] = field(default_factory=list)


def profile_for(name: str) -> AgentProfile:
    """Return the known profile for ``name``, or a permissive generic one."""
    return _BY_NAME.get(
        os.path.basename(name), AgentProfile(name=os.path.basename(name))
    )


def resolve(command: list[str]) -> ResolvedAgent:
    """Locate the agent named by ``command`` and classify its own files.

    Raises :class:`FileNotFoundError` if the program is not on ``PATH``.
    """
    if not command:
        raise ValueError("no agent command given")
    name = command[0]
    found = shutil.which(name) if os.path.sep not in name else name
    if not found or not os.path.exists(found):
        raise FileNotFoundError(f"{name}: not found on PATH")
    located = os.path.abspath(found)
    program = os.path.realpath(located)

    profile = profile_for(name)
    local_paths = [
        _expand(path) for path in (*profile.state_paths, *COMMON_STATE_PATHS)
    ]
    # Only the agent's own executable stays here -- enough for it to start and
    # to re-exec itself.  Bundled helpers such as ripgrep deliberately go to
    # the target: running them against the partly materialised mirror would
    # return quietly wrong answers, which is worse than a visible failure.
    local_programs = [located, program]
    interpreter = _shebang_interpreter(program)
    if interpreter:
        local_programs.append(interpreter)

    return ResolvedAgent(
        profile=profile,
        program=program,
        argv=[found, *command[1:]],
        local_paths=sorted({path for path in local_paths if path}),
        local_programs=sorted({path for path in local_programs if path}),
    )


def _expand(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def _shebang_interpreter(program: str) -> str | None:
    """Return the interpreter of a ``#!`` script, so its re-exec stays local."""
    try:
        with open(program, "rb") as handle:
            first = handle.readline(256)
    except OSError:
        return None
    if not first.startswith(b"#!"):
        return None
    parts = first[2:].decode("utf-8", "replace").strip().split()
    return parts[0] if parts else None
