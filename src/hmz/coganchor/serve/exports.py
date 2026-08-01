"""Translation from the virtual paths coganchor speaks to real paths on this host.

A client addresses this machine using *virtual* paths -- normally the very
paths the agent it is tracing believes it is using.  An export maps a virtual
prefix onto a real directory here, which lets the workspace live at a different
location than the client thinks (and lets the test suite prove that nothing
ever touches the client's own copy).

Every request is resolved through this table, so an export list is also this
machine's authorisation boundary: paths that match no export are refused.
"""

from __future__ import annotations

import errno
import os
import posixpath
from dataclasses import dataclass

from hmz.coganchor.proto import rewrite_path_prefix

__all__ = ["Export", "ExportTable"]


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

    def __init__(self, exports: list[Export]) -> None:
        if not exports:
            raise ValueError("at least one export is required")
        self._exports = sorted(exports, key=lambda e: len(e.virtual), reverse=True)

    @classmethod
    def parse(cls, specs: list[str]) -> ExportTable:
        return cls([Export.parse(spec) for spec in specs])

    @property
    def exports(self) -> list[Export]:
        return list(self._exports)

    def resolve(self, virtual: str) -> str:
        """Map a virtual path to a real one.

        Raises :class:`PermissionError` (``EACCES``) when the path escapes
        every export.  ``..`` segments are collapsed before matching, so a
        request can never climb out of its export.
        """
        path = _normalise(virtual)
        for export in self._exports:
            if path == export.virtual:
                return export.real
            prefix = export.virtual.rstrip("/") + "/"
            if path.startswith(prefix):
                return os.path.join(export.real, path[len(prefix) :])
        raise PermissionError(errno.EACCES, "path is outside every export", virtual)

    def rewrite(self, text: str) -> str:
        """Replace virtual prefixes inside a command argument with real paths.

        Commands run natively here and know nothing about the export table, so
        an argument naming a virtual path has to be translated before the
        process starts.  ``rewrite_path_prefix`` returns the text untouched for
        an identity export, which is the usual case.
        """
        for export in self._exports:
            text = rewrite_path_prefix(text, export.virtual, export.real)
        return text


def _normalise(path: str) -> str:
    if not path.startswith("/"):
        raise ValueError(f"virtual paths must be absolute, got {path!r}")
    return posixpath.normpath(path)
