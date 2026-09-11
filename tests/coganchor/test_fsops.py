"""Every operation a session may ask of its target, replayed on a directory here.

`test_serve.py` drives the shape of the thing -- the export table, the streaming read, the
atomic write -- and four of the mutations. This is the rest of them, one apiece, checked on
the target's own directory rather than on what the reply said: an operation that answered
`{}` and did nothing would pass either way otherwise.

All of it is the serving half, which runs on the target and is POSIX rather than Linux: this
is the file that says so on whatever the matrix is running.
"""

from __future__ import annotations

import errno
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.proto import Op
from hmz.coganchor.remote import RemoteOSError
from tests.coganchor.conftest import VIRTUAL_EXPORT

if TYPE_CHECKING:
    from tests.coganchor.conftest import Link


def _at(link: Link, *named: str) -> str:
    """One path as the session names it, which is not where it really is."""
    return "/".join((VIRTUAL_EXPORT, *named))


# ---------------------------------------------------------------- directories


def test_the_directories_above_one_are_made_where_they_were_asked_for(
    link: Link,
) -> None:
    link.client.mkdir(_at(link, "one/two/three"), parents=True)

    assert (link.target / "one" / "two" / "three").is_dir()


def test_making_one_again_where_the_ones_above_were_asked_for_is_not_a_failure(
    link: Link,
) -> None:
    """`makedirs` with `exist_ok`, which is what `mkdir -p` means."""
    link.client.mkdir(_at(link, "one/two"), parents=True)

    link.client.mkdir(_at(link, "one/two"), parents=True)

    assert (link.target / "one" / "two").is_dir()


def test_a_directory_under_one_that_is_not_there_is_the_target_s_own_errno(
    link: Link,
) -> None:
    with pytest.raises(RemoteOSError) as raised:
        link.client.mkdir(_at(link, "nowhere/at/all"))

    assert raised.value.errno == errno.ENOENT


def test_a_directory_made_at_the_mode_it_was_asked_for_is_at_that_mode(
    link: Link,
) -> None:
    link.client.mkdir(_at(link, "shut"), mode=0o700)

    assert stat.S_IMODE((link.target / "shut").stat().st_mode) == 0o700


# --------------------------------------------------------------------- files


def test_a_file_taken_away_is_gone(link: Link) -> None:
    (link.target / "gone.txt").write_text("here for now")

    link.client.unlink(_at(link, "gone.txt"))

    assert not (link.target / "gone.txt").exists()


def test_a_file_that_was_never_there_is_the_target_s_own_errno(link: Link) -> None:
    with pytest.raises(RemoteOSError) as raised:
        link.client.unlink(_at(link, "never-there.txt"))

    assert raised.value.errno == errno.ENOENT


def test_a_second_name_for_one_file_is_the_same_file(link: Link) -> None:
    (link.target / "first.txt").write_text("one file")

    link.client.link(_at(link, "first.txt"), _at(link, "second.txt"))

    assert (link.target / "second.txt").read_text() == "one file"
    assert (link.target / "first.txt").stat().st_ino == (
        link.target / "second.txt"
    ).stat().st_ino


def test_a_path_moved_without_replacing_is_still_moved(link: Link) -> None:
    (link.target / "here.txt").write_text("moving")

    link.client.rename(_at(link, "here.txt"), _at(link, "there.txt"), replace=False)

    assert not (link.target / "here.txt").exists()
    assert (link.target / "there.txt").read_text() == "moving"


def test_a_path_moved_over_another_replaces_it(link: Link) -> None:
    (link.target / "here.txt").write_text("the new one")
    (link.target / "there.txt").write_text("the old one")

    link.client.rename(_at(link, "here.txt"), _at(link, "there.txt"))

    assert (link.target / "there.txt").read_text() == "the new one"


# ------------------------------------------------------ what is written about one


def test_the_bits_a_path_is_kept_at_are_the_ones_it_was_set_to(link: Link) -> None:
    (link.target / "key").write_text("a secret")

    link.client.chmod(_at(link, "key"), 0o600)

    assert stat.S_IMODE((link.target / "key").stat().st_mode) == 0o600


def test_only_the_permission_bits_are_set(link: Link) -> None:
    """`S_IMODE` of what was asked for: a file must not be made a device by a chmod."""
    (link.target / "key").write_text("a secret")

    link.client.chmod(_at(link, "key"), stat.S_IFREG | 0o640)

    said = (link.target / "key").stat().st_mode
    assert stat.S_IMODE(said) == 0o640
    assert stat.S_ISREG(said)


def test_the_times_a_path_carries_are_the_ones_it_was_given(link: Link) -> None:
    (link.target / "dated.txt").write_text("when")
    when = 1_600_000_000_000_000_000

    link.client.utime(_at(link, "dated.txt"), when, when)

    said = (link.target / "dated.txt").stat()
    assert said.st_mtime_ns == when
    assert said.st_atime_ns == when


def test_a_time_that_was_not_given_is_the_one_the_path_already_had(link: Link) -> None:
    """`None` for one of the two is `UTIME_OMIT`, which is what `utimensat` takes."""
    (link.target / "dated.txt").write_text("when")
    when = 1_600_000_000_000_000_000
    link.client.utime(_at(link, "dated.txt"), when, when)
    later = 1_700_000_000_000_000_000

    link.client.utime(_at(link, "dated.txt"), None, later)

    said = (link.target / "dated.txt").stat()
    assert said.st_mtime_ns == later
    assert said.st_atime_ns == when


# ----------------------------------------------------------------- cutting one down


def test_a_file_cut_down_is_that_long(link: Link) -> None:
    (link.target / "long.txt").write_text("far more than four")

    link.client.call(Op.TRUNCATE, path=_at(link, "long.txt"), size=4)

    assert (link.target / "long.txt").read_bytes() == b"far "


def test_a_file_extended_out_is_that_long_and_the_rest_is_nothing(link: Link) -> None:
    (link.target / "short.txt").write_bytes(b"ab")

    link.client.call(Op.TRUNCATE, path=_at(link, "short.txt"), size=6)

    assert (link.target / "short.txt").read_bytes() == b"ab\0\0\0\0"


# -------------------------------------------------------------- what it reads back


def test_what_a_link_names_is_what_it_names_rather_than_where_it_leads(
    link: Link,
) -> None:
    """Not resolved on the way out: a session asked what the link says, not what is there."""
    link.client.symlink("../outside/the/export", _at(link, "pointing"))

    said = link.client.call(Op.READLINK, path=_at(link, "pointing"))

    assert said["target"] == "../outside/the/export"
    assert (link.target / "pointing").readlink() == Path("../outside/the/export")


def test_something_that_is_not_a_link_is_the_target_s_own_errno(link: Link) -> None:
    (link.target / "plain.txt").write_text("not a link")

    with pytest.raises(RemoteOSError) as raised:
        link.client.call(Op.READLINK, path=_at(link, "plain.txt"))

    assert raised.value.errno == errno.EINVAL
