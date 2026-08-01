"""The skills a coding agent CLI would load, found the way that CLI finds them.

Here rather than beside the sheet that offers them, because both halves need the same list:
whatever is asking a person which skills an agent is to have, and the driver that then has to
tell the backend. An agent is configured with the skills it has, so what a backend is told is
the rest of them -- and the rest of what is only knowable by looking.

Nothing is asked of the CLI itself, for the reason nothing else here asks it either: starting
one costs seconds a prompt does not have. Where each of them looks is written down in
:mod:`hmz.backends`, and reading a `SKILL.md` is reading its front matter and stopping.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz.backends import named

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["Skill", "leaving", "skills"]

#: How much of a `SKILL.md` is read to find its front matter. The front matter is at the top
#: and the rest of the file is the skill itself, which can be a hundred kilobytes of prose.
_FRONT = 4096

#: What front matter is fenced with, and how little of a description a row has room for.
_FENCE = "---"
_ABOUT = 90


@dataclass(frozen=True, slots=True)
class Skill:
    """One skill a backend would load.

    Attributes:
      name: What the CLI knows it by, which is what a turn is told about: the name in its
        front matter, or the directory it is in where it states none -- which is the rule
        every one of these CLIs reads a skill by.
      about: The line it describes itself with, which is what says whether to switch it off.
      whose: Where it came from: yours, or this project's.
    """

    name: str
    about: str
    whose: str


def skills(backend: str, where: Path | str | None = None) -> list[Skill]:
    """The skills one backend would load here, the way that backend finds them.

    Args:
      backend: The CLI, by any name it answers to.
      where: The project whose own skills to include, defaulting to this directory.

    Returns:
      One entry per skill, yours before the project's and each set in the order it is on disk.
      Empty for a backend that is not known here, keeps none, or has none installed.
    """
    profile = named(backend)
    if profile is None:
        return []
    found: list[Skill] = []
    seen: set[str] = set()
    for root, globs, whose in (
        (profile.directory(), profile.skills, "yours"),
        # Under your own home rather than the backend's, and so not moved by whatever moves
        # that: `.agents` is the directory more than one of these has agreed to read.
        (Path.home(), profile.shared, "yours"),
        (Path(where or Path.cwd()), profile.works, "this project"),
    ):
        for pattern in globs:
            for path in sorted(root.glob(pattern)):
                skill = _skill(path, whose)
                # One name is one skill: a project's own of the same name is the same skill
                # to the CLI, which loads whichever of them it prefers and lists it once.
                if skill is not None and skill.name not in seen:
                    seen.add(skill.name)
                    found.append(skill)
    return found


def leaving(
    backend: str, wanted: Iterable[str] | None, where: Path | str | None = None
) -> list[str]:
    """The skills to switch off, for an agent that is to have the ones it was given.

    An agent says which skills it has rather than which it has not, because that is what a
    person chose from a list of them -- and every backend here is told the other way round,
    since a CLI comes with all of its skills loaded and has to be talked out of one. Which
    ones those are is only knowable by looking, so this is where the looking happens.

    Args:
      backend: The CLI, by any name it answers to.
      wanted: The skills the agent is to have, or None for the CLI as it comes -- which is
        every skill it finds, and so nothing to switch off.
      where: The project whose own skills count, defaulting to this directory.

    Returns:
      The names to switch off, in the order the CLI would have loaded them, and nothing at
      all for an agent that was never told which skills to have.
    """
    if wanted is None:
        return []
    having = set(wanted)
    return [one.name for one in skills(backend, where) if one.name not in having]


def _skill(path: Path, whose: str) -> Skill | None:
    """One `SKILL.md`, read as the CLI reads it: its front matter, and nothing else.

    Args:
      path: The file.
      whose: Where it came from.

    Returns:
      The skill, or None for a file that cannot be read at all.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            head = stream.read(_FRONT)
    except OSError:
        return None
    front: Any = {}
    if head.startswith(_FENCE):
        _, _, rest = head.partition("\n")
        block, _, _ = rest.partition(f"\n{_FENCE}")
        with contextlib.suppress(yaml.YAMLError):
            front = yaml.safe_load(block)
    said = cast("dict[str, Any]", front) if isinstance(front, dict) else {}
    # The directory is the name where the front matter states none, which is the rule these
    # CLIs read a skill by -- the file is always `SKILL.md`.
    name = str(said.get("name") or path.parent.name).strip()
    about = " ".join(str(said.get("description") or "").split())
    return Skill(
        name=name,
        about=about[:_ABOUT] + ("…" if len(about) > _ABOUT else ""),
        whose=whose,
    )
