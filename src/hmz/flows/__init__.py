"""What a flow is called, where it is found, and how a file says it holds more than one.

Named rather than pathed: `hmz exec -f ralph_loop` is a name, and anything with a slash or an
extension in it is a file taken as given. A name is looked for in the places flows come from --
the ones humanize ships, the ones its own repository holds, whatever [flowverses](verses.py)
have been added, and then this project's own directory and yours -- so a flow of your own may
stand in for one of humanize's by taking its name.

A flow is a function marked with :func:`flow`, and nothing else is one. `@flow()` is the flow
its file holds under the file's own name; `@flow(name="draft")` is one of several a file holds,
called `<file>:draft` -- so that three phases of one thing live in one file and are three things
to run. What the function is called is the file's own business: `run`, `main`, `draft_it`, all
the same to a name that never mentions it.
"""

from __future__ import annotations

import contextlib
import os
import runpy
import sys
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, overload

from .verses import BUILTIN, OFFICIAL, Flowverse, flowverses

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "BUILTIN",
    "BUILTIN_AT",
    "OFFICIAL",
    "Flow",
    "Flowverse",
    "Offer",
    "find",
    "flow",
    "flowverses",
    "found",
    "held",
    "loaded",
    "where",
]

#: Where the flows humanize itself ships are: a directory of them, as a flowverse is, rather
#: than beside this file -- what is beside this file is how a flow is found, which is not one.
BUILTIN_AT = Path(__file__).parent / "builtin"

#: What a flow's own name is separated from the one inside its file by. A file that holds one
#: flow is named by itself; one that holds three names each of them after it.
_INSIDE = ":"

#: Where a flow of your own lives, nearest first, and what to call each place on screen. Kept
#: unresolved: the project one is relative to wherever humanize is being run, and `~` is
#: whoever is running it, neither of which is settled when this is imported.
#:
#: Looked in with `os.path` and `glob` rather than `pathlib`: a place that cannot be read, or
#: a `~` with no home behind it, is a place with no flows in it. The os functions say that;
#: the pathlib ones raise, which would make an unreadable `.humanize/flows` in this directory
#: the reason a flow humanize itself came with could not be found.
where = (
    ("local", ".humanize/flows"),
    ("user", "~/.humanize/flows"),
)


@dataclass(frozen=True, slots=True)
class Flow:
    """What a flow says about itself where it is written.

    Attributes:
      name: What it is called inside its file, which is the half after the colon. "" for the
        one a file holds under its own name, which is what `@flow()` marks.
      about: One line saying what it does, for whoever is choosing between them. Read off the
        function's own docstring where the decorator was not told one, and off the file's
        where the file is one flow and its function says nothing.
    """

    name: str = ""
    about: str = ""


#: Where a decorated function keeps what it said about itself. On the function rather than in
#: a table, because a file is read by running it: a table would be one more thing to find,
#: and this travels with the thing it describes.
_SAID = "__humanize_flow__"


@overload
def flow[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def flow[**P, T](
    *, name: str = "", about: str = ""
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def flow[**P, T](
    call: Callable[P, T] | None = None, /, *, name: str = "", about: str = ""
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a flow. Nothing else is one.

    Written with no name, it is the flow its file holds under the file's own name::

        @flow
        def run(agents: tuple[AgentBase], task: str) -> None:
            ...

    is `ralph_loop`, in `ralph_loop.py`. Written with one, it is one of several that file
    holds, and is called `<file>:<name>`::

        @flow(name="gen-idea", about="opens a loose idea into a repo-grounded draft")
        def first_pass(agents: Agents, task: str) -> None:
            ...

    is `humanize1:gen-idea`. What the function is called is the file's own business either
    way: a name that is written down where a flow is run is a name to keep, and one taken
    from the function would change under whoever renamed it.

    Args:
      call: The function, when the decorator is written with no arguments at all.
      name: What to call this one among the flows its file holds, or "" for the one the file
        holds under its own name.
      about: One line saying what it does, defaulting to the first line of its docstring.

    Returns:
      The function, unchanged but for what it now says about itself: a flow is called the way
      it always was, and a decorator that wrapped it would put itself between the flow and
      whatever reads its arguments.
    """

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(said, _SAID, Flow(name=name, about=about or _first(said.__doc__)))
        return said

    return marks if call is None else marks(call)


def loaded(where_: str | os.PathLike[str]) -> dict[str, Any]:
    """Runs a flow's file and answers with what it left behind.

    With its own directory importable while it runs, and only while: a flowverse is a
    directory of flows and whatever they import beside them, and a flow that reaches for the
    file next to it is reaching for something that came with it. Put back afterwards, since
    what a flow imports is not something the rest of this process should be able to.

    Args:
      where_: The Python file, already resolved.

    Returns:
      Everything the file defined, by name.
    """
    beside = os.path.dirname(os.path.abspath(where_))
    sys.path.insert(0, beside)
    try:
        return runpy.run_path(str(where_))
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(beside)


def held(where_: str | os.PathLike[str]) -> list[Flow]:
    """Every flow one file holds: its own first, and the rest as it declares them.

    Args:
      where_: The Python file. It is run to be read, so whatever it does as it is imported
        happens here.

    Returns:
      One per function it marked with :func:`flow`, the one it marked with no name first --
      which is the flow the file holds under its own name. Nothing at all for a file that
      marks none, or cannot be read: this is asked while a list is being drawn, and a file
      that will not import is one line of that list rather than the end of it.
    """
    try:
        inside = loaded(where_)
    except Exception:  # noqa: BLE001 -- a file that will not run holds no flows to list
        return []
    return _flows_of(inside)


def _flows_of(inside: dict[str, Any]) -> list[Flow]:
    """Every flow in what running one file left behind.

    Args:
      inside: What the file defined, by name.

    Returns:
      One per function the file marked with :func:`flow`, in the order it declared them --
      which for three phases of one thing is their order -- and the one it marked with no name
      first, since that is the one the file is named after and a list that put it third would
      read as the third thing in the file. Nothing at all for a file that marks nothing, which
      a directory of flows may well have in it: something the flows beside it import, or the
      file that sets their tests up. A name declared twice is the first of them: a file that
      holds two flows of one name is a file to correct, and picking one of them at random is
      not the way to say so.
    """
    said: list[Flow] = []
    for one in inside.values():
        marked = getattr(one, _SAID, None)
        if not isinstance(marked, Flow) or any(
            marked.name == already.name for already in said
        ):
            continue
        # The file's own docstring where the flow it holds says nothing: a file that is one
        # flow is documented as that flow, and its first line is what it does.
        if not marked.name and not marked.about:
            marked = Flow(name="", about=_first(inside.get("__doc__")))
        said.append(marked)
    return [one for one in said if not one.name] + [one for one in said if one.name]


class Offer(NamedTuple):
    """One flow there is to run, as whatever is offering them lists it.

    Attributes:
      whose: Where it came from: a flowverse by name, or `local` and `user` for the flows of
        this project and of yours.
      name: What to call it, which is what `-f` takes.
      about: The line it says about itself, or "" for one that says nothing.
    """

    whose: str
    name: str
    about: str = ""


def found() -> list[Offer]:
    """Every flow there is to run, and where each came from.

    Returns:
      One per flow: the flows humanize ships, then the ones its own repository holds, then
      whatever flowverses have been added, then this project's own and yours. A flow humanize
      ships is called by a bare name, one from a flowverse by `<flowverse>/<name>`, and one of
      yours by its path -- so a flow of yours that happens to share a name with one of
      humanize's is a different flow here rather than the same one, and is written down,
      offered and remembered under a name of its own. A file that holds several says so,
      `<name>:<inside>` apiece.
    """
    from .verses import flows as inside

    listed: list[Offer] = []
    for verse in flowverses():
        for base in inside(verse):
            listed.extend(
                Offer(
                    verse.name,
                    one if verse.name == BUILTIN else f"{verse.name}/{one}",
                    said,
                )
                for one, said in _named(verse.at / f"{base}.py", base)
            )
    for whose, folder in where:
        for path in sorted(glob(os.path.join(os.path.expanduser(folder), "*.py"))):
            base = os.path.basename(path)
            # The same test `find` applies, or the two disagree: a directory or a broken link
            # named like a flow would be listed as one and then not be there when it was
            # picked.
            if base.startswith("_") or not os.path.isfile(path):
                continue
            called = os.path.join(folder, base)
            listed.extend(
                Offer(whose, one, said) for one, said in _named(Path(path), called)
            )
    return listed


def _named(at: Path, called: str) -> list[tuple[str, str]]:
    """What each flow in one file is called, given what the file itself is called.

    Args:
      at: The file.
      called: What the file is called where it was found.

    Returns:
      One `(name, what it says about itself)` pair per flow: the file's own name for the flow
      it holds under it, and `<called>:<inside>` for each of the rest. Nothing at all for a
      file that holds no flow -- a directory of flows has files beside them that are not one --
      but just the file's name for one that could not be read: a file that will not import is
      still a flow somebody named, and saying so where they pick it is better than leaving it
      off the list.
    """
    try:
        inside = loaded(at)
    except Exception:  # noqa: BLE001 -- named as a flow, and not readable to be sure it is
        return [(called, "")]
    return [
        (called if not one.name else f"{called}{_INSIDE}{one.name}", one.about)
        for one in _flows_of(inside)
    ]


def about(named_: str) -> str:
    """The line one flow says about itself, for whoever is choosing between them.

    Args:
      named_: What the flow is called, as :func:`found` calls it.

    Returns:
      The line, or "" for a flow that says nothing or cannot be read.
    """
    at, inside = _split(named_)
    for one in held(find(at)):
        if one.name == inside:
            return one.about
    return ""


def _split(named_: str) -> tuple[str, str]:
    """One flow's name, split into the file and the flow inside it.

    Args:
      named_: What the flow is called.

    Returns:
      The file's name and the name inside it, which is "" for a file's own flow. A colon in a
      path -- a Windows drive, a URL somebody pasted -- is not one of these: only the last
      one is read, and only where what follows it is a name rather than a path.
    """
    at, sep, inside = named_.rpartition(_INSIDE)
    if not sep or os.sep in inside or "/" in inside:
        return named_, ""
    return at, inside


def find(named_: str) -> str:
    """Where the flow called this is.

    Args:
      named_: A flow's name -- `ralph_loop`, `official/rlar`, `humanize1:gen-plan` -- or the
        path to a file taken as given, which is what a flow of your own is called, `~` and all.

    Returns:
      The path to run: the flow the flowverse named holds, else the nearest flow of that
      name, else the file the path names -- and `named_` itself if nothing answers to it, so
      that whatever named it hears about it. Resolved, since a flow is free to change the
      working directory the name was resolved against.
    """
    at, _ = _split(named_)
    whose, _, rest = at.partition("/")
    if rest:
        # Named outright -- `official/rlar` -- which is the one spelling that says which
        # flowverse, and so the one that cannot be stood in for by a flow of your own.
        for verse in flowverses():
            beside = verse.at / f"{rest}.py"
            if whose == verse.name and beside.is_file():
                return str(beside.resolve())
    else:
        # Nearest wins: this project, then yours, then whatever there is to run -- so a flow
        # of your own may stand in for one of humanize's by taking its name.
        for _, folder in where:
            beside_ = os.path.join(os.path.expanduser(folder), f"{at}.py")
            if os.path.isfile(beside_):
                return os.path.realpath(beside_)
        for verse in flowverses():
            beside = verse.at / f"{at}.py"
            if beside.is_file():
                return str(beside.resolve())
    said = os.path.expanduser(at)
    return os.path.realpath(said) if os.path.isfile(said) else at


def inside(named_: str) -> str:
    """Which of the flows in a file this name asks for.

    Args:
      named_: What the flow is called.

    Returns:
      The name after the colon, or "" for the flow a file holds under its own name.
    """
    return _split(named_)[1]


def _first(said: str | None) -> str:
    """The first line of a docstring, which is what a flow says about itself in a list."""
    return (said or "").strip().splitlines()[0].strip() if said else ""
