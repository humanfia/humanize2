"""The copy of a credential a redirected run answers reads from.

The cache on its own, without a supervisor around it: what is copied, what is not, when a copy
stops being the answer, and what is left on `/dev/shm` afterwards. The half of it that is a
tracee reading through the copy is in `test_redirect.py`, where the supervisor is.

Everything here is a file under `tmp_path`. Nothing reaches a real credential.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.providers import _staging
from hmz.coganchor.providers._staging import Staging

if TYPE_CHECKING:
    from collections.abc import Iterator

#: What a provider's file holds here, which is what a copy of it has to hold too.
PROVIDER = '{"token": "the provider"}'

pytestmark = pytest.mark.skipif(
    not _staging._ROOT.is_dir(), reason="there is no /dev/shm to copy a credential into"
)


@pytest.fixture
def staging() -> Iterator[Staging]:
    """A cache that takes its directory away again however the test ends."""
    held = Staging()
    try:
        yield held
    finally:
        held.close()


@pytest.fixture
def credential(tmp_path: Path) -> Path:
    """A provider's own credential file, at the mode these are kept at."""
    at = tmp_path / ".credentials.json"
    at.write_text(PROVIDER)
    at.chmod(0o600)
    return at


def test_a_credential_is_copied_once_and_answered_from_the_copy(
    staging: Staging, credential: Path
) -> None:
    at = staging.reading(str(credential))

    assert at is not None
    assert Path(at).read_text() == PROVIDER
    assert staging.reading(str(credential)) == at  # the second read makes nothing


def test_the_copy_is_in_memory_and_this_users_alone(
    staging: Staging, credential: Path
) -> None:
    """`/dev/shm` is shared and world-writable: a secret put there is put there at 0600."""
    at = Path(staging.reading(str(credential)) or "")

    assert at.is_relative_to(_staging._ROOT)
    assert stat.S_IMODE(at.stat().st_mode) == 0o600
    assert stat.S_IMODE(at.parent.stat().st_mode) == 0o700
    assert at.parent.stat().st_uid == os.getuid()


def test_the_copy_says_what_the_provider_says_about_when_it_changed(
    staging: Staging, credential: Path
) -> None:
    """A CLI that reads a credential again when it changed must not read a copy as a change."""
    at = Path(staging.reading(str(credential)) or "")

    assert at.stat().st_mtime_ns == credential.stat().st_mtime_ns


def test_a_credential_that_was_written_is_copied_again(
    staging: Staging, credential: Path
) -> None:
    """The half that is not an optimisation: the write went to the provider's own file."""
    first = staging.reading(str(credential))

    staging.wrote(str(credential))
    credential.write_text("refreshed")
    second = staging.reading(str(credential))

    assert first is not None
    assert not Path(first).exists()  # and the token it held is gone from memory with it
    assert second is not None
    assert second != first
    assert Path(second).read_text() == "refreshed"


def test_a_credential_another_run_refreshed_is_noticed(
    staging: Staging, credential: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two agents of one account: the other one's refresh is a write this run never saw."""
    monkeypatch.setattr(_staging, "_FRESH", 0.0)
    staging.reading(str(credential))

    credential.write_text("somebody else's refresh")
    again = staging.reading(str(credential))

    assert again is not None
    assert Path(again).read_text() == "somebody else's refresh"


def test_a_credential_that_has_not_changed_is_not_copied_again(
    staging: Staging, credential: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_staging, "_FRESH", 0.0)
    first = staging.reading(str(credential))

    assert staging.reading(str(credential)) == first


@pytest.mark.parametrize(
    "name",
    [
        # A directory is listed and written into, and kimi keeps one credential per endpoint
        # it has signed into, so what is inside one has to be what is really inside it.
        "oauth",
        # A lock is a rendezvous between processes, and a copy of one is a lock the other
        # process cannot see. pi keeps one beside its `auth.json`.
        ".credentials.json.lock",
        # Nothing there at all: the read has to fail where the provider is, not read the copy
        # of something else.
        "never-signed-in",
    ],
)
def test_what_there_is_no_copy_of_is_answered_with_itself(
    staging: Staging, tmp_path: Path, name: str
) -> None:
    at = tmp_path / name
    if name == "oauth":
        at.mkdir()
    elif at.suffix == ".lock":
        at.write_text("")

    assert staging.reading(str(at)) is None
    # And that is an answer to hold: an account with four credential paths and one file has
    # three that are not there, and a CLI asks about those hundreds of times too.
    assert str(at) in staging._held


def test_a_file_too_large_to_be_a_credential_is_left_where_it_is(
    staging: Staging, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Megabytes are a CLI's project history rather than its account."""
    monkeypatch.setattr(_staging, "_MOST", 8)
    at = tmp_path / "history.json"
    at.write_text(PROVIDER)

    assert staging.reading(str(at)) is None


def test_a_symlink_is_answered_with_itself(staging: Staging, tmp_path: Path) -> None:
    """What a link says is asked of the link, and a copy of one is a regular file."""
    at = tmp_path / "link"
    at.symlink_to(tmp_path / "elsewhere")

    assert staging.reading(str(at)) is None


def test_nothing_is_left_in_memory_when_the_run_is_over(credential: Path) -> None:
    held = Staging()
    at = held.reading(str(credential))

    held.close()

    assert at is not None
    assert not Path(at).parent.exists()
    assert held.reading(str(credential)) is None  # and nothing is made after that


def test_a_run_that_never_reads_a_credential_makes_no_directory(tmp_path: Path) -> None:
    """The account nobody chose costs nothing, and so does the turn that only writes."""
    held = Staging()
    try:
        held.wrote(str(tmp_path / "nothing"))

        assert held._at is None
    finally:
        held.close()


def test_what_a_run_that_was_killed_left_behind_is_swept_up(credential: Path) -> None:
    """Teardown belongs to the run that made it, and `SIGKILL` runs no teardown."""
    gone = os.fork()
    if not gone:
        os._exit(0)  # a process id nothing is using, which is what a killed run leaves
    os.waitpid(gone, 0)
    left = _staging._ROOT / f"hmz-{gone}-00000000-abcdefgh"
    left.mkdir(mode=0o700)
    (left / "1.credentials.json").write_text(PROVIDER)

    held = Staging()
    try:
        held.reading(str(credential))
    finally:
        held.close()

    assert not left.exists()


def test_whoever_killed_a_supervisor_sweeps_up_after_it() -> None:
    """Which is how a turn ends: the process it ran in is killed, and `SIGKILL` runs nothing."""
    killed = os.fork()
    if not killed:
        os._exit(0)
    os.waitpid(killed, 0)
    theirs = os.fork()
    if not theirs:
        os._exit(0)
    os.waitpid(theirs, 0)
    left = _staging._ROOT / f"hmz-{killed}-00000000-abcdefgh"
    beside = _staging._ROOT / f"hmz-{theirs}-00000000-abcdefgh"
    left.mkdir(mode=0o700)
    beside.mkdir(mode=0o700)
    (left / "1.credentials.json").write_text(PROVIDER)

    try:
        _staging.swept(killed)

        assert not left.exists()
        assert beside.exists()  # another run's is another run's to sweep
    finally:
        beside.rmdir()


def test_a_directory_of_a_run_that_is_still_going_is_left_alone(
    credential: Path,
) -> None:
    """A pid that is somebody's is a run whose credentials are being read this moment."""
    mine = _staging._ROOT / f"hmz-{os.getpid()}-00000000-abcdefgh"
    mine.mkdir(mode=0o700)
    held = Staging()
    try:
        held.reading(str(credential))

        assert mine.exists()
    finally:
        held.close()
        mine.rmdir()
