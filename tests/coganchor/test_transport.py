"""Tests for reaching the target: parsing, bootstrapping, and ssh."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hmz.coganchor.transport import Target, build_bundle
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
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "HOME": str(Path.home()),
        },
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
