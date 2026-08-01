"""Deciding what belongs to the target.

Three independent questions, answered here:

* **Paths.** A :class:`Layout` maps a directory on this machine (the mirror)
  onto the path it occupies on the target.  By default the two are identical,
  so the agent genuinely believes it is working on the target.
* **Programs.** Everything the agent spawns runs on the target, except the
  agent's own runtime -- its binary and its re-execs, which stay here and are
  listed in ``local_programs``.
* **Redirects.** A path the agent names may be answered with another one --
  the credentials of the provider a turn runs as, rather than whichever
  account this machine is signed into.  What it is answered with is local
  state, so it is listed in ``local_paths`` too and never reaches the target.
"""

from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass

from hmz.coganchor.proto import rewrite_path_prefix

__all__ = ["Layout", "Router"]


@dataclass(frozen=True, slots=True)
class Layout:
    """One ``local shadow directory <-> remote path`` correspondence."""

    local_root: str
    virtual_root: str

    @classmethod
    def create(cls, local_root: str, virtual_root: str | None) -> Layout:
        local = _normalise(local_root)
        return cls(local, _normalise(virtual_root) if virtual_root else local)

    def contains(self, local_path: str) -> bool:
        return _within(local_path, self.local_root)

    def to_virtual(self, local_path: str) -> str:
        suffix = local_path[len(self.local_root) :].lstrip("/")
        return (
            posixpath.join(self.virtual_root, suffix) if suffix else self.virtual_root
        )


@dataclass(slots=True)
class Router:
    """Routes paths and programs between this machine and the target."""

    layouts: tuple[Layout, ...]
    #: Paths kept on this machine even when nested inside a layout, such as
    #: the agent's own state directory.
    local_paths: tuple[str, ...] = ()
    #: Program paths (prefix match) that must run on this machine.
    local_programs: tuple[str, ...] = ()
    #: Paths answered with others, as ``(what the agent names, what it gets)``.
    #: A directory stands for everything inside it, because a credential is
    #: often one file of several kept together.
    redirects: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        # Longest root first, so nested layouts win over their parents.
        self.layouts = tuple(
            sorted(self.layouts, key=lambda item: -len(item.local_root))
        )
        # And longest named path first, so a path under two redirects takes the
        # one that says most about it.
        self.redirects = tuple(
            sorted(
                (
                    (_normalise(named), _normalise(instead))
                    for named, instead in self.redirects
                ),
                key=lambda pair: -len(pair[0]),
            )
        )

    def layout_for(self, local_path: str) -> Layout | None:
        """Return the layout owning ``local_path``, or ``None`` if it is local."""
        if any(_within(local_path, kept) for kept in self.local_paths):
            return None
        for layout in self.layouts:
            if layout.contains(local_path):
                return layout
        return None

    def is_remote_path(self, local_path: str) -> bool:
        return self.layout_for(local_path) is not None

    def to_virtual(self, local_path: str) -> str:
        layout = self.layout_for(local_path)
        if layout is None:
            raise ValueError(f"{local_path!r} is not inside a remote layout")
        return layout.to_virtual(local_path)

    def virtual_cwd(self, local_cwd: str) -> str:
        """Translate a working directory, leaving purely local ones untouched."""
        layout = self.layout_for(local_cwd)
        return layout.to_virtual(local_cwd) if layout else local_cwd

    def rewrite(self, text: str) -> str:
        """Rewrite mirror paths inside a command argument into target paths.

        A no-op in the usual setup, where the mirror sits at exactly the path
        the workspace occupies on the target -- ``rewrite_path_prefix`` returns
        the text untouched when the two roots match.  It only matters when
        ``--shadow`` or ``--remote-path`` put them at different paths, and
        without it a command like ``grep -r pattern /mirror/src`` would name a
        directory the target does not have.
        """
        for layout in self.layouts:
            text = rewrite_path_prefix(text, layout.local_root, layout.virtual_root)
        return text

    def runs_locally(self, program: str) -> bool:
        """True when a program belongs to this machine rather than the target."""
        return any(_within(program, prefix) for prefix in self.local_programs)

    def swap(self, path: str) -> str | None:
        """Return the path this session answers ``path`` with, or ``None``.

        ``None`` for nearly every path there is.  Three shapes are answered:
        what a redirect names, what lies under a directory one names, and what
        lies beside one under the same name and another suffix -- which is how
        a credential is rotated, ``.tmp`` written and renamed over the real
        one, and leaving that unanswered would write the new token into the
        store being redirected away from.  The same rule as
        :meth:`hmz.providers.redirect.Swaps.swap`, which the two halves of
        a redirected run keep in step by saying it the same way.
        """
        for named, instead in self.redirects:
            if path == named:
                return instead
            if _within(path, named):
                return posixpath.join(instead, path[len(named) :].lstrip("/"))
            if path.startswith(named + "."):
                return instead + path[len(named) :]
        return None


def _normalise(path: str) -> str:
    expanded = os.path.abspath(os.path.expanduser(path))
    return expanded.rstrip("/") or "/"


def _within(path: str, root: str) -> bool:
    if root == "/":
        return path.startswith("/")
    return path == root or path.startswith(root + "/")
