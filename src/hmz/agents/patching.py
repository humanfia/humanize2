"""Reaching a coding agent by patching the bundle it ships, on a copy that is ours.

The deepest of the three ways humanize reaches into a CLI it drives, and the one it turns to
last. Two of these agents -- Claude Code and opencode -- are shipped as a single Bun
executable: the whole of the program, its JavaScript minified and packed into one file behind
a documented ``---- Bun! ----`` trailer, runtime and all. There is no script to preload and no
hook table meant for one run; what the CLI does is inside that file. So where a shallower layer
cannot reach a thing, this one reaches it by rewriting the bundle -- and, because that is
brittle by construction, does everything it can to be safe about it and falls back the moment
it cannot.

Never the installed binary. A patch is applied to a copy humanize makes in a directory of its
own, run for the length of one session and removed after, so nothing this does outlives the run
or touches what the person at this machine installed. And never on faith: the copy is
fingerprinted against what :mod:`hmz.backends` wrote down for it -- a line the bundle must
contain, and an optional digest -- before a byte is changed, because a bundle is rebuilt release
by release and what was patched this morning is a different file tonight under the same name. A
copy that does not answer to its fingerprint is one nobody here has seen, and is left alone.

What a patch may do is bounded by what a re-embed can do safely. The trailer carries a byte
count and per-module offsets the loader itself reads back, so a rewrite that changed a length
would move everything after it and hand the runtime a file it cannot parse -- a copy that
segfaults being worse than no patch at all. So every rewrite here is the same length as what it
replaces, nothing moves, and the one book-keeping a same-length edit still has to do is turn off
the precompiled bytecode of any module it touched: Bun runs a module's bytecode in preference to
its source, so a source edit that left the bytecode in place would be an edit that never ran. A
module whose bytecode is cleared is recompiled from its now-patched source the first time it is
reached, which costs a module's compile and changes nothing else.

None of this raises. Every failure -- an unknown version, a digest that does not match, a site
that has moved, a copy that will not start -- is a reason to fall back to the hooked layer and go
on, logged so that a run which quietly took the shallower path can be seen to have done so. A
patch that did not apply is never a run that did not happen.

What reaches two or three of these backends reaches no more: the Bun executables here, and a Deno
one if a later release proves re-embeddable. The agents shipped as native Rust carry no bundle to
patch, and the plain Node scripts are reached by the preload layer instead. This is written for
the ones that are a bundle, and says so rather than implying more.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import mmap
    from collections.abc import Sequence
    from pathlib import Path
    from typing import Self

    from hmz.backends import Bundled, Profile

__all__ = ["Patch", "Patched", "located", "patched"]

log = logging.getLogger(__name__)

#: The trailer Bun writes at the very end of a standalone executable, whichever CLI it built.
#: Its presence is what says a file is one of these at all, and where the module graph is read
#: back from -- the bytes just before it are the graph's own header. Documented by Bun and
#: stable across the releases seen here; a file without it is not a bundle this reaches.
_TRAILER = b"\n---- Bun! ----\n"

#: How many bytes of graph header sit just before the trailer -- a byte count and the offsets of
#: the module table and the entry point, the first twenty of which are read and the rest left.
_HEADER = 32

#: How many bytes one module's record in the table is: two string pointers for its name and
#: source, one for its source map, one for its bytecode, and a little more this does not read.
#: What the table's length must be a whole number of, or it is not the table this reads.
_RECORD = 52

#: How long a copy is given to prove it still starts before the patch is called a failure. A
#: bundle answers `--version` without opening a session or reaching a network, so a copy that
#: has not said its version in this long is one that will not run at all -- which is the whole
#: thing this probe is for.
_PROBE_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class Patch:
    """One rewrite to make inside a bundle: what to find, and what to put there instead.

    Same length on both sides, and refused otherwise: the file is packed behind a trailer that
    records where everything in it is, so a rewrite that changed a length would move every byte
    after it and leave the loader reading the wrong offset for the rest. A patch is a
    substitution in place, never an insertion.

    Attributes:
      find: The bytes to replace, exactly as the bundler left them -- the call, the constant,
        the flag being reached for. Every occurrence of it inside the one module the fingerprint
        picked out is rewritten; occurrences elsewhere in the file are left alone.
      into: What to write in their place, which MUST be the same number of bytes.
    """

    find: bytes
    into: bytes

    def __post_init__(self) -> None:
        """Refuses a rewrite that is not a substitution in place.

        Raises:
          ValueError: The two sides are different lengths, which a packed bundle cannot take.
        """
        if len(self.find) != len(self.into):
            raise ValueError(
                f"a bundle patch must be the same length on both sides: "
                f"{len(self.find)} -> {len(self.into)}"
            )


@dataclass(frozen=True, slots=True)
class Located:
    """A bundle that answered to its fingerprint, and where inside it a patch would land.

    Attributes:
      bundle: The file that was located and fingerprinted -- the copy's source, and for the
        single-file executables here the CLI's own program.
      module: The index, in the bundle's own module graph, of the module a patch is written
        into: the one the fingerprint line was found in, preferring the entry module where the
        line is inlined into several.
      digest: The SHA-256 of the located file, whole, where the fingerprint recorded one to
        compare against -- and "" where it did not, which is most of them, a 200 MB hash on
        every start being a cost the fingerprint line already saves.
    """

    bundle: Path
    module: int
    digest: str


class Patched:
    """A patched copy of a CLI, held for as long as the session that made it needs it.

    The copy lives in a directory humanize owns and is removed when this is closed or collected,
    whichever comes first -- a finalizer for the reason the mounted skills are one: a run that
    dropped the handle without closing it still leaves nothing of a 200 MB copy behind.
    """

    def __init__(self, path: Path, where: Path) -> None:
        """Holds the copy and arranges for it to be taken away again.

        Args:
          path: The program to run -- the patched copy of the CLI.
          where: The directory it was made in, which is what is removed.
        """
        import shutil
        import weakref

        #: The program to run instead of the installed one, for the length of the session.
        self.path = path
        self._where = where
        self._remove = weakref.finalize(self, shutil.rmtree, where, ignore_errors=True)

    def close(self) -> None:
        """Removes the copy and the directory it was made in, now rather than at collection."""
        self._remove()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class _Module:
    """One module inside a bundle, as much of its record as a patch here reads."""

    name: str
    #: Where this module's source is in the file, and how long it is.
    at: int
    length: int
    #: Where this module's bytecode pointer is in the file -- the offset and length pair that
    #: has to be zeroed for a source edit to be what runs.
    bytecode_at: int
    #: Whether the module carries bytecode at all, so a rewrite of a plain-source module does
    #: not go looking for a pointer to clear.
    has_bytecode: bool


@dataclass(frozen=True, slots=True)
class _Graph:
    """A bundle's module graph, read back from behind its trailer."""

    entry: int
    modules: tuple[_Module, ...]


def _graph(data: mmap.mmap) -> _Graph | None:
    """Reads a Bun standalone graph out of a file's bytes, or says it is not one.

    The last ``---- Bun! ----`` in the file is the end of the graph; the 32 bytes before it are
    its header -- a byte count and the offsets of the module table and the entry point -- and the
    table is a run of fixed-size records, each naming where one module's source and bytecode are.
    Only the fields a patch needs are read: a name, a source span, and the bytecode pointer to
    clear.

    Args:
      data: The whole file, memory-mapped.

    Returns:
      The graph, or None for a file with no trailer or one whose table does not fit -- either of
      which is a file this does not patch.
    """
    import struct

    end = data.rfind(_TRAILER)
    if end < _HEADER:
        return None
    header = end - _HEADER
    byte_count, table_off, table_len, entry = struct.unpack_from("<QIII", data, header)
    base = end + len(_TRAILER) - 48 - byte_count
    # A table that is not a whole number of records is a file whose record shape is not the one
    # read here -- a Bun that packs its modules differently -- and stepping it in 52s would read
    # a record straddling two, so it is left alone rather than parsed into nonsense.
    if base < 0 or table_len % _RECORD or base + table_off + table_len > len(data):
        return None
    modules: list[_Module] = []
    for record in range(base + table_off, base + table_off + table_len, _RECORD):
        if record + _RECORD > len(data):
            return None
        name_off, name_len, cont_off, cont_len = struct.unpack_from(
            "<IIII", data, record
        )
        _bc_off, bc_len = struct.unpack_from("<II", data, record + 24)
        name = bytes(data[base + name_off : base + name_off + name_len]).decode(
            "utf-8", "replace"
        )
        modules.append(
            _Module(
                name=name,
                at=base + cont_off,
                length=cont_len,
                bytecode_at=record + 24,
                has_bytecode=bc_len != 0,
            )
        )
    if not modules or entry >= len(modules):
        return None
    return _Graph(entry=entry, modules=tuple(modules))


def _chosen(graph: _Graph, data: mmap.mmap, says: bytes) -> int | None:
    """Which module a fingerprint line picks out, or None where it is not exactly one.

    A line inlined into several modules -- a version constant, say -- is taken to mean the entry
    module, which is the one a patch of the program itself is written against; a line in exactly
    one module means that module; a line in none means a bundle whose site has moved, and a fall
    back.

    Args:
      graph: The module graph to look in.
      data: The whole file, so a module's source can be read.
      says: The line the fingerprint says the bundle must contain.

    Returns:
      The module's index, or None where the line names no one module -- it is in none, or in
      several and the entry is not among them, either of which is a bundle to leave alone rather
      than to patch a guess of.
    """
    found = [
        i
        for i, module in enumerate(graph.modules)
        if says in data[module.at : module.at + module.length]
    ]
    if graph.entry in found:
        return graph.entry
    if len(found) == 1:
        return found[0]
    return None


def _bundle(profile: Profile, program: Path) -> tuple[Path, Bundled] | None:
    """The one file inside a CLI's install this layer patches, and the fingerprint that named it.

    The bundle is located by the glob :mod:`hmz.backends` wrote down, read relative to the
    directory the program was resolved to. The program itself is preferred where it is a match,
    which is what the two Bun executables are -- the whole CLI in one file -- so a copy of it is a
    copy of the program. A match that is a file beside the program rather than the program is not
    reached: running it would mean copying the install whole and repointing its launcher, which
    is more than a same-length patch of one file, and is left to fall back instead.

    Args:
      profile: The backend, for the globs it wrote down under ``bundles``.
      program: The resolved program the CLI runs as.

    Returns:
      The file to fingerprint and copy, paired with the ``Bundled`` whose glob found it -- so the
      one that is checked is the one that named it -- or None where no glob names the program.
    """
    program = program.resolve()
    for bundled in profile.bundles:
        for candidate in sorted(program.parent.glob(bundled.path)):
            if candidate.resolve() == program:
                return candidate.resolve(), bundled
    return None


def located(profile: Profile, program: Path) -> Located | None:
    """Fingerprints a CLI's bundle, saying where a patch would land or why it will not.

    Everything up to the copy: the bundle is found, read, and checked against what was written
    down for it -- a line it must contain, and a digest where one was recorded. A bundle that
    passes says which module a patch is written into; one that fails says nothing and is left
    alone.

    Args:
      profile: The backend whose bundle this is, for its ``bundles`` fingerprints.
      program: The resolved program the CLI runs as.

    Returns:
      Where a patch would land, or None for a backend with no bundle written down, a file that is
      not a bundle, a fingerprint that does not match, or a site that has moved -- each logged.
    """
    if not profile.bundles:
        return None
    found = _bundle(profile, program)
    if found is None:
        log.debug("no patchable bundle located for %s at %s", profile.name, program)
        return None
    return _located(profile, *found)


def _located(profile: Profile, bundle: Path, bundled: Bundled) -> Located | None:
    """The same question, asked of a bundle somebody has already found.

    Split out so that the whole path -- fingerprint, copy, rewrite -- globs the install once:
    :func:`patched` needs the ``Bundled`` that named the file as well as the file, and calling
    :func:`located` and then looking the bundle up a second time is two walks of a directory
    that may hold a two-hundred-megabyte executable, and two answers that can disagree.

    Args:
      profile: The backend whose bundle this is, for what a refusal says.
      bundle: The file :func:`_bundle` found.
      bundled: The fingerprint whose glob found it.

    Returns:
      Where a patch would land, or None -- each reason logged, as :func:`located` says.
    """
    import hashlib
    import mmap

    try:
        with (
            bundle.open("rb") as handle,
            mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as raw,
        ):
            graph = _graph(raw)
            if graph is None:
                log.info(
                    "%s bundle at %s is not a Bun executable", profile.name, bundle
                )
                return None
            module = _chosen(graph, raw, bundled.says.encode())
            if module is None:
                # Absent, or present in several modules the entry is not among -- either way the
                # bundle is a shape this has not seen, which a new release is, and a fall back.
                log.info(
                    "%s bundle at %s does not name one module by %r -- falling back",
                    profile.name,
                    bundle,
                    bundled.says,
                )
                return None
            # The digest is the whole file, so it is read only where one was recorded to compare
            # against -- a 200 MB hash on every start is a cost the fingerprint line already paid.
            digest = hashlib.sha256(raw).hexdigest() if bundled.digest else ""
    except (OSError, ValueError) as why:
        # ValueError is what mmap answers an empty file with -- a half-written install, say --
        # and is a bundle to leave alone rather than a run to fail.
        log.info("%s bundle at %s could not be read: %s", profile.name, bundle, why)
        return None
    if bundled.digest and bundled.digest != digest:
        log.info(
            "%s bundle at %s digest %s is not the one recorded -- falling back",
            profile.name,
            bundle,
            digest[:12],
        )
        return None
    return Located(bundle=bundle, module=module, digest=digest)


def patched(
    profile: Profile,
    program: Path,
    patches: Sequence[Patch] = (),
    *,
    probe: bool = True,
) -> Patched | None:
    """A session-scoped patched copy of a CLI, or None to run the installed one instead.

    The whole of the safe path: the bundle is fingerprinted, copied into a directory humanize
    owns, and rewritten in place -- every patch the same length as what it replaces, inside the
    one module the fingerprint picked out, with that module's bytecode cleared so the rewritten
    source is what runs. The copy is then made to prove it still starts before it is handed back;
    one that will not is removed and the run falls back. Nothing here raises: a patch that cannot
    be applied returns None and is logged, and the caller reaches the CLI a shallower way.

    Args:
      profile: The backend to patch, for its bundle fingerprints.
      program: The resolved program the CLI runs as, which is what is copied.
      patches: The rewrites to make. Empty re-embeds the bundle unchanged, which is the copy and
        the fingerprint without an edit -- useful only to prove the path.
      probe: Whether to check the copy still starts before returning it. On by default; a caller
        with its own way of finding out may turn it off.

    Returns:
      The patched copy, held for the session, or None where the bundle could not be safely
      patched -- each reason logged.
    """
    import os
    import shutil
    import tempfile
    from pathlib import Path

    from hmz import home

    found = _bundle(profile, program)
    if found is None:
        log.debug("no patchable bundle located for %s at %s", profile.name, program)
        return None
    _, bundled = found
    where = _located(profile, *found)
    if where is None:
        return None
    try:
        into = home() / "patched"
        into.mkdir(parents=True, exist_ok=True)
        _reap(into)
        made = Path(tempfile.mkdtemp(dir=into, prefix=f"{profile.name}-{os.getpid()}-"))
    except OSError as why:
        log.info("%s could not make a directory to patch in: %s", profile.name, why)
        return None
    copy = made / program.name
    try:
        shutil.copy2(where.bundle, copy)
    except OSError as why:
        log.info("%s bundle could not be copied for patching: %s", profile.name, why)
        shutil.rmtree(made, ignore_errors=True)
        return None
    # The copy is fingerprinted again, not the file `located` read: Claude Code updates itself
    # while it runs, so a bundle swapped between the read and the copy is patched against the
    # module it actually has rather than the one the installed file had a moment ago.
    if not _rewrite(profile, copy, bundled, patches):
        shutil.rmtree(made, ignore_errors=True)
        return None
    if probe and not _starts(copy):
        log.info("%s patched copy did not start -- falling back", profile.name)
        shutil.rmtree(made, ignore_errors=True)
        return None
    return Patched(copy, made)


def _reap(into: Path) -> None:
    """Removes the patched copies of runs that are no longer here to remove their own.

    A copy is taken away by the run that made it, at close or at collection -- but a run killed
    outright collects nothing, and its 200 MB copy would sit under here forever. Each is named
    for the process that made it, so a directory whose process is gone is one nobody will come
    back for, and is swept before a new one is made. A directory whose process is still alive is
    another run's and is left strictly alone.

    Args:
      into: The directory copies are made in.
    """
    import os
    import shutil

    import psutil

    for made in into.glob("*-*-*"):
        if not made.is_dir():
            continue
        try:
            owner = int(made.name.rsplit("-", 2)[1])
        except (IndexError, ValueError):
            continue
        if owner == os.getpid() or psutil.pid_exists(owner):
            continue
        shutil.rmtree(made, ignore_errors=True)


def _rewrite(
    profile: Profile, copy: Path, bundled: Bundled, patches: Sequence[Patch]
) -> bool:
    """Fingerprints a copy afresh and makes the same-length edits inside the module it names.

    The copy is checked against the fingerprint rather than trusted to be the file `located`
    read -- which closes the gap where the installed bundle changed between the two -- and each
    patch is applied only within that module's source span, and only if what it looks for is
    actually there. A site that is not there is a bundle to leave alone, not one to edit blindly.
    The module's bytecode is cleared once any edit was made, so the rewritten source is what runs.

    Args:
      profile: The backend, for the log.
      copy: The copy to edit in place.
      bundled: The fingerprint the copy must answer to -- the line, and the digest where one was
        recorded.
      patches: The rewrites to make.

    Returns:
      Whether the copy was left patched as asked. False for a copy that does not answer to the
      fingerprint or a site that had moved, in which case the copy is not to be used.
    """
    import hashlib
    import mmap
    import struct

    try:
        with copy.open("r+b") as handle, mmap.mmap(handle.fileno(), 0) as raw:
            graph = _graph(raw)
            if graph is None:
                return False
            module = _chosen(graph, raw, bundled.says.encode())
            if module is None:
                log.info(
                    "%s copy no longer names one module -- falling back", profile.name
                )
                return False
            if bundled.digest and bundled.digest != hashlib.sha256(raw).hexdigest():
                log.info(
                    "%s copy is not the digest recorded -- falling back", profile.name
                )
                return False
            one = graph.modules[module]
            source = bytes(raw[one.at : one.at + one.length])
            edited = source
            for patch in patches:
                if patch.find not in edited:
                    log.info(
                        "%s patch site %r had moved -- falling back",
                        profile.name,
                        patch.find,
                    )
                    return False
                edited = edited.replace(patch.find, patch.into)
            if edited != source:
                raw[one.at : one.at + one.length] = edited
                if one.has_bytecode:
                    struct.pack_into("<II", raw, one.bytecode_at, 0, 0)
                raw.flush()
            else:
                log.debug("%s bundle needed no edit", profile.name)
    except (OSError, ValueError) as why:
        log.info("%s copy could not be patched: %s", profile.name, why)
        return False
    return True


def _starts(copy: Path) -> bool:
    """Whether a patched copy runs far enough to say its version.

    Args:
      copy: The program to try.

    Returns:
      True where it answered `--version` cleanly, False where it failed, was killed, or took too
      long -- any of which is a copy not to run a turn on.
    """
    import subprocess

    try:
        done = subprocess.run(
            [str(copy), "--version"],
            capture_output=True,
            timeout=_PROBE_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0
