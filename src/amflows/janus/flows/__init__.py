"""The flows that come with amflows, which are the loops from flowbench written as flows.

Named rather than pathed: `amflows run -f ralph_loop` is one of these, and anything with a
slash or an extension in it is a file of your own.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["find", "prebuilt"]


def prebuilt() -> list[str]:
    """The flows that come with amflows, by the name they are run under.

    Returns:
      Every name, in alphabetical order.
    """
    return sorted(
        path.stem
        for path in Path(__file__).parent.glob("*.py")
        if not path.stem.startswith("_")
    )


def find(named: str) -> str:
    """Where the flow called this is, whether it came with amflows or not.

    Args:
      named: A prebuilt flow's name, or the path to a file of your own.

    Returns:
      The path to run, which is `named` itself unless it names a prebuilt flow.
    """
    beside = Path(__file__).parent / f"{named}.py"
    return str(beside) if beside.is_file() else named
