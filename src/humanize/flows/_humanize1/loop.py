"""The RLCR loop: what it keeps between rounds, and the gate a round has to get through.

`hooks/loop-codex-stop-hook.sh`, as a hook hung on `Moment.STOP`. The plugin blocks Claude's
exit and answers with the next prompt; the moment a turn stops is the same moment, and a
`Verdict(refused=True, because=...)` is the same answer. Every gate the hook runs is run here,
in the order the hook runs them, and answers with the plugin's own words -- so a round that
would have been blocked there is blocked here for the same reason.

What the loop keeps is kept where the plugin keeps it: `.humanize/rlcr/<timestamp>/`, with
`state.md` holding the same fields, so `humanize monitor rlcr` reads a run of this exactly as
it reads a run of the plugin.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from humanize.agents import Verdict

from . import blocks, prompts
from .prompts import render

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pydantic import BaseModel

    from humanize.agents import AgentBase, Occasion, SessionBase
    from humanize.backends import Profile

__all__ = [
    "ALLOWED",
    "COMPLETE",
    "MAX_LINES",
    "STOP",
    "Loop",
    "State",
    "answered",
    "git",
    "issues",
    "spoken",
    "verdict",
]

#: What the reviewer says to end a phase, and what it says to break the circuit. Matched
#: against the last non-empty line, trimmed, and nothing else: the plugin is strict here
#: because `CANNOT COMPLETE` is a review that says the opposite of what a substring finds.
COMPLETE = "COMPLETE"
STOP = "STOP"

#: How long a file may get before the loop makes the builder split it, as the hook's own
#: `MAX_LINES`, and the extensions it counts as code and as documentation.
MAX_LINES = 2000
_CODE = frozenset({
    "py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "cc", "cxx", "h", "hpp",
    "cs", "go", "rs", "rb", "php", "swift", "kt", "kts", "scala", "sh", "bash", "zsh",
})  # fmt: skip
_DOCS = frozenset(["md", "rst", "txt", "adoc", "asciidoc"])

#: What a mainline verdict may be, and what the drift state may be.
ADVANCED, STALLED, REGRESSED, UNKNOWN = "advanced", "stalled", "regressed", "unknown"
NORMAL, REPLAN_REQUIRED = "normal", "replan_required"

#: How many consecutive rounds of no mainline progress ask for a recovery round, and how many
#: end the loop. The hook's own two and three.
_REPLAN_AT = 2
_STOP_AT = 3

#: How long a git command is given, in seconds, as the hook's `GIT_TIMEOUT`.
_GIT = 30

#: What the loop leaves under the workspace, untracked, exactly where the plugin leaves it.
LOOPS = ".humanize/rlcr"
BITLESSON = ".humanize/bitlesson.md"

#: Which files under the loop directory a round may be written to, and the marker files that
#: say where the loop has got to.
REVIEW_STARTED = ".review-phase-started"
EXIT_REASON = ".methodology-exit-reason"

#: Untracked paths that are the loop's own rather than the work's, which do not make a
#: working tree dirty. The hook's `^\?\? \.humanize[-/]`.
_OURS = re.compile(r"^\?\? \.humanize[-/]")

#: The verdict line every implementation review has to carry, and the placeholder wording a
#: goal tracker still has in it when nobody has filled it in.
_VERDICT = re.compile(
    r"Mainline Progress Verdict:\s*(ADVANCED|STALLED|REGRESSED)(?:[^A-Za-z]|$)",
    re.IGNORECASE,
)
_VERDICTS = re.compile(r"ADVANCED|STALLED|REGRESSED", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\[To be [a-z]")

#: A finding the code review found, which is a `[P0-9]` in the first ten characters of a line.
_FINDING = re.compile(r"\[P[0-9]\]")

#: How far back the plugin scans a review for findings, how many rounds of history it points
#: the reviewer at, and how short a line has to be to read as an `Open Question` heading
#: rather than as a sentence about one.
_SCANNED = 50
_RECENT = 3
_HEADING = 40

#: The `## BitLesson Delta` block a summary carries, and what its fields may say.
_DELTA = re.compile(r"^##\s+BitLesson Delta\s*$", re.MULTILINE)
_ACTION = re.compile(r"^[\s-]*Action:\s*([A-Za-z]+)\s*$", re.MULTILINE)
_LESSONS = re.compile(r"^[\s-]*Lesson ID\(s\):\s*(.*)$", re.MULTILINE)
_NOTES = re.compile(r"^[\s-]*Notes:\s*(.*)$", re.MULTILINE)
_UNWRITTEN = re.compile(r"^(\[.*\]|<.*>)$")
_LESSON_ID = re.compile(r"^Lesson ID:\s*(\S+)\s*$", re.MULTILINE)

#: What the exit was, which is what the state file is renamed to on the way out.
ALLOWED = ("complete", "cancel", "maxiter", "stop", "unexpected")


def spoken(agent: AgentBase | SessionBase, prompt: str) -> tuple[str, float]:
    """What a turn answered, taking it again for as long as taking it keeps failing.

    A turn that failed is a turn to take again, and only that turn: a round here is hours of
    work and a review is one question about it, so letting a failed review send the round back
    would pay for the expensive half twice to recover from the cheap half.

    Args:
      agent: Whose turn it is -- a session, when the turns are to remember each other, and
        the agent itself for a review, which is a session that has just started.
      prompt: What to say to it.

    Returns:
      What it answered, and how long the answer took -- which is what a timeout is measured
      against, since a turn already under way cannot be cut short from here.
    """
    began = time.monotonic()
    while True:
        said = agent(prompt, suppress=True)
        # A turn that exits clean having said nothing has not answered either, and passing
        # that on would spend a round asking the other side to reply to silence.
        if said:
            return said, time.monotonic() - began
        time.sleep(5)


def answered[T: BaseModel](
    agent: AgentBase | SessionBase, prompt: str, schema: type[T]
) -> T:
    """What a turn answered as the shape it was asked for, taking it again while it fails.

    :func:`spoken` for a question rather than for work: the answer is a field to read instead
    of a paragraph to look for a marker in, and the model is held to the shape rather than
    asked for it. A turn that failed, or that answered in some other shape, is the same thing
    here -- a question that has not been answered -- and is asked again.

    Args:
      agent: Whose turn it is.
      prompt: What to ask it.
      schema: The shape the answer is to be read as.

    Returns:
      The answer, as that shape.
    """
    while True:
        said = agent(prompt, suppress=True, schema=schema)
        if said is not None:
            return said
        time.sleep(5)


def verdict(said: str) -> str:
    """The mainline progress verdict a review states, read as the hook reads it.

    Args:
      said: The whole review.

    Returns:
      One of `advanced`, `stalled` and `regressed`, or `unknown` for a review that stated
      none -- or stated more than one on the line, which is a template rather than a verdict.
    """
    lines = [line for line in said.splitlines() if _VERDICT.search(line)]
    if not lines:
        return UNKNOWN
    found = _VERDICTS.findall(lines[-1])
    return found[0].lower() if len(found) == 1 else UNKNOWN


def issues(said: str) -> str:
    """What a code review found, from its first finding to the end of it.

    The hook scans only the last fifty lines of the review for a `[P0-9]` in the first ten
    characters of a line, and takes everything from there: a marker in the middle of the
    reviewer's reasoning is not a finding, and the findings are always at the end.

    Args:
      said: The whole review.

    Returns:
      The findings as the builder is to be given them, or "" for a review that found nothing.
    """
    lines = said.splitlines()
    tail = lines[-_SCANNED:]
    for at, line in enumerate(tail):
        if _FINDING.search(line[:10]):
            found = "\n".join(tail[at:])
            return f"## Code Review Issues\n\n{found}\n"
    return ""


def git(*args: str, at: Path) -> tuple[int, str]:
    """Runs one git command in the workspace and answers with what it said.

    Args:
      args: The command, after `git`.
      at: The workspace.

    Returns:
      Its status and its output, or a status of its own for a git that could not be run --
      the gates fail closed on that, as the hook does.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(at), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT,
        )
    except (OSError, subprocess.SubprocessError):
        return 124, ""
    return done.returncode, done.stdout.strip()


@dataclass
class State:
    """`state.md`, field for field, so that anything reading a run of the plugin reads this.

    Written to the loop directory as YAML frontmatter and read back each round: the builder
    is refused every way it has of editing this file, and reading it back is what makes that
    refusal worth having.
    """

    current_round: int = 0
    max_iterations: int = 42
    codex_model: str = ""
    codex_effort: str = ""
    codex_timeout: int = 5400
    push_every_round: bool = False
    full_review_round: int = 5
    plan_file: str = ""
    plan_tracked: bool = False
    start_branch: str = ""
    base_branch: str = ""
    base_commit: str = ""
    review_started: bool = False
    ask_codex_question: bool = True
    session_id: str = ""
    agent_teams: bool = False
    privacy_mode: bool = False
    bitlesson_required: bool = True
    bitlesson_file: str = BITLESSON
    bitlesson_allow_empty_none: bool = True
    mainline_stall_count: int = 0
    last_mainline_verdict: str = UNKNOWN
    drift_status: str = NORMAL
    started_at: str = ""

    def written(self) -> str:
        """The file, as the setup script writes it."""
        said = [f"{name}: {_yaml(value)}" for name, value in asdict(self).items()]
        return "---\n" + "\n".join(said) + "\n---\n"


def _yaml(value: object) -> str:
    """One state field, written the way the setup script writes it.

    Args:
      value: What it is set to.

    Returns:
      A switch as `true` or `false`, since that is what the hook's own tests compare against,
      and anything else as it is.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@dataclass
class Loop:
    """One RLCR loop, as the thing the builder runs into every time it tries to stop.

    A round is the builder believing the whole plan is done, which is the moment it stops --
    so that is where the review goes, and what the review says is what the builder hears
    instead of stopping.

    Attributes:
      reviewer: Who reads each round, in a session that has just started every time.
      where: The loop directory, which is `.humanize/rlcr/<timestamp>`.
      root: The workspace the work happens in.
      state: What the loop keeps between rounds, which is also on disk.
      said: What each round's review said, oldest first, which is what the run has to show.
      over: Why the loop ended, once it has, or "" while it is still going.
      finalizing: Whether the work has passed review and is being tidied up.
      analysing: Whether the loop is in the methodology analysis it exits through.
      exit_reason: What the exit will be recorded as once the analysis is done.
    """

    reviewer: AgentBase
    where: Path
    root: Path
    state: State
    said: list[str] = field(default_factory=list[str])
    over: str = ""
    finalizing: bool = False
    analysing: bool = False
    exit_reason: str = ""
    #: What `git status --porcelain` said this round, read once for the gates that ask, and
    #: None where this is not a git repository at all.
    _status: str | None = None

    # --------------------------------------------------------------------------------
    # The gate
    # --------------------------------------------------------------------------------

    def __call__(self, occasion: Occasion) -> Verdict | None:
        """Runs every gate the plugin's stop hook runs, in the order it runs them.

        Args:
          occasion: The turn stopping, whose `said` is the builder's answer for the round.

        Returns:
          What to send the builder on with, or None to let it stop -- which is the loop
          being over, one way or another.
        """
        gates: tuple[Callable[[Occasion], Verdict | None], ...] = (
            self._schema,
            self._branch,
            self._plan_integrity,
            self._todos,
            self._git_status,
            self._large_files,
            self._analysis_phase,
            self._git_clean,
            self._unpushed,
            self._summary_written,
            self._contract_written,
            self._bitlesson_delta,
            self._goal_tracker_started,
            self._max_iterations,
            self._finalize_done,
        )
        for gate in gates:
            refused = gate(occasion)
            # A gate that ended the loop has said so on the loop rather than in a verdict:
            # there is no verdict for "stop, we are done", which is what None already means.
            if self.over:
                return None
            if refused is not None:
                return refused
        return self._review(occasion)

    # --------------------------------------------------------------------------------
    # The gates, in the hook's own order
    # --------------------------------------------------------------------------------

    def _schema(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Reads the state back off disk, and ends the loop if it no longer reads.

        The builder is refused every way it has of writing this file, and reading it back is
        what makes that refusal worth having: a state file that has been edited anyway is a
        loop whose round number nothing can trust.
        """
        try:
            held = (self.where / self._state_file).read_text(encoding="utf-8")
        except OSError:
            self._ends("unexpected")
            return None
        for name, kind in (("current_round", int), ("max_iterations", int)):
            found = re.search(rf"^{name}:\s*(\S+)\s*$", held, re.MULTILINE)
            if found is None:
                # A field the setup script wrote and the file no longer has: whatever else
                # was done to it, this is not a state file the loop can go on from.
                self._ends("unexpected")
                return None
            with contextlib.suppress(ValueError):
                # What is on disk wins, which is the whole point of reading it back. A value
                # that no longer reads as a number is left as it was rather than taken as
                # zero, and the round after it will write the file out again.
                setattr(self.state, name, kind(found.group(1)))
        return None

    def _branch(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round that moved the work to another branch."""
        status, branch = git("rev-parse", "--abbrev-ref", "HEAD", at=self.root)
        if status or not branch:
            return Verdict(
                refused=True,
                because="Git operation failed or timed out.\n\nCannot verify branch "
                "consistency. Please check git status manually and try again.",
            )
        if self.state.start_branch and branch != self.state.start_branch:
            return self._blocks(
                blocks.BRANCH_CHANGED,
                START_BRANCH=self.state.start_branch,
                CURRENT_BRANCH=branch,
            )
        return None

    def _plan_integrity(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round that changed the plan it is being judged against.

        Skipped once the code review has started: the plan is no longer being read there, and
        a `--skip-impl` loop has no real plan file to read.
        """
        if self.state.review_started:
            return None
        backup = self.where / "plan.md"
        plan = self.root / self.state.plan_file
        if not backup.is_file():
            return Verdict(
                refused=True,
                because="Plan file backup not found in loop directory.\n\n"
                f"This backup is required for plan integrity verification: {backup}",
            )
        if not plan.is_file():
            return self._blocks(
                blocks.PLAN_FILE_DELETED,
                PLAN_FILE=self.state.plan_file,
                BACKUP_PATH=backup,
            )
        if self.state.plan_tracked:
            _, dirty = git("status", "--porcelain", self.state.plan_file, at=self.root)
            if dirty:
                return self._blocks(
                    blocks.PLAN_FILE_UNCOMMITTED,
                    PLAN_FILE=self.state.plan_file,
                    PLAN_GIT_STATUS=dirty,
                )
        if plan.read_bytes() != backup.read_bytes():
            return self._blocks(
                blocks.PLAN_FILE_MODIFIED,
                PLAN_FILE=self.state.plan_file,
                BACKUP_PATH=backup,
            )
        return None

    def _todos(self, occasion: Occasion) -> Verdict | None:
        """Refuses a round the builder still has tasks open in.

        Read from the same two places the plugin reads: the tasks the backend keeps for the
        session, and the last `TodoWrite` in its transcript. `[queued]` work is not one of
        them -- a queued issue is documented rather than done, and the round is not held for
        it.
        """
        left = _open_tasks(self.reviewer, occasion)
        if not left:
            return None
        return self._blocks(blocks.INCOMPLETE_TODOS, INCOMPLETE_LIST="\n".join(left))

    def _git_status(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Reads the working tree once, for the two gates that both ask about it.

        Fails closed, as the hook does: a `git status` that would not run is a repository
        nothing can vouch for, and a round is not let out on that.
        """
        self._status = None
        status, _ = git("rev-parse", "--git-dir", at=self.root)
        if status:
            return None  # not a git repository, so nothing here to check
        failed, everything = git("status", "--porcelain", at=self.root)
        if failed:
            return self._blocks(blocks.GIT_STATUS_FAILED, GIT_STATUS_EXIT=failed)
        self._status = everything
        return None

    def _analysis_phase(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Sees the methodology analysis through, once the loop is exiting through one.

        Every other gate is skipped while this one is running: the analysis writes under the
        loop directory, and the work it is analysing is already done.
        """
        if not self.analysing:
            return None
        done = self.where / "methodology-analysis-done.md"
        report = self.where / "methodology-analysis-report.md"
        if not (_written(done) and _written(report)):
            return Verdict(
                refused=True,
                because="# Methodology Analysis Incomplete\n\nPlease complete the "
                "methodology analysis before exiting.\n\nYou need to:\n"
                f"1. Write the analysis report to {report}\n"
                f"2. Write a completion note to {done}",
            )
        # The tree still has to be clean: the main gate below is skipped in this phase, so
        # without this a tracked edit made during the analysis would slip through unreviewed.
        if self._left():
            return self._blocks(
                blocks.GIT_NOT_CLEAN,
                GIT_ISSUES="uncommitted changes after methodology analysis",
                SPECIAL_NOTES="",
            )
        # Ended before the flag is cleared, for the reason the finalize phase renames
        # before setting one: the live file is the one the flag names.
        self._ends(self.exit_reason or "unexpected")
        self.analysing = False
        return None

    def _git_clean(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round that left work uncommitted, or the loop's own state tracked."""
        if self._status is None:
            return None
        tracked, held = git("ls-files", "--", ".humanize", at=self.root)
        if not tracked and held:
            return self._blocks(blocks.GIT_TRACKED_HUMANIZE)
        rows = self._status.splitlines()
        left = [row for row in rows if not _OURS.match(row)]
        if not left:
            return None
        notes = ""
        untracked = [row for row in rows if row.startswith("??")]
        if any(_OURS.match(row) for row in untracked):
            notes += blocks.GIT_NOT_CLEAN_HUMANIZE_LOCAL
        if any(not _OURS.match(row) for row in untracked):
            notes += blocks.GIT_NOT_CLEAN_UNTRACKED
        return self._blocks(
            blocks.GIT_NOT_CLEAN, GIT_ISSUES="uncommitted changes", SPECIAL_NOTES=notes
        )

    def _unpushed(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round that left commits unpushed, where the run asked for pushes."""
        if not self.state.push_every_round:
            return None
        _, said = git("status", "-sb", at=self.root)
        ahead = re.search(r"ahead (\d+)", said)
        if ahead is None:
            return None
        _, branch = git("rev-parse", "--abbrev-ref", "HEAD", at=self.root)
        return self._blocks(
            blocks.UNPUSHED_COMMITS,
            AHEAD_COUNT=ahead.group(1),
            CURRENT_BRANCH=branch or "unknown",
        )

    def _large_files(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round that left a file longer than the loop allows.

        Over the `git status` the gate before it read: only the files this round touched,
        since a repository that was already like this is not something the round did.
        """
        if self._status is None:
            return None
        found: list[str] = []
        for row in self._status.splitlines():
            named = row[3:].split(" -> ")[-1]
            path = self.root / named
            if not path.is_file():
                continue
            kind = path.suffix.lstrip(".").lower()
            about = (
                "code" if kind in _CODE else "documentation" if kind in _DOCS else ""
            )
            if not about:
                continue
            with contextlib.suppress(OSError, UnicodeDecodeError):
                lines = len(path.read_text(encoding="utf-8").splitlines())
                if lines > MAX_LINES:
                    found.append(f"\n- `{path}`: {lines} lines ({about} file)")
        if not found:
            return None
        return self._blocks(
            blocks.LARGE_FILES, MAX_LINES=MAX_LINES, LARGE_FILES="".join(found)
        )

    def _summary_written(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round the builder did not write a summary for."""
        if _written(self.summary):
            return None
        return self._blocks(blocks.WORK_SUMMARY_MISSING, SUMMARY_FILE=self.summary)

    def _contract_written(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a round the builder did not state a contract for."""
        if self.finalizing or self.contract.is_file():
            return None
        return self._blocks(
            blocks.ROUND_CONTRACT_MISSING, ROUND_CONTRACT_FILE=self.contract
        )

    def _bitlesson_delta(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a summary whose BitLesson Delta is missing or does not add up."""
        if self.finalizing or not self.state.bitlesson_required:
            return None
        return self._delta(self.summary.read_text(encoding="utf-8"))

    def _goal_tracker_started(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses round 0 if the goal tracker is still the placeholder it was written as."""
        tracker = self.tracker
        if (
            self.finalizing
            or self.state.review_started
            or self.state.current_round
            or not tracker.is_file()
        ):
            return None
        held = tracker.read_text(encoding="utf-8")
        missing = [
            f"\n- **{about}**: Still contains placeholder text"
            for heading, about in (
                ("### Ultimate Goal", "Ultimate Goal"),
                ("### Acceptance Criteria", "Acceptance Criteria"),
                ("#### Active Tasks", "Active Tasks"),
            )
            if _PLACEHOLDER.search(_section(held, heading))
        ]
        if not missing:
            return None
        return self._blocks(
            blocks.GOAL_TRACKER_NOT_INITIALIZED,
            GOAL_TRACKER_FILE=tracker,
            MISSING_ITEMS="".join(missing),
        )

    def _max_iterations(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Ends the loop once it has had as many rounds as it was given.

        Not in the finalize phase, which is already past the review, and not in the review
        phase, which runs until the findings are cleared however many rounds that takes.
        """
        if self.finalizing or self.state.review_started:
            return None
        if self.state.current_round + 1 <= self.state.max_iterations:
            return None
        return self._analyse(
            "maxiter",
            f"Reached max iterations ({self.state.max_iterations}) without completion",
        )

    def _finalize_done(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Ends the loop once the finalize phase has passed every gate above."""
        if not self.finalizing:
            return None
        return self._analyse(
            "complete", "All acceptance criteria met and code review passed"
        )

    # --------------------------------------------------------------------------------
    # The review itself
    # --------------------------------------------------------------------------------

    def _review(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Puts the round to the reviewer, and works out what happens next.

        Args:
          occasion: The turn stopping.

        Returns:
          What the builder hears instead of stopping, or None once the loop is over.
        """
        if self.state.review_started and not (self.where / REVIEW_STARTED).is_file():
            # The state says the code review has started and nothing says it ever did, which
            # is a state file somebody edited: the loop does not carry on from there.
            return Verdict(
                refused=True,
                because="Review phase state inconsistency detected.\n\nThe state file "
                "indicates review_started=true, but no review phase marker exists.\nThis "
                "can happen if the state file was manually edited.\n\n**To fix:**\nReset "
                "the state by stopping the flow and starting it again.",
            )
        aligning = (
            self.state.current_round % self.state.full_review_round
            == self.state.full_review_round - 1
        )
        asked = self._review_prompt(aligning=aligning)
        self.review_prompt.write_text(asked, encoding="utf-8")

        said = ""
        if not self.state.review_started:
            # What the last review of this round said, if this round has been reviewed
            # before: a review that writes the file itself is believed over what it
            # answered with, but only where it wrote it this time -- the round the reviewer
            # is asked to look at again would otherwise be judged on its old answer.
            before = (
                self.result.read_text(encoding="utf-8") if self.result.is_file() else ""
            )
            said, took = spoken(self.reviewer, asked)
            if took > self.state.codex_timeout:
                return self._blocks(
                    blocks.REVIEW_FAILED,
                    FAILURE_REASON=f"the review took {took:.0f}s, over the "
                    f"{self.state.codex_timeout}s it was given",
                    ROUND_NUMBER=self.state.current_round,
                    BASE_BRANCH=self.state.base_branch,
                )
            written = (
                self.result.read_text(encoding="utf-8") if self.result.is_file() else ""
            )
            if not written.strip() or written == before:
                self.result.write_text(said, encoding="utf-8")
            said = self.result.read_text(encoding="utf-8")
            if not said.strip():
                return self._blocks(
                    blocks.REVIEW_FAILED,
                    FAILURE_REASON="the review result file is empty",
                    ROUND_NUMBER=self.state.current_round,
                    BASE_BRANCH=self.state.base_branch,
                )
            self.said.append(said)
            if (drifted := self._drift(said)) is not None:
                return drifted
            if _last(said) == COMPLETE:
                return self._complete()
        if self.state.review_started:
            return self._code_review()
        if _last(said) == STOP:
            return self._analyse(
                "stop",
                f"Circuit breaker triggered - stagnation detected at round "
                f"{self.state.current_round}",
            )
        return self._next_round(said, aligning=aligning)

    def _drift(self, said: str) -> Verdict | None:
        """Keeps the mainline drift counters, and breaks the circuit once they run out.

        Args:
          said: What the review said.

        Returns:
          What to refuse the round with, where the review stated no verdict at all or where
          the mainline has failed to move for as many rounds as it gets, and None otherwise.
        """
        last = _last(said)
        found = verdict(said)
        if last != STOP and found == UNKNOWN:
            return self._blocks(
                blocks.MAINLINE_VERDICT_MISSING,
                REVIEW_RESULT_FILE=self.result,
                REVIEW_PROMPT_FILE=self.review_prompt,
            )
        if found == ADVANCED:
            self.state.mainline_stall_count = 0
            self.state.last_mainline_verdict = ADVANCED
            self.state.drift_status = NORMAL
        elif found in (STALLED, REGRESSED):
            self.state.mainline_stall_count += 1
            self.state.last_mainline_verdict = found
            self.state.drift_status = (
                REPLAN_REQUIRED
                if self.state.mainline_stall_count >= _REPLAN_AT
                else NORMAL
            )
        if last == COMPLETE:
            self.state.mainline_stall_count = 0
            self.state.last_mainline_verdict = ADVANCED
            self.state.drift_status = NORMAL
        elif last != STOP and self.state.mainline_stall_count >= _STOP_AT:
            self._write_state()
            self._ends("stop")
            return self._blocks(
                blocks.MAINLINE_DRIFT_STOP,
                STALL_COUNT=self.state.mainline_stall_count,
                LAST_VERDICT=self.state.last_mainline_verdict,
                PLAN_FILE=self.state.plan_file,
            )
        self._write_state()
        return None

    def _complete(self) -> Verdict | None:
        """Takes the implementation as done, and moves the loop into the code review.

        Returns:
          What the builder hears next, which is either the findings of the first code review
          or the finalize phase, and None where the loop ends here instead.
        """
        if self.state.current_round >= self.state.max_iterations:
            return self._analyse(
                "maxiter",
                f"Review confirmed COMPLETE but at max iterations "
                f"({self.state.max_iterations})",
            )
        if not self.state.base_branch:
            return self._finalize("No base_branch configured for code review")
        self.state.review_started = True
        self.state.mainline_stall_count = 0
        self.state.last_mainline_verdict = ADVANCED
        self.state.drift_status = NORMAL
        self._write_state()
        (self.where / REVIEW_STARTED).write_text(
            f"build_finish_round={self.state.current_round}\n", encoding="utf-8"
        )
        return self._code_review()

    def _code_review(self) -> Verdict | None:
        """Reviews what is in the repository, and sends the builder back to fix what it finds.

        Returns:
          The findings as the builder's next prompt, or None once there is nothing left to
          fix -- which is the finalize phase, and is refused into rather than allowed.
        """
        at = self.state.current_round + 1
        base = self.state.base_commit or self.state.base_branch
        asked = render(
            prompts.CODE_REVIEW,
            REVIEW_ROUND=at,
            BASE_BRANCH=self.state.base_branch,
            BASE_COMMIT=self.state.base_commit or "N/A",
            REVIEW_BASE=base,
            REVIEW_BASE_TYPE="commit" if self.state.base_commit else "branch",
            TIMESTAMP=_stamp(),
        )
        (self.where / f"round-{at}-review-prompt.md").write_text(
            asked, encoding="utf-8"
        )
        said, took = spoken(self.reviewer, asked)
        if took > self.state.codex_timeout:
            return self._blocks(
                blocks.REVIEW_FAILED,
                FAILURE_REASON=f"the code review took {took:.0f}s, over the "
                f"{self.state.codex_timeout}s it was given",
                ROUND_NUMBER=at,
                BASE_BRANCH=self.state.base_branch,
            )
        found = issues(said)
        if not found:
            return self._finalize("")
        (self.where / f"round-{at}-review-result.md").write_text(said, encoding="utf-8")
        self.said.append(said)
        self.state.current_round = at
        self._write_state()
        self._scaffold(at)
        asked = render(
            prompts.REVIEW_PHASE,
            REVIEW_CONTENT=found,
            SUMMARY_FILE=self.summary,
            PLAN_FILE=self.state.plan_file,
            GOAL_TRACKER_FILE=self.tracker,
            ROUND_CONTRACT_FILE=self.contract,
            CURRENT_ROUND=at,
        )
        if self.state.bitlesson_required and "BitLesson" not in asked:
            asked += render(
                prompts.REVIEW_PHASE_BITLESSON, BITLESSON_FILE=self._bitlesson
            )
        asked += prompts.ROUND_ROUTING_NOTE
        self.prompt.write_text(asked, encoding="utf-8")
        return Verdict(refused=True, because=asked)

    def _finalize(self, skipped: str) -> Verdict:
        """Moves the loop into the finalize phase, which is a round of its own.

        Args:
          skipped: Why the code review was skipped, or "" for a review that passed.

        Returns:
          The finalize prompt, which the builder hears instead of stopping.
        """
        # Renamed before the flag is set, or the rename would look for the file it is
        # about to make: which file is the live one is what the flag says.
        self._rename("finalize-state.md")
        self.finalizing = True
        asked = render(
            prompts.FINALIZE_SKIPPED if skipped else prompts.FINALIZE,
            REVIEW_SKIP_REASON=skipped,
            FINALIZE_SUMMARY_FILE=self.summary,
            PLAN_FILE=self.state.plan_file,
            GOAL_TRACKER_FILE=self.tracker,
            BASE_BRANCH=self.state.base_branch,
            START_BRANCH=self.state.start_branch,
        )
        return Verdict(refused=True, because=asked)

    def _next_round(self, said: str, *, aligning: bool) -> Verdict:
        """Builds the next round's prompt out of the review, exactly as the hook builds it.

        Args:
          said: What the review said.
          aligning: Whether the round just reviewed was a full alignment check.

        Returns:
          The prompt, which the builder hears instead of stopping.
        """
        at = self.state.current_round + 1
        self.state.current_round = at
        self._write_state()
        self._scaffold(at)
        replanning = self.state.drift_status == REPLAN_REQUIRED
        asked = render(
            prompts.DRIFT_REPLAN if replanning else prompts.NEXT_ROUND,
            PLAN_FILE=self.state.plan_file,
            REVIEW_CONTENT=said,
            GOAL_TRACKER_FILE=self.tracker,
            BITLESSON_FILE=self._bitlesson,
            ROUND_CONTRACT_FILE=self.contract,
            CURRENT_ROUND=at,
            STALL_COUNT=self.state.mainline_stall_count,
            LAST_MAINLINE_VERDICT=self.state.last_mainline_verdict,
        )
        if replanning and self.state.bitlesson_required and "BitLesson" not in asked:
            asked += render(
                prompts.REVIEW_PHASE_BITLESSON, BITLESSON_FILE=self._bitlesson
            )
        if self.state.agent_teams:
            asked = _injected(asked, prompts.AGENT_TEAMS_ENFORCEMENT)
        if self.state.ask_codex_question and _asks_a_question(said):
            asked = asked.replace(
                "<!-- REVIEWER's REVIEW RESULT  END  -->\n---",
                "<!-- REVIEWER's REVIEW RESULT  END  -->\n---\n\n"
                + prompts.OPEN_QUESTION_NOTICE,
                1,
            )
        if aligning:
            asked += prompts.POST_ALIGNMENT_ACTION_ITEMS
        asked += render(prompts.NEXT_ROUND_FOOTER, NEXT_SUMMARY_FILE=self.summary)
        asked += prompts.ROUND_ROUTING_NOTE
        if self.state.push_every_round:
            asked += prompts.PUSH_EVERY_ROUND_NOTE
        asked += prompts.GOAL_TRACKER_UPDATE_REQUEST
        if self.state.agent_teams and not self.state.review_started:
            asked += (
                "\n" + prompts.AGENT_TEAMS_CONTINUE + "\n" + prompts.AGENT_TEAMS_CORE
            )
        self.prompt.write_text(asked, encoding="utf-8")
        return Verdict(refused=True, because=asked)

    def _review_prompt(self, *, aligning: bool) -> str:
        """What the reviewer is asked about the round that has just finished.

        Args:
          aligning: Whether this round is a full alignment check.

        Returns:
          The prompt, rendered from the plugin's own template.
        """
        at = self.state.current_round
        history = self._commits()
        recent = (
            "".join(
                f"- @{self.where}/round-{r}-summary.md\n"
                f"- @{self.where}/round-{r}-review-result.md\n"
                for r in range(at - 1, max(at - 1 - _RECENT, -1), -1)
            )
            or "(first round, no prior history)"
        )
        section = render(
            prompts.COMMIT_HISTORY_SECTION,
            COMMIT_HISTORY=history,
            RECENT_ROUND_FILES=recent,
        )
        return render(
            prompts.FULL_ALIGNMENT_REVIEW if aligning else prompts.REGULAR_REVIEW,
            CURRENT_ROUND=at,
            PLAN_FILE=self.state.plan_file,
            PROMPT_FILE=self.prompt,
            SUMMARY_CONTENT=self.summary.read_text(encoding="utf-8"),
            GOAL_TRACKER_FILE=self.tracker,
            DOCS_PATH="docs",
            GOAL_TRACKER_UPDATE_SECTION=render(
                prompts.GOAL_TRACKER_UPDATE_SECTION, GOAL_TRACKER_FILE=self.tracker
            ),
            COMMIT_HISTORY_SECTION=section,
            COMPLETED_ITERATIONS=at + 1,
            LOOP_DIR=self.where,
            PREV_ROUND=max(at - 1, 0),
            PREV_PREV_ROUND=max(at - 2, 0),
            REVIEW_RESULT_FILE=self.result,
        )

    def _commits(self) -> str:
        """The commits the work has made so far, which the review reads as its own history."""
        base = self.state.base_commit
        if base:
            status, _ = git("merge-base", "--is-ancestor", base, "HEAD", at=self.root)
            if status == 0:
                _, said = git(
                    "log",
                    "--oneline",
                    "--no-decorate",
                    "--reverse",
                    f"{base}..HEAD",
                    at=self.root,
                )
                return "\n".join(said.splitlines()[-80:]) or "(no commits yet)"
        _, said = git(
            "log", "--oneline", "--no-decorate", "--reverse", "-30", at=self.root
        )
        if not said:
            return "(no commits yet)"
        return f"(base commit unavailable, showing recent branch commits)\n{said}"

    # --------------------------------------------------------------------------------
    # The BitLesson delta, which every summary carries
    # --------------------------------------------------------------------------------

    def _delta(self, summary: str) -> Verdict | None:
        """Reads the BitLesson Delta out of a summary, and refuses one that does not add up.

        Args:
          summary: What the builder wrote for the round.

        Returns:
          What to refuse the round with, or None for a delta that is in order.
        """
        found = _DELTA.search(summary)
        if found is None:
            return self._blocks(blocks.BITLESSON_DELTA_MISSING)
        block = summary[found.end() :].split("\n## ", maxsplit=1)[0]
        action = _ACTION.search(block)
        named = action.group(1).lower() if action else ""
        if named not in ("none", "add", "update"):
            return self._blocks(blocks.BITLESSON_DELTA_INVALID)
        lessons = _LESSONS.search(block)
        said = (lessons.group(1) if lessons else "").strip()
        kept = self.root / self.state.bitlesson_file
        known = (
            _LESSON_ID.findall(kept.read_text(encoding="utf-8"))
            if kept.is_file()
            else []
        )
        if named == "none":
            if said and said.upper() != "NONE":
                return self._blocks(
                    blocks.BITLESSON_DELTA_INCONSISTENT, BITLESSON_FILE=kept
                )
            if not known and not self.state.bitlesson_allow_empty_none:
                return self._blocks(
                    blocks.BITLESSON_DELTA_EMPTY_KB, BITLESSON_FILE=kept
                )
            return None
        if not said or said.upper() == "NONE":
            return self._blocks(blocks.BITLESSON_DELTA_MISSING_IDS, ACTION=named)
        notes = _NOTES.search(block)
        wrote = (notes.group(1) if notes else "").strip()
        if not wrote or _UNWRITTEN.match(wrote):
            return self._blocks(blocks.BITLESSON_DELTA_MISSING_NOTES, ACTION=named)
        if not kept.is_file():
            return self._blocks(blocks.BITLESSON_FILE_MISSING, ACTION=named)
        wanted = [one.strip() for one in said.split(",") if one.strip()]
        if any(one not in known for one in wanted):
            return self._blocks(
                blocks.BITLESSON_DELTA_INCONSISTENT, BITLESSON_FILE=kept
            )
        return None

    # --------------------------------------------------------------------------------
    # Where the loop keeps things, and how it ends
    # --------------------------------------------------------------------------------

    @property
    def _state_file(self) -> str:
        """Which state file is the live one, which is what says what phase the loop is in."""
        if self.analysing:
            return "methodology-analysis-state.md"
        return "finalize-state.md" if self.finalizing else "state.md"

    @property
    def _bitlesson(self) -> Path:
        """Where the lessons this project has learned are kept."""
        return self.root / self.state.bitlesson_file

    @property
    def summary(self) -> Path:
        """What the builder writes about the round it has just finished."""
        if self.finalizing:
            return self.where / "finalize-summary.md"
        return self.where / f"round-{self.state.current_round}-summary.md"

    @property
    def contract(self) -> Path:
        """What the builder states the round's one objective in."""
        return self.where / f"round-{self.state.current_round}-contract.md"

    @property
    def prompt(self) -> Path:
        """What the builder was told to do this round."""
        return self.where / f"round-{self.state.current_round}-prompt.md"

    @property
    def review_prompt(self) -> Path:
        """What the reviewer was asked about this round."""
        return self.where / f"round-{self.state.current_round}-review-prompt.md"

    @property
    def result(self) -> Path:
        """What the reviewer answered about this round."""
        return self.where / f"round-{self.state.current_round}-review-result.md"

    @property
    def tracker(self) -> Path:
        """What the run is anchored to, which no round may change the top of."""
        return self.where / "goal-tracker.md"

    def _scaffold(self, at: int) -> None:
        """Writes the summary a round is to fill in, if the round has none yet.

        Args:
          at: The round.
        """
        summary = self.where / f"round-{at}-summary.md"
        if not summary.exists():
            summary.write_text(
                render(prompts.ROUND_SUMMARY_TEMPLATE, ROUND=at), encoding="utf-8"
            )

    def _write_state(self) -> None:
        """Puts the state back, which is the one file the builder may not touch."""
        (self.where / self._state_file).write_text(
            self.state.written(), encoding="utf-8"
        )

    def _rename(self, to: str) -> None:
        """Moves the live state file, which is how the loop says what phase it is in.

        Args:
          to: What it becomes.
        """
        was = self.where / self._state_file
        if was.exists():
            shutil.move(str(was), str(self.where / to))

    def _left(self) -> str:
        """Whatever the working tree has that is not the loop's own, or "" for a clean one."""
        if self._status is None:
            return ""
        return "\n".join(
            row for row in self._status.splitlines() if not _OURS.match(row)
        )

    def _analyse(self, reason: str, about: str) -> Verdict | None:
        """Puts the loop into its methodology analysis, or ends it where there is none.

        Args:
          reason: What the exit will be recorded as.
          about: The sentence the analysis is told about why the loop is exiting.

        Returns:
          The analysis prompt, which the builder hears instead of stopping, or None where
          the loop simply ends.
        """
        done = self.where / "methodology-analysis-done.md"
        if (
            self.state.privacy_mode
            or (self.where / "methodology-analysis-state.md").exists()
            or _written(done)
        ):
            self._ends(reason)
            return None
        self._rename("methodology-analysis-state.md")
        self.analysing, self.exit_reason = True, reason
        (self.where / EXIT_REASON).write_text(reason, encoding="utf-8")
        done.touch()
        return Verdict(
            refused=True,
            because=render(
                prompts.METHODOLOGY_ANALYSIS,
                EXIT_REASON=reason,
                EXIT_REASON_DESCRIPTION=about,
                CURRENT_ROUND=self.state.current_round,
                MAX_ITERATIONS=self.state.max_iterations,
                LOOP_DIR=self.where,
            ),
        )

    def _ends(self, reason: str) -> None:
        """Ends the loop, keeping the state file under the name that says why.

        Args:
          reason: One of the five the plugin allows.
        """
        self.over = reason if reason in ALLOWED else "unexpected"
        self._rename(f"{self.over}-state.md")
        with contextlib.suppress(OSError):
            (self.where / EXIT_REASON).unlink(missing_ok=True)

    @staticmethod
    def _blocks(template: str, **fields: object) -> Verdict:
        """One refusal, in the plugin's own words.

        Args:
          template: The block message.
          fields: What its placeholders are worth.

        Returns:
          The verdict, which the builder hears instead of stopping.
        """
        return Verdict(refused=True, because=render(template, **fields))


def _written(path: Path) -> bool:
    """Whether a file is there and has something in it.

    Args:
      path: The file.

    Returns:
      True if it exists and holds more than whitespace.
    """
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError):
        return False


def _last(said: str) -> str:
    """The last non-empty line of an answer, trimmed, which is where a marker has to be.

    Args:
      said: The whole answer.

    Returns:
      That line, or "" for an answer with no lines in it.
    """
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _section(held: str, heading: str) -> str:
    """One section of a markdown file, from a heading to the next one at or above it.

    Args:
      held: The file.
      heading: The line the section starts at.

    Returns:
      What is under it, or "" where the heading is not there.
    """
    found: list[str] = []
    taking = False
    for line in held.splitlines():
        if line.startswith(heading):
            taking = True
            continue
        if taking and line.startswith("##"):
            break
        if taking:
            found.append(line)
    return "\n".join(found)


def _injected(asked: str, enforcement: str) -> str:
    """Puts the agent teams warning above the plan, as the hook's own awk puts it there.

    Args:
      asked: The round's prompt.
      enforcement: What to inject.

    Returns:
      The prompt with the warning above `## Original Implementation Plan`, or at the end of
      it where there is no such heading -- which is what the hook does too.
    """
    heading = "## Original Implementation Plan"
    if heading in asked:
        return asked.replace(heading, f"\n{enforcement}\n\n{heading}", 1)
    return f"{asked}\n{enforcement}\n"


def _asks_a_question(said: str) -> bool:
    """Whether a review put an open question to whoever is at the prompt.

    Args:
      said: The review.

    Returns:
      True if any line of it is short and says `Open Question`, which is the heading rather
      than a sentence about one -- the hook's own test, length and all.
    """
    return any(
        len(line) < _HEADING and "Open Question" in line for line in said.splitlines()
    )


def _stamp() -> str:
    """Now, as the plugin stamps a file: UTC, to the second."""
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _open_tasks(agent: AgentBase, occasion: Occasion) -> list[str]:
    """Every task the builder still has open, read from where its backend keeps them.

    The plugin's `check-todos-from-transcript.py`: the tasks the backend files under the
    session, and the last `TodoWrite` in its transcript. A `[queued]` task is not one of
    them -- queued work is documented rather than done, and the round is not held for it.

    Args:
      agent: Whose tasks they are, which is where its home directory is read from.
      occasion: The turn stopping, which says which session.

    Returns:
      One line per task still open, as the plugin lists them, and nothing at all where the
      backend keeps none of this where it can be read.
    """
    from humanize import backends

    profile = backends.named(agent.backend)
    if profile is None or not occasion.session:
        return []
    found: list[str] = []
    tasks = profile.directory() / "tasks" / occasion.session
    for path in sorted(tasks.glob("*.json")) if tasks.is_dir() else []:
        task = _json(path)
        if not isinstance(task, dict):
            continue
        held = cast("dict[str, Any]", task)
        status = str(held.get("status") or "pending")
        if status in ("completed", "deleted"):
            continue
        subject = str(held.get("subject") or "")
        about = str(held.get("description") or "")
        lane = _lane(subject, about)
        if lane == "queued":
            continue
        said = subject or about or f"Task {path.stem}"
        found.append(f"  - [{status}] [{lane}] (Task #{path.stem}) {said}")
    for todo in _todo_writes(profile, occasion.session):
        status = str(todo.get("status") or "")
        said = str(todo.get("content") or "")
        if status == "completed":
            continue
        lane = _lane(said)
        if lane == "queued":
            continue
        found.append(f"  - [{status}] [{lane}] {said}")
    return found


def _json(path: Path) -> Any:
    """One JSON file, or None for one that will not read.

    Args:
      path: The file.

    Returns:
      Whatever it holds.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _todo_writes(profile: Profile, session: str) -> list[dict[str, Any]]:
    """The last todo list a session wrote, out of the transcript the backend keeps.

    Args:
      profile: The backend, which says where its logs are and what they are called.
      session: The session id.

    Returns:
      The todos as they were last written, and nothing at all where the transcript is not
      there or holds none.
    """
    latest: list[dict[str, Any]] = []
    for pattern in profile.logs:
        for path in sorted(profile.directory().glob(pattern.format(ident=session))):
            try:
                held = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line in held.splitlines():
                if not line.strip():
                    continue
                try:
                    entry: Any = json.loads(line)
                except ValueError:
                    continue
                for name, called in _tool_calls(entry):
                    todos = called.get("todos")
                    if name == "TodoWrite" and isinstance(todos, list):
                        latest = [
                            cast("dict[str, Any]", one)
                            for one in cast("list[Any]", todos)
                            if isinstance(one, dict)
                        ]
    return latest


def _tool_calls(entry: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every tool call one line of a transcript holds.

    Args:
      entry: The line, read.

    Yields:
      What was called and what it was called with, for each of them.
    """
    if not isinstance(entry, dict):
        return
    said = cast("dict[str, Any]", entry)
    kind = said.get("type")
    content: Any = []
    if kind == "assistant":
        message = said.get("message")
        content = (
            cast("dict[str, Any]", message).get("content", [])
            if isinstance(message, dict)
            else []
        )
    elif kind == "message":
        content = said.get("content", [])
    if isinstance(content, list):
        for raw in cast("list[Any]", content):
            if not isinstance(raw, dict):
                continue
            block = cast("dict[str, Any]", raw)
            if block.get("type") != "tool_use":
                continue
            named = str(block.get("name") or "")
            with_it: Any = block.get("input") or {}
            if named and isinstance(with_it, dict):
                yield named, cast("dict[str, Any]", with_it)
    if kind == "tool_use":
        named = str(said.get("name") or said.get("tool_name") or "")
        with_it = said.get("input") or said.get("tool_input") or {}
        if named and isinstance(with_it, dict):
            yield named, cast("dict[str, Any]", with_it)


#: A task's lane, which is the tag it starts with. Anything untagged is blocking, which is
#: the safe way to be wrong: a round is held for it rather than left half done.
_LANE = re.compile(r"^\s*\[(mainline|blocking|queued)\](?:\s|$)", re.IGNORECASE)


def _lane(*parts: str) -> str:
    """Which lane a task is in, read off whichever of its fields says.

    Args:
      parts: The task's subject and description, in that order.

    Returns:
      `mainline`, `blocking` or `queued`, defaulting to `blocking`.
    """
    for part in parts:
        found = _LANE.match(part or "")
        if found:
            return found.group(1).lower()
    return "blocking"


def directory(root: Path, stamp: str) -> Path:
    """Where one run of the loop keeps everything, which is where the plugin keeps it.

    Args:
      root: The workspace.
      stamp: What this run is named after, which is the moment it started.

    Returns:
      The directory, made if it is not there.
    """
    where = root / LOOPS / stamp
    where.mkdir(parents=True, exist_ok=True)
    return where


def started() -> str:
    """A name for this run, as the setup script names one: local time, to the second.

    Returns:
      The stamp, which is the loop directory's name.
    """
    import datetime

    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")


def sanitized(root: Path) -> str:
    """The workspace path as a single name, which is what the plugin's cache is filed under.

    Args:
      root: The workspace.

    Returns:
      Its path with everything that is not a word character replaced by a dash, runs of them
      collapsed -- Claude Code's own convention, and the plugin's.
    """
    said = re.sub(r"[^a-zA-Z0-9._-]", "-", str(root))
    return re.sub(r"-{2,}", "-", said)


def cache(root: Path, stamp: str) -> Path:
    """Where a run's debug files go, which is out of the project rather than in it.

    Args:
      root: The workspace.
      stamp: The run.

    Returns:
      The directory, made if it is not there.
    """
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    where = base / "humanize" / sanitized(root) / stamp
    where.mkdir(parents=True, exist_ok=True)
    return where
