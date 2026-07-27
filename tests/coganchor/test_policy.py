"""Unit tests for path routing and program placement."""

from __future__ import annotations

import pytest

from humanize.coganchor.policy import Layout, Router


def make_router(**kwargs: object) -> Router:
    return Router(layouts=(Layout.create("/mirror", "/project"),), **kwargs)  # type: ignore[arg-type]


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
