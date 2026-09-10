"""Change detection for native settings held by a persistent external CLI."""

from __future__ import annotations

import glob
import hashlib
import os
import stat
from pathlib import Path

#: How much of a file is read to tell it from the version before it. Contents count -- see
#: below -- but only where reading them costs less than being wrong about them: a settings
#: file, a skill, a command, a prompt are each far under this, and what is over it is a
#: bundled artifact whose size, modification time and change time are in the fingerprint
#: already. This is asked once a turn per session, and a skills directory that has grown a
#: `node_modules` would otherwise be a tree read whole every time any of them starts one.
_READ_TO = 1 << 20


def snapshot(paths: set[Path]) -> bytes:
    """Fingerprints native inputs, including linked skills and plugin dependencies.

    Contents count too, up to :data:`_READ_TO`: a same-size edit with a restored mtime can
    happen within one filesystem ctime tick. Above it, that identity is what a file is taken
    on. Missing paths count too. Directory identities bound symbolic-link cycles.
    """
    digest = hashlib.sha256()
    visited: set[tuple[int, int]] = set()

    def note(path: Path) -> bool:
        digest.update(os.fsencode(path))
        try:
            info = path.stat()
        except OSError:
            digest.update(b"missing")
            return False
        identity = (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        digest.update(str(identity).encode())
        if stat.S_ISREG(info.st_mode) and info.st_size <= _READ_TO:
            try:
                with path.open("rb") as contents:
                    digest.update(hashlib.file_digest(contents, "sha256").digest())
            except OSError:
                digest.update(b"unreadable")
        if stat.S_ISDIR(info.st_mode):
            key = (info.st_dev, info.st_ino)
            if key in visited:
                return False
            visited.add(key)
            return True
        return False

    expanded: set[Path] = set()
    for path in paths:
        expanded.add(path)
        if glob.has_magic(str(path)):
            root = Path(path.anchor or ".")
            expanded.update(root.glob(str(path.relative_to(root))))
    for root in sorted(expanded):
        if not note(root):
            continue
        for directory, folders, files in os.walk(root, followlinks=True):
            folders[:] = [
                name for name in sorted(folders) if note(Path(directory) / name)
            ]
            for name in sorted(files):
                note(Path(directory) / name)
    return digest.digest()
