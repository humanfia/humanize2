"""Tests for reaching the target: parsing, bootstrapping, and ssh."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hmz.coganchor.transport import (
    MINIMUM_PYTHON,
    PYTHON_CANDIDATES,
    REMOTE_CACHE,
    Target,
    _ssh_serve_line,
    build_bundle,
    python_command,
)
from tests.coganchor.conftest import REPO_ROOT, Anchorage


def test_target_parsing() -> None:
    assert Target.parse("ssh://build-box") == Target("ssh", host="build-box")
    assert Target.parse("ssh://user@box:2222") == Target(
        "ssh", host="user@box", port=2222
    )
    assert Target.parse("docker://janus-9f2c") == Target("docker", host="janus-9f2c")
    assert Target.parse("tcp://10.0.0.5:7777") == Target(
        "tcp", host="10.0.0.5", port=7777
    )
    assert Target.parse("local") == Target("local")
    assert Target.parse("local:/srv/project") == Target("local", path="/srv/project")


@pytest.mark.parametrize(
    "spec", ["", "box", "http://box", "docker://", "tcp://box", "tcp://box:none"]
)
def test_malformed_targets_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError, match=r"target|expected"):
        Target.parse(spec)


def test_target_descriptions_round_trip() -> None:
    for spec in (
        "ssh://build-box",
        "docker://janus-9f2c",
        "tcp://10.0.0.5:7777",
        "local:/srv/project",
    ):
        assert Target.parse(spec).describe() == spec


def test_bundle_is_self_contained(tmp_path: Path) -> None:
    """The target needs nothing but python3, so the bundle must run alone."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    assert bundle.stat().st_size > 0

    result = subprocess.run(
        [sys.executable, str(bundle), "anchor", "serve", "--help"],
        capture_output=True,
        text=True,
        # An empty PYTHONPATH proves nothing is being imported from this repo.
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        cwd="/",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--export" in result.stdout


def test_the_bundle_is_the_same_wherever_it_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The target caches it by digest, so nothing but the source may change it."""
    here = build_bundle(tmp_path / "here.pyz").read_bytes()
    umask = os.umask(0o002)
    try:
        # A zip entry holds local wall-clock time, so west of UTC is where a bundle stamped with
        # a fixed instant both forks the digest and falls out of the range a zip can hold. The
        # umask is the other thing a second developer would differ in.
        monkeypatch.setenv("TZ", "America/Los_Angeles")
        time.tzset()
        elsewhere = build_bundle(tmp_path / "elsewhere.pyz").read_bytes()
    finally:
        os.umask(umask)
        monkeypatch.undo()
        time.tzset()
    assert here == elsewhere


def test_bundle_reports_failure_in_its_exit_status(tmp_path: Path) -> None:
    """A target that cannot start must not look like a clean exit."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    target = tmp_path / "target"
    target.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(bundle),
            "anchor",
            "serve",
            "--export",
            f"/project:{target}",
            "--listen",
            "bad",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, "the bundle swallowed a start-up failure"
    assert "malformed listen address" in result.stderr


def test_a_target_keeping_its_python_off_the_path_is_found_it_anyway(
    tmp_path: Path,
) -> None:
    """An interpreter that is not on the ``PATH`` is still an interpreter.

    macOS ships no ``python3`` on the ``PATH`` a remote command is given, so looking there
    and stopping is a target that fails for want of something it has. Driven with an empty
    ``PATH`` for real, which is the same target as a Mac's: the bare names answer to nothing
    and only the places one is kept are left.
    """
    kept = [
        candidate
        for candidate in PYTHON_CANDIDATES
        if candidate.startswith("/") and os.access(candidate, os.X_OK)
    ]
    if not kept:
        pytest.skip(
            "this machine keeps no interpreter at any of the absolute candidates"
        )
    empty = tmp_path / "empty"
    empty.mkdir()

    said = "import sys; print(sys.version_info[0], sys.version_info[1])"
    result = subprocess.run(
        python_command(["-c", said]),
        capture_output=True,
        text=True,
        env={"PATH": str(empty)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    found = tuple(int(part) for part in result.stdout.split())
    assert found >= MINIMUM_PYTHON, "an interpreter too old for the bundle was taken"


def test_a_target_with_no_python_at_all_says_what_it_looked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer is to install one of them, so the list is the message."""
    monkeypatch.setattr(
        "hmz.coganchor.transport.PYTHON_CANDIDATES", ("python3-not-here", "/no/python3")
    )

    result = subprocess.run(
        python_command(["-c", "pass"]), capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "python3-not-here" in result.stderr
    assert "/no/python3" in result.stderr


def test_the_line_ssh_carries_is_read_by_the_shell_there_before_anything_runs() -> None:
    """So what it must not take apart, and what it must, are both in it.

    The line that finds the interpreter is a script and travels quoted; the cache path
    travels bare, because the ``~`` in it is that shell's to expand and a quoted one names a
    directory called ``~`` under wherever the session began; and an export holding a space is
    one word on arrival.
    """
    bundle = f"{REMOTE_CACHE}/humanize-0123456789abcdef.pyz"

    line = _ssh_serve_line(bundle, ["/a b:/c d"])

    words = shlex.split(line)
    assert words[:3] == ["exec", "/bin/sh", "-c"]
    assert "for py in" in words[3], (
        "the line that finds the interpreter arrived in pieces"
    )
    assert words[4:7] == ["humanize", bundle, "anchor"]
    assert words[-2:] == ["--export", "/a b:/c d"]
    assert f" {bundle} " in line, (
        "a quoted ~ is a directory of that name, not the home one"
    )


def _bare() -> dict[str, str]:
    """The environment the anchored run below gets, which is the one the probe must use.

    Deliberately small -- a `PATH`, the source tree, and a home to read an ssh config out of
    -- so that what reaches the far side is what humanize puts there rather than whatever the
    suite happened to be started with. `SSH_AUTH_SOCK` is the one that matters: an agent
    forwarded into the terminal running the tests would let a probe in and leave the run
    itself outside, which is a skip that never happens in front of a failure that always
    does.
    """
    return {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "HOME": str(Path.home()),
    }


def _ssh_to_localhost_works() -> bool:
    try:
        probe = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "localhost",
                "true",
            ],
            capture_output=True,
            timeout=20,
            env=_bare(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


@pytest.mark.timeout(180)
def test_ssh_transport_bootstraps_and_runs(tmp_path: Path) -> None:
    """The full ssh path: build a zipapp, ship it, and work through the pipe."""
    if not _ssh_to_localhost_works():
        pytest.skip("passwordless ssh to localhost is not available")

    target = tmp_path / "target"
    mirror = tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()
    (target / "shipped.txt").write_text("arrived over ssh\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hmz",
            "anchor",
            "--target",
            "ssh://localhost",
            "--workspace",
            "/coganchor-project",
            "--remote-path",
            str(target),
            "--shadow",
            str(mirror),
            "bash",
            "-c",
            "cat shipped.txt; echo written-back > reply.txt",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_bare(),
        timeout=150,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "arrived over ssh" in result.stdout
    assert (target / "reply.txt").read_text() == "written-back\n"


def test_running_without_an_agent_is_an_error(anchorage: Anchorage) -> None:
    result = anchorage.run()
    assert result.returncode == 2
    assert "no agent given" in result.stderr


def test_unknown_agent_is_reported_clearly(anchorage: Anchorage) -> None:
    result = anchorage.run("definitely-not-installed-xyz")
    assert result.returncode == 1
    assert "not found on PATH" in result.stderr
