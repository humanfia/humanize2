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
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

__all__ = ["Model", "installed"]


@dataclass(frozen=True, slots=True)
class Model:
    """One model a backend runs, and the efforts it runs at.

    Attributes:
      name: What to ask the backend for.
      efforts: The efforts this model takes, which is not always all of them.
      swarms: Whether it also runs a turn as a fleet of subagents rather than as one agent,
        which is a second thing to say about a turn and not a harder version of the first --
        so it is chosen alongside the effort rather than among them.
    """

    name: str
    efforts: tuple[str, ...]
    swarms: bool = False


#: What Claude Code documents on its own command line, for every model it runs, and above
#: them the one it does not document but takes: `ultracode` is `xhigh` with the turn opted
#: into orchestrating a fleet of its own, which is more work than any single-agent effort and
#: so is the top of this list. Hardest first, as every effort here is: the one to reach for
#: is the one at the top.
_CLAUDE_EFFORTS = ("ultracode", "max", "xhigh", "high", "medium", "low")

#: What each backend runs, as each of them reported it. Codex says which efforts each of its
#: models takes and they differ, so they are written down as it gave them.
#:
#: Model ids only, never the aliases a backend also answers to. `opus` is whichever Opus is
#: newest today and something else tomorrow, so a cycle that recorded it says nothing about
#: what actually ran -- and two runs of one flow a month apart would not be comparable.
#:
#: Written down in the order they are offered in, which is by tier and then newest first:
#: fable before opus before sonnet before haiku, and 5 before 4.8. Nothing sorts them, because
#: nothing can -- a tier is not in the name and a version is not a number.
_RUNS: dict[str, tuple[Model, ...]] = {
    "claude": (
        Model("claude-fable-5", _CLAUDE_EFFORTS),
        Model("claude-opus-5", _CLAUDE_EFFORTS),
        Model("claude-opus-4-8", _CLAUDE_EFFORTS),
        Model("claude-opus-4-7", _CLAUDE_EFFORTS),
        Model("claude-opus-4-6", _CLAUDE_EFFORTS),
        Model("claude-sonnet-5", _CLAUDE_EFFORTS),
        Model("claude-sonnet-4-6", _CLAUDE_EFFORTS),
        Model("claude-haiku-4-5", _CLAUDE_EFFORTS),
    ),
    "codex": (
        Model("gpt-5.6-sol", ("ultra", "max", "xhigh", "high", "medium", "low")),
        Model("gpt-5.6-terra", ("ultra", "max", "xhigh", "high", "medium", "low")),
        Model("gpt-5.6-luna", ("max", "xhigh", "high", "medium", "low")),
        Model("gpt-5.5", ("xhigh", "high", "medium", "low")),
    ),
    "kimi": (
        Model("kimi-code/k3", ("max", "high", "medium", "low"), swarms=True),
        Model("kimi-code/k3-256k", ("max", "high", "medium", "low"), swarms=True),
        Model(
            "kimi-code/kimi-for-coding", ("max", "high", "medium", "low"), swarms=True
        ),
    ),
}

#: Where Claude Code keeps the models this account may run.
_CLAUDE_CACHE = Path.home() / ".claude.json"

#: What a context window is written as on the end of a model Claude Code offers. It is a way
#: of running the model rather than a model, and a backend asked for one answers that there is
#: no such model.
_WINDOW = re.compile(r"\[[^\]]*\]$")


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
      Every model this account can name, newest first among the ones written down here and
      the rest after them, each at every effort Claude documents.
    """
    known = [model.name for model in _RUNS["claude"]]
    try:
        held: Any = json.loads(_CLAUDE_CACHE.read_text())
    except (OSError, ValueError):
        held = {}
    # `claude-fable-5[1m]` is that model at its largest window, which is a setting and not a
    # model: the id is what the backend answers to, and the window rides along with it.
    account = sorted(
        {
            _WINDOW.sub("", str(cast("dict[str, Any]", option)["value"]))
            for option in cast(
                "list[Any]", held.get("additionalModelOptionsCache") or []
            )
            if isinstance(option, dict) and cast("dict[str, Any]", option).get("value")
        }
    )
    named = known + [name for name in account if name not in known]
    return tuple(Model(name, _CLAUDE_EFFORTS) for name in named)
