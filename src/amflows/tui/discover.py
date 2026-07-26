"""Which agents are installed here, and what each one runs.

Nothing is typed in: a backend that is not on this machine is not offered, and an effort a
model does not take is not offered against it.

Nothing is asked of the backends either. Asking means starting one, and starting one costs
what it costs -- measured on the machine this was written on, `claude --help` took over
thirty seconds, `codex app-server` seventy-six, and `kimi web` about a minute. A prompt
cannot wait on that. What they run is written down here instead, taken from the answers
those same backends gave when they were asked; Claude's own cache is read as well, because
which models an account may run is the one part of this that is not the same for everyone.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Model", "installed"]


@dataclass(frozen=True, slots=True)
class Model:
    """One model a backend runs, and the efforts it runs at.

    Attributes:
      name: What to ask the backend for.
      efforts: The efforts this model takes, which is not always all of them.
    """

    name: str
    efforts: tuple[str, ...]


#: What Claude Code documents on its own command line, for every model it runs.
_CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")

#: What each backend runs, as each of them reported it. Codex says which efforts each of its
#: models takes and they differ, so they are written down as it gave them.
_RUNS: dict[str, tuple[Model, ...]] = {
    "claude": (
        Model("opus", _CLAUDE_EFFORTS),
        Model("sonnet", _CLAUDE_EFFORTS),
        Model("fable", _CLAUDE_EFFORTS),
    ),
    "codex": (
        Model("gpt-5.6-sol", ("low", "medium", "high", "xhigh", "max", "ultra")),
        Model("gpt-5.6-terra", ("low", "medium", "high", "xhigh", "max", "ultra")),
        Model("gpt-5.6-luna", ("low", "medium", "high", "xhigh", "max")),
        Model("gpt-5.5", ("low", "medium", "high", "xhigh")),
    ),
    "kimi": (
        Model("kimi-code/k3", ("low", "medium", "high", "max")),
        Model("kimi-code/k3-256k", ("low", "medium", "high", "max")),
        Model("kimi-code/kimi-for-coding", ("low", "medium", "high", "max")),
    ),
}

#: Where Claude Code keeps the models this account may run.
_CLAUDE_CACHE = Path.home() / ".claude.json"


def installed() -> dict[str, tuple[Model, ...]]:
    """The backends on this machine, and what each runs.

    Costs a `which` apiece and one file read, so it can be asked for at a prompt.

    Returns:
      One entry per backend that is on this machine, as its models.
    """
    found = {
        backend: models
        for backend, models in _RUNS.items()
        if shutil.which(backend) is not None
    }
    if "claude" in found:
        found["claude"] = _claude()
    return found


def _claude() -> tuple[Model, ...]:
    """Claude's models: the ones it documents, plus the ones this account may run.

    Returns:
      Every model, each at every effort Claude documents.
    """
    named = {model.name for model in _RUNS["claude"]}
    try:
        held = json.loads(_CLAUDE_CACHE.read_text())
    except (OSError, ValueError):
        held = {}
    named |= {
        str(option["value"])
        for option in held.get("additionalModelOptionsCache") or []
        if isinstance(option, dict) and option.get("value")
    }
    return tuple(Model(name, _CLAUDE_EFFORTS) for name in sorted(named))
