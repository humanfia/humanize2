"""End-to-end smoke tests: every task in the catalogue, checked on the target."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from humanize.coganchor import standin
from tests.coganchor.conftest import Anchorage
from tests.coganchor.tasks import SMOKE_TASKS, SmokeTask


def test_catalogue_is_large_enough() -> None:
    """The suite is meant to cover a broad slice of real agent behaviour."""
    assert len(SMOKE_TASKS) >= 50
    assert len({task.name for task in SMOKE_TASKS}) == len(SMOKE_TASKS)


@pytest.mark.parametrize("task", SMOKE_TASKS, ids=lambda task: task.name)
def test_smoke_task(anchorage: Anchorage, task: SmokeTask) -> None:
    anchorage.seed(task.seed)
    result = anchorage.run(*task.command, stdin=task.stdin)
    combined = result.stdout + result.stderr

    assert result.returncode == task.exit_code, (
        f"{task.name}: exit {result.returncode} != {task.exit_code}\n{combined}"
    )
    for expected in task.stdout:
        assert expected in combined, f"{task.name}: missing {expected!r} in\n{combined}"
    for forbidden in task.absent:
        assert forbidden not in combined, f"{task.name}: unexpected {forbidden!r}"

    for name, content in task.target_files.items():
        path = anchorage.target / name
        assert path.exists(), f"{task.name}: {name} never reached the target"
        assert path.read_text() == content, f"{task.name}: {name} has the wrong content"
    for name in task.target_missing:
        assert not (anchorage.target / name).exists(), (
            f"{task.name}: {name} should have been removed on the target"
        )


def test_stub_program_is_usable() -> None:
    """The stand-in's exec must succeed, or a command would look like it failed."""
    assert os.access(standin.STUB_PROGRAM, os.X_OK)


def test_seeded_files_exist_only_on_the_target(anchorage: Anchorage) -> None:
    """The mirror starts empty, so a successful read must have crossed the wire."""
    anchorage.seed({"proof.txt": "only on B\n"})
    assert not (anchorage.mirror / "proof.txt").exists()

    result = anchorage.shell("cat proof.txt")
    assert "only on B" in result.stdout


def test_writes_never_stay_local_only(anchorage: Anchorage) -> None:
    result = anchorage.shell("echo landed > evidence.txt")
    assert result.returncode == 0
    assert anchorage.target_text("evidence.txt") == "landed\n"


def test_agent_state_directory_is_not_mirrored(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """A path listed as agent state keeps using the local machine."""
    private = tmp_path / "private"
    private.mkdir()
    (private / "token").write_text("local secret\n")

    result = anchorage.run(
        "bash", "-c", f"cat {private}/token", local_paths=(str(private),)
    )
    assert "local secret" in result.stdout


def test_exit_status_survives_a_signal(anchorage: Anchorage) -> None:
    result = anchorage.shell("bash -c 'kill -9 $$'; echo status=$?")
    assert "status=137" in result.stdout


def test_large_round_trip_is_byte_exact(anchorage: Anchorage) -> None:
    payload = "".join(f"{index:07d}\n" for index in range(40_000))
    anchorage.seed({"payload.txt": payload})

    result = anchorage.shell(
        "cp payload.txt echoed.txt; md5sum payload.txt echoed.txt | cut -d' ' -f1 | uniq | wc -l"
    )
    assert "1" in result.stdout
    assert anchorage.target_text("echoed.txt") == payload
