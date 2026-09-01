"""Translation from the virtual paths coganchor speaks to real paths on this host.

A client addresses this machine using *virtual* paths -- normally the very
paths the agent it is tracing believes it is using.  An export maps a virtual
prefix onto a real directory here, which lets the workspace live at a different
location than the client thinks (and lets the test suite prove that nothing
ever touches the client's own copy).

Every request is resolved through this table, so an export list is also this
machine's authorisation boundary: paths that match no export are refused.

A path is matched as this machine's own filesystem would read it: a Mac reaches
``/var``, ``/tmp`` and ``/etc`` through ``/private``, and ignores case besides,
so a request naming a directory the way the other end learned to name it must
still land on the file the export opened.
"""

from __future__ import annotations

import errno
import os
import posixpath
import sys
from dataclasses import dataclass

from hmz.coganchor.proto import (
    CASE_INSENSITIVE,
    path_key,
    path_spellings,
    path_within,
    rewrite_path_prefix,
)

__all__ = ["Export", "ExportTable"]

#: Whether this machine's filesystem ignores case.  The target is the one end that can say,
#: since it is the end holding the files, and it says it of itself rather than being told.
INSENSITIVE = sys.platform in CASE_INSENSITIVE


@dataclass(frozen=True, slots=True)
class Export:
    """One ``virtual -> real`` directory mapping."""

    virtual: str
    real: str

    @classmethod
    def parse(cls, spec: str) -> Export:
        """Parse ``VIRTUAL:REAL``, or ``PATH`` for an identity mapping."""
        virtual, sep, real = spec.partition(":")
        if not sep:
            real = virtual
        if not virtual or not real:
            raise ValueError(f"malformed export {spec!r}; expected VIRTUAL[:REAL]")
        return cls(_normalise(virtual), os.path.abspath(os.path.expanduser(real)))


class ExportTable:
    """An ordered set of :class:`Export` mappings, resolved longest-prefix first."""

    def __init__(
        self, exports: list[Export], *, insensitive: bool = INSENSITIVE
    ) -> None:
        if not exports:
            raise ValueError("at least one export is required")
        # Longest first, measured as the prefixes are matched: an export written the long
        # way round -- `/private/tmp/x` for `/tmp/x` -- is no deeper for having been.
        self._exports = sorted(
            exports, key=lambda e: len(path_key(e.virtual)), reverse=True
        )
        self._insensitive = insensitive

    @classmethod
    def parse(cls, specs: list[str], *, insensitive: bool = INSENSITIVE) -> ExportTable:
        return cls([Export.parse(spec) for spec in specs], insensitive=insensitive)

    @property
    def exports(self) -> list[Export]:
        return list(self._exports)

    def resolve(self, virtual: str) -> str:
        """Map a virtual path to a real one.

        Raises :class:`PermissionError` (``EACCES``) when the path escapes
        every export.  ``..`` segments are collapsed before matching, so a
        request can never climb out of its export.

        The match is made on the spelling this machine's filesystem would settle on rather
        than on the characters that arrived, because the client names a path as the agent
        typed it and this end is where it turns into a file.  What that admits is an
        export's own directory under its other name, never a directory outside one: the
        real path is always built by joining onto ``export.real``.  On a Mac the two names
        are the same directory.  On a machine that is not one they are not, and folding
        them is still right, because the agent was told the *target's* spelling and the
        two ends have to read it alike.
        """
        path = _normalise(virtual)
        for export in self._exports:
            below = path_within(path, export.virtual, fold_case=self._insensitive)
            if below is None:
                continue
            return os.path.join(export.real, below) if below else export.real
        raise PermissionError(errno.EACCES, "path is outside every export", virtual)

    def rewrite(self, text: str) -> str:
        """Replace virtual prefixes inside a command argument with real paths.

        Commands run natively here and know nothing about the export table, so
        an argument naming a virtual path has to be translated before the
        process starts.  ``rewrite_path_prefix`` returns the text untouched for
        an identity export, which is the usual case.

        Every name the export answers to is translated, not only the one it was opened
        under, since an argument is matched by its characters and the other end may have
        been handed either.
        """
        for export in self._exports:
            for spelling in path_spellings(export.virtual):
                text = rewrite_path_prefix(
                    text, spelling, export.real, insensitive=self._insensitive
                )
        return text


def _normalise(path: str) -> str:
    if not path.startswith("/"):
        raise ValueError(f"virtual paths must be absolute, got {path!r}")
    return posixpath.normpath(path)
