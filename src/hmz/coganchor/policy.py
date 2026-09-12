"""Deciding what belongs to the target.

Three independent questions, answered here:

* **Paths.** A :class:`Layout` maps a directory on this machine (the mirror)
  onto the path it occupies on the target.  By default the two are identical,
  so the agent genuinely believes it is working on the target.  A target that
  spells a path more than one way -- a Mac reaches ``/tmp`` through
  ``/private/tmp`` and ignores case besides -- is met by
  :meth:`Router.canonical`, which settles on this machine's spelling before
  anything is matched, mirrored or created.
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
from typing import TYPE_CHECKING

from hmz.coganchor.proto import (
    CASE_INSENSITIVE,
    path_key,
    path_spellings,
    path_within,
    rewrite_path_prefix,
    spelled_twice,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Layout", "Router"]


def _unknown_platform() -> str:
    """What the target is before it has been asked, which is nothing at all."""
    return ""


@dataclass(frozen=True, slots=True)
class Layout:
    """One ``local shadow directory <-> remote path`` correspondence."""

    local_root: str
    virtual_root: str

    @classmethod
    def create(cls, local_root: str, virtual_root: str | None) -> Layout:
        local = _normalise(local_root)
        return cls(local, _normalise(virtual_root) if virtual_root else local)

    def contains(self, local_path: str, *, insensitive: bool = False) -> bool:
        return self.below(local_path, insensitive=insensitive) is not None

    def below(self, local_path: str, *, insensitive: bool = False) -> str | None:
        """What of ``local_path`` lies inside the mirror, or ``None`` if it is outside."""
        return path_within(local_path, self.local_root, fold_case=insensitive)

    def to_virtual(self, local_path: str) -> str:
        """Name ``local_path`` as the target names it.

        Takes no flag for case and needs none: whoever asks has already decided this path
        is the mirror's, so the only question left is which part of it lies below the root
        -- answered by the characters where they settle it, and by folding case where they
        do not.  Answering with the root itself instead, as falling through would, is how a
        file's bytes get pushed at the workspace directory.

        Raises:
          ValueError: If the path is not inside this layout at all.
        """
        suffix = self.below(local_path)
        if suffix is None:
            suffix = self.below(local_path, insensitive=True)
        if suffix is None:
            raise ValueError(f"{local_path!r} is not inside {self.local_root!r}")
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
    #: What the target said it is, asked for rather than held.  These settings are written
    #: before there is a connection to ask, and how the target spells a path is the one thing
    #: about it that nobody here may assume, so the answer is fetched when it is wanted --
    #: which is never before the handshake, since no path is routed until the agent runs.
    platform: Callable[[], str] = _unknown_platform

    @property
    def insensitive(self) -> bool:
        """Whether the target's filesystem ignores case, as a Mac's does by default."""
        return self.platform() in CASE_INSENSITIVE

    @property
    def settles(self) -> bool:
        """Whether anything here could reach this machine under more than one name.

        False for the ordinary session -- a Linux target, and a mirror at a path with one
        spelling -- and that is worth asking before a syscall's paths are read, because a
        session with nothing to settle and nothing to answer need not read them at all.
        """
        return self.insensitive or any(
            spelled_twice(layout.local_root) for layout in self.layouts
        )

    def __post_init__(self) -> None:
        # Longest root first, so nested layouts win over their parents -- measured as the
        # roots are matched, since a root written the long way round is no deeper for it.
        self.layouts = tuple(
            sorted(self.layouts, key=lambda item: -len(path_key(item.local_root)))
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

    def canonical(self, local_path: str) -> str:
        """How this machine spells a path the agent may have named as the target does.

        A path is read out of the traced process exactly as it named it, and an agent working
        against a Mac is told the target's spellings: ``/private/var/...`` for a directory the
        mirror holds at ``/var/...``, and whichever case a model happened to type for a
        filesystem that does not distinguish one.  Every one of those names the same file on
        the target and only one of them names it here, so a path inside a layout is put back
        onto that layout's own root and the rest of it left exactly as it came.

        This is the whole of the fix, and where it happens is the point of it.  Folding when
        paths are *compared* instead would let the other spelling stay the path everything
        downstream acts on -- the mirror is created at the path the agent named, so a
        ``/private`` one would have this machine build a tree under ``/private`` or refuse to
        for want of root, and a miscased one would build a second tree beside the first.

        A path outside every layout comes back exactly as it was named.  It is this machine's
        own business, and answering it with another would turn a file that is simply not there
        into one that could not be reached.
        """
        for layout in self.layouts:
            suffix = layout.below(local_path, insensitive=self.insensitive)
            if suffix is None:
                continue
            return (
                posixpath.join(layout.local_root, suffix)
                if suffix
                else layout.local_root
            )
        return local_path

    def layout_for(self, local_path: str) -> Layout | None:
        """Return the layout owning ``local_path``, or ``None`` if it is local."""
        insensitive = self.insensitive
        # A hole is carved by the same rule the layout is matched by, or a state directory
        # inside the workspace could be stepped over by a name that differs from it only in
        # the case the target does not distinguish -- and be mirrored onto the target, which
        # is the one place the agent's own state must never reach.
        if any(
            path_within(local_path, kept, fold_case=insensitive) is not None
            for kept in self.local_paths
        ):
            return None
        for layout in self.layouts:
            if layout.contains(local_path, insensitive=insensitive):
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

        Every name the mirror answers to is translated, not only the one it was configured
        under: an argument is matched by its characters, so a mirror at ``/tmp/mirror``
        named as ``/private/tmp/mirror`` is the same directory and has to cross as one.
        """
        insensitive = self.insensitive
        for layout in self.layouts:
            for spelling in path_spellings(layout.local_root):
                text = rewrite_path_prefix(
                    text,
                    spelling,
                    layout.virtual_root,
                    insensitive=insensitive,
                )
        return text

    def runs_locally(self, program: str) -> bool:
        """True when a program belongs to this machine rather than the target."""
        insensitive = self.insensitive
        return any(
            path_within(program, prefix, fold_case=insensitive) is not None
            for prefix in self.local_programs
        )

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
    """Plain containment, by the characters alone.

    What :meth:`Router.swap` answers by, and it slices the path it is given against the
    root's own length afterwards, so this must not fold anything away.  The layouts are
    matched by :func:`hmz.coganchor.proto.path_within` instead, which may.
    """
    if root == "/":
        return path.startswith("/")
    return path == root or path.startswith(root + "/")
