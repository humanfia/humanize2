"""One whole RLCR loop, driven by agents that do what the test tells them to.

Nothing here runs a coding agent. The loop is a hook on the moment a turn stops, so a fake
agent that writes the files a round writes and then stops takes the loop through every phase
it has: a round is reviewed, the review says the work is done, the code review finds nothing,
and the finalize round ends the loop -- which is the path the plugin calls `complete`.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, ClassVar

import pytest

from humanize.agents import (
    EVERYWHERE,
    AgentBase,
    AgentConfig,
    Event,
    Moment,
    Occasion,
    SessionBase,
)
from humanize.flows import humanize1
from humanize.flows._rlcr import loop

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A plan with a goal and a criterion, which is what the loop is anchored to.
PLAN = """# Add undo to the editor

## Goal Description
The editor can undo the last edit.

## Acceptance Criteria
- AC-1: `undo()` restores the previous buffer.
  - Positive Tests: undo after one edit restores the buffer
  - Negative Tests: undo with no edits does nothing

## Task Breakdown
| Task ID | Description | Target AC | Tag | Depends On |
|---------|-------------|-----------|-----|------------|
| task1 | write undo | AC-1 | coding | - |
"""

#: What a round has to leave behind for the gates to let it stop.
SUMMARY = """# Round {round} Summary

## What Was Implemented
undo, as the plan says

## Files Changed
- editor.py

## Validation
- the tests pass

## Remaining Items
- none

## BitLesson Delta
- Action: none
- Lesson ID(s): NONE
- Notes: nothing new was learned
"""

CONTRACT = """# Round {round} Contract

- Mainline Objective: implement undo
- Target ACs: AC-1
- Blocking Side Issues In Scope: none
- Queued Side Issues Out of Scope: none
- Success Criteria: undo restores the buffer
"""

#: A tracker with the placeholders filled in, which is what round 0 is asked to write.
TRACKER = """# Goal Tracker

## IMMUTABLE SECTION

### Ultimate Goal
The editor can undo the last edit.

### Acceptance Criteria
- AC-1: `undo()` restores the previous buffer.

---

## MUTABLE SECTION

#### Active Tasks
| Task | Target AC | Status | Tag | Owner | Notes |
|------|-----------|--------|-----|-------|-------|
| [mainline] write undo | AC-1 | in_progress | coding | claude | - |
"""


class Scripted(AgentBase):
    """An agent whose every turn is what the test said it would be."""

    #: Everything, including the moment a tool can actually be refused: the flow says the
    #: builder has to run it, and a stand-in that did not could not be the builder.
    moments: ClassVar = EVERYWHERE | {Moment.PERMISSION_REQUEST}

    def __init__(
        self, config: AgentConfig, *, name: str, doing: Callable[[str], str]
    ) -> None:
        """Initializes it.

        Args:
          config: What it says it runs.
          name: What the flow calls it.
          doing: What one turn of it does, given the prompt, answering with what it says.
        """
        super().__init__(config, name=name)
        self.doing = doing
        #: Every prompt it was given, in order, which is what a test reads the run off.
        self.heard: list[str] = []

    def new(self) -> ScriptedSession:
        """Opens a conversation."""
        return ScriptedSession(self)


class ScriptedSession(SessionBase):
    """One conversation with a scripted agent."""

    def _stream(self, prompt: str) -> Iterator[Event]:
        agent = self._agent
        assert isinstance(agent, Scripted)
        agent.heard.append(prompt)
        yield Event(kind="result", text=agent.doing(prompt))


def _git(*args: str, at: Path) -> None:
    """Runs one git command, failing the test if it fails."""
    subprocess.run(["git", "-C", str(at), *args], check=True, capture_output=True)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A git repository with a plan committed in it, which is what the loop needs to start.

    Committed, so the runs below say `track_plan_file` -- which is the plugin's own rule: a
    plan is either in git and declared to be, or gitignored, and a loop started against the
    other one is refused before it can build anything against a plan nothing is watching.
    """
    _git("init", "-b", "main", at=tmp_path)
    _git("config", "user.email", "t@example.com", at=tmp_path)
    _git("config", "user.name", "t", at=tmp_path)
    (tmp_path / ".gitignore").write_text(".humanize*\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text(PLAN)
    (tmp_path / "editor.py").write_text("def undo():\n    pass\n")
    _git("add", "-A", at=tmp_path)
    _git("commit", "-m", "the plan", at=tmp_path)
    return tmp_path


def _builder(where: Path, wrote: list[str]) -> Callable[[str], str]:
    """A builder that writes what a round writes and commits it, then says it is done.

    Args:
      where: The workspace.
      wrote: Filled in with what each turn wrote, so a test can see which rounds happened.

    Returns:
      What one turn of it does.
    """
    turns = {"at": 0}

    def turn(prompt: str) -> str:
        turns["at"] += 1
        (found,) = sorted((where / ".humanize" / "rlcr").iterdir())
        if "Finalize Phase" in prompt:
            (found / "finalize-summary.md").write_text(
                "# Finalize\n\nsimplified nothing\n"
            )
            wrote.append("finalize")
            return "finalized"
        at = 0
        for line in prompt.splitlines():
            if "round-" in line and "-summary.md" in line:
                at = int(line.split("round-")[1].split("-summary")[0])
                break
        (found / f"round-{at}-summary.md").write_text(SUMMARY.format(round=at))
        (found / f"round-{at}-contract.md").write_text(CONTRACT.format(round=at))
        (found / "goal-tracker.md").write_text(TRACKER)
        # Something different every turn, so that every round has a commit of its own --
        # a round that changed nothing is one the clean check would let through anyway.
        (where / "editor.py").write_text(f"def undo():\n    return {turns['at']}\n")
        _git("add", "editor.py", at=where)
        _git("commit", "-m", f"round {at}", at=where)
        wrote.append(f"round-{at}")
        return f"round {at} done"

    return turn


def _reviewer(said: list[str]) -> Callable[[str], str]:
    """A reviewer that accepts the work and then finds nothing wrong with the code.

    Args:
      said: Filled in with what it was asked about, in order.

    Returns:
      What one turn of it does.
    """

    def turn(prompt: str) -> str:
        if prompt.startswith("You are a specialized agent that validates"):
            said.append("compliance")
            return "PASS: the plan adds undo to the editor in this repository."
        if prompt.startswith("# Code Review Phase"):
            said.append("code-review")
            return "Reviewed the whole change. Nothing to fix before this ships."
        said.append("summary-review")
        return (
            "Everything the summary claims holds.\n\n"
            "Mainline Progress Verdict: ADVANCED\n\nCOMPLETE"
        )

    return turn


@pytest.mark.timeout(120)
def test_a_loop_that_is_accepted_runs_to_complete(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round, review, code review, finalize: the whole of the plugin's happy path."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []
    asked: list[str] = []
    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=_builder(workspace, wrote)),
        reviewer=Scripted(CONFIG, name="reviewer", doing=_reviewer(asked)),
        human=humanize1.HumanAgent(),
    )
    config = humanize1.Config(
        gen_idea=False,
        gen_plan=False,
        plan_file="docs/plan.md",
        track_plan_file=True,
        skip_quiz=True,
        privacy=True,
    )

    humanize1.run(agents, "add undo", config)

    (found,) = sorted((workspace / ".humanize" / "rlcr").iterdir())
    # The loop ended where the plugin ends a loop that passed: the state file says so.
    assert (found / "complete-state.md").is_file()
    assert not (found / "state.md").exists()
    # Round 0, its review, the code review, and the finalize round it ends on.
    assert wrote == ["round-0", "finalize"]
    assert asked == ["compliance", "summary-review", "code-review"]
    # And it left the files the plugin leaves, under the names it leaves them under.
    assert (found / "round-0-prompt.md").is_file()
    assert (found / "round-0-review-prompt.md").is_file()
    assert (found / "round-0-review-result.md").is_file()
    assert (found / "goal-tracker.md").is_file()
    assert (found / "plan.md").read_text() == PLAN
    assert (
        found / ".review-phase-started"
    ).read_text().strip() == "build_finish_round=0"


@pytest.mark.timeout(120)
def test_a_round_that_wrote_nothing_is_sent_back_rather_than_reviewed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cheap gates run before the expensive review, which is why they are gates.

    The summary itself is not what is missing: the setup writes the scaffold for round 0, as
    the plugin's own setup script does, so what a round that did nothing is short of is the
    contract it was told to state before it started.
    """
    monkeypatch.chdir(workspace)
    wrote: list[str] = []
    asked: list[str] = []
    building = _builder(workspace, wrote)
    turns = {"at": 0}

    def forgetful(prompt: str) -> str:
        turns["at"] += 1
        if turns["at"] == 1:
            return "I think I am done"  # nothing written, nothing committed
        return building(prompt)

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=forgetful),
        reviewer=Scripted(CONFIG, name="reviewer", doing=_reviewer(asked)),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "add undo",
        humanize1.Config(
            gen_idea=False,
            gen_plan=False,
            plan_file="docs/plan.md",
            track_plan_file=True,
            skip_quiz=True,
            privacy=True,
        ),
    )

    builder = agents.builder
    assert isinstance(builder, Scripted)
    # The second thing it heard is the refusal, in the plugin's own words, and no review was
    # run to produce it.
    assert "Round Contract Missing" in builder.heard[1]
    assert asked[1] == "summary-review"
    assert (
        min((workspace / ".humanize" / "rlcr").iterdir()) / "complete-state.md"
    ).is_file()


@pytest.mark.timeout(120)
def test_findings_send_the_builder_back_before_the_loop_can_finish(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `[P0-9]` in the code review is a round of its own, and the loop does not end on it."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []
    reviews = {"at": 0}

    def reviewing(prompt: str) -> str:
        if prompt.startswith("You are a specialized agent that validates"):
            return "PASS: it is this repository's."
        if prompt.startswith("# Code Review Phase"):
            reviews["at"] += 1
            if reviews["at"] == 1:
                return (
                    "Looked at the diff.\n- [P1] undo returns a number - editor.py:2\n"
                )
            return "Fixed. Nothing left to raise."
        return "Holds.\n\nMainline Progress Verdict: ADVANCED\n\nCOMPLETE"

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=_builder(workspace, wrote)),
        reviewer=Scripted(CONFIG, name="reviewer", doing=reviewing),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "add undo",
        humanize1.Config(
            gen_idea=False,
            gen_plan=False,
            plan_file="docs/plan.md",
            track_plan_file=True,
            skip_quiz=True,
            privacy=True,
        ),
    )

    builder = agents.builder
    assert isinstance(builder, Scripted)
    assert any("Code Review Findings" in said for said in builder.heard)
    assert "[P1] undo returns a number" in "\n".join(builder.heard)
    # The round the findings opened is round 1, and the finalize round follows it.
    assert wrote == ["round-0", "round-1", "finalize"]


@pytest.mark.timeout(120)
def test_a_review_with_no_verdict_is_sent_back_for_one(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without it the loop cannot tell an advancing round from a stalled one, so it refuses."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []
    reviews = {"at": 0}

    def reviewing(prompt: str) -> str:
        if prompt.startswith("You are a specialized agent that validates"):
            return "PASS: it is this repository's."
        if prompt.startswith("# Code Review Phase"):
            return "Nothing to raise."
        reviews["at"] += 1
        if reviews["at"] == 1:
            return "Looks fine to me.\n\nCOMPLETE"  # no verdict line at all
        return "Holds.\n\nMainline Progress Verdict: ADVANCED\n\nCOMPLETE"

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=_builder(workspace, wrote)),
        reviewer=Scripted(CONFIG, name="reviewer", doing=reviewing),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "add undo",
        humanize1.Config(
            gen_idea=False,
            gen_plan=False,
            plan_file="docs/plan.md",
            track_plan_file=True,
            skip_quiz=True,
            privacy=True,
        ),
    )

    builder = agents.builder
    assert isinstance(builder, Scripted)
    assert any("Mainline Verdict Missing" in said for said in builder.heard)


@pytest.mark.timeout(120)
def test_the_loop_stops_after_as_many_rounds_as_it_was_given(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--max`, which is the one thing that ends a loop nobody is ever going to accept."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=_builder(workspace, wrote)),
        reviewer=Scripted(
            CONFIG,
            name="reviewer",
            doing=lambda said: (
                "PASS: it is this repository's."
                if said.startswith("You are a specialized agent that validates")
                else "Still wrong.\n\nMainline Progress Verdict: ADVANCED\n"
            ),
        ),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "add undo",
        humanize1.Config(
            gen_idea=False,
            gen_plan=False,
            plan_file="docs/plan.md",
            track_plan_file=True,
            skip_quiz=True,
            privacy=True,
            max=2,
        ),
    )

    (found,) = sorted((workspace / ".humanize" / "rlcr").iterdir())
    assert (found / "maxiter-state.md").is_file()
    assert wrote == ["round-0", "round-1", "round-2"]


@pytest.mark.timeout(120)
def test_the_circuit_breaks_after_three_rounds_of_no_progress(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stalled twice is a recovery round; stalled three times is a loop to stop."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=_builder(workspace, wrote)),
        reviewer=Scripted(
            CONFIG,
            name="reviewer",
            doing=lambda said: (
                "PASS: it is this repository's."
                if said.startswith("You are a specialized agent that validates")
                else "Nothing moved.\n\nMainline Progress Verdict: STALLED\n"
            ),
        ),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "add undo",
        humanize1.Config(
            gen_idea=False,
            gen_plan=False,
            plan_file="docs/plan.md",
            track_plan_file=True,
            skip_quiz=True,
            privacy=True,
        ),
    )

    builder = agents.builder
    assert isinstance(builder, Scripted)
    # The second stall asks for a recovery round, and the third breaks the circuit.
    assert any("Drift Recovery Mode" in said for said in builder.heard)
    assert any("Mainline Drift Circuit Breaker" in said for said in builder.heard)
    (found,) = sorted((workspace / ".humanize" / "rlcr").iterdir())
    assert (found / "stop-state.md").is_file()


@pytest.mark.timeout(120)
def test_the_methodology_analysis_is_the_way_out_unless_privacy_says_otherwise(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop exits through it, and the state file is not renamed until it is done."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []
    building = _builder(workspace, wrote)

    def turn(prompt: str) -> str:
        if "Methodology Analysis Phase" in prompt:
            (found,) = sorted((workspace / ".humanize" / "rlcr").iterdir())
            (found / "methodology-analysis-report.md").write_text(
                "rounds were productive\n"
            )
            (found / "methodology-analysis-done.md").write_text("analysis complete\n")
            wrote.append("methodology")
            return "analysed"
        return building(prompt)

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=turn),
        reviewer=Scripted(CONFIG, name="reviewer", doing=_reviewer([])),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "add undo",
        humanize1.Config(
            gen_idea=False,
            gen_plan=False,
            plan_file="docs/plan.md",
            track_plan_file=True,
            skip_quiz=True,
        ),
    )

    (found,) = sorted((workspace / ".humanize" / "rlcr").iterdir())
    assert wrote == ["round-0", "finalize", "methodology"]
    assert (found / "complete-state.md").is_file()
    assert (found / "methodology-analysis-report.md").is_file()


@pytest.mark.timeout(120)
def test_skip_impl_goes_straight_to_the_code_review(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No plan, no implementation phase: the branch is reviewed as it stands."""
    monkeypatch.chdir(workspace)
    wrote: list[str] = []
    asked: list[str] = []

    agents = humanize1.Agents(
        drafter=Scripted(CONFIG, name="drafter", doing=lambda _: ""),
        planner=Scripted(CONFIG, name="planner", doing=lambda _: ""),
        analyst=Scripted(CONFIG, name="analyst", doing=lambda _: ""),
        builder=Scripted(CONFIG, name="builder", doing=_builder(workspace, wrote)),
        reviewer=Scripted(CONFIG, name="reviewer", doing=_reviewer(asked)),
        human=humanize1.HumanAgent(),
    )

    humanize1.run(
        agents,
        "review what is here",
        humanize1.Config(
            gen_idea=False, gen_plan=False, rlcr=True, skip_impl=True, privacy=True
        ),
    )

    # No summary review at all: the loop starts in the review phase, as `--skip-impl` says.
    assert asked == ["code-review"]  # nothing else: no plan, so nothing to check it
    (found,) = sorted((workspace / ".humanize" / "rlcr").iterdir())
    assert (found / "complete-state.md").is_file()
    assert loop.State().bitlesson_required  # the default, which skip-impl turns off
    assert "bitlesson_required: false" in (found / "complete-state.md").read_text()


def test_a_plan_git_is_holding_is_refused_unless_the_run_said_so(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plugin's rule: a plan is either in git and declared to be, or it is gitignored."""
    monkeypatch.chdir(workspace)
    running = loop.Loop(
        None,  # pyright: ignore[reportArgumentType]
        workspace / ".humanize" / "rlcr" / "now",
        workspace,
        loop.State(plan_file="docs/plan.md", plan_tracked=False, start_branch="main"),
    )

    from humanize.flows._rlcr.guards import Prompted

    refused = Prompted(running, workspace)(
        Occasion(moment=Moment.USER_PROMPT_SUBMIT, agent="builder")
    )

    assert refused is not None
    assert "now tracked in git" in refused.because


@pytest.mark.timeout(120)
def test_a_plan_that_leaves_git_mid_loop_is_refused_too(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loop told the plan is in git is a loop whose integrity check needs it to stay there."""
    monkeypatch.chdir(workspace)
    running = loop.Loop(
        None,  # pyright: ignore[reportArgumentType]
        workspace / ".humanize" / "rlcr" / "now",
        workspace,
        loop.State(plan_file="docs/plan.md", plan_tracked=True, start_branch="main"),
    )
    _git("rm", "--cached", "docs/plan.md", at=workspace)

    from humanize.flows._rlcr.guards import Prompted

    refused = Prompted(running, workspace)(
        Occasion(moment=Moment.USER_PROMPT_SUBMIT, agent="builder")
    )

    assert refused is not None
    assert "no longer tracked in git" in refused.because
