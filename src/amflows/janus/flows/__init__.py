"""Where a flow is found, and what there is to find.

Named rather than pathed: `amflows run -f ralph_loop` is a name, and anything with a slash or
an extension in it is a file taken as given. A name is looked for in this project first, then
in yours, then among the ones amflows came with -- so a flow of your own may stand in for one
of amflows' by taking its name, and a project may stand in for both.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["find", "found", "where"]

#: Where flows live, nearest first, and what to call each place on screen. Kept unresolved:
#: the project one is relative to wherever amflows is being run, and `~` is whoever is
#: running it, neither of which is settled when this is imported.
where = (
    ("this project", ".amflows/flows"),
    ("yours", "~/.amflows/flows"),
    ("amflows", str(Path(__file__).parent)),
)


def found() -> list[tuple[str, str]]:
    """Every flow there is to run, and where each came from.

    Returns:
      One `(where it came from, its name)` pair apiece, nearest first and alphabetical
      within each place. A name appears once: the nearest flow answering to it is the one
      that runs, so the ones it stands in for are not offered as if they still did.
    """
    listed: list[tuple[str, str]] = []
    taken: set[str] = set()
    for whose, folder in where:
        for path in sorted(Path(folder).expanduser().glob("*.py")):
            if path.stem.startswith("_") or path.stem in taken:
                continue
            taken.add(path.stem)
            listed.append((whose, path.stem))
    return listed


def find(named: str) -> str:
    """Where the flow called this is.

    Args:
      named: A flow's name, or the path to a file taken as given.

    Returns:
      The path to run: the nearest flow of that name, or `named` itself if nothing answers
      to it -- which is what makes a path work wherever a name does. Resolved, since a flow
      is free to change the working directory the name was resolved against.
    """
    for _, folder in where:
        beside = Path(folder).expanduser() / f"{named}.py"
        if beside.is_file():
            return str(beside.resolve())
    return named
