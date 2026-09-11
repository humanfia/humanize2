"""Unit tests for the lazily materialised mirror of the target workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from hmz.coganchor.policy import Layout, Router
from hmz.coganchor.shadow import ShadowTree, prepare_shadow_root
from tests.coganchor.conftest import VIRTUAL_EXPORT, Link


@dataclass
class Fixture:
    target: Path
    mirror: Path
    shadow: ShadowTree

    def local(self, name: str) -> Path:
        return self.mirror / name


@pytest.fixture
def fixture(link: Link, tmp_path: Path) -> Fixture:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    router = Router(layouts=(Layout.create(str(mirror), VIRTUAL_EXPORT),))
    return Fixture(link.target, mirror, ShadowTree(link.client, router))


def test_directory_materialises_with_target_metadata(fixture: Fixture) -> None:
    (fixture.target / "readme.md").write_text("x" * 1234)
    (fixture.target / "src").mkdir()
    (fixture.target / "link").symlink_to("readme.md")

    fixture.shadow.ensure_directory(str(fixture.mirror))

    mirrored = fixture.local("readme.md")
    assert mirrored.stat().st_size == 1234, "stat must report the target's size"
    assert fixture.local("src").is_dir()
    assert fixture.local("link").readlink() == Path("readme.md")


def test_placeholder_holds_no_content_until_opened(fixture: Fixture) -> None:
    (fixture.target / "big.txt").write_text("real content here")

    fixture.shadow.ensure_directory(str(fixture.mirror))
    assert fixture.local("big.txt").read_bytes() == b"\x00" * len("real content here")

    fixture.shadow.ensure_content(str(fixture.local("big.txt")))
    assert fixture.local("big.txt").read_text() == "real content here"


def test_placeholders_are_sparse(fixture: Fixture) -> None:
    """A large placeholder must not actually consume disk."""
    (fixture.target / "huge.bin").write_bytes(b"\x01" * 8_000_000)

    fixture.shadow.ensure_directory(str(fixture.mirror))
    info = fixture.local("huge.bin").stat()
    assert info.st_size == 8_000_000
    assert info.st_blocks * 512 < 1_000_000


def test_local_edits_are_pushed_on_flush(fixture: Fixture) -> None:
    (fixture.target / "edit.txt").write_text("before")
    fixture.shadow.ensure_content(str(fixture.local("edit.txt")))

    fixture.shadow.note_write(str(fixture.local("edit.txt")))
    fixture.local("edit.txt").write_text("after")

    assert fixture.shadow.flush() == 1
    assert (fixture.target / "edit.txt").read_text() == "after"


def test_flush_is_idempotent(fixture: Fixture) -> None:
    fixture.shadow.ensure_directory(str(fixture.mirror))
    fixture.shadow.note_write(str(fixture.local("new.txt")))
    fixture.local("new.txt").write_text("fresh")

    assert fixture.shadow.flush() == 1
    assert fixture.shadow.flush() == 0, "an unchanged file must not be pushed twice"


def test_new_local_files_reach_the_target(fixture: Fixture) -> None:
    fixture.shadow.ensure_directory(str(fixture.mirror))
    fixture.shadow.note_write(str(fixture.local("created.txt")))
    fixture.local("created.txt").write_text("made locally")

    fixture.shadow.flush()
    assert (fixture.target / "created.txt").read_text() == "made locally"


def test_invalidation_picks_up_target_side_changes(fixture: Fixture) -> None:
    (fixture.target / "shared.txt").write_text("v1")
    fixture.shadow.ensure_content(str(fixture.local("shared.txt")))
    assert fixture.local("shared.txt").read_text() == "v1"

    (fixture.target / "shared.txt").write_text("v2 is longer")
    fixture.shadow.invalidate()
    fixture.shadow.ensure_content(str(fixture.local("shared.txt")))
    assert fixture.local("shared.txt").read_text() == "v2 is longer"


def test_files_deleted_on_the_target_disappear_locally(fixture: Fixture) -> None:
    (fixture.target / "doomed.txt").write_text("bye")
    fixture.shadow.ensure_directory(str(fixture.mirror))
    assert fixture.local("doomed.txt").exists()

    (fixture.target / "doomed.txt").unlink()
    fixture.shadow.invalidate()
    fixture.shadow.ensure_directory(str(fixture.mirror))
    assert not fixture.local("doomed.txt").exists()


def test_rename_carries_the_record_across(fixture: Fixture) -> None:
    (fixture.target / "old.txt").write_text("contents")
    fixture.shadow.ensure_directory(str(fixture.mirror))

    (fixture.target / "old.txt").rename(fixture.target / "new.txt")
    fixture.local("old.txt").rename(fixture.local("new.txt"))
    fixture.shadow.rename(str(fixture.local("old.txt")), str(fixture.local("new.txt")))

    fixture.shadow.ensure_content(str(fixture.local("new.txt")))
    assert fixture.local("new.txt").read_text() == "contents"


def test_missing_directory_is_reported_not_raised(fixture: Fixture) -> None:
    fixture.shadow.ensure_directory(str(fixture.mirror / "absent"))
    assert not (fixture.mirror / "absent").exists()


def test_paths_outside_the_layout_are_ignored(fixture: Fixture, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere" / "file.txt"
    fixture.shadow.ensure_directory(str(outside.parent))
    fixture.shadow.ensure_content(str(outside))
    assert not outside.exists()


# ------------------------------------------------------------- shadow root


def test_prepare_creates_a_missing_root(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    prepare_shadow_root(str(root))
    assert root.is_dir()


def test_prepare_leaves_no_marker_inside_the_workspace(tmp_path: Path) -> None:
    """An agent listing the workspace must not see coganchor's bookkeeping."""
    root = tmp_path / "clean"
    prepare_shadow_root(str(root))
    assert list(root.iterdir()) == []


def test_prepare_refuses_a_directory_with_unrelated_files(tmp_path: Path) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "important.txt").write_text("do not delete me")

    with pytest.raises(FileExistsError, match="not an humanize mirror"):
        prepare_shadow_root(str(root))
    assert (root / "important.txt").exists()


def test_prepare_accepts_a_previously_used_root(tmp_path: Path) -> None:
    root = tmp_path / "reused"
    prepare_shadow_root(str(root))
    (root / "mirrored.txt").write_text("from an earlier run")
    prepare_shadow_root(str(root))


def test_prepare_refuses_a_mirror_recorded_against_another_target(
    tmp_path: Path,
) -> None:
    """Reusing a mirror for a second target would delete what only the first has."""
    root = tmp_path / "reused"
    prepare_shadow_root(str(root), target="ssh://one")
    (root / "from-one.txt").write_text("only the first target has this")

    with pytest.raises(FileExistsError, match="mirrors ssh://one"):
        prepare_shadow_root(str(root), target="ssh://two")
    assert (root / "from-one.txt").exists()

    prepare_shadow_root(str(root), target="ssh://two", force=True)


def test_prepare_can_be_forced(tmp_path: Path) -> None:
    root = tmp_path / "forced"
    root.mkdir()
    (root / "stuff.txt").write_text("x")
    prepare_shadow_root(str(root), force=True)


def _linked(fixture: Fixture) -> tuple[str, str]:
    """One placeholder, and a second name for it made on both sides as a hard link is.

    Returns:
      The two local paths, the first mirrored and the second only just made.
    """
    (fixture.target / "one.txt").write_text("real content here")
    fixture.shadow.ensure_directory(str(fixture.mirror))
    # The tracee's `link` lands on both: here, and replayed on the target.
    (fixture.target / "two.txt").hardlink_to(fixture.target / "one.txt")
    first, second = str(fixture.local("one.txt")), str(fixture.local("two.txt"))
    Path(second).hardlink_to(first)
    return first, second


def test_a_second_name_for_a_placeholder_reads_the_file_rather_than_its_zeroes(
    fixture: Fixture,
) -> None:
    first, second = _linked(fixture)

    fixture.shadow.duplicate(first, second)

    fixture.shadow.ensure_content(second)
    assert fixture.local("two.txt").read_text() == "real content here"


def test_a_second_name_nobody_recorded_is_the_zeroes_it_holds(fixture: Fixture) -> None:
    """Which is what `duplicate` is for: a placeholder reached by a name with no record."""
    _first, second = _linked(fixture)

    fixture.shadow.ensure_content(second)

    assert fixture.local("two.txt").read_bytes() == b"\x00" * len("real content here")


def test_a_second_name_for_something_nobody_recorded_records_nothing(
    fixture: Fixture,
) -> None:
    """A hard link between two files the mirror never made is not the mirror's to know."""
    fixture.shadow.duplicate(
        str(fixture.local("never-mirrored")), str(fixture.local("nor-this"))
    )

    assert str(fixture.local("nor-this")) not in fixture.shadow._files


def test_what_was_taken_away_is_forgotten_whole(fixture: Fixture) -> None:
    """A directory dropped takes what was under it, or the next run reads a stale record."""
    (fixture.target / "box").mkdir()
    (fixture.target / "box" / "inside.txt").write_text("under it")
    fixture.shadow.ensure_directory(str(fixture.mirror))
    fixture.shadow.ensure_directory(str(fixture.local("box")))
    assert any("inside.txt" in one for one in fixture.shadow._files)

    fixture.shadow.forget(str(fixture.local("box")))

    assert not any("inside.txt" in one for one in fixture.shadow._files)
    assert not any("box" in one for one in fixture.shadow._dirs)


def test_a_write_outside_the_mirror_is_not_the_mirror_s_to_push(
    fixture: Fixture, tmp_path: Path
) -> None:
    """The tracee writes to its own machine as well, and none of that goes to the target."""
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("this machine's own")

    fixture.shadow.note_write(str(elsewhere))

    assert fixture.shadow.flush() == 0


def test_a_file_that_went_away_before_the_push_is_not_pushed(fixture: Fixture) -> None:
    """The unlink was replayed already, so there is nothing left here to send."""
    (fixture.target / "gone.txt").write_text("here for now")
    fixture.shadow.ensure_directory(str(fixture.mirror))
    fixture.local("gone.txt").write_text("edited")
    fixture.shadow.note_write(str(fixture.local("gone.txt")))
    fixture.local("gone.txt").unlink()

    assert fixture.shadow.flush() == 0


def test_something_that_is_not_a_file_is_not_pushed(fixture: Fixture) -> None:
    """A directory the tracee made is replayed as a mkdir rather than sent as bytes."""
    made = fixture.local("made")
    made.mkdir(parents=True)

    fixture.shadow.note_write(str(made))

    assert fixture.shadow.flush() == 0


def test_content_is_fetched_through_the_link_that_names_it(fixture: Fixture) -> None:
    """A tracee opens a symlink and expects the file, so the mirror follows it first."""
    (fixture.target / "real.txt").write_text("what the link leads to")
    (fixture.target / "alias").symlink_to("real.txt")
    fixture.shadow.ensure_directory(str(fixture.mirror))

    fixture.shadow.ensure_content(str(fixture.local("alias")))

    assert fixture.local("real.txt").read_text() == "what the link leads to"
