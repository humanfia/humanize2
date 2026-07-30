"""What the builder is told instead of stopping, one message per gate that refused it.

`prompt-template/block/` in PolyArch/humanize, verbatim: these are what its hooks answer with
when they refuse a stop or a tool, and what the agent reads is the whole of the difference a
gate makes. A message paraphrased here would be a gate that behaves differently.
"""

from __future__ import annotations

__all__ = [
    "BITLESSON_DELTA_EMPTY_KB",
    "BITLESSON_DELTA_INCONSISTENT",
    "BITLESSON_DELTA_INVALID",
    "BITLESSON_DELTA_MISSING",
    "BITLESSON_DELTA_MISSING_IDS",
    "BITLESSON_DELTA_MISSING_NOTES",
    "BITLESSON_FILE_MISSING",
    "BRANCH_CHANGED",
    "GIT_ADD_HUMANIZE",
    "GIT_NOT_CLEAN",
    "GIT_NOT_CLEAN_HUMANIZE_LOCAL",
    "GIT_NOT_CLEAN_UNTRACKED",
    "GIT_PUSH",
    "GIT_STATUS_FAILED",
    "GIT_TRACKED_HUMANIZE",
    "GOAL_TRACKER_BASH_WRITE",
    "GOAL_TRACKER_MODIFICATION",
    "GOAL_TRACKER_NOT_INITIALIZED",
    "INCOMPLETE_TODOS",
    "LARGE_FILES",
    "MAINLINE_DRIFT_STOP",
    "MAINLINE_VERDICT_MISSING",
    "PLAN_BACKUP_PROTECTED",
    "PLAN_FILE_DELETED",
    "PLAN_FILE_MODIFIED",
    "PLAN_FILE_UNCOMMITTED",
    "PROMPT_FILE_WRITE",
    "REVIEW_FAILED",
    "ROUND_CONTRACT_BASH_WRITE",
    "ROUND_CONTRACT_MISSING",
    "STATE_FILE_MODIFICATION",
    "SUMMARY_BASH_WRITE",
    "TODOS_FILE_ACCESS",
    "UNPUSHED_COMMITS",
    "WORK_SUMMARY_MISSING",
    "WRONG_CONTRACT_LOCATION",
    "WRONG_ROUND_NUMBER",
    "WRONG_SUMMARY_LOCATION",
]

INCOMPLETE_TODOS = """# Incomplete Tasks Detected

You are trying to stop, but you still have **incomplete tasks**:

{{INCOMPLETE_LIST}}

**Required Action**:
1. Complete all remaining tasks before attempting to stop
2. Mark each task as completed using the **TaskUpdate** tool (set status to "completed")
3. Only after ALL tasks are completed, you may proceed to write your summary and stop

Do NOT proceed to review until all tasks are finished. This saves time and ensures thorough \
work."""

LARGE_FILES = """# Large Files Detected

You are trying to stop, but some files exceed the **{{MAX_LINES}}-line limit**:
{{LARGE_FILES}}

**Why This Matters**:
- Large files are harder to maintain, review, and understand
- They hinder modular development and code reusability
- They make future changes more error-prone

**Required Actions**:

For **code files**:
1. Split into smaller, modular files (each < {{MAX_LINES}} lines)
2. Ensure functionality remains **strictly unchanged** after splitting
3. If you have access to a code simplifier agent, use it to review and optimize the refactored \
code
4. Maintain clear module boundaries and interfaces

For **documentation files**:
1. Split into logical sections or chapters (each < {{MAX_LINES}} lines)
2. Ensure smooth **cross-references** between split files
3. Maintain **narrative flow** and coherence across files
4. Update any table of contents or navigation structures

After splitting the files, commit the changes and attempt to exit again."""

GIT_NOT_CLEAN = """# Git Not Clean

You are trying to stop, but you have **{{GIT_ISSUES}}**.
{{SPECIAL_NOTES}}
**Required Actions**:
0. If you have access to a code simplifier agent, use it to review and simplify your code \
before committing
1. Review untracked files - add build artifacts to `.gitignore`
2. Stage only real changes with specific paths: `git add <files>`
3. Commit with a descriptive message following project conventions

**Important Rules**:
- Do NOT use `git add -A`, `git add --all`, or `git add .` during an active RLCR loop
- Never stage `.humanize/` or legacy `.humanize-*` loop artifacts
- Commit message must follow project conventions
- AI tools (Claude, Codex, etc.) must NOT have authorship in commits
- Do NOT include `Co-Authored-By: Claude` or similar AI attribution

After committing all changes, you may attempt to exit again."""

GIT_NOT_CLEAN_UNTRACKED = """
**Note on Untracked Files**:
Some untracked files may be build artifacts, test outputs, or runtime-generated files.
These should typically be added to `.gitignore` rather than committed:
- Build outputs (e.g., `target/`, `build/`, `dist/`)
- Dependencies (e.g., `node_modules/`, `vendor/`)
- IDE/editor files (e.g., `.idea/`, `.vscode/`)
- Log files, cache files, temporary files

Review untracked files and add appropriate patterns to `.gitignore`.
"""

GIT_NOT_CLEAN_HUMANIZE_LOCAL = """
**Special Case - .humanize directory detected**:
The `.humanize/` directory is created by the RLCR loop and should NOT be committed.
Please add it to .gitignore:
```bash
echo '.humanize*' >> .gitignore
git add .gitignore
```
"""

GIT_TRACKED_HUMANIZE = """# Tracked Humanize State Blocked

Detected tracked or staged files under `.humanize/`.

These files are local Humanize loop state and must remain outside version control.

## Required Fix

1. Remove Humanize state from the index:

       git rm --cached -r .humanize

2. Keep only real project files staged.
3. Retry the stop action after the local state is no longer tracked.

## Important

- Do NOT use `git add -f` on Humanize state files.
- Do NOT commit RLCR trackers, round summaries, contracts, or cancel/finalize markers."""

GIT_STATUS_FAILED = """# Git Status Failed

Git status operation failed ({{GIT_STATUS_EXIT}}).

Cannot verify repository state. Please check git status manually and try again."""

UNPUSHED_COMMITS = """# Unpushed Commits Detected

You are trying to stop, but you have **{{AHEAD_COUNT}} unpushed commit(s)** on branch \
`{{CURRENT_BRANCH}}`.

Since `push_every_round` is enabled, you must push your commits before exiting.

**Required Action**:
```bash
git push origin {{CURRENT_BRANCH}}
```

After pushing all commits, you may attempt to exit again."""

WORK_SUMMARY_MISSING = """# Work Summary Missing

You attempted to exit without writing your work summary.

**Required Action**: Write your work summary to:
```
{{SUMMARY_FILE}}
```

The summary should include:
- What was implemented
- Files created/modified
- Tests added/passed
- Any remaining items

After writing the summary, you may attempt to exit again."""

ROUND_CONTRACT_MISSING = """# Round Contract Missing

Before you try to exit this round, write the current round contract to:
`{{ROUND_CONTRACT_FILE}}`

The round contract must restate:
- The single **mainline objective** for this round
- The target ACs
- Which issues are truly **blocking**
- Which issues are **queued** and out of scope
- The concrete success criteria for this round

Do not continue without a round contract. The loop uses it to prevent goal drift."""

GOAL_TRACKER_NOT_INITIALIZED = """# Goal Tracker Not Initialized

You are in **Round 0** and the Goal Tracker has not been properly initialized.

**Missing items in `{{GOAL_TRACKER_FILE}}`**:
{{MISSING_ITEMS}}

**Required Actions**:
1. Read `{{GOAL_TRACKER_FILE}}`
2. Replace placeholder text with actual content:
   - Extract or define the **Ultimate Goal** from your understanding of the plan
   - Define 3-7 specific, testable **Acceptance Criteria**
   - Populate **Active Tasks** with tasks from the plan, mapping each to an AC
3. Write the updated goal-tracker.md

**IMPORTANT**: The IMMUTABLE SECTION can only be set in Round 0. After this round, it becomes \
read-only.

After updating the Goal Tracker, you may attempt to exit again."""

BRANCH_CHANGED = """Git branch changed during RLCR loop.

Started on: {{START_BRANCH}}
Current: {{CURRENT_BRANCH}}

Branch switching is not allowed. Switch back to {{START_BRANCH}} or stop the flow."""

PLAN_FILE_DELETED = """Project plan file has been deleted.

Original: {{PLAN_FILE}}
Backup available at: {{BACKUP_PATH}}

You can restore from backup if needed. Plan file modifications are not allowed during RLCR \
loop."""

PLAN_FILE_UNCOMMITTED = """Plan file has uncommitted modifications.

File: {{PLAN_FILE}}
Status: {{PLAN_GIT_STATUS}}

This RLCR loop was started with track_plan_file. Plan file modifications are not allowed \
during the loop."""

PLAN_FILE_MODIFIED = """# Plan File Modified

The plan file `{{PLAN_FILE}}` has been modified since the session started.

**Modifying plan files is forbidden during an active session.**

If you need to change the plan:
1. Stop the flow
2. Update the plan file
3. Start it again

Backup available at: `{{BACKUP_PATH}}`"""

MAINLINE_VERDICT_MISSING = """# Mainline Verdict Missing

The implementation review output is missing the required line:

`Mainline Progress Verdict: ADVANCED / STALLED / REGRESSED`

Humanize cannot safely update the drift state or choose the correct next-round prompt without \
this verdict.

Retry the exit so the reviewer reruns the implementation review.

Files:
- Review result: {{REVIEW_RESULT_FILE}}
- Review prompt: {{REVIEW_PROMPT_FILE}}"""

MAINLINE_DRIFT_STOP = """# Mainline Drift Circuit Breaker

The RLCR loop has been stopped because the implementation failed to advance the mainline for \
**{{STALL_COUNT}} consecutive rounds**.

- Last mainline verdict: `{{LAST_VERDICT}}`
- Plan anchor: `{{PLAN_FILE}}`
- Drift status: `replan_required`

This loop should not continue automatically.

Next action:
1. Re-read the original plan
2. Identify why recent rounds kept stalling or regressing
3. Start a fresh RLCR loop with a narrower recovered mainline objective"""

REVIEW_FAILED = """# Review Failed

The code review could not be completed. This is a blocking error that requires retry.

## Error Details

**Reason**: {{FAILURE_REASON}}
**Round**: {{ROUND_NUMBER}}
**Base Branch**: {{BASE_BRANCH}}

## What Happened

The review failed to produce valid output. This can occur due to:
- Network connectivity issues
- Reviewer timeout or unavailability
- Invalid review configuration
- Internal errors

## Required Action

**You must retry the exit.** The review phase cannot be skipped - the loop must continue until \
code review passes with no `[P0-9]` issues found.

Steps to retry:
1. Ensure your changes are committed
2. Write your summary to the expected file
3. Attempt to exit again"""

BITLESSON_DELTA_MISSING = """# BitLesson Delta Missing

Your summary is missing the required `## BitLesson Delta` section.

Required minimal format:

```markdown
## BitLesson Delta
- Action: none|add|update
- Lesson ID(s): <IDs or NONE>
- Notes: <what changed and why>
```"""

BITLESSON_DELTA_INVALID = """# Invalid BitLesson Delta Action

Your `## BitLesson Delta` section exists, but must include one action:

- `none`
- `add`
- `update`"""

BITLESSON_DELTA_INCONSISTENT = """# BitLesson Delta Inconsistent

Your `## BitLesson Delta` declaration does not match the expected BitLesson state.

Review and fix:
- `Action: none` -> `Lesson ID(s): NONE` (or omit Lesson IDs)
- `Action: add|update` -> provide concrete Lesson ID(s) and ensure each exists in \
`{{BITLESSON_FILE}}`"""

BITLESSON_DELTA_EMPTY_KB = """# BitLesson Recording Required

`Action: none` is not allowed for this round because `{{BITLESSON_FILE}}` still has no concrete \
lesson entries.

If this round resolves issues discovered in previous rounds, add/update at least one reusable \
lesson entry and report `Action: add` or `Action: update`."""

BITLESSON_DELTA_MISSING_NOTES = """# BitLesson Delta Missing Notes

`Action: {{ACTION}}` requires a `Notes:` field explaining what changed and why.

The Notes field must not be empty or contain placeholder text like `[what changed and why]`."""

BITLESSON_DELTA_MISSING_IDS = """# BitLesson Delta Missing Lesson IDs

`Action: {{ACTION}}` requires concrete `Lesson ID(s)` (not `NONE`)."""

BITLESSON_FILE_MISSING = """# BitLesson File Missing

Summary declares `Action: {{ACTION}}`, but `{{BITLESSON_FILE}}` does not exist."""

# ------------------------------------------------------------------------------------
# What the builder may not do while the loop runs -- the plugin's tool validators.
# ------------------------------------------------------------------------------------

STATE_FILE_MODIFICATION = """# State File Modification Blocked

You cannot modify `state.md`. This file is managed by the loop system. Modifying it would \
corrupt the loop state. If you think the work is done, just stop and another round of review \
will be auto-triggered."""

GOAL_TRACKER_MODIFICATION = """# Goal Tracker Update Blocked (Round {{CURRENT_ROUND}})

After Round 0, you may update only the **MUTABLE SECTION** of the active goal tracker.

Use Write or Edit on:
`{{CORRECT_PATH}}`

## Rules

- Keep the **IMMUTABLE SECTION** unchanged
- Do not modify `goal-tracker.md` via Bash
- Do not write to an old loop session's tracker

If you need the reviewer to correct tracker drift that you could not safely resolve yourself, \
include an optional `Goal Tracker Update Request` in your summary."""

GOAL_TRACKER_BASH_WRITE = """# Bash Write Blocked: Use Write or Edit Tool

Do not use Bash commands to modify goal-tracker.md.

**Use the Write or Edit tool instead**: `{{CORRECT_PATH}}`

Bash commands like cat, echo, sed, awk, etc. bypass the validation hooks.
Please use the proper tools to modify the Goal Tracker."""

SUMMARY_BASH_WRITE = """# Bash Write Blocked: Use Write or Edit Tool

Do not use Bash commands to modify summary files.

**Use the Write or Edit tool instead**: `{{CORRECT_PATH}}`

Bash commands like cat, echo, sed, awk, etc. bypass the validation hooks.
Please use the proper tools to ensure correct round number validation."""

ROUND_CONTRACT_BASH_WRITE = """# Round Contract Bash Write Blocked

Do not use Bash commands to modify round contract files.

Use the `Write` or `Edit` tool instead:

`{{CORRECT_PATH}}`"""

PROMPT_FILE_WRITE = """# Prompt File Write Blocked

You cannot write to `round-*-prompt.md` files.

**Prompt files contain instructions FROM the reviewer TO you.**

You cannot modify your own instructions. Your job is to:
1. Read the current round's prompt file for instructions
2. Execute the tasks described in the prompt
3. Write your results to the summary file

If the prompt contains errors, document this in your summary file."""

TODOS_FILE_ACCESS = """# Todos File Access Blocked

Do NOT create or access `round-*-todos.md` files.

**Use the native Task tools instead (TaskCreate, TaskUpdate, TaskList).**

The native task tools provide proper state tracking visible in the UI and
integration with the task management system."""

PLAN_BACKUP_PROTECTED = """# Plan Backup Protected

The `plan.md` file in the loop directory is a backup of the original plan file and cannot be \
modified.

This backup ensures plan integrity throughout the session.

If you need to reference the plan, read it instead of modifying it."""

WRONG_ROUND_NUMBER = """# Wrong Round Number

You are trying to {{ACTION}} `round-{{CLAUDE_ROUND}}-{{FILE_TYPE}}.md`, but the current round \
is **{{CURRENT_ROUND}}**.

**Correct path**: `{{CORRECT_PATH}}`

Do NOT increment the round number yourself."""

WRONG_SUMMARY_LOCATION = """# Wrong Summary Location

Summary files MUST be in the loop directory.

**Correct path**: `{{CORRECT_PATH}}`"""

WRONG_CONTRACT_LOCATION = """# Wrong Round Contract Location

Round contract files MUST be in the active loop directory.

**Correct path**: `{{CORRECT_PATH}}`"""

GIT_ADD_HUMANIZE = """# Git Add Blocked: .humanize Protection

The `.humanize/` directory contains local loop state that should NOT be committed.

Your command was blocked because it would add .humanize files to version control.

## Allowed Commands

Use specific file paths instead of broad patterns:

    git add <specific-file>
    git add src/
    git add -p  # patch mode

## Blocked Commands

These commands are blocked when .humanize exists:

    git add .humanize      # direct reference
    git add -A             # adds all including .humanize
    git add --all          # adds all including .humanize
    git add .              # may include .humanize if not gitignored
    git add -f .           # force bypasses gitignore

## Adding .humanize to .gitignore

If you need to add `.humanize*` to `.gitignore`, follow these steps:

1. Edit `.gitignore` to append `.humanize*`
2. Run: `git add .gitignore`
3. Run: `git commit -m "Add humanize local folder into gitignore"`

IMPORTANT: The commit message must NOT contain the literal string ".humanize" to avoid \
triggering this protection."""

GIT_PUSH = """# Git Push Blocked

Current commits should stay local - no need to push to remote.
The loop will handle commits locally until completion.

If you need to push, turn on `push_every_round` when setting the flow up."""
