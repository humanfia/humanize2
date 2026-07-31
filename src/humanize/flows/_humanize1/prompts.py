"""Every word either agent is told, kept as PolyArch/humanize writes them.

The plugin is prompts: its commands are markdown Claude reads, its subagents are markdown
their model reads, its hooks answer with markdown Claude is sent on with. So the port of the
plugin is these strings, and the flow is the order they go out in. They are copied rather
than paraphrased, `{{PLACEHOLDER}}` and all, so that a diff against the plugin's own
`prompt-template/` shows what has drifted.

What is written differently is written differently because the mechanism is: the plugin runs
`codex exec` and `codex review` and this drives whichever agent was chosen as the reviewer,
and the plugin's IO validation is a shell script where this is Python. Each of those is
marked where it appears.

The two commands before the loop are in :mod:`planning`, beside this rather than in it: the
loop's own words are already two thousand lines, which is the length the loop itself refuses
to let a round leave behind.
"""

from __future__ import annotations

__all__ = [
    "AGENT_TEAMS_CONTINUE",
    "AGENT_TEAMS_CORE",
    "AGENT_TEAMS_INSTRUCTIONS",
    "BITLESSON",
    "BITLESSON_SELECTION",
    "CODE_REVIEW",
    "COMMIT_HISTORY_SECTION",
    "DRIFT_REPLAN",
    "FINALIZE",
    "FINALIZE_SKIPPED",
    "FULL_ALIGNMENT_REVIEW",
    "GOAL_TRACKER",
    "GOAL_TRACKER_SKIP_IMPL",
    "GOAL_TRACKER_SKIP_IMPL_ANCHORED",
    "GOAL_TRACKER_UPDATE_REQUEST",
    "GOAL_TRACKER_UPDATE_SECTION",
    "METHODOLOGY_ANALYSIS",
    "NEXT_ROUND",
    "NEXT_ROUND_FOOTER",
    "OPEN_QUESTION_NOTICE",
    "PLAN_COMPLIANCE",
    "PLAN_UNDERSTANDING_QUIZ",
    "POST_ALIGNMENT_ACTION_ITEMS",
    "PUSH_EVERY_ROUND_NOTE",
    "REGULAR_REVIEW",
    "REVIEW_PHASE",
    "ROUND_0",
    "ROUND_0_SKIP_IMPL",
    "ROUND_0_SKIP_IMPL_ANCHORED",
    "ROUND_0_SKIP_IMPL_UNANCHORED",
    "ROUND_CONTRACT_SKIP_IMPL",
    "ROUND_CONTRACT_SKIP_IMPL_ANCHORED",
    "ROUND_ROUTING_NOTE",
    "SUMMARY_TEMPLATE",
    "TASK_LANES",
    "blocks",
    "render",
]

from . import blocks

#: What the plugin's own delegation warning says, injected above the plan in agent teams mode.
AGENT_TEAMS_ENFORCEMENT = (
    "**Delegation Warning**: Do NOT implement code yourself in Agent Teams mode; delegate "
    "all coding tasks to team members."
)


def render(template: str, **fields: object) -> str:
    """Fills a template in, the way the plugin's template loader fills one in.

    Args:
      template: The text, with `{{NAME}}` where a value goes.
      fields: What each name is worth.

    Returns:
      The text with every named placeholder replaced. One nothing was given for is left
      standing, exactly as the plugin's loader leaves it: a prompt with a hole in it is
      easier to notice than a prompt that quietly lost a section.
    """
    said = template
    for name, value in fields.items():
        said = said.replace(f"{{{{{name}}}}}", str(value))
    return said


# ======================================================================================
# start-rlcr-loop -- the setup script's round 0, and the state it sets up
# ======================================================================================

#: templates/bitlesson.md, verbatim.
BITLESSON = """# BitLesson Knowledge Base

This file is project-specific. Keep entries precise and reusable for future rounds.

## Entry Template (Strict)

Use this exact field order for every entry:

```markdown
## Lesson: <unique-id>
Lesson ID: <BL-YYYYMMDD-short-name>
Scope: <component/subsystem/files>
Problem Description: <specific failure mode with trigger conditions>
Root Cause: <direct technical cause>
Solution: <exact fix that resolved the problem>
Constraints: <limits, assumptions, non-goals>
Validation Evidence: <tests/commands/logs/PR evidence>
Source Rounds: <round numbers where problem appeared and was solved>
```

## Entries

<!-- Add lessons below using the strict template. -->
"""

#: agents/plan-understanding-quiz.md, as the prompt its model is given.
PLAN_UNDERSTANDING_QUIZ = """You are a specialized agent that analyzes an implementation plan \
and generates targeted multiple-choice technical comprehension questions. Your goal is to test \
whether the user genuinely understands HOW the plan will be implemented, not just what the \
plan title says.

## Your Task

### Analyze the Plan

1. **Read the plan thoroughly** to understand:
   - What components, files, or systems are being modified
   - What technical approach or mechanism is being used
   - How different pieces of the implementation connect together
   - What existing patterns or systems the plan builds upon

2. **Explore the repository** to add context:
   - Check README.md, CLAUDE.md, or other documentation files
   - Look at the directory structure and key files referenced in the plan
   - Understand the existing architecture that the plan interacts with

### Generate Multiple-Choice Questions

Create exactly 2 multiple-choice questions that test the user's understanding of the plan's \
**technical implementation details**. Each question must have exactly 4 options (A through D), \
with exactly 1 correct answer.

- **QUESTION_1**: Should test whether the user knows what components/systems are being changed \
and how. Focus on the core technical mechanism or approach.
- **QUESTION_2**: Should test whether the user understands how different parts of the \
implementation connect, what existing patterns are being followed, or what the key technical \
constraints are.

**Good question characteristics:**
- Derived from the plan's specific content, not generic templates
- Test understanding of HOW things will be done, not just WHAT the plan describes
- Not too low-level (no exact line numbers, exact syntax, or trivial details)
- A user who has carefully read and understood the plan should pick the correct answer
- A user who just skimmed the title or blindly accepted a generated plan would likely pick wrong
- Wrong options should be plausible (not obviously absurd) but clearly incorrect to someone who \
read the plan

### Generate Plan Summary

Write a 2-3 sentence summary explaining what the plan does and how, suitable for educating a \
user who showed gaps in understanding. Focus on the technical approach, not just the goal.

## Important Notes

- Exactly two questions, each with exactly four options
- Randomize the position of the correct answer (do not always put it first or last)
- The plan may be written in any language - generate questions and options in the same language \
as the plan
- Focus on substance over format
- If the plan is very short or lacks technical detail, derive questions from whatever \
implementation hints are available
- Questions should feel like a friendly knowledge check, not an adversarial interrogation

The plan is at @{{PLAN_FILE}}. Its content:

{{PLAN_CONTENT}}
"""

#: agents/plan-compliance-checker.md, as the prompt its model is given.
PLAN_COMPLIANCE = """You are a specialized agent that validates an implementation plan before \
it enters an RLCR (iterative development) loop. You perform two checks and return a single \
verdict.

### Check A: Repository Relevance

1. **Quickly explore the repository** to understand what it does:
   - Check README.md, CLAUDE.md, or other documentation files
   - Look at the directory structure
   - Identify the main technologies, languages, and purpose

2. **Analyze the plan content** to determine if it relates to this repository:
   - Does the plan mention concepts, technologies, or components in this repo?
   - Is the plan about modifying, extending, or using this codebase?
   - Does the plan reference file paths, functions, or features that exist here?
   - Does the plan have substantive content (not empty or near-empty)?

3. **Be lenient** - only reject plans that are clearly unrelated to the repository (e.g., a \
cooking recipe plan for a software project). If the plan could reasonably be connected, it \
passes.

### Check B: Branch-Switch Detection

1. **Read the entire plan** and look for instructions that require switching, checking out, or \
creating git branches during implementation. Look for patterns such as:
   - "switch to branch X", "checkout branch Y", "create branch Z"
   - "work on branch X", "move to branch X"
   - `git checkout -b`, `git switch`, `git branch`, `gh pr checkout`
   - Worktree creation instructions
   - Any instruction implying the implementer should change branches mid-work

2. **Disambiguate safe patterns** - the following are NOT branch switches and should NOT \
trigger a failure:
   - `git checkout -- <file>` (file restore, not branch switch)
   - Negated instructions like "do not switch branches" or "stay on the current branch"
   - References to branches in a descriptive context (e.g., "this feature was branched from \
main")
   - `--base-branch` configuration (this is a review parameter, not a branch switch)

3. **Why this matters**: RLCR requires the working branch to remain constant across all rounds \
of the loop. Plans that mandate branch switching are incompatible with the RLCR workflow.

## Important Notes

- If in doubt on relevance, lean toward passing (same lenient approach as other validators)
- If in doubt on branch-switch detection, lean toward passing (avoid false positives)
- The plan may be written in any language - that is okay
- Focus on the substance, not the format of the plan

The plan is at @{{PLAN_FILE}}. Its content:

{{PLAN_CONTENT}}
"""

#: setup-rlcr-loop.sh, the goal tracker it writes in normal mode.
GOAL_TRACKER = """# Goal Tracker

<!--
This file tracks the ultimate goal, acceptance criteria, and plan evolution.
It prevents goal drift by maintaining a persistent anchor across all rounds.

RULES:
- IMMUTABLE SECTION: Do not modify after initialization
- MUTABLE SECTION: Update each round, but document all changes
- Every task must be in one of: Active, Completed, or Deferred
- Deferred items require explicit justification
-->

## IMMUTABLE SECTION
<!-- Do not modify after initialization -->

### Ultimate Goal
{{GOAL_SECTION}}

### Acceptance Criteria
<!-- Each criterion must be independently verifiable -->
<!-- The builder must extract or define these in Round 0 -->

{{AC_SECTION}}

---

## MUTABLE SECTION
<!-- Update each round with justification for changes -->

### Plan Version: 1 (Updated: Round 0)

#### Plan Evolution Log
<!-- Document any changes to the plan with justification -->
| Round | Change | Reason | Impact on AC |
|-------|--------|--------|--------------|
| 0 | Initial plan | - | - |

#### Active Tasks
<!-- Mainline tasks only: each task must directly advance the current round objective and \
carry routing metadata -->
| Task | Target AC | Status | Tag | Owner | Notes |
|------|-----------|--------|-----|-------|-------|
| [To be populated by the builder based on plan] | - | pending | coding or analyze | claude or \
codex | mainline task only |

### Blocking Side Issues
<!-- Only issues that directly block current mainline progress belong here -->
| Issue | Discovered Round | Blocking AC | Resolution Path |
|-------|-----------------|-------------|-----------------|

### Queued Side Issues
<!-- Non-blocking issues stay queued and must NOT replace the round objective -->
| Issue | Discovered Round | Why Not Blocking | Revisit Trigger |
|-------|-----------------|------------------|-----------------|

### Completed and Verified
<!-- Only move tasks here after the reviewer has verified them -->
| AC | Task | Completed Round | Verified Round | Evidence |
|----|------|-----------------|----------------|----------|

### Explicitly Deferred
<!-- Items here require strong justification -->
| Task | Original AC | Deferred Since | Justification | When to Reconsider |
|------|-------------|----------------|---------------|-------------------|
"""

#: setup-rlcr-loop.sh, the goal tracker it writes for `--skip-impl` with no plan.
GOAL_TRACKER_SKIP_IMPL = """# Goal Tracker (Skip Implementation Mode)

This RLCR loop was started with `--skip-impl`. The implementation phase was skipped,
and the loop is running in code review mode only.

This tracker is still used to keep the review loop aligned around one mainline objective
and to separate blocking issues from queued follow-up work.

## IMMUTABLE SECTION

### Ultimate Goal

Pass code review for the current branch without regressing existing behavior.

### Acceptance Criteria

- AC-1: All blocking `[P0-9]` code review findings are resolved.
- AC-2: Non-blocking follow-up items are explicitly queued and do not block completion.
- AC-3: Finalize phase can complete without introducing new review regressions.

---

## MUTABLE SECTION

### Plan Version: Review-Only (Updated: Round 0)

#### Plan Evolution Log
| Round | Change | Reason | Impact on AC |
|-------|--------|--------|--------------|
| 0 | Skip implementation mode initialized | Loop started with `--skip-impl` | Focus on \
review-only objective |

#### Active Tasks
| Task | Target AC | Status | Notes |
|------|-----------|--------|-------|
| [mainline] Pass code review for current branch | AC-1 | pending | Review-only mode |

### Blocking Side Issues
| Issue | Discovered Round | Blocking AC | Resolution Path |
|-------|-----------------|-------------|-----------------|

### Queued Side Issues
| Issue | Discovered Round | Why Not Blocking | Revisit Trigger |
|-------|-----------------|------------------|-----------------|

### Completed and Verified
| AC | Task | Completed Round | Verified Round | Evidence |
|----|------|-----------------|----------------|----------|

### Explicitly Deferred
| Task | Original AC | Deferred Since | Justification | When to Reconsider |
|------|-------------|----------------|---------------|-------------------|
"""

#: setup-rlcr-loop.sh, the goal tracker it writes for `--skip-impl` with a plan to anchor to.
GOAL_TRACKER_SKIP_IMPL_ANCHORED = """# Goal Tracker (Skip Implementation Mode with Plan Anchor)

This RLCR loop was started with `--skip-impl`. The implementation phase was skipped,
but an explicit plan was provided and remains the scope anchor for review-only work.

This tracker is still used to keep the review loop aligned around one mainline objective
and to separate blocking issues from queued follow-up work.

## IMMUTABLE SECTION

### Ultimate Goal

{{PLAN_GOAL_CONTENT}}

### Acceptance Criteria

{{PLAN_AC_CONTENT}}

---

## MUTABLE SECTION

### Plan Version: Review-Only (Updated: Round 0)

#### Plan Evolution Log
| Round | Change | Reason | Impact on AC |
|-------|--------|--------|--------------|
| 0 | Skip implementation mode initialized around explicit plan anchor | Loop started with \
`--skip-impl` and retained @{{PLAN_FILE}} as scope anchor | Review stays aligned with original \
plan |

#### Active Tasks
| Task | Target AC | Status | Notes |
|------|-----------|--------|-------|
| [mainline] Preserve original plan alignment while resolving blocking review findings | Plan \
ACs in scope | pending | Review-only mode with explicit plan anchor |

### Blocking Side Issues
| Issue | Discovered Round | Blocking AC | Resolution Path |
|-------|-----------------|-------------|-----------------|

### Queued Side Issues
| Issue | Discovered Round | Why Not Blocking | Revisit Trigger |
|-------|-----------------|------------------|-----------------|

### Completed and Verified
| AC | Task | Completed Round | Verified Round | Evidence |
|----|------|-----------------|----------------|----------|

### Explicitly Deferred
| Task | Original AC | Deferred Since | Justification | When to Reconsider |
|------|-------------|----------------|---------------|-------------------|
"""

#: setup-rlcr-loop.sh, `write_summary_template`.
SUMMARY_TEMPLATE = """# Round {{ROUND}} Summary

## What Was Implemented

[Describe what was done]

## Files Changed

[List files created/modified/deleted]

## Validation

[List tests/commands run and outcomes]

## Remaining Items

[List any deferred or pending items]

## BitLesson Delta

Action: none
Lesson ID(s): NONE
Notes: [what changed and why]
"""

#: The stop hook's own summary scaffold for a round it opens, which differs from the setup
#: script's -- the headings are the ones a later round is asked for.
ROUND_SUMMARY_TEMPLATE = """# Round {{ROUND}} Summary

## Work Completed
- [Describe what was implemented in this phase]

## Files Changed
- [List created/modified files]

## Validation
- [List tests/commands run and outcomes]

## Remaining Items
- [List unresolved items, if any]

## BitLesson Delta
- Action: none|add|update
- Lesson ID(s): NONE
- Notes: [what changed and why]
"""

#: setup-rlcr-loop.sh, the round 0 contract for `--skip-impl` with no plan.
ROUND_CONTRACT_SKIP_IMPL = """# Round 0 Contract

- Mainline Objective: Run code review for the current branch and resolve only findings that \
block clean acceptance.
- Target ACs: AC-1, AC-2
- Blocking Side Issues In Scope: Any `[P0-9]` findings from the active review cycle.
- Queued Side Issues Out of Scope: Non-blocking cleanup, follow-up refactors, or future \
improvements that do not block review acceptance.
- Success Criteria: Code review passes with no blocking findings, and any remaining \
non-blocking follow-up is explicitly queued.
"""

#: setup-rlcr-loop.sh, the round 0 contract for `--skip-impl` anchored to a plan.
ROUND_CONTRACT_SKIP_IMPL_ANCHORED = """# Round 0 Contract

- Mainline Objective: Keep the current branch aligned with @{{PLAN_FILE}} while resolving only \
review findings that block clean acceptance.
- Target ACs: The original plan acceptance criteria affected by the current branch changes.
- Blocking Side Issues In Scope: Any `[P0-9]` findings or regressions that block review \
acceptance or violate the original plan scope.
- Queued Side Issues Out of Scope: Non-blocking cleanup, follow-up refactors, or future \
improvements that do not block review acceptance or plan alignment.
- Success Criteria: Code review passes and the current branch still matches the original \
plan's intended scope.
"""

#: The task lane rules, which round 0 states and every round after it restates.
TASK_LANES = """For all tasks that need to be completed, please use the Task system \
(TaskCreate, TaskUpdate, TaskList).

Every task MUST start with exactly one lane tag:
- `[mainline]` for plan-derived work that directly advances the round objective
- `[blocking]` for issues that prevent the mainline objective from succeeding safely
- `[queued]` for non-blocking bugs, cleanup, or follow-up work

Rules:
- `[mainline]` tasks are the primary success condition for the round
- `[blocking]` tasks may be resolved in the round only if they truly block mainline progress
- `[queued]` tasks must NOT become the round objective and do NOT need to be cleared before \
moving on
- If a new issue is not blocking the current objective, tag it `[queued]` and keep moving on \
the mainline
"""

#: setup-rlcr-loop.sh, the BitLesson section of the round 0 prompt.
BITLESSON_SELECTION = """
---

## BitLesson Selection (REQUIRED FOR EACH TASK)

Before executing each task or sub-task, you MUST:

1. Read @{{BITLESSON_FILE}}
2. Select the relevant lesson IDs for each task/sub-task -- match only lessons directly \
relevant to its scope and failure mode, prefer precision over recall, and answer `NONE` when \
nothing is relevant
3. Follow the selected lesson IDs (or `NONE`) during implementation

Include a `## BitLesson Delta` section in your summary with:
- Action: none|add|update
- Lesson ID(s): NONE or comma-separated IDs
- Notes: what changed and why (required if action is add or update)

Reference: @{{BITLESSON_FILE}}
"""

#: setup-rlcr-loop.sh, the round 0 prompt in normal mode. The plan itself is appended where
#: `{{PLAN_CONTENT}}` is, as the script appends the plan backup.
ROUND_0 = """Read and execute below with ultrathink

## Goal Tracker Setup (REQUIRED FIRST STEP)

Before starting implementation, you MUST initialize the Goal Tracker:

1. Read @{{GOAL_TRACKER_FILE}}
2. If the "Ultimate Goal" section says "[To be extracted...]", extract a clear goal statement \
from the plan
3. If the "Acceptance Criteria" section says "[To be defined...]", define 3-7 specific, \
testable criteria
4. Populate the "Active Tasks" table with MAINLINE tasks from the plan, mapping each to an AC \
and filling Tag/Owner
5. Record any already-known side issues in either "Blocking Side Issues" or "Queued Side Issues"
6. Write the updated goal-tracker.md

## Round Contract Setup (REQUIRED BEFORE CODING)

Before starting implementation, create @{{ROUND_CONTRACT_FILE}} with:

1. **One mainline objective** for this round
2. **Target ACs** (1-2 ACs only)
3. **Blocking side issues in scope** for this round
4. **Queued side issues out of scope** for this round
5. **Round success criteria**

Use this contract to keep the round focused. Do NOT let non-blocking bugs or cleanup work \
replace the mainline objective.

**IMPORTANT**: The IMMUTABLE SECTION can only be modified in Round 0. After this round, it \
becomes read-only.

---

## Implementation Plan

{{TASK_LANES}}
## Task Tag Routing (MUST FOLLOW)

Each task must have one routing tag from the plan: `coding` or `analyze`.

- Tag `coding`: you execute the task directly.
- Tag `analyze`: it is a question rather than work. Settle it if the repository settles it, \
and otherwise state it in your round summary -- the reviewer reads the repository without \
having watched you work, and answers it in its review.
- Keep Goal Tracker "Active Tasks" columns **Tag** and **Owner** aligned with execution \
(`coding -> claude`, `analyze -> codex`).
- If a task has no explicit tag, default to `coding` (you execute it directly).

{{PLAN_CONTENT}}
{{BITLESSON_SELECTION}}{{AGENT_TEAMS}}
---

## Goal Tracker Rules

Throughout your work, you MUST maintain the Goal Tracker:

1. **Before starting a round**: Re-anchor on the original plan and current round contract
2. **Before starting a task**: Mark the relevant mainline task as "in_progress" in Active Tasks
   - Confirm Tag/Owner routing is correct before execution
3. **Active Tasks** are MAINLINE tasks only - side issues do not belong there
4. **Blocking Side Issues** are reserved for issues that truly stop mainline progress
5. **Queued Side Issues** are non-blocking and must not take over the round
6. **After completing a mainline task**: Move it to "Completed and Verified" with evidence \
(but mark as "pending verification")
7. **If you discover the plan has errors**:
   - Do NOT silently change direction
   - Add entry to "Plan Evolution Log" with justification
   - Explain how the change still serves the Ultimate Goal
8. **If you need to defer a task**:
   - Move it to "Explicitly Deferred" section
   - Provide strong justification
   - Explain impact on Acceptance Criteria
9. **If you discover new issues**:
   - Add to "Blocking Side Issues" only if mainline progress is blocked
   - Otherwise add to "Queued Side Issues" or keep them as `[queued]` tasks/backlog

---

Note: You MUST NOT try to exit this loop by lying or editing loop state files.

After completing the work, please:
0. If you have access to a code simplifier agent, use it to review and optimize the code you \
just wrote
1. Finalize @{{GOAL_TRACKER_FILE}} (this is Round 0, so you are initializing it - see "Goal \
Tracker Setup" above)
2. Write your round contract into @{{ROUND_CONTRACT_FILE}}
3. Commit your changes with a descriptive commit message
4. Write your work summary into @{{SUMMARY_FILE}}
"""

#: setup-rlcr-loop.sh, the round 0 prompt for `--skip-impl`.
ROUND_0_SKIP_IMPL = """# Skip Implementation Mode - Code Review Loop

This RLCR loop was started with `--skip-impl`.

**Mode**: Code Review Only (skipping implementation phase)
**Base Branch**: {{BASE_BRANCH}}
**Current Branch**: {{START_BRANCH}}

## What This Means

The loop will automatically run a code review of your changes when you try to exit.
If issues are found (marked with [P0-9] priority), you'll need to fix them before the loop ends.
Do not try to execute anything to trigger the review - just stop and it will run automatically.

Before requesting review, read:
- @{{PLAN_FILE}}
- @{{GOAL_TRACKER_FILE}}
- @{{ROUND_CONTRACT_FILE}}

## Your Task

1. Review your current work
2. When ready, try to exit - the reviewer will review your code
3. Fix any issues the reviewer finds
4. Repeat until no issues remain
5. Enter finalize phase for code simplification

## Review Objective

Use the round contract as the current anchor:
- Keep one stable mainline objective and do not let it drift
- Treat review findings as `[blocking]` only if they block review acceptance
- Record non-blocking follow-up as `[queued]`
- Do not let queued work take over the round

{{ANCHOR}}

Keep @{{ROUND_CONTRACT_FILE}} updated if the blocking/queued split changes materially during \
review iterations.

When you're ready for review, write a brief summary of your changes and try to exit (do not \
try to execute anything, just stop).

Write your summary to: @{{SUMMARY_FILE}}
"""

#: The two endings of the skip-impl round 0 prompt: with a plan to stay inside, and without.
ROUND_0_SKIP_IMPL_ANCHORED = """- Keep review-only work aligned with the original plan at \
@{{PLAN_FILE}}

Implementation phase is skipped, but the original plan still defines the intended branch scope.
"""
ROUND_0_SKIP_IMPL_UNANCHORED = """There is no explicit implementation plan for this loop, so \
the review-only contract is the primary anchor.
"""

#: prompt-template/claude/agent-teams-instructions.md, verbatim.
AGENT_TEAMS_INSTRUCTIONS = """## Agent Teams Mode

You are operating in **Agent Teams mode** as the **Team Leader** within an RLCR \
(Review-Loop-Correct-Repeat) development cycle.

This is the initial round. Read the implementation plan thoroughly before creating your team. \
Key RLCR files to be aware of:
- **Plan file** (provided above): The full scope of work and requirements your team must \
implement
- **Goal tracker** (`goal-tracker.md`): Tracks acceptance criteria, task status, and plan \
evolution - read it before splitting tasks
- **Work summary**: After all teammates finish, you must write a summary of what was \
accomplished into the designated summary file
"""

#: prompt-template/claude/agent-teams-core.md, verbatim.
AGENT_TEAMS_CORE = """### Your Role

You are the team leader. Your ONLY job is coordination and delegation. You must NEVER write \
code, edit files, or implement anything yourself.

Your primary responsibilities are:
- **Split tasks** into independent, parallelizable units of work
- **Create agent teams** to execute these tasks using the Task tool with `team_name` parameter
- **Coordinate** team members to prevent overlapping or conflicting changes
- **Monitor progress** and resolve blocking issues between team members
- **Wait for teammates** to finish their work before proceeding - do not implement tasks \
yourself while waiting

If you feel the urge to implement something directly, STOP and delegate it to a team member \
instead.

### Guidelines

1. **Task Splitting**: Break work into independent tasks that can be worked on in parallel \
without file conflicts. Each task should have clear scope and acceptance criteria. Aim for 5-6 \
tasks per teammate to keep everyone productive and allow reassignment if someone gets stuck.
2. **Cold Start**: Every team member starts with zero prior context (they do NOT inherit your \
conversation history). However, they DO automatically load project-level CLAUDE.md files and \
MCP servers. When spawning members, focus on providing: the implementation plan or relevant \
goals, specific file paths they need to work on, what has been done so far, and what exactly \
needs to be accomplished. Do not repeat what CLAUDE.md already covers.
3. **File Conflict Prevention**: Two teammates editing the same file causes silent overwrites, \
not merge conflicts - one teammate's work will be completely lost. Assign strict file ownership \
boundaries. If two tasks must touch the same file, sequence them with task dependencies \
(blockedBy) so they never run in parallel.
4. **Coordination**: Track team member progress via TaskList and resolve any discovered \
dependencies. If a member is blocked or stuck, help unblock them or reassign the work to \
another member.
5. **Quality**: Review team member output before considering tasks complete. Verify that \
changes are correct, do not conflict with other members' work, and meet the acceptance criteria.
6. **Commits**: Each team member should commit their own changes. You coordinate the overall \
commit strategy and ensure all commits are properly sequenced.
7. **Plan Approval**: For high-risk or architecturally significant tasks, consider requiring \
teammates to plan before implementing (using plan mode). Review and approve their plans before \
they proceed.
8. **BitLesson Discipline**: Require selecting the relevant BitLesson entries before each \
sub-task and record selected lesson IDs (or `NONE`) in the work notes.

### Important

- Use the Task tool to spawn agents as team members
- Monitor team members and reassign work if they get stuck
- Merge team work and resolve any conflicts before writing your summary
- Do NOT write code yourself - if you catch yourself about to edit a file or run implementation \
commands, delegate it instead
- When teammates go idle after sending you a message, this is NORMAL - they are waiting for \
your response, not done forever
"""

#: prompt-template/claude/agent-teams-continue.md, verbatim.
AGENT_TEAMS_CONTINUE = """## Agent Teams Continuation

Continue using **Agent Teams mode** as the **Team Leader** within the RLCR development cycle. \
You are continuing from a previous round where the reviewer reviewed your work and provided \
feedback above.

### Continuation Context

- **Previous Team No Longer Exists**: Your teammates from the previous round are gone. Do NOT \
attempt to message or reference old teammates. You must create a brand new team for this round.
- **Review First**: Before spawning any team members, carefully analyze the review feedback \
above. Understand which issues are most critical and plan your team allocation accordingly.
- **Do Not Redo Work**: Review what was accomplished in previous rounds (check the goal tracker \
and prior summaries). Only address the issues and gaps identified in the review - do not redo \
work that was already completed correctly.
- **Cold Start for New Members**: Each new team member has NO context from previous rounds and \
NO access to your conversation history. They DO have access to CLAUDE.md and project \
configuration automatically. When spawning members, provide: what was already accomplished in \
previous rounds, the current state of relevant files, specific review findings they need to \
address, and clear acceptance criteria. Do not repeat what CLAUDE.md already covers.
- **Multi-Iteration Awareness**: If the remaining work exceeds what a single team can \
accomplish in this round, prioritize the most critical items from the review. Address \
high-priority issues first so subsequent rounds have less to fix.
- **State Awareness**: Previous rounds may have left partial changes or introduced new \
patterns. Verify the current state of files (e.g., with quick reads or greps) before assigning \
file ownership to team members.
"""


# ======================================================================================
# The loop -- what the reviewer is asked each round, and what the builder hears back
# ======================================================================================

#: prompt-template/codex/goal-tracker-update-section.md, verbatim.
GOAL_TRACKER_UPDATE_SECTION = """## Goal Tracker Update Requests (YOUR RESPONSIBILITY)

The builder should normally keep the **mutable section** of `goal-tracker.md` up to date \
directly. If its summary contains a "Goal Tracker Update Request" section, or if you detect \
tracker drift during review, YOU must:

1. **Evaluate the tracker state**: Is the mutable section still aligned with the Ultimate Goal \
and current AC progress?
2. **If correction is needed**: Update @{{GOAL_TRACKER_FILE}} yourself with the requested \
changes:
   - Move tasks between Active/Completed/Deferred sections as appropriate
   - Add entries to "Plan Evolution Log" with round number and justification
   - Add new issues to "Blocking Side Issues" or "Queued Side Issues" as appropriate
   - **NEVER modify the IMMUTABLE SECTION** (Ultimate Goal and Acceptance Criteria)
3. **If you reject a requested tracker change**: Include in your review why it was rejected

Common update requests you should handle:
- Task completion: Move from "Active Tasks" to "Completed and Verified"
- New blocking issues: Add to "Blocking Side Issues"
- New queued issues: Add to "Queued Side Issues"
- Plan changes: Add to "Plan Evolution Log" with your assessment
- Deferrals: Only allow with strong justification; add to "Explicitly Deferred"
"""

#: prompt-template/codex/commit-history-section.md, verbatim.
COMMIT_HISTORY_SECTION = """## Development History (Integral Context)

Accumulated commits since loop start (oldest first):
```
{{COMMIT_HISTORY}}
```

### Recent Round Files
Read these files before conducting your review to understand the trajectory of work:
{{RECENT_ROUND_FILES}}

Use this history to identify patterns across rounds: recurring issues, stalled progress, or \
drift from the mainline objective. Weight recent rounds more heavily but watch for systemic \
trends in the full commit log.
"""

#: prompt-template/codex/regular-review.md, verbatim but for naming the two agents by what
#: this flow calls them.
REGULAR_REVIEW = """# Code Review - Round {{CURRENT_ROUND}}

## Original Implementation Plan

**IMPORTANT**: The original plan that the builder is implementing is located at:
@{{PLAN_FILE}}

You MUST read this plan file first to understand the full scope of work before conducting your \
review.
This plan contains the complete requirements and implementation details that the builder should \
be following.

Based on the original plan and @{{PROMPT_FILE}}, the builder claims to have completed the work. \
Please conduct a thorough critical review to verify this.

---
Below is the builder's summary of the work completed:
<!-- BUILDER's WORK SUMMARY START -->
{{SUMMARY_CONTENT}}
<!-- BUILDER's WORK SUMMARY  END  -->
---

{{COMMIT_HISTORY_SECTION}}

## Part 1: Implementation Review

- Your task is to conduct a deep critical review, focusing on finding implementation issues and \
identifying gaps between "plan-design" and actual implementation.
- Relevant top-level guidance documents, phased implementation plans, and other important \
documentation and implementation references are located under @{{DOCS_PATH}}.
- If the builder planned to defer any tasks to future phases in its summary, DO NOT follow its \
lead. Instead, you should force it to complete ALL tasks as planned.
  - Such deferred tasks are considered incomplete work and should be flagged in your review \
comments, requiring the builder to address them.
  - If the builder planned to defer any tasks, please explore the codebase in-depth and draft a \
detailed implementation plan. This plan should be included in your review comments for the \
builder to follow.
  - Your review should be meticulous and skeptical. Look for any discrepancies, missing \
features, incomplete implementations.
- If the builder does not plan to defer any tasks, but honestly admits that some tasks are \
still pending (not yet completed), you should also include those pending tasks in your review.
  - Your review should elaborate on those unfinished tasks, explore the codebase, and draft an \
implementation plan.
  - A good engineering implementation plan should be **singular, directive, and definitive**, \
rather than discussing multiple possible implementation options.
  - The implementation plan should be **unambiguous**, internally consistent, and coherent from \
beginning to end, so that **the builder can execute the work accurately and without error**.

## Part 2: Goal Alignment Check (MANDATORY)

Read @{{GOAL_TRACKER_FILE}} and verify:

1. **Acceptance Criteria Progress**: For each AC, is progress being made? Are any ACs being \
ignored?
2. **Forgotten Items**: Are there tasks from the original plan that are not tracked in \
Active/Completed/Deferred?
3. **Deferred Items**: Are deferrals justified? Do they block any ACs?
4. **Plan Evolution**: If the builder modified the plan, is the justification valid?

Include a brief Goal Alignment Summary in your review:
```
ACs: X/Y addressed | Forgotten items: N | Unjustified deferrals: N
```

## Part 3: Required Finding Classification

You MUST classify your findings into these lanes:
- **Mainline Gaps**: plan-derived work or AC progress that is missing, incomplete, or regressing
- **Blocking Side Issues**: bugs or implementation issues that block the current mainline \
objective from succeeding safely
- **Queued Side Issues**: valid non-blocking follow-up issues that should be documented but \
must NOT take over the next round

Also include a one-line verdict:
```
Mainline Progress Verdict: ADVANCED / STALLED / REGRESSED
```

This verdict line is mandatory. If you omit it, the loop will block the round and require the \
review to be rerun.

If the builder mostly worked on queued side issues and failed to advance the mainline, say so \
explicitly.

## Part 4: {{GOAL_TRACKER_UPDATE_SECTION}}

## Part 5: Output Requirements

- If the builder's summary put a question to you, answer it: it is a task the plan tagged \
`analyze`, and you are the one reading the repository without having watched the work.
- In short, your review comments can include: problems/findings/blockers; claims that don't \
match reality; implementation plans for deferred work (to be implemented now); implementation \
plans for unfinished work; goal alignment issues.
- Your output should be structured so the builder can tell which items are mainline gaps, \
blocking side issues, and queued side issues.
- If after your investigation the actual situation does not match what the builder claims to \
have completed, or there is pending work to be done, output your review comments to \
@{{REVIEW_RESULT_FILE}}.
- **CRITICAL**: Only output "COMPLETE" as the last line if ALL tasks from the original plan are \
FULLY completed with no deferrals
  - DEFERRED items are considered INCOMPLETE - do NOT output COMPLETE if any task is deferred
  - UNFINISHED items are considered INCOMPLETE - do NOT output COMPLETE if any task is pending
  - The ONLY condition for COMPLETE is: all original plan tasks are done, all ACs are met, no \
deferrals or pending work allowed
- The word COMPLETE on the last line will stop the builder.
"""

#: prompt-template/codex/full-alignment-review.md, verbatim but for naming the two agents.
FULL_ALIGNMENT_REVIEW = """# FULL GOAL ALIGNMENT CHECK - Round {{CURRENT_ROUND}}

This is a **mandatory checkpoint** (at configurable intervals). You must conduct a \
comprehensive goal alignment audit.

## Original Implementation Plan

**IMPORTANT**: The original plan that the builder is implementing is located at:
@{{PLAN_FILE}}

You MUST read this plan file first to understand the full scope of work before conducting your \
review.

---
## The builder's Work Summary
<!-- BUILDER's WORK SUMMARY START -->
{{SUMMARY_CONTENT}}
<!-- BUILDER's WORK SUMMARY  END  -->
---

{{COMMIT_HISTORY_SECTION}}

## Part 1: Goal Tracker Audit (MANDATORY)

Read @{{GOAL_TRACKER_FILE}} and verify:

### 1.1 Acceptance Criteria Status
For EACH Acceptance Criterion in the IMMUTABLE SECTION:
| AC | Status | Evidence (if MET) | Blocker (if NOT MET) | Justification (if DEFERRED) |
|----|--------|-------------------|---------------------|----------------------------|
| AC-1 | MET / PARTIAL / NOT MET / DEFERRED | ... | ... | ... |
| ... | ... | ... | ... | ... |

### 1.2 Forgotten Items Detection
Compare the original plan (@{{PLAN_FILE}}) with the current goal-tracker:
- Are there tasks that are neither in "Active", "Completed", nor "Deferred"?
- Are there tasks marked "complete" in summaries but not verified?
- List any forgotten items found.

### 1.3 Deferred Items Audit
For each item in "Explicitly Deferred":
- Is the deferral justification still valid?
- Should it be un-deferred based on current progress?
- Does it contradict the Ultimate Goal?

### 1.4 Goal Completion Summary
```
Acceptance Criteria: X/Y met (Z deferred)
Active Tasks: N remaining
Estimated remaining rounds: ?
Critical blockers: [list if any]
```

## Part 2: Mainline Drift Audit (MANDATORY)

Determine whether the recent rounds are still serving the original plan:
- Is the current round's mainline objective clear and singular?
- Has the builder been advancing mainline ACs, or mostly clearing side issues?
- Which findings are true **blocking side issues** versus merely **queued side issues**?

Include a short drift summary:
```
Mainline Progress Verdict: ADVANCED / STALLED / REGRESSED
Blocking Side Issues: N
Queued Side Issues: N
```

The `Mainline Progress Verdict` line is mandatory. If you omit it, the loop will block the \
round and require the review to be rerun.

## Part 3: Implementation Review

- Conduct a deep critical review of the implementation
- Verify the builder's claims match reality
- Identify any gaps, bugs, or incomplete work
- Reference @{{DOCS_PATH}} for design documents

## Part 4: {{GOAL_TRACKER_UPDATE_SECTION}}

## Part 5: Progress Stagnation Check (MANDATORY for Full Alignment Rounds)

To implement the original plan at @{{PLAN_FILE}}, we have completed **{{COMPLETED_ITERATIONS}} \
iterations** (Round 0 to Round {{CURRENT_ROUND}}).

The project's `{{LOOP_DIR}}/` directory contains the history of each round's iteration:
- Round input prompts: `round-N-prompt.md`
- Round output summaries: `round-N-summary.md`
- Round review prompts: `round-N-review-prompt.md`
- Round review results: `round-N-review-result.md`

**How to Access Historical Files**: Read the historical review results and summaries using file \
paths like:
- `@{{LOOP_DIR}}/round-{{PREV_ROUND}}-review-result.md` (previous round)
- `@{{LOOP_DIR}}/round-{{PREV_PREV_ROUND}}-review-result.md` (2 rounds ago)
- `@{{LOOP_DIR}}/round-{{PREV_ROUND}}-summary.md` (previous summary)

**Your Task**: Review the historical review results, especially the **recent rounds** of \
development progress and review outcomes, to determine if the development has stalled.

**Signs of Stagnation** (circuit breaker triggers):
- Same issues appearing repeatedly across multiple rounds
- No meaningful progress on Acceptance Criteria over several rounds
- The builder making the same mistakes repeatedly
- Circular discussions without resolution
- No new code changes despite continued iterations
- The reviewer giving similar feedback repeatedly without the builder addressing it

**If development is stagnating**, write **STOP** (as a single word on its own line) as the last \
line of your review output @{{REVIEW_RESULT_FILE}} instead of COMPLETE.

## Part 6: Output Requirements

- If issues found OR any AC is NOT MET (including deferred ACs), write your findings to \
@{{REVIEW_RESULT_FILE}}
- Include specific action items for the builder to address, classified into:
  - Mainline Gaps
  - Blocking Side Issues
  - Queued Side Issues
- **If development is stagnating** (see Part 5), write "STOP" as the last line
- **CRITICAL**: Only write "COMPLETE" as the last line if ALL ACs from the original plan are \
FULLY MET with no deferrals
  - DEFERRED items are considered INCOMPLETE - do NOT output COMPLETE if any AC is deferred
  - The ONLY condition for COMPLETE is: all original plan tasks are done, all ACs are met, no \
deferrals allowed
"""

#: prompt-template/codex/code-review-phase.md is an audit note in the plugin: `codex review`
#: takes no prompt, so the file only records that it ran. Here the reviewer is whichever
#: agent was chosen, so the review has to be asked for -- and this asks for exactly what
#: `codex review --base` produces, since the loop reads it the same way.
CODE_REVIEW = """# Code Review Phase - Round {{REVIEW_ROUND}}

The builder has finished the work for the plan in this repository, and the question here is \
not whether it does what was asked, but whether what is now in the repository is any good.

Review the change as a whole: everything since {{REVIEW_BASE}}, which is the {{REVIEW_BASE_TYPE}} \
the work started from. Read the diff, read the code around it, and run the tests.

Be skeptical in one direction in particular: work stubbed out, tests weakened or special-cased \
to pass, error paths nothing takes, a case the tests do not reach, something duplicated rather \
than shared, a name that now lies.

## Output Format

Report each issue on its own line, starting with a severity marker in the first ten characters, \
exactly like this:

```
- [P0] Critical issue description - /path/to/file.py:line-range
  Detailed explanation of the issue.

- [P1] High priority issue - /path/to/file.py:line-range
  Detailed explanation.
```

`[P0]` is what must not ship and `[P9]` is what you would mention and not insist on. The loop \
reads these markers and nothing else: an issue written without one is an issue nobody will fix, \
and a line carrying one is a round the builder will spend fixing it.

If there is nothing that should be fixed before this ships, say so plainly and write no `[P0-9]` \
marker anywhere in your answer: a review that finds something every time is not a review.
"""

#: prompt-template/claude/next-round-prompt.md, verbatim but for naming the two agents.
NEXT_ROUND = """Your work is not finished. Read and execute the below with ultrathink.

## Original Implementation Plan

**IMPORTANT**: Before proceeding, review the original plan you are implementing:
@{{PLAN_FILE}}

This plan contains the full scope of work and requirements. Ensure your work aligns with this \
plan.

---

## Round Re-anchor (REQUIRED FIRST STEP)

Before writing code:
- Re-read @{{PLAN_FILE}}
- Re-read @{{GOAL_TRACKER_FILE}}
- Re-read the most recent round summaries/reviews that led to this round
- Write the current round contract to @{{ROUND_CONTRACT_FILE}}

Your round contract must contain:
- Exactly one **mainline objective**
- The 1-2 target ACs for this round
- Which issues are truly **blocking** that mainline objective
- Which issues are **queued** and explicitly out of scope
- Concrete success criteria for this round

Do not start implementation until the round contract exists.

## Task Lane Rules

Use the Task system (TaskCreate, TaskUpdate, TaskList) with one required tag per task:
- `[mainline]` for plan-derived work that directly advances this round's objective
- `[blocking]` for issues that prevent the mainline objective from succeeding safely
- `[queued]` for non-blocking bugs, cleanup, or follow-up work

Rules:
- `[mainline]` work is the round's primary success condition
- `[blocking]` work is allowed only when it truly blocks the mainline objective
- `[queued]` work must be documented but must NOT replace the round objective
- If a new bug does not block the current objective, tag it `[queued]` and keep moving on \
mainline work

Before executing each task in this round:
1. Read @{{BITLESSON_FILE}}
2. Select the relevant lesson IDs for each task/sub-task
3. Follow selected lesson IDs (or `NONE`) during implementation

---
Below is the reviewer's review result:
<!-- REVIEWER's REVIEW RESULT START -->
{{REVIEW_CONTENT}}
<!-- REVIEWER's REVIEW RESULT  END  -->
---

## Goal Tracker Reference

Before starting work, **read** @{{GOAL_TRACKER_FILE}} to understand:
- The Ultimate Goal and Acceptance Criteria you're working toward
- Which tasks are Active, Completed, or Deferred
- Which side issues are blocking vs queued
- Any Plan Evolution that has occurred
- The latest side-issue state that needs attention

**IMPORTANT**: Keep the mutable section of `goal-tracker.md` up to date during the round.
Do NOT change the immutable section after Round 0.
If you cannot safely reconcile the tracker yourself, include an optional "Goal Tracker Update \
Request" section in your summary (see below).

## Mainline Guardrails

- Keep the mainline objective from @{{ROUND_CONTRACT_FILE}} stable for this round
- Do not let queued issues take over the round
- If the reviewer reported several findings, classify them into:
  - mainline gaps
  - blocking side issues
  - queued side issues
- Only mainline gaps and blocking side issues should drive the next code changes
"""

#: prompt-template/claude/drift-replan-prompt.md, verbatim but for naming the two agents.
DRIFT_REPLAN = """Your work is not finished. Read and execute the below with ultrathink.

## Drift Recovery Mode

The reviewer judged the recent implementation rounds as failing to advance the mainline.

- Consecutive stalled/regressed rounds: {{STALL_COUNT}}
- Last mainline verdict: {{LAST_MAINLINE_VERDICT}}

This round is a **drift recovery round**. Do not continue with normal issue-clearing behavior.

## Original Implementation Plan

**IMPORTANT**: Re-anchor on the original plan first:
@{{PLAN_FILE}}

## Required Recovery Re-anchor

Before changing code:
- Re-read @{{PLAN_FILE}}
- Re-read @{{GOAL_TRACKER_FILE}}
- Re-read the recent round summaries and review results that led here
- Rewrite the round contract at @{{ROUND_CONTRACT_FILE}}

Your recovery contract must contain:
- Exactly one recovered **mainline objective**
- The 1-2 target ACs that prove mainline progress this round
- The root cause of recent drift or stagnation
- Which issues are truly **blocking** the recovered mainline objective
- Which issues remain **queued** and explicitly out of scope
- Concrete success criteria that would change the verdict back to `ADVANCED`

Do not start implementation until the recovery contract exists.

## Task Lane Rules

Use the Task system (TaskCreate, TaskUpdate, TaskList) with one required tag per task:
- `[mainline]` for plan-derived work that directly advances the recovered objective
- `[blocking]` for issues that prevent the recovered mainline objective from succeeding safely
- `[queued]` for non-blocking bugs, cleanup, or follow-up work

Rules:
- This round must prove mainline movement, not just reduce noise
- `[blocking]` work is allowed only when it directly unblocks the recovered mainline objective
- `[queued]` work must stay documented but must NOT replace the recovered objective
- If a new issue does not block the recovered objective, tag it `[queued]` and keep moving on \
mainline work

---
Below is the reviewer's review result:
<!-- REVIEWER's REVIEW RESULT START -->
{{REVIEW_CONTENT}}
<!-- REVIEWER's REVIEW RESULT  END  -->
---

## Goal Tracker Reference

Before starting work, **read and update** @{{GOAL_TRACKER_FILE}} as needed:
- Keep the immutable section unchanged
- Record the drift/stagnation cause in the mutable section if it changed planning
- Keep blocking vs queued issue classification accurate
- Ensure the tracker and contract now describe the same recovered mainline objective

## Recovery Guardrails

- Do not spend this round mostly on queued cleanup
- Do not broaden scope to compensate for previous stalls
- If the original approach was flawed, log the plan evolution explicitly instead of silently \
changing direction
- If you cannot produce a credible recovered mainline objective, say so in the summary with \
concrete blockers
"""

#: prompt-template/claude/review-phase-prompt.md, verbatim but for naming the two agents.
REVIEW_PHASE = """# Code Review Findings

You are in the **Review Phase**. The reviewer has performed a code review and found issues \
that need to be addressed.

## Required Re-anchor

Before touching code:
- Re-read the original plan at @{{PLAN_FILE}}
- Re-read the goal tracker at @{{GOAL_TRACKER_FILE}}
- Refresh the current round contract at @{{ROUND_CONTRACT_FILE}}

The round contract must preserve a single mainline objective. Code review findings do NOT \
automatically become the new round objective.

## Review Results

{{REVIEW_CONTENT}}

## Issue Classification

Classify each review finding before acting on it:
- **blocking side issue**: prevents the current mainline objective from succeeding safely or \
prevents review acceptance
- **queued side issue**: valid follow-up, but does not block the current round objective

Queued issues may be documented, but they must NOT take over the round.

## Task Rules

Every task must use one lane tag:
- `[blocking]` for review findings that must be fixed now
- `[queued]` for non-blocking follow-up work

Do not create new `[mainline]` tasks in review phase unless the review proves the previous \
mainline objective was incomplete.

## Instructions

1. **Refresh the round contract** at `{{ROUND_CONTRACT_FILE}}`
2. **Address blocking issues first** and keep the mainline objective stable
3. **Focus on fixes only** - do not add new features or make unrelated changes
4. **Commit your changes** after fixing the issues
5. **Write your summary** to: `{{SUMMARY_FILE}}`

## Summary Template

Your summary should include:
- The mainline objective for this round
- Which blocking issues were fixed
- Which issues were reclassified as queued follow-up
- How each fixed issue was resolved
- Any issues that could not be resolved (with explanation)
- Confirmation that `goal-tracker.md` was updated if the blocking/queued issue lists changed
- A Goal Tracker Update Request only if tracker reconciliation still needs the reviewer's help

## Important Notes

- The COMPLETE signal has no effect during the review phase
- You must address the code review findings to proceed
- After you commit and write your summary, the reviewer will perform another code review
- The loop continues until no `[P0-9]` issues are found
"""

#: The stop hook's `continue_review_loop_with_issues` BitLesson section.
REVIEW_PHASE_BITLESSON = """
## BitLesson Selection (REQUIRED FOR EACH FIX TASK)

Before implementing each fix task, you MUST:

1. Read @{{BITLESSON_FILE}}
2. Select the relevant lesson IDs for each fix task/sub-task
3. Follow the selected lesson IDs (or `NONE`) during implementation

Reference: @{{BITLESSON_FILE}}
"""

#: The stop hook's `append_task_tag_routing_note`, verbatim.
ROUND_ROUTING_NOTE = """
## Task Tag Routing Reminder

Follow the plan's per-task routing tags strictly:
- `coding` task -> the builder executes directly
- `analyze` task -> a question for the reviewer: state it in the round summary
- Keep Goal Tracker Active Tasks columns `Tag` and `Owner` aligned with execution
"""

#: prompt-template/claude/next-round-footer.md, verbatim.
NEXT_ROUND_FOOTER = """
---

Note: You MUST NOT try to exit by lying or editing loop state files.

After completing the work, please:
0. If you have access to a code simplifier agent, use it to review and optimize your code
1. Commit your changes with a descriptive commit message
2. Write your work summary into @{{NEXT_SUMMARY_FILE}}
"""

#: prompt-template/claude/post-alignment-action-items.md, verbatim.
POST_ALIGNMENT_ACTION_ITEMS = """
### Post-Alignment Check Action Items

This round follows a Full Goal Alignment Check. Pay special attention to:
- **Forgotten Items**: The reviewer may have identified tasks that were being ignored. Address \
them.
- **AC Status**: If any Acceptance Criteria were marked NOT MET, prioritize work toward those.
- **Deferred Items**: If any deferrals were flagged as unjustified, un-defer them now.
- **Queued Issues**: Keep non-blocking follow-up work queued unless it now clearly blocks \
mainline progress.
"""

#: prompt-template/claude/push-every-round-note.md, verbatim.
PUSH_EVERY_ROUND_NOTE = """
Note: Since `push_every_round` is enabled, you must push your commits to remote after each \
round.
"""

#: prompt-template/claude/open-question-notice.md, verbatim.
OPEN_QUESTION_NOTICE = """**IMPORTANT**: The reviewer has found Open Question(s). You must use \
`AskUserQuestion` to clarify those questions with the user first, before proceeding to resolve \
any other findings."""

#: prompt-template/claude/goal-tracker-update-request.md, verbatim.
GOAL_TRACKER_UPDATE_REQUEST = """
**Optional fallback**: if you could not safely update the mutable section of \
`goal-tracker.md` directly, include this section in your summary:
```markdown
## Goal Tracker Update Request

### Requested Changes:
- [E.g., "Mark Task X as completed with evidence: tests pass"]
- [E.g., "Add to Blocking Side Issues: bug Y blocks AC-2"]
- [E.g., "Add to Queued Side Issues: cleanup Z is non-blocking"]
- [E.g., "Plan Evolution: changed approach from A to B because..."]
- [E.g., "Defer Task Z because... (impact on AC: none/minimal)"]

### Justification:
[Explain why these changes are needed and how they serve the Ultimate Goal]
```

The reviewer will review your request and reconcile the Goal Tracker if justified.
"""

#: prompt-template/claude/finalize-phase-prompt.md, verbatim.
FINALIZE = """# Finalize Phase

The code review has passed. The implementation is complete and all acceptance criteria have \
been met.

You are now in the **Finalize Phase**. This is your opportunity to simplify and refactor the \
code before final completion.

## Your Task

Use a code-simplifier agent via the Task tool to review and simplify the recent code changes.

## Constraints

These constraints are **non-negotiable**:

1. **Must NOT change existing functionality** - All features must work exactly as before
2. **Must NOT fail existing tests** - Run tests to verify nothing is broken
3. **Must NOT introduce new bugs** - Be careful with refactoring
4. **Only perform functionality-equivalent changes** - Simplification and cleanup only

## Focus Areas

The code-simplifier agent should focus on:
- Code that was recently added or modified
- Focus more on changes between `{{BASE_BRANCH}}` and `{{START_BRANCH}}`
- Removing unnecessary complexity
- Improving readability and maintainability
- Consolidating duplicate code
- Simplifying control flow where possible
- Removing dead code or unused variables

## Reference Files

- Original plan: @{{PLAN_FILE}}
- Goal tracker: @{{GOAL_TRACKER_FILE}}

## Before Exiting

1. Complete all `[mainline]` and `[blocking]` tasks (mark them as completed using TaskUpdate \
with status "completed")
2. `[queued]` tasks may remain only if they are documented as non-blocking follow-up work
3. Commit your changes with a descriptive message
4. Write your finalize summary to: **{{FINALIZE_SUMMARY_FILE}}**

Your summary should include:
- What simplifications were made
- Files modified during the Finalize Phase
- Confirmation that tests still pass
- Any notes about the refactoring decisions
"""

#: prompt-template/claude/finalize-phase-skipped-prompt.md, verbatim.
FINALIZE_SKIPPED = """# Finalize Phase (Review Skipped)

**Warning**: Code review was skipped due to: {{REVIEW_SKIP_REASON}}

The implementation could not be fully validated. You are now in the **Finalize Phase**.

## Important Notice

Since the code review was skipped, please manually verify your changes before finalizing:

1. Review your code changes for any obvious issues
2. Run any available tests to verify correctness
3. Check for common code quality issues

## Simplification (Optional)

If time permits, use a code-simplifier agent via the Task tool to simplify and refactor your \
code.

Focus more on changes between `{{BASE_BRANCH}}` and `{{START_BRANCH}}`.

## Constraints

These constraints are **non-negotiable**:

1. **Must NOT change existing functionality** - All features must work exactly as before
2. **Must NOT fail existing tests** - Run tests to verify nothing is broken
3. **Must NOT introduce new bugs** - Be careful with refactoring
4. **Only perform functionality-equivalent changes** - Simplification and cleanup only

## Reference Files

- Original plan: @{{PLAN_FILE}}
- Goal tracker: @{{GOAL_TRACKER_FILE}}

## Before Exiting

1. Complete all `[mainline]` and `[blocking]` tasks (mark them as completed using TaskUpdate \
with status "completed")
2. `[queued]` tasks may remain only if they are documented as non-blocking follow-up work
3. Commit your changes with a descriptive message
4. Write your finalize summary to: **{{FINALIZE_SUMMARY_FILE}}**

Your summary should include:
- What work was done
- Files modified
- Confirmation that tests still pass (if possible)
- Any notes about manual verification performed
"""

#: prompt-template/claude/methodology-analysis-prompt.md, verbatim but for the one thing that
#: differs: the plugin files its issue against PolyArch/humanize, and so does this.
METHODOLOGY_ANALYSIS = """# Methodology Analysis Phase

The RLCR loop has reached its exit point.

**Exit reason**: {{EXIT_REASON}} - {{EXIT_REASON_DESCRIPTION}}
**Rounds completed**: {{CURRENT_ROUND}} of {{MAX_ITERATIONS}}

Before the loop fully exits, please perform a methodology improvement analysis. This analysis \
helps improve the Humanize development methodology itself -- it is NOT about the project you \
just worked on.

## Instructions

### 1. Spawn an Agent for Sanitized Analysis

Use the Task tool to spawn an analysis agent on the most capable model you have. Give it this \
task:

**Agent prompt**: Read the development records in `{{LOOP_DIR}}`:
- All files matching `round-*-summary.md`
- All files matching `round-*-review-result.md`

Analyze these records from a **pure methodology perspective** and write your findings to \
`{{LOOP_DIR}}/methodology-analysis-report.md`.

**CRITICAL SANITIZATION RULES** - The report MUST NOT contain:
- File paths, directory paths, or module paths
- Function names, variable names, class names, or method names
- Branch names, commit hashes, or git identifiers
- Business domain terms, product names, or feature names
- Code snippets or code fragments of any kind
- Raw error messages or stack traces
- Project-specific URLs or endpoints
- Any information that could identify the specific project

**Focus areas for analysis**:
- Iteration efficiency: Were rounds productive or did they repeat similar work?
- Feedback loop quality: Did reviewer feedback lead to meaningful improvements?
- Stagnation patterns: Were there signs of going in circles?
- Review effectiveness: Did reviews catch real issues or create false positives?
- Plan-to-execution alignment: Did execution follow the plan or drift?
- Round count vs. progress ratio: Was the number of rounds proportional to progress?
- Communication clarity: Were summaries and reviews clear and actionable?

**Output format**: Write a structured report with methodology improvement suggestions. Each \
suggestion should describe a general pattern observed and a concrete improvement to the RLCR \
methodology. If no improvements are found, write a brief note saying the methodology worked \
well for this session.

### 2. Read the Analysis Report

After the agent completes, read `{{LOOP_DIR}}/methodology-analysis-report.md`. ALL subsequent \
user-facing content MUST be derived solely from this report -- do NOT reference raw development \
records directly.

### 3. Handle Results

**If no improvements found**: Briefly inform the user that the methodology analysis found no \
significant improvement suggestions. Then write a completion note to \
`{{LOOP_DIR}}/methodology-analysis-done.md` and exit.

**If improvements found**:

a) Report to the user:
   - Brief summary of the exit reason ({{EXIT_REASON}}: {{EXIT_REASON_DESCRIPTION}})
   - Methodology improvement suggestions from the report

b) Use `AskUserQuestion` to ask if the user would like to help improve Humanize by opening a \
GitHub issue with these suggestions. Emphasize:
   - This is completely voluntary
   - The content is fully sanitized (no project-specific information)
   - It helps improve the methodology for everyone

c) **If user declines**: Thank them, write completion marker to \
`{{LOOP_DIR}}/methodology-analysis-done.md`, and exit.

d) **If user agrees**:
   - Draft a GitHub issue title and body from the analysis report
   - Show the draft via a second `AskUserQuestion` for the user to review and confirm
   - If confirmed: run `gh issue create --repo PolyArch/humanize --title "..." --body "..."`
   - If `gh` is not available, provide the title and body so the user can create the issue \
manually
   - Write completion marker to `{{LOOP_DIR}}/methodology-analysis-done.md` and exit

### 4. Completion Marker

You MUST write meaningful content to `{{LOOP_DIR}}/methodology-analysis-done.md` before \
exiting. This file signals that the analysis phase is complete. A brief summary of what was \
done (e.g., "Analysis complete, no suggestions" or "Analysis complete, issue filed") is \
sufficient.
"""
