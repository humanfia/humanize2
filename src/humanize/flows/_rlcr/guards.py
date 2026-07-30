"""What the builder may not do while the loop is running, and what it is told instead.

The plugin's four `PreToolUse` validators -- `loop-write-validator.sh`, `-edit-`, `-read-`
and `-bash-` -- and its `UserPromptSubmit` plan-file validator, as hooks on the one moment
where saying no to a tool actually stops it: `Moment.PERMISSION_REQUEST`, which the backend
waits on. Hung on the builder while the loop runs and taken down with it.

They all guard the same thing, which is that the loop's own state is the loop's: the plan is
fixed, the state file is not the builder's to write, the goal tracker's immutable half is
immutable after round 0, and a round writes to its own round's files and no other's.

The plugin's `PostToolUse` Bash hook has no counterpart here, and needs none: all it does is
patch the session id into `state.md` so a later hook can tell whose loop it is, and the flow
is holding the loop rather than looking it up.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from humanize.agents import Verdict

from . import blocks
from .prompts import render

if TYPE_CHECKING:
    from pathlib import Path

    from humanize.agents import Occasion

    from .loop import Loop

__all__ = ["Guard", "Prompted"]

#: The files a round writes, by what they are called, and the tools that write them.
_ROUND = re.compile(r"round-(\d+)-(summary|prompt|contract|todos)\.md$", re.IGNORECASE)

#: A redirection, which is the plainest way a shell command writes a file.
_REDIRECT = re.compile(r">>?\s*(\S+)")

#: The commands that write a file without one: an in-place edit, or something copied over the
#: top of it. A command that only reads a file -- `cat`, `grep`, a test run -- writes nothing,
#: and is none of the loop's business.
_INPLACE = re.compile(
    r"(^|[\s|;&(])(tee|dd|truncate|cp|mv|install|rsync)\b"
    r"|(^|[\s|;&(])(sed|perl|awk)\b[^|;&]*\s-i\b"
)

#: A push, which the loop does not want unless it asked for one.
_PUSH = re.compile(r"\bgit\s+push\b")


class Guard:
    """One hook, on the moment a tool is asked about, holding the loop it is guarding.

    Every check the plugin's validators run, on the tool they run it for. What it answers is
    the plugin's own refusal, which is what the agent reads: a refusal worded differently is
    a guard that behaves differently.
    """

    def __init__(self, loop: Loop, root: Path) -> None:
        """Initializes the guard.

        Args:
          loop: The loop it is guarding, which is where the round and the phase are read
            from -- both change while this is hung, so neither is copied here.
          root: The workspace, which is what a relative path in a tool call is relative to.
        """
        self._loop = loop
        self._root = root

    def __call__(self, occasion: Occasion) -> Verdict | None:
        """Says whether a tool may run, and what to say about it if it may not.

        Args:
          occasion: What the builder reached for, and what it reached for it with.

        Returns:
          A refusal, or None to let the tool run.
        """
        called = occasion.input
        tool = occasion.tool
        if tool == "Bash":
            return self._bash(str(called.get("command") or ""))
        named = str(called.get("file_path") or called.get("path") or "")
        if not named:
            return None
        if tool in ("Write", "Edit", "NotebookEdit", "MultiEdit"):
            return self._writes(named, str(called.get("old_string") or ""))
        if tool == "Read":
            return self._reads(named)
        return None

    # --------------------------------------------------------------------------------
    # What a tool may write
    # --------------------------------------------------------------------------------

    def _writes(self, named: str, old: str) -> Verdict | None:
        """Whether a file may be written, which is the write and edit validators.

        Args:
          named: The file.
          old: What an edit is replacing, which says whether it is touching the immutable
            half of the goal tracker.

        Returns:
          A refusal, or None.
        """
        where = self._at(named)
        base = where.name
        if base.endswith("todos.md") and _ROUND.search(base):
            return self._refuse(blocks.TODOS_FILE_ACCESS)
        if base in ("state.md", "finalize-state.md", "methodology-analysis-state.md"):
            return self._refuse(blocks.STATE_FILE_MODIFICATION)
        if base == "plan.md" and self._ours(where):
            return self._refuse(blocks.PLAN_BACKUP_PROTECTED)
        if where == (self._root / self._loop.state.plan_file).resolve():
            return self._refuse(
                blocks.PLAN_FILE_MODIFIED,
                PLAN_FILE=self._loop.state.plan_file,
                BACKUP_PATH=self._loop.where / "plan.md",
            )
        if base == "goal-tracker.md":
            return self._tracker(where, old)
        found = _ROUND.search(base)
        if found is None:
            return None
        at, kind = int(found.group(1)), found.group(2).lower()
        if kind == "prompt":
            return self._refuse(blocks.PROMPT_FILE_WRITE)
        if not self._ours(where):
            return self._refuse(
                blocks.WRONG_CONTRACT_LOCATION
                if kind == "contract"
                else blocks.WRONG_SUMMARY_LOCATION,
                CORRECT_PATH=self._loop.where / base,
            )
        if at != self._loop.state.current_round:
            return self._refuse(
                blocks.WRONG_ROUND_NUMBER,
                ACTION="write",
                CLAUDE_ROUND=at,
                FILE_TYPE=kind,
                CURRENT_ROUND=self._loop.state.current_round,
                CORRECT_PATH=self._loop.where
                / f"round-{self._loop.state.current_round}-{kind}.md",
            )
        return None

    def _tracker(self, where: Path, old: str) -> Verdict | None:
        """Whether the goal tracker may be written, which is only ever this loop's own.

        Args:
          where: The file.
          old: What an edit is replacing, which after round 0 may not be in the immutable
            half -- the plugin's own test, and the reason an edit says what it replaces.

        Returns:
          A refusal, or None.
        """
        if where != (self._loop.tracker).resolve():
            return self._refuse(
                blocks.GOAL_TRACKER_MODIFICATION,
                CURRENT_ROUND=self._loop.state.current_round,
                CORRECT_PATH=self._loop.tracker,
            )
        if self._loop.state.current_round <= 0:
            return None  # round 0 is where the immutable half is written
        # After round 0 the immutable half is immutable: a whole-file write cannot be told
        # from one that rewrites it, and an edit that replaces something above the divider
        # is rewriting it.
        held = _read(where)
        immutable = held.split("## MUTABLE SECTION")[0]
        if not old or (old.strip() and old.strip() in immutable):
            return self._refuse(
                blocks.GOAL_TRACKER_MODIFICATION,
                CURRENT_ROUND=self._loop.state.current_round,
                CORRECT_PATH=self._loop.tracker,
            )
        return None

    # --------------------------------------------------------------------------------
    # What a tool may read
    # --------------------------------------------------------------------------------

    def _reads(self, named: str) -> Verdict | None:
        """Whether a file may be read, which is the read validator.

        Only the loop's own files are guarded: everything else in the repository is what the
        builder is here to read. A round reads its own round's files, and a goal tracker is
        read out of the loop that is running rather than out of one that has finished.

        Args:
          named: The file.

        Returns:
          A refusal, or None.
        """
        where = self._at(named)
        base = where.name
        if base.endswith("todos.md") and _ROUND.search(base):
            return self._refuse(blocks.TODOS_FILE_ACCESS)
        if base == "goal-tracker.md" and self._elsewhere(where):
            return self._refuse(
                blocks.GOAL_TRACKER_MODIFICATION,
                CURRENT_ROUND=self._loop.state.current_round,
                CORRECT_PATH=self._loop.tracker,
            )
        found = _ROUND.search(base)
        if found is None or not self._elsewhere(where):
            return None
        at, kind = int(found.group(1)), found.group(2).lower()
        if at == self._loop.state.current_round:
            return None
        return self._refuse(
            blocks.WRONG_ROUND_NUMBER,
            ACTION="read",
            CLAUDE_ROUND=at,
            FILE_TYPE=kind,
            CURRENT_ROUND=self._loop.state.current_round,
            CORRECT_PATH=self._loop.where
            / f"round-{self._loop.state.current_round}-{kind}.md",
        )

    # --------------------------------------------------------------------------------
    # What a command may do
    # --------------------------------------------------------------------------------

    def _bash(self, command: str) -> Verdict | None:
        """Whether a shell command may run, which is the bash validator.

        A command is the way round every check above: `sed -i` writes a file without ever
        reaching for `Edit`. So the same files are guarded again here, and the answer is to
        use the tool that can be checked.

        Args:
          command: What the builder wants to run.

        Returns:
          A refusal, or None.
        """
        if not command.strip():
            return None
        if _adds_everything(command) and (self._root / ".humanize").exists():
            return self._refuse(blocks.GIT_ADD_HUMANIZE)
        if _PUSH.search(command) and not self._loop.state.push_every_round:
            return self._refuse(blocks.GIT_PUSH)
        for word in _touched(command):
            base = word.rsplit("/", 1)[-1]
            if base in (
                "state.md",
                "finalize-state.md",
                "methodology-analysis-state.md",
            ):
                return self._refuse(blocks.STATE_FILE_MODIFICATION)
            if base == "plan.md" and ".humanize/rlcr/" in word:
                return self._refuse(blocks.PLAN_BACKUP_PROTECTED)
            if base == "goal-tracker.md":
                return self._refuse(
                    blocks.GOAL_TRACKER_BASH_WRITE, CORRECT_PATH=self._loop.tracker
                )
            found = _ROUND.search(base)
            if found is None:
                continue
            kind = found.group(2).lower()
            if kind == "todos":
                return self._refuse(blocks.TODOS_FILE_ACCESS)
            if kind == "prompt":
                return self._refuse(blocks.PROMPT_FILE_WRITE)
            return self._refuse(
                blocks.ROUND_CONTRACT_BASH_WRITE
                if kind == "contract"
                else blocks.SUMMARY_BASH_WRITE,
                CORRECT_PATH=self._loop.where
                / f"round-{self._loop.state.current_round}-{kind}.md",
            )
        return None

    # --------------------------------------------------------------------------------

    def _at(self, named: str) -> Path:
        """One path as the guard compares them: absolute, and resolved.

        Args:
          named: The path a tool was called with.

        Returns:
          It, against the workspace where it was relative.
        """
        from pathlib import Path as _Path

        where = _Path(named)
        if not where.is_absolute():
            where = self._root / where
        try:
            return where.resolve()
        except OSError:
            return where

    def _ours(self, where: Path) -> bool:
        """Whether a path is inside the loop directory this run is keeping.

        Args:
          where: The path, resolved.

        Returns:
          True if it is under this loop's own directory.
        """
        try:
            return where.is_relative_to(self._loop.where.resolve())
        except OSError:
            return False

    def _elsewhere(self, where: Path) -> bool:
        """Whether a loop file is one this run keeps, rather than one from another run.

        Args:
          where: The path, resolved.

        Returns:
          True if it looks like a loop file and is not this loop's.
        """
        return ".humanize" in where.parts and not self._ours(where)

    @staticmethod
    def _refuse(template: str, **fields: object) -> Verdict:
        """One refusal, in the plugin's own words.

        Args:
          template: What to say.
          fields: What its placeholders are worth.

        Returns:
          The verdict, which the backend reads as the tool having been declined.
        """
        return Verdict(refused=True, because=render(template, **fields))


class Prompted:
    """The plugin's `UserPromptSubmit` validator, which checks the plan before a turn runs.

    Everything the stop hook checks about the plan, checked again before the turn that would
    change it rather than after: the branch is the one the loop started on, and a plan the
    run was told to track is tracked and committed.
    """

    def __init__(self, loop: Loop, root: Path) -> None:
        """Initializes the check.

        Args:
          loop: The loop it is checking for.
          root: The workspace.
        """
        self._loop = loop
        self._root = root

    def __call__(self, occasion: Occasion) -> Verdict | None:  # noqa: ARG002
        """Refuses a turn that would run against a moved branch or an untracked plan.

        Args:
          occasion: The prompt about to go out.

        Returns:
          A refusal, or None to let the turn run.
        """
        from .loop import git

        status, branch = git("rev-parse", "--abbrev-ref", "HEAD", at=self._root)
        if status or not branch:
            return None  # not a git repository, or a git that would not answer
        state = self._loop.state
        if state.start_branch and branch != state.start_branch:
            return Verdict(
                refused=True,
                because=render(
                    blocks.BRANCH_CHANGED,
                    START_BRANCH=state.start_branch,
                    CURRENT_BRANCH=branch,
                ),
            )
        if not state.plan_file:
            return None
        tracked, _ = git("ls-files", "--error-unmatch", state.plan_file, at=self._root)
        if not state.plan_tracked:
            # The other way round, and the plugin refuses it too: a plan that has been put
            # into git during a loop that was told it was not in git is a plan whose
            # integrity is now checked against the wrong thing.
            if tracked == 0:
                return Verdict(
                    refused=True,
                    because="Plan file is now tracked in git but the loop was started "
                    f"without track_plan_file.\n\nFile: {state.plan_file}\n\nThe plan "
                    "file must remain gitignored during this RLCR loop.",
                )
            return None
        if tracked != 0:
            return Verdict(
                refused=True,
                because="Plan file is no longer tracked in git.\n\nFile: "
                f"{state.plan_file}\n\nThis RLCR loop was started with track_plan_file, "
                "but the plan file has been removed from git tracking.",
            )
        _, dirty = git("status", "--porcelain", state.plan_file, at=self._root)
        if dirty:
            return Verdict(
                refused=True,
                because=render(
                    blocks.PLAN_FILE_UNCOMMITTED,
                    PLAN_FILE=state.plan_file,
                    PLAN_GIT_STATUS=dirty,
                ),
            )
        return None


def _touched(command: str) -> list[str]:
    """Every path a shell command would write.

    Two ways a command writes a file: a redirection, and something that edits in place or
    copies over the top. Anything that only reads one is left alone -- the loop guards its own
    state, and reading it is what the builder is told to do.

    Args:
      command: The command.

    Returns:
      The paths it would write, which is nothing at all for a command that writes none.
    """
    found = list(_REDIRECT.findall(command))
    if _INPLACE.search(command):
        found.extend(
            word.strip("'\"")
            for word in command.split()
            if not word.startswith("-") and ("/" in word or word.endswith(".md"))
        )
    return found


def _adds_everything(command: str) -> bool:
    """Whether a command would stage the whole tree, which would take the loop's state too.

    Args:
      command: The command.

    Returns:
      True for a `git add` reaching for everything -- `-A`, `--all`, `.` -- or naming
      `.humanize` itself. `git add -p` and `git add <path>` are what it asks for instead.
    """
    return any(_adds(part.split()) for part in re.split(r"[|;&]+", command))


def _adds(words: list[str]) -> bool:
    """Whether one command of a line is a `git add` of everything.

    Args:
      words: That command, split.

    Returns:
      True if it is.
    """
    if "git" not in words:
        return False
    at = words.index("git")
    if words[at + 1 : at + 2] != ["add"]:
        return False
    return any(
        word in ("-A", "--all", ".") or word.removeprefix("./").startswith(".humanize")
        for word in words[at + 2 :]
    )


def _read(where: Path) -> str:
    """A file, or "" for one that will not read.

    Args:
      where: The file.

    Returns:
      What it holds.
    """
    try:
        return where.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
