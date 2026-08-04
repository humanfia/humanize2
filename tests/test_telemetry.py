"""What humanize reports about itself, what it never reports, and who was asked.

Two promises are checked here, because they are the two the feature is worth having only if
it keeps. Nothing is sent by a machine nobody has asked -- an absent answer is not a yes --
and nothing that is sent carries what a person would be surprised by: no task, no prompt, no
path of theirs, no key. The rest is the plumbing that lets a report say what was running.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz import telemetry
from hmz.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _unstarted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Starts each test with nothing reporting, whatever the test before it started."""
    monkeypatch.setattr(telemetry, "_started", [])
    monkeypatch.setattr(telemetry, "_ABOUT", {})


def test_nobody_has_been_asked_until_somebody_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The absence is the whole point: it is what tells a first start from a deliberate no."""
    monkeypatch.delenv(telemetry.SAYS, raising=False)

    assert telemetry.enabled() is None
    assert not telemetry.start()  # and silence sends nothing

    telemetry.asked(enable_sentry=False)
    assert telemetry.enabled() is False
    assert Settings().enable_sentry is False


def test_the_environment_answers_for_one_process_without_writing_it_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is what a scripted install, a CI job and this suite use."""
    monkeypatch.setenv(telemetry.SAYS, "off")
    Settings().answers(enable_sentry=True)

    assert telemetry.enabled() is False  # the environment wins for this process
    assert Settings().enable_sentry is True  # and nothing was written down about it

    monkeypatch.setenv(telemetry.SAYS, "on")
    assert telemetry.enabled() is True


def test_nothing_is_reported_by_a_machine_nobody_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash and a snag both go nowhere, and neither raises for going nowhere."""
    monkeypatch.delenv(telemetry.SAYS, raising=False)
    sent: list[object] = []
    monkeypatch.setattr(telemetry, "start", lambda: bool(sent))

    telemetry.crash(ValueError("nothing to see"), doing="a test")
    telemetry.snag("dead-key", sheet="Nothing")

    assert sent == []


def test_what_the_layers_say_about_a_run_is_asked_for_only_when_it_is_needed() -> None:
    """Nothing is gathered on a machine that reports nothing, which is most of them."""
    asked: list[str] = []

    telemetry.about("flow", lambda: asked.append("flow") or {"flow": "chat"})

    assert asked == []  # registered, not run
    assert telemetry.held() == {"flow": {"flow": "chat"}}
    assert asked == ["flow"]


def test_one_that_cannot_say_is_left_out_rather_than_taking_the_report_with_it() -> (
    None
):
    """A report that could not describe the run is still a report worth having."""

    def raises() -> object:
        raise RuntimeError("no")

    telemetry.about("flow", lambda: {"flow": "chat"})
    telemetry.about("machine", raises)

    assert telemetry.held() == {"flow": {"flow": "chat"}}


@pytest.mark.parametrize(
    ("said", "gone"),
    [
        ("/homes/someone/secret-project/x.py", "/homes/someone"),
        ("https://x-access-token:ghp_abcdefghijklmnop@github.com/org/repo", "ghp_"),
        ("the key is sk-ant-api03-abcdefghijklmnop and it works", "sk-ant-api03"),
        ("https://user:hunter2@example.com/x", "hunter2"),
    ],
)
def test_what_must_not_leave_a_machine_is_taken_out_of_whatever_carries_it(
    said: str, gone: str
) -> None:
    """Every string that reaches a report goes through this, however it got there."""
    assert gone not in telemetry._plainer(said)


def test_a_long_string_is_cut_short_because_it_is_a_file_somebody_pasted() -> None:
    assert len(telemetry._plainer("x" * 4000)) <= telemetry._LONG + 1


def test_no_frame_of_a_stack_carries_what_humanize_was_working_on() -> None:
    """The switch is off in the settings; this is the same thing said again on the way out."""
    event: dict[str, Any] = {
        "server_name": "somebodys-laptop",
        "user": {"id": "someone"},
        "request": {"env": {"REMOTE_ADDR": "10.0.0.1"}},
        "breadcrumbs": [{"message": "the task was: fix the build"}],
        "exception": {
            "values": [
                {
                    "value": "cannot read /homes/someone/project/TASK.md",
                    "stacktrace": {
                        "frames": [
                            {
                                "abs_path": "/homes/someone/humanize/src/hmz/runner.py",
                                "vars": {"task": "fix the build", "key": "sk-abc"},
                                "context_line": "    run(agents, task)",
                                "pre_context": ["    # the task"],
                                "post_context": ["    return"],
                            }
                        ]
                    },
                }
            ]
        },
    }

    held = telemetry._before_send(event, {})

    assert held is not None
    for gone in ("server_name", "user", "request", "breadcrumbs"):
        assert gone not in held
    (one,) = held["exception"]["values"]
    (frame,) = one["stacktrace"]["frames"]
    assert "vars" not in frame
    assert "context_line" not in frame
    assert "pre_context" not in frame
    assert "/homes/someone" not in frame["abs_path"]
    assert "/homes/someone" not in one["value"]


def test_what_is_sent_and_what_is_not_are_both_written_down() -> None:
    """The question cannot be answered by somebody who has not been told what it means."""
    assert len(telemetry.SENT) > 1
    assert len(telemetry.KEPT) > 1
    said = " ".join(telemetry.KEPT).lower()
    for never in ("typed", "transcript", "key"):
        assert never in said


def test_a_setting_written_elsewhere_survives_a_workspace_being_remembered(
    tmp_path: Path,
) -> None:
    """Two of these are alive at once wherever a menu writes one while the app writes flows."""
    from hmz.kept import Runs

    one, other = Settings(tmp_path), Settings(tmp_path)
    one.answers(enable_sentry=True)
    other.remember("chat", ("a",), [Runs("claude/m:high")])

    read = Settings(tmp_path)
    assert read.enable_sentry is True
    assert read.flow == "chat"


def test_a_workspace_may_be_forgotten_without_forgetting_anything_else(
    tmp_path: Path,
) -> None:
    """Which is what the second page of the settings menu is for."""
    from hmz.kept import Runs

    Settings(tmp_path).answers(enable_sentry=False)
    kept = Settings(tmp_path)
    kept.remember("chat", ("a",), [Runs("claude/m:high")])
    elsewhere = Settings(tmp_path / "other")
    elsewhere.remember("rlar", ("a",), [Runs("codex/n:low")])

    assert Settings(tmp_path).forget()

    assert Settings(tmp_path).flow == ""
    assert Settings(tmp_path / "other").flow == "rlar"  # somebody else's is untouched
    assert (
        Settings(tmp_path).enable_sentry is False
    )  # and so is what is true everywhere
    assert not Settings(tmp_path).forget()  # nothing left to forget
