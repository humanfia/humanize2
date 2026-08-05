"""A lazily materialised local mirror of the target's workspace.

The shadow tree is what makes interception cheap.  Instead of forwarding every
``read`` and ``getdents64``, coganchor reproduces the target's *structure*
locally the first time a directory is touched: real directories, real
symlinks, and sparse placeholder files carrying the remote size, mode and
mtime.  From then on ``stat``, ``getdents64``, ``read``, ``write``, ``mmap``
and ``lseek`` all run natively at full speed and still tell the truth.

Only two things cross the network per file:

* **content pull** -- the first time a file is opened for reading, and
* **content push** -- when a locally modified file must become visible to
  the target, which happens before any remote command runs.

A remote command may change anything, so finishing one bumps a *generation*
counter that invalidates every cached directory listing.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import logging
import os
import shutil
import stat as stat_module
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.coganchor.policy import Layout, Router
    from hmz.coganchor.remote import RemoteClient

__all__ = ["ShadowTree", "prepare_shadow_root"]

log = logging.getLogger(__name__)

#: Shadow roots are recorded here rather than marked in place, so the mirror
#: stays byte-for-byte what the target has -- an agent listing the workspace
#: must not see coganchor's own bookkeeping.
REGISTRY_DIR = "~/.cache/humanize/shadows"

#: What points that somewhere else for one process and everything it starts. For a machine
#: that keeps its caches elsewhere, and for a test suite: these records outlive the mirrors
#: they are about, so a suite writing them into somebody's own cache is a suite that leaves
#: thousands of them there and then reads one back as a mirror it never made.
SHADOWS = "HUMANIZE_SHADOWS"

_FETCH_SUFFIX = ".humanize-fetch"

#: Bound on symlink chasing, matching the kernel's own ``ELOOP`` limit.
_MAX_LINK_HOPS = 40


@dataclass(slots=True)
class FileRecord:
    """What coganchor last knew about one file, on both sides."""

    kind: str
    mode: int
    remote_size: int
    remote_mtime_ns: int
    content_present: bool = False
    local_size: int = -1
    local_mtime_ns: int = -1

    def matches_remote(self, entry: dict[str, Any]) -> bool:
        return bool(
            self.kind == entry["kind"]
            and self.remote_size == entry["size"]
            and self.remote_mtime_ns == entry["mtime_ns"]
        )


class ShadowTree:
    """Keeps the local mirror consistent with the target."""

    def __init__(self, client: RemoteClient, router: Router) -> None:
        self._client = client
        self._router = router
        self._dirs: dict[str, int] = {}
        self._files: dict[str, FileRecord] = {}
        self._dirty_candidates: set[str] = set()
        self._generation = 0

    # ------------------------------------------------------------------ queries

    def invalidate(self) -> None:
        """Forget every cached listing, because the target may have changed."""
        self._generation += 1

    # ------------------------------------------------------------ materialising

    def ensure_path(self, local_path: str) -> None:
        """Make ``local_path`` resolvable: materialise the directory holding it."""
        parent = os.path.dirname(local_path.rstrip("/")) or "/"
        self.ensure_directory(parent)

    def ensure_directory(self, local_dir: str) -> None:
        """Mirror one remote directory locally, at most once per generation."""
        layout = self._router.layout_for(local_dir)
        if layout is None or self._dirs.get(local_dir) == self._generation:
            return
        self.flush()
        virtual = layout.to_virtual(local_dir)
        try:
            listing = self._client.listdir(virtual)
        except OSError as exc:
            if exc.errno in (errno.ENOENT, errno.ENOTDIR, errno.EACCES):
                self._dirs[local_dir] = self._generation
                self._drop_local(local_dir)
                return
            raise
        self._apply_listing(layout, local_dir, listing)
        self._dirs[local_dir] = self._generation

    def ensure_content(self, local_path: str) -> None:
        """Fetch a file's bytes if the local copy is still a placeholder."""
        if not self._router.is_remote_path(local_path):
            return
        self.ensure_path(local_path)
        # Opening a symlink reads whatever it points at, so that is the file
        # whose content has to be here.
        path = self._follow_links(local_path)
        layout = self._router.layout_for(path)
        record = self._files.get(path)
        if layout is None or record is None or record.kind != "file":
            return
        if record.content_present:
            return
        virtual = layout.to_virtual(path)
        scratch = path + _FETCH_SUFFIX
        try:
            with open(scratch, "wb") as sink:
                meta = self._client.read_file(virtual, sink)
            os.chmod(scratch, stat_module.S_IMODE(record.mode))
            os.replace(scratch, path)
        except OSError:
            _unlink_quietly(scratch)
            raise
        os.utime(path, ns=(meta["mtime_ns"], meta["mtime_ns"]))
        record.remote_size = meta["size"]
        record.remote_mtime_ns = meta["mtime_ns"]
        record.content_present = True
        self._record_local_state(path, record)

    def _follow_links(self, local_path: str) -> str:
        """Resolve local symlinks, materialising each directory on the way."""
        path = local_path
        for _ in range(_MAX_LINK_HOPS):
            try:
                target = os.readlink(path)
            except OSError:
                return path
            path = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not self._router.is_remote_path(path):
                return path
            self.ensure_path(path)
        return path

    def duplicate(self, source: str, target: str) -> None:
        """Record that ``target`` now aliases ``source``, as a hard link does.

        Without this the new name has no record, so a placeholder that was
        never fetched would be read as zeroes through it.
        """
        record = self._files.get(source)
        if record is None:
            return
        copy = replace(record)
        self._files[target] = copy
        self._record_local_state(target, copy)

    def note_write(self, local_path: str) -> None:
        """Remember that the tracee is about to write here, so ``flush`` looks."""
        if self._router.is_remote_path(local_path):
            self._dirty_candidates.add(local_path)

    def forget(self, local_path: str) -> None:
        """Drop state for a path the tracee removed or renamed away."""
        covers = _subtree_test(local_path)
        self._files = {
            key: value for key, value in self._files.items() if not covers(key)
        }
        self._dirs = {
            key: value for key, value in self._dirs.items() if not covers(key)
        }
        self._dirty_candidates = {
            path for path in self._dirty_candidates if not covers(path)
        }

    def rename(self, source: str, target: str) -> None:
        """Carry cached state across a rename the tracee just performed.

        Without this a renamed placeholder would lose its record, so its
        content would never be fetched and the file would read as zeroes.
        """
        self.forget(target)
        covers = _subtree_test(source)
        rebase = _subtree_rebase(source, target)
        self._files = {
            rebase(key) if covers(key) else key: v for key, v in self._files.items()
        }
        self._dirs = {
            rebase(key) if covers(key) else key: v for key, v in self._dirs.items()
        }
        self._dirty_candidates = {
            rebase(path) if covers(path) else path for path in self._dirty_candidates
        }

    # -------------------------------------------------------------- write-back

    def flush(self) -> int:
        """Push every locally modified file to the target.

        Called before any remote command runs and before re-reading a
        directory, so the target never observes stale content.  Returns the
        number of files pushed.
        """
        pushed = 0
        for local_path in sorted(self._dirty_candidates):
            layout = self._router.layout_for(local_path)
            if layout is None:
                continue
            try:
                info = os.lstat(local_path)
            except OSError:
                continue  # removed locally; the unlink was replayed already
            if not stat_module.S_ISREG(info.st_mode):
                continue
            record = self._files.get(local_path)
            if (
                record is not None
                and record.local_size == info.st_size
                and record.local_mtime_ns == info.st_mtime_ns
            ):
                continue
            self._push(layout, local_path, info)
            pushed += 1
        return pushed

    def _push(self, layout: Layout, local_path: str, info: os.stat_result) -> None:
        virtual = layout.to_virtual(local_path)
        with open(local_path, "rb") as source:
            meta = self._client.write_file(virtual, source, info.st_mode)
        record = FileRecord(
            kind="file",
            mode=info.st_mode,
            remote_size=meta.get("size", info.st_size),
            remote_mtime_ns=meta.get("mtime_ns", 0),
            content_present=True,
        )
        self._files[local_path] = record
        self._record_local_state(local_path, record)
        log.debug("pushed %s -> %s (%d bytes)", local_path, virtual, info.st_size)

    # ---------------------------------------------------------------- internals

    def _apply_listing(
        self,
        layout: Layout,  # noqa: ARG002  -- the caller resolved against it already
        local_dir: str,
        listing: dict[str, Any],
    ) -> None:
        os.makedirs(local_dir, exist_ok=True)
        expected: set[str] = set()
        for entry in listing["entries"]:
            name = entry["name"]
            expected.add(name)
            self._apply_entry(os.path.join(local_dir, name), entry)
        self._remove_vanished(local_dir, expected)

    def _apply_entry(self, local_path: str, entry: dict[str, Any]) -> None:
        kind = entry["kind"]
        if kind == "dir":
            self._apply_dir(local_path, entry)
        elif kind == "link":
            self._apply_link(local_path, entry)
        else:
            self._apply_file(local_path, entry)

    def _apply_dir(self, local_path: str, entry: dict[str, Any]) -> None:
        if os.path.islink(local_path) or (
            os.path.exists(local_path) and not os.path.isdir(local_path)
        ):
            _remove_any(local_path)
        os.makedirs(local_path, exist_ok=True)
        self._files[local_path] = FileRecord(
            kind="dir",
            mode=entry["mode"],
            remote_size=entry["size"],
            remote_mtime_ns=entry["mtime_ns"],
            content_present=True,
        )

    def _apply_link(self, local_path: str, entry: dict[str, Any]) -> None:
        target = entry.get("target", "")
        try:
            if os.readlink(local_path) == target:
                return
        except OSError:
            pass
        _remove_any(local_path)
        os.symlink(target, local_path)
        self._files[local_path] = FileRecord(
            kind="link",
            mode=entry["mode"],
            remote_size=entry["size"],
            remote_mtime_ns=entry["mtime_ns"],
            content_present=True,
        )

    def _apply_file(self, local_path: str, entry: dict[str, Any]) -> None:
        record = self._files.get(local_path)
        if (
            record is not None
            and record.matches_remote(entry)
            and _is_intact(local_path, record)
        ):
            return
        if os.path.isdir(local_path) and not os.path.islink(local_path):
            _remove_any(local_path)
        fresh = FileRecord(
            kind=entry["kind"],
            mode=entry["mode"],
            remote_size=entry["size"],
            remote_mtime_ns=entry["mtime_ns"],
            content_present=entry["size"] == 0 and entry["kind"] == "file",
        )
        # A sparse placeholder of the right size, mode and mtime makes local
        # stat(), getdents64() and ls() report the target's truth for free.
        with open(local_path, "wb") as handle:
            if entry["size"] and entry["kind"] == "file":
                handle.truncate(entry["size"])
        os.chmod(local_path, stat_module.S_IMODE(entry["mode"]))
        os.utime(local_path, ns=(entry["mtime_ns"], entry["mtime_ns"]))
        self._files[local_path] = fresh
        self._record_local_state(local_path, fresh)

    def _remove_vanished(self, local_dir: str, expected: set[str]) -> None:
        try:
            present = set(os.listdir(local_dir))
        except OSError:
            return
        for name in present - expected:
            # Scratch files from an interrupted fetch are swept too: nothing
            # else ever removes them, and a fetch can never be in flight here
            # because both run on the supervisor's single thread.
            path = os.path.join(local_dir, name)
            log.debug("dropping %s: gone on the target", path)
            _remove_any(path)
            self.forget(path)

    def _drop_local(self, local_dir: str) -> None:
        """The directory no longer exists remotely; remove the local mirror."""
        if os.path.isdir(local_dir) and not os.path.islink(local_dir):
            _remove_any(local_dir)
        self.forget(local_dir)

    def _record_local_state(self, local_path: str, record: FileRecord) -> None:
        try:
            info = os.lstat(local_path)
        except OSError:
            return
        record.local_size = info.st_size
        record.local_mtime_ns = info.st_mtime_ns


def _subtree_test(root: str) -> Callable[[str], bool]:
    """Predicate matching ``root`` and everything beneath it."""
    prefix = root.rstrip("/") + "/"
    return lambda path: path == root or path.startswith(prefix)


def _subtree_rebase(source: str, target: str) -> Callable[[str], str]:
    """Move a path from under ``source`` to the same place under ``target``."""
    return lambda path: target + path[len(source) :]


def _is_intact(local_path: str, record: FileRecord) -> bool:
    """True when the local copy still matches what we last wrote there."""
    try:
        info = os.lstat(local_path)
    except OSError:
        return False
    return (
        info.st_size == record.local_size and info.st_mtime_ns == record.local_mtime_ns
    )


def _remove_any(path: str) -> None:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
    except OSError:
        log.debug("could not remove %s", path, exc_info=True)


def _unlink_quietly(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def prepare_shadow_root(path: str, *, force: bool = False, target: str = "") -> None:
    """Create or validate the local directory that mirrors the target.

    Refuses to take over a directory that already holds unrelated files, and
    refuses to re-point an existing mirror at a different target: the mirror is
    authoritative, so in both cases anything the target does not have would be
    deleted.  Previously used shadows are remembered outside the directory, in
    :data:`REGISTRY_DIR`.
    """
    record = _registry_entry(path)
    previous = _recorded_target(record)
    if previous is not None and previous != target and not force:
        raise FileExistsError(
            errno.EEXIST,
            f"{path} mirrors {previous}, not {target}. humanize replaces this "
            "directory with the new target's contents and would delete "
            "everything only the old one has. Use a different directory, or "
            "pass --force.",
            path,
        )
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    elif not os.path.isdir(path):
        raise NotADirectoryError(errno.ENOTDIR, "shadow root is not a directory", path)
    elif not force and previous is None and any(os.scandir(path)):
        raise FileExistsError(
            errno.EEXIST,
            f"{path} already contains files and is not an humanize mirror. "
            "humanize replaces this directory with the target's contents and "
            "would delete them. Use an empty directory, or pass --force.",
            path,
        )
    os.makedirs(os.path.dirname(record), exist_ok=True)
    with open(record, "w", encoding="utf-8") as handle:
        json.dump({"shadow": path, "target": target}, handle)


def _recorded_target(record: str) -> str | None:
    """The target this mirror was last used against, or ``None`` if it is new."""
    try:
        with open(record, encoding="utf-8") as handle:
            return str(json.load(handle).get("target", ""))
    except (OSError, ValueError):
        return None


def _registry_entry(path: str) -> str:
    digest = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:16]
    where = os.environ.get(SHADOWS) or REGISTRY_DIR
    return os.path.join(os.path.expanduser(where), f"{digest}.json")
