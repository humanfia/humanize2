"""humanize1: what it refuses to be set up as, and what a round has to get past.

The flow is PolyArch/humanize, so what is checked here is that it still is: the combinations
the plugin cannot run are refused before a turn is taken, the markers it reads are read the
same way, and the gates its stop hook runs still refuse the same rounds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from humanize.agents import Moment, Occasion
from humanize.flows._rlcr import guards, loop, prompts
from humanize.flows.humanize1 import Config
from humanize.runner import configures, drives, wanted

if TYPE_CHECKING:
    from pathlib import Path


def _loop(tmp_path: Path, **fields: object) -> loop.Loop:
    """A loop of the shape a run has, with nothing driving it."""
    where = tmp_path / ".humanize" / "rlcr" / "now"
    where.mkdir(parents=True)
    state = loop.State(plan_file="docs/plan.md", start_branch="main", **fields)  # pyright: ignore[reportArgumentType]
    running = loop.Loop(None, where, tmp_path, state)  # pyright: ignore[reportArgumentType]
    (where / "state.md").write_text(state.written())
    return running


# ------------------------------------------------------------------------------------
# What the flow drives, and what it says it can be set up with
# ------------------------------------------------------------------------------------


def test_each_phase_has_its_own_agents_and_the_person_is_not_chosen() -> None:
    """One per side of each phase, and the builder has to be one a hook can say no to."""
    assert drives("humanize1") == (
        "drafter",
        "planner",
        "analyst",
        "builder",
        "reviewer",
    )
    places = {place.name: place for place in wanted("humanize1")}
    assert Moment.PERMISSION_REQUEST in places["builder"].moments
    # And nobody is asked what the person runs, so they are not among the five.
    assert "human" not in places


def test_the_flow_says_it_can_be_set_up_with_its_own_config() -> None:
    """Which is how anything starting it finds out there is anything to ask about."""
    model = configures("humanize1")

    assert model is not None
    assert set(model.model_fields) == set(Config.model_fields)


def test_every_flag_the_plugin_takes_is_a_field() -> None:
    """One field per flag, under the plugin's own name for it."""
    fields = set(Config.model_fields)

    assert {
        "n",
        "gen_plan_mode",
        "auto_start_rlcr_if_converged",
        "alternative_plan_language",
        "plan_file",
        "max",
        "codex_timeout",
        "full_review_round",
        "base_branch",
        "track_plan_file",
        "push_every_round",
        "skip_impl",
        "claude_answer_codex",
        "agent_teams",
        "skip_quiz",
        "yolo",
        "privacy",
        "require_bitlesson_entry_for_none",
    } <= fields


def test_the_defaults_are_the_plugin_s_own() -> None:
    """A run nobody set up is the run the plugin does with no flags at all."""
    config = Config()

    assert (config.gen_idea, config.gen_plan, config.rlcr) == (True, True, True)
    assert (config.n, config.max, config.full_review_round) == (6, 42, 5)
    assert config.codex_timeout == 5400
    assert config.gen_plan_mode == "discussion"


def test_yolo_is_the_two_flags_it_is_a_name_for() -> None:
    """As `--yolo` is in the plugin: an alias, spelled out where it is read."""
    config = Config(yolo=True)

    assert (config.skip_quiz, config.claude_answer_codex) == (True, True)


@pytest.mark.parametrize(
    ("fields", "because"),
    [
        ({"gen_idea": False, "gen_plan": False, "rlcr": False}, "nothing to run"),
        ({"gen_idea": True, "gen_plan": False, "rlcr": True}, "not a plan"),
        ({"skip_impl": True, "rlcr": False}, "skip_impl is about the loop"),
        ({"gen_idea": False, "gen_plan": True}, "needs a draft"),
        ({"gen_plan": False, "gen_idea": False}, "needs a plan"),
    ],
)
def test_a_run_that_cannot_hand_over_is_refused(
    fields: dict[str, object], because: str
) -> None:
    """Before a turn is taken, and by the flow rather than by whatever is asking."""
    with pytest.raises(ValueError, match=because):
        Config.model_validate(fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"gen_idea": True, "gen_plan": True, "rlcr": True},
        {"gen_idea": True, "gen_plan": True, "rlcr": False},
        {"gen_idea": True, "gen_plan": False, "rlcr": False},
        {"gen_idea": False, "gen_plan": False, "rlcr": True, "plan_file": "p.md"},
        {"gen_idea": False, "gen_plan": False, "rlcr": True, "skip_impl": True},
        {"gen_idea": False, "gen_plan": True, "rlcr": True, "idea_output": "d.md"},
    ],
)
def test_the_combinations_that_can_run_are_taken(fields: dict[str, object]) -> None:
    """Each of these hands from one phase to the next, or starts from a file that is there."""
    assert Config.model_validate(fields) is not None


@pytest.mark.parametrize(
    "fields", [{"n": 1}, {"n": 11}, {"full_review_round": 1}, {"max": -1}]
)
def test_a_setting_outside_what_the_plugin_takes_is_refused(
    fields: dict[str, object],
) -> None:
    """`--n` is 2 to 10 and `--full-review-round` is at least 2, as the scripts check."""
    with pytest.raises(ValueError, match="Input should be"):
        Config.model_validate(fields)


# ------------------------------------------------------------------------------------
# What the loop reads out of a review
# ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "found"),
    [
        ("Mainline Progress Verdict: ADVANCED", "advanced"),
        ("mainline progress verdict: stalled\n", "stalled"),
        ("Mainline Progress Verdict: REGRESSED (see below)", "regressed"),
        ("Mainline Progress Verdict: ADVANCED / STALLED / REGRESSED", "unknown"),
        ("nothing about it at all", "unknown"),
    ],
)
def test_the_mainline_verdict_is_read_as_the_hook_reads_it(
    said: str, found: str
) -> None:
    """The template line states all three, and is not a verdict -- the hook says so too."""
    assert loop.verdict(said) == found


def test_the_last_verdict_line_is_the_one_that_counts() -> None:
    """A review that quotes the format and then states one has stated one."""
    said = "Mainline Progress Verdict: ADVANCED\nand later\nMainline Progress Verdict: STALLED"

    assert loop.verdict(said) == "stalled"


@pytest.mark.parametrize(
    ("said", "accepted"),
    [
        ("holds.\n\nCOMPLETE", True),
        ("holds.\n\n  COMPLETE  \n\n", True),
        # The plugin is strict on purpose: a review that says the opposite while quoting
        # the word must not end the run, and neither must one that trails a full stop.
        ("holds.\n\ncomplete.", False),
        ("CANNOT COMPLETE", False),
        (
            "Answer with the single word\nCOMPLETE\nif it holds. It does not: AC-2.",
            False,
        ),
    ],
)
def test_only_the_last_line_being_the_word_accepts_the_work(
    said: str, accepted: bool
) -> None:
    """Nothing between the two agents parses anything, so one word has to carry the verdict."""
    assert (loop._last(said) == loop.COMPLETE) is accepted


def test_findings_are_taken_from_the_first_marker_to_the_end() -> None:
    """A `[P0-9]` in the first ten characters of a line, in the last fifty lines."""
    said = "some reasoning\n- [P1] a thing - a.py:1\n  why\n- [P3] another - b.py:2\n"

    found = loop.issues(said)

    assert found.startswith("## Code Review Issues")
    assert "- [P1] a thing" in found
    assert "some reasoning" not in found


def test_a_marker_in_the_middle_of_a_line_is_not_a_finding() -> None:
    """Which is what keeps a review that explains the format from reading as one."""
    assert loop.issues("the reviewer writes findings like [P0] this one") == ""


def test_a_review_with_nothing_to_fix_finds_nothing() -> None:
    """And is what moves the loop into the finalize phase."""
    assert loop.issues("Everything looks good. Nothing to fix before this ships.") == ""


# ------------------------------------------------------------------------------------
# What a round has to get past
# ------------------------------------------------------------------------------------


def test_a_round_with_no_summary_is_refused(tmp_path: Path) -> None:
    """The first thing the hook checks that the builder can actually do something about."""
    running = _loop(tmp_path)

    refused = running._summary_written(Occasion(moment=Moment.STOP, agent="builder"))

    assert refused is not None
    assert "Work Summary Missing" in refused.because


def test_a_round_with_no_contract_is_refused(tmp_path: Path) -> None:
    """The round contract is what keeps one round to one objective."""
    running = _loop(tmp_path)
    running.summary.write_text("# Round 0 Summary\n")

    refused = running._contract_written(Occasion(moment=Moment.STOP, agent="builder"))

    assert refused is not None
    assert "Round Contract Missing" in refused.because


def test_a_goal_tracker_left_as_a_placeholder_is_refused(tmp_path: Path) -> None:
    """Round 0 is where the immutable half is written, so round 0 is where this is checked."""
    running = _loop(tmp_path)
    running.tracker.write_text(
        prompts.render(
            prompts.GOAL_TRACKER,
            GOAL_SECTION="[To be extracted from plan by the builder in Round 0]",
            AC_SECTION="[To be defined by the builder in Round 0 based on the plan]",
        )
    )

    refused = running._goal_tracker_started(
        Occasion(moment=Moment.STOP, agent="builder")
    )

    assert refused is not None
    assert "Ultimate Goal" in refused.because
    assert "Acceptance Criteria" in refused.because


@pytest.mark.parametrize(
    ("delta", "because"),
    [
        ("", "BitLesson Delta Missing"),
        ("## BitLesson Delta\n- Action: sideways\n", "must include one action"),
        (
            "## BitLesson Delta\n- Action: none\n- Lesson ID(s): BL-1\n",
            "does not match",
        ),
        (
            "## BitLesson Delta\n- Action: add\n- Lesson ID(s): NONE\n",
            "requires concrete",
        ),
        (
            (
                "## BitLesson Delta\n- Action: add\n- Lesson ID(s): BL-1\n"
                "- Notes: [what changed and why]\n"
            ),
            "requires a `Notes:` field",
        ),
    ],
)
def test_a_bitlesson_delta_that_does_not_add_up_is_refused(
    tmp_path: Path, delta: str, because: str
) -> None:
    """Every rule `bitlesson-validate-delta.sh` applies, in the order it applies them."""
    running = _loop(tmp_path)

    refused = running._delta(f"# Round 0 Summary\n\n{delta}")

    assert refused is not None
    assert because in refused.because


def test_a_delta_that_names_a_lesson_the_project_has_is_taken(tmp_path: Path) -> None:
    """Which is the only way `add` gets through: the lesson has to be there to be added."""
    running = _loop(tmp_path)
    lessons = tmp_path / running.state.bitlesson_file
    lessons.parent.mkdir(parents=True, exist_ok=True)
    lessons.write_text("## Lesson: one\nLesson ID: BL-20260101-one\n")

    said = (
        "# Round 0 Summary\n\n## BitLesson Delta\n- Action: add\n"
        "- Lesson ID(s): BL-20260101-one\n- Notes: the retry needed a backoff\n"
    )

    assert running._delta(said) is None


def test_a_delta_of_none_is_taken_when_nothing_was_learned(tmp_path: Path) -> None:
    """Which is what most rounds say, and is why the empty case is allowed by default."""
    running = _loop(tmp_path)

    said = "# Round 0 Summary\n\n## BitLesson Delta\n- Action: none\n- Lesson ID(s): NONE\n"

    assert running._delta(said) is None


def test_none_is_refused_where_the_run_asked_for_a_lesson_a_round(
    tmp_path: Path,
) -> None:
    """`--require-bitlesson-entry-for-none`, which is the flag's whole effect."""
    running = _loop(tmp_path, bitlesson_allow_empty_none=False)

    said = "# Round 0 Summary\n\n## BitLesson Delta\n- Action: none\n- Lesson ID(s): NONE\n"
    refused = running._delta(said)

    assert refused is not None
    assert "BitLesson Recording Required" in refused.because


# ------------------------------------------------------------------------------------
# What the builder may not do while the loop runs
# ------------------------------------------------------------------------------------


def _asked(tool: str, **called: object) -> Occasion:
    """One tool call, as the moment a backend asks whether it may run."""
    return Occasion(
        moment=Moment.PERMISSION_REQUEST, agent="builder", tool=tool, input=called
    )


def test_the_state_file_is_not_the_builder_s_to_write(tmp_path: Path) -> None:
    """However it reaches for it: the tool, or a shell command that writes the same file."""
    running = _loop(tmp_path)
    guard = guards.Guard(running, tmp_path)

    written = guard(_asked("Write", file_path=str(running.where / "state.md")))
    shelled = guard(_asked("Bash", command=f"sed -i s/0/9/ {running.where}/state.md"))

    assert written is not None
    assert "State File Modification" in written.because
    assert shelled is not None
    assert "State File Modification" in shelled.because


def test_the_plan_is_fixed_once_the_loop_has_started(tmp_path: Path) -> None:
    """Both of them: the plan itself, and the backup the loop checks it against."""
    running = _loop(tmp_path)
    guard = guards.Guard(running, tmp_path)

    plan = guard(_asked("Edit", file_path=str(tmp_path / "docs" / "plan.md")))
    backup = guard(_asked("Write", file_path=str(running.where / "plan.md")))

    assert plan is not None
    assert "Plan File Modified" in plan.because
    assert backup is not None
    assert "Plan Backup Protected" in backup.because


def test_a_round_writes_its_own_round_s_summary_and_no_other(tmp_path: Path) -> None:
    """Incrementing the round number is the loop's job, and doing it is how a round is lost."""
    running = _loop(tmp_path, current_round=2)
    guard = guards.Guard(running, tmp_path)

    ahead = guard(_asked("Write", file_path=str(running.where / "round-3-summary.md")))
    mine = guard(_asked("Write", file_path=str(running.where / "round-2-summary.md")))

    assert ahead is not None
    assert "Wrong Round Number" in ahead.because
    assert mine is None


def test_the_summary_goes_in_the_loop_directory(tmp_path: Path) -> None:
    """A summary written anywhere else is a summary the review will not read."""
    running = _loop(tmp_path)
    guard = guards.Guard(running, tmp_path)

    refused = guard(_asked("Write", file_path=str(tmp_path / "round-0-summary.md")))

    assert refused is not None
    assert "Wrong Summary Location" in refused.because


def test_the_builder_may_not_rewrite_its_own_instructions(tmp_path: Path) -> None:
    """The round prompt is what the reviewer said, and is not the builder's to edit."""
    running = _loop(tmp_path)
    guard = guards.Guard(running, tmp_path)

    refused = guard(_asked("Write", file_path=str(running.where / "round-0-prompt.md")))

    assert refused is not None
    assert "Prompt File Write Blocked" in refused.because


def test_the_immutable_half_of_the_tracker_is_immutable_after_round_zero(
    tmp_path: Path,
) -> None:
    """An edit that replaces something above the divider is rewriting what was fixed."""
    running = _loop(tmp_path, current_round=1)
    running.tracker.write_text(
        "## IMMUTABLE SECTION\n### Ultimate Goal\nship the thing\n"
        "## MUTABLE SECTION\n### Plan Version: 1\n"
    )
    guard = guards.Guard(running, tmp_path)

    above = guard(
        _asked("Edit", file_path=str(running.tracker), old_string="ship the thing")
    )
    below = guard(
        _asked("Edit", file_path=str(running.tracker), old_string="### Plan Version: 1")
    )

    assert above is not None
    assert "Goal Tracker Update Blocked" in above.because
    assert below is None


def test_the_tracker_may_be_written_whole_in_round_zero(tmp_path: Path) -> None:
    """Round 0 is where it is initialized, which is a write of the whole file."""
    running = _loop(tmp_path)
    running.tracker.write_text("## IMMUTABLE SECTION\n## MUTABLE SECTION\n")

    assert (
        guards.Guard(running, tmp_path)(_asked("Write", file_path=str(running.tracker)))
        is None
    )


def test_a_push_is_refused_unless_the_run_asked_for_one(tmp_path: Path) -> None:
    """Commits stay local until `--push-every-round` says otherwise."""
    quiet = guards.Guard(_loop(tmp_path / "a"), tmp_path / "a")
    pushing = guards.Guard(_loop(tmp_path / "b", push_every_round=True), tmp_path / "b")
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)

    refused = quiet(_asked("Bash", command="git push origin main"))

    assert refused is not None
    assert "Git Push Blocked" in refused.because
    assert pushing(_asked("Bash", command="git push origin main")) is None


def test_git_add_all_is_refused_where_the_loop_has_state_to_lose(
    tmp_path: Path,
) -> None:
    """`.humanize/` is the loop's own, and `git add -A` is how it ends up committed."""
    running = _loop(tmp_path)
    guard = guards.Guard(running, tmp_path)

    refused = guard(_asked("Bash", command="git add -A"))

    assert refused is not None
    assert ".humanize Protection" in refused.because
    assert guard(_asked("Bash", command="git add src/humanize/runner.py")) is None


@pytest.mark.parametrize(
    ("command", "guarded"),
    [
        # A command that only reads the loop's own files is none of the loop's business.
        ("cat .humanize/rlcr/now/state.md", False),
        ("grep -n Action .humanize/rlcr/now/round-0-summary.md", False),
        ("pytest -q tests/test_x.py", False),
        # And one that writes them is, however it writes them.
        ("sed -i s/0/9/ .humanize/rlcr/now/state.md", True),
        ("echo done > .humanize/rlcr/now/round-0-summary.md", True),
        ("cp /tmp/x .humanize/rlcr/now/goal-tracker.md", True),
    ],
)
def test_a_command_is_guarded_by_what_it_would_write(
    tmp_path: Path, command: str, guarded: bool
) -> None:
    """The plugin guards a bash write because a write through bash skips the tool that checks."""
    running = _loop(tmp_path)

    refused = guards.Guard(running, tmp_path)(_asked("Bash", command=command))

    assert (refused is not None) is guarded


@pytest.mark.parametrize(
    ("command", "everything"),
    [
        ("git add -A", True),
        ("git add --all", True),
        ("git add .", True),
        ("git add .humanize", True),
        ("git add ./.humanize/rlcr", True),
        ("git add -p", False),
        ("git add src/humanize/runner.py", False),
        ("git add ./src", False),
        # The plugin says as much: a commit message that says `.humanize` is not a stage.
        ('git commit -m "ignore ."', False),
    ],
)
def test_git_add_is_refused_only_when_it_reaches_for_everything(
    tmp_path: Path, command: str, everything: bool
) -> None:
    """`.humanize/` is the loop's own, and staging everything is how it ends up committed."""
    running = _loop(tmp_path)
    (tmp_path / ".humanize").mkdir(exist_ok=True)

    refused = guards.Guard(running, tmp_path)(_asked("Bash", command=command))

    assert (
        refused is not None and ".humanize Protection" in refused.because
    ) is everything


def test_the_work_itself_is_not_guarded(tmp_path: Path) -> None:
    """Everything that is not the loop's own state is what the builder is here to write."""
    running = _loop(tmp_path)
    guard = guards.Guard(running, tmp_path)

    assert guard(_asked("Write", file_path=str(tmp_path / "src" / "a.py"))) is None
    assert guard(_asked("Read", file_path=str(tmp_path / "README.md"))) is None
    assert guard(_asked("Bash", command="pytest -q")) is None
