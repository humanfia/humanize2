"""Unit tests for path routing and program placement."""

from __future__ import annotations

import pytest

from hmz.coganchor.policy import Layout, Router


def make_router(**kwargs: object) -> Router:
    return Router(layouts=(Layout.create("/mirror", "/project"),), **kwargs)  # pyright: ignore[reportArgumentType]


def test_identity_layout_keeps_paths_unchanged() -> None:
    layout = Layout.create("/home/user/project", None)
    assert (
        layout.to_virtual("/home/user/project/src/a.py")
        == "/home/user/project/src/a.py"
    )


def test_layout_translates_the_mirror_onto_the_target() -> None:
    layout = Layout.create("/mirror", "/project")
    assert layout.to_virtual("/mirror/src/a.py") == "/project/src/a.py"
    assert layout.to_virtual("/mirror") == "/project"


def test_paths_inside_the_layout_are_remote() -> None:
    router = make_router()
    assert router.is_remote_path("/mirror/src/a.py")
    assert router.is_remote_path("/mirror")
    assert not router.is_remote_path("/mirrored-elsewhere/a.py")
    assert not router.is_remote_path("/etc/passwd")


def test_local_paths_carve_holes_in_the_layout() -> None:
    router = make_router(local_paths=("/mirror/.agent-state",))
    assert router.is_remote_path("/mirror/src/a.py")
    assert not router.is_remote_path("/mirror/.agent-state/session.json")


def test_nested_layouts_prefer_the_longest_match() -> None:
    router = Router(
        layouts=(
            Layout.create("/mirror", "/project"),
            Layout.create("/mirror/data", "/data"),
        ),
    )
    assert router.to_virtual("/mirror/src/a.py") == "/project/src/a.py"
    assert router.to_virtual("/mirror/data/set.csv") == "/data/set.csv"


def test_programs_default_to_the_target() -> None:
    router = make_router(local_programs=("/opt/agent/bin/agent",))
    assert not router.runs_locally("/bin/bash")
    assert not router.runs_locally("/usr/bin/git")
    assert router.runs_locally("/opt/agent/bin/agent")


def test_working_directory_outside_a_layout_is_untouched() -> None:
    router = make_router()
    assert router.virtual_cwd("/mirror/sub") == "/project/sub"
    assert router.virtual_cwd("/tmp") == "/tmp"


def test_rewrite_is_a_no_op_for_identity_layouts() -> None:
    router = Router(layouts=(Layout.create("/project", None),))
    assert router.rewrite("cat /project/f") == "cat /project/f"


def test_rewrite_maps_mirror_paths_to_target_paths() -> None:
    assert make_router().rewrite("cat /mirror/f") == "cat /project/f"


def test_to_virtual_rejects_paths_outside_every_layout() -> None:
    with pytest.raises(ValueError, match="not inside"):
        make_router().to_virtual("/etc/passwd")


def mac_router(**kwargs: object) -> Router:
    """A router whose target said it is a Mac, which is the only end that can say."""
    return Router(platform=lambda: "darwin", **kwargs)  # pyright: ignore[reportArgumentType]


def test_a_path_the_target_spells_through_private_is_settled_onto_the_mirror() -> None:
    """`/tmp` on a Mac is reached through `/private/tmp`, and both name the mirror."""
    router = Router(layouts=(Layout.create("/tmp/mirror", "/project"),))
    assert router.canonical("/private/tmp/mirror/src/a.py") == "/tmp/mirror/src/a.py"
    assert router.is_remote_path(router.canonical("/private/tmp/mirror/src/a.py"))
    assert (
        router.to_virtual(router.canonical("/private/tmp/mirror/src/a.py"))
        == "/project/src/a.py"
    )


def test_a_path_outside_every_layout_keeps_the_spelling_it_was_named_with() -> None:
    """The regression that sank folding at comparison time, guarded from the other side.

    A `/private` path that is not the mirror's stays exactly as it was named, so it is
    answered by this machine as any other absent path is -- one that is not there, rather
    than one under a directory only root may create.
    """
    router = Router(layouts=(Layout.create("/tmp/mirror", "/project"),))
    for outside in (
        "/private/tmp/elsewhere/a.py",
        "/private/tmp/mirror-elsewhere/a.py",
        "/private/var/db/secret",
    ):
        assert router.canonical(outside) == outside
        assert not router.is_remote_path(router.canonical(outside))


def test_a_mirror_named_under_private_is_settled_onto_its_own_root() -> None:
    """Settling re-roots onto the layout's own spelling, whichever way that is written."""
    router = Router(layouts=(Layout.create("/private/tmp/mirror", "/project"),))
    assert router.canonical("/tmp/mirror/src/a.py") == "/private/tmp/mirror/src/a.py"
    assert router.canonical("/private/tmp/mirror") == "/private/tmp/mirror"


def test_case_is_settled_only_when_the_target_says_it_ignores_case() -> None:
    """A Mac reads `/users/me` and `/Users/me` as one directory; Linux reads two."""
    layouts = (Layout.create("/Users/me/w", "/Users/me/w"),)
    assert mac_router(layouts=layouts).canonical("/users/ME/w/Src/A.py") == (
        "/Users/me/w/Src/A.py"
    )
    assert Router(layouts=layouts).canonical("/users/ME/w/Src/A.py") == (
        "/users/ME/w/Src/A.py"
    )


def test_a_target_that_has_not_been_reached_yet_is_no_mac() -> None:
    """The settings are written before the handshake, so until it happens nothing folds."""
    router = Router(layouts=(Layout.create("/Users/me/w", None),))
    assert not router.insensitive
    assert not router.is_remote_path("/users/me/w/a.py")


def test_a_session_with_one_spelling_for_everything_has_nothing_to_settle() -> None:
    """What the supervisor asks before it reads a syscall's paths a second time."""
    assert not Router(layouts=(Layout.create("/home/me/w", None),)).settles
    assert Router(layouts=(Layout.create("/tmp/mirror", None),)).settles
    assert Router(layouts=(Layout.create("/private/tmp/mirror", None),)).settles
    assert mac_router(layouts=(Layout.create("/home/me/w", None),)).settles
    # A mirror at the root holds both spellings of three directories, so it settles too.
    assert Router(layouts=(Layout.create("/", None),)).settles


def test_a_layout_names_a_path_it_was_given_in_another_case() -> None:
    """What a caller reaching a layout without the router's flag must still be answered.

    `ShadowTree` resolves against the layout it was handed, and a fall-through to the
    workspace root would push a file's bytes at the workspace directory itself.
    """
    layout = Layout.create("/Users/me/w", "/project")
    assert layout.to_virtual("/Users/ME/w/vendor/lib.py") == "/project/vendor/lib.py"
    with pytest.raises(ValueError, match="not inside"):
        layout.to_virtual("/etc/passwd")


def test_a_hole_is_carved_by_the_rule_the_layout_is_matched_by() -> None:
    """The agent's own state must not be mirrored because a model typed it differently."""
    kept = ("/Users/me/w/.agent-state",)
    assert not mac_router(
        layouts=(Layout.create("/Users/me/w", "/project"),), local_paths=kept
    ).is_remote_path("/Users/me/w/.Agent-State/session.json")
    assert Router(
        layouts=(Layout.create("/Users/me/w", "/project"),), local_paths=kept
    ).is_remote_path("/Users/me/w/.Agent-State/session.json")


def test_an_argument_naming_the_mirror_by_its_other_name_is_rewritten() -> None:
    """`/tmp/m` and `/private/tmp/m` are one directory, and a command may name either."""
    router = Router(layouts=(Layout.create("/tmp/mirror", "/project"),))
    assert (
        router.rewrite("grep -r x /private/tmp/mirror/src") == "grep -r x /project/src"
    )
    assert router.rewrite("grep -r x /tmp/mirror/src") == "grep -r x /project/src"


def test_an_argument_naming_the_mirror_in_another_case_is_rewritten_for_a_mac() -> None:
    layouts = (Layout.create("/Mirror", "/project"),)
    assert mac_router(layouts=layouts).rewrite("cat /mirror/f") == "cat /project/f"
    assert Router(layouts=layouts).rewrite("cat /mirror/f") == "cat /mirror/f"
