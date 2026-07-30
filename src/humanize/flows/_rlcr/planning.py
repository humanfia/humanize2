"""What either agent is told while the idea is opened and the plan is written.

`commands/gen-idea.md` and `commands/gen-plan.md` in PolyArch/humanize, and the two subagents
they call, as the prompts their models are given: a slash command's body is what Claude reads,
and an agent's body is what its model reads, so the port of a command is its body.

Beside :mod:`prompts` rather than in it because the loop's own words are already two thousand
lines, which is the length the loop itself refuses to let a round leave behind.
"""

from __future__ import annotations

__all__ = [
    "GEN_IDEA",
    "GEN_IDEA_TEMPLATE",
    "GEN_PLAN_ANALYSIS",
    "GEN_PLAN_CANDIDATE",
    "GEN_PLAN_CONVERGENCE",
    "GEN_PLAN_FINAL",
    "GEN_PLAN_REVISION",
    "GEN_PLAN_TEMPLATE",
    "GEN_PLAN_TRANSLATE",
    "RELEVANCE",
]


# ======================================================================================
# gen-idea -- commands/gen-idea.md, as the instructions Claude is given
# ======================================================================================

#: prompt-template/idea/gen-idea-template.md, verbatim.
GEN_IDEA_TEMPLATE = """# <TITLE>

## Original Idea

<ORIGINAL_IDEA>

## Primary Direction: <PRIMARY_NAME>

### Rationale

<PRIMARY_RATIONALE>

### Approach Summary

<PRIMARY_APPROACH_SUMMARY>

### Objective Evidence

<PRIMARY_OBJECTIVE_EVIDENCE>

### Known Risks

<PRIMARY_KNOWN_RISKS>

## Alternative Directions Considered

<ALTERNATIVES>

## Synthesis Notes

<SYNTHESIS_NOTES>
"""

#: commands/gen-idea.md, phases 2 to 4. Phase 0 and phase 1 are the argument parsing and the
#: IO validation `validate-gen-idea-io.sh` does, which the flow does in Python before this is
#: sent -- so what would have been read out of that script's stdout is filled in here.
GEN_IDEA = """# Generate Idea Draft from Loose Input

Read and execute below with ultrathink.

## Hard Constraint: Draft-Only Output

This command MUST NOT implement features, modify source code, or create commits while \
producing the draft. Permitted writes are limited to the single output draft file produced in \
Phase 4. All exploration subagents run read-only.

This command transforms a loose idea into a repo-grounded draft suitable as input to plan \
generation. It applies directed-diversity exploration: a lead picks N orthogonal directions, N \
parallel `Explore` subagents develop each, the lead synthesizes a draft with one primary \
direction plus N-1 alternatives. Each direction carries objective evidence from the repo.

## Workflow Overview

> **Sequential Execution Constraint**: All phases MUST execute strictly in order. Each phase \
fully completes before the next.

1. Direction Generation
2. Parallel Exploration
3. Synthesis and Write

Already settled for you, so do not re-derive them:
- `IDEA_BODY`: the idea, which is quoted in full at the end of this message.
- `N`: {{N}} directions.
- `OUTPUT_FILE`: {{OUTPUT_FILE}}

---

## Phase 2: Direction Generation

Generate exactly `N` orthogonal directions for exploring the idea.

### Context to Gather

Before generating directions, read (paths relative to the project root):
- `README.md` at the project root.
- `CLAUDE.md` at the project root (if it exists).
- `.claude/CLAUDE.md` (if it exists).
- Top-level directory listing via `Glob` with pattern `*` (one level, no recursion).

This context grounds the directions in the actual repo rather than generic brainstorming.

### Generation Rules

Produce exactly `N` direction entries. Each entry has:
- `name`: a 2-5 word short label.
- `rationale`: a single sentence explaining why this angle is distinct from the other \
directions.

Hard constraint: **orthogonality**. Two near-duplicate directions defeat the \
directed-diversity premise. Before returning:
- If two directions feel like dupes, replace one with a genuinely different angle.
- If a direction collapses to "just do X better" with no angle distinction, replace it.
- Do not emit directions that merely restate the idea in different words.

### Retry and Degradation

- If the first pass returns fewer than `N` entries, regenerate once with an explicit "you MUST \
produce `N` orthogonal directions" instruction.
- If the second pass still returns fewer than `N` but at least 2, proceed with the reduced \
count and say so: `Warning: direction generation returned <count> of <N> requested \
directions; proceeding with reduced count.`
- If fewer than 2 directions are produced, stop with error: `direction generation degraded; \
retry.`

---

## Phase 3: Parallel Exploration

Dispatch all directions in a **single Task-tool message** containing one Task invocation per \
direction. This is the parallel-swarm step.

### Subagent Invocation

For each direction, launch one `Explore` subagent. Each invocation prompt MUST include:

1. A verbatim copy of the idea body.
2. The assigned direction (name + rationale).
3. The following instruction block (reproduce verbatim in the subagent prompt):

> Explore this direction within the current repo. Gather OBJECTIVE EVIDENCE:
> - Specific repo paths with existing patterns worth extending.
> - Prior art or precedent in the codebase or adjacent tooling.
> - Measurable considerations (approximate complexity, LOC surface, performance implications) \
where discoverable from reading the code.
>
> Read-only. Do not write any files.
>
> If no concrete evidence exists for this direction, report the literal string `exploratory, \
no concrete precedent` once in OBJECTIVE_EVIDENCE and stop exploring further. Fabrication of \
references is forbidden.
>
> Return a structured proposal with exactly these fields:
> - `APPROACH_SUMMARY`: concrete design description (what to build, core mechanism, affected \
components).
> - `OBJECTIVE_EVIDENCE`: bullet list of repo paths, prior art, or the `exploratory, no \
concrete precedent` sentinel.
> - `KNOWN_RISKS`: short bullet list.
> - `CONFIDENCE`: one of `high`, `medium`, `low`.

### Collection and Degradation

Collect all subagent responses. For each response:
- Parse the four required fields. If a field is missing, mark that proposal as degraded and \
drop it.
- If fewer than 2 proposals survive, stop with error: `exploration phase degraded; retry.`
- Otherwise continue with the surviving proposals.

Associate each surviving proposal with its originating direction. When numbering alternatives \
in Phase 4 after any drops, renumber survivors sequentially as Alt-1..Alt-K. Do not preserve \
gaps from dropped proposals.

---

## Phase 4: Synthesis and Write

### Step 4.1: Pick the Primary Direction

Review all surviving proposals. Choose the strongest as the primary based on:
1. Evidence density -- more concrete repo references outranks fewer.
2. Fit with existing repo patterns -- extending patterns outranks introducing unfamiliar \
paradigms.
3. Implementation surface area -- prefer smaller surface where quality is otherwise comparable.
4. Declared `CONFIDENCE` -- `high` > `medium` > `low` as tiebreaker.

Record the chosen direction as `PRIMARY`; the remaining surviving directions become the \
Alt-1..Alt-K list, numbered sequentially in their original direction order with no gaps for \
any dropped proposals.

### Step 4.2: Infer Title

Generate a 4-10 word Title Case title that captures the primary direction, not the original \
input phrasing verbatim. Example: idea `add undo/redo` with primary direction `command-pattern \
history` yields title `Command-Pattern Undo Stack For The Editor`.

### Step 4.3: Populate the Template

The template is:

```markdown
{{TEMPLATE}}
```

Produce the finalized draft content in memory by replacing placeholders:
- `<TITLE>` -- the inferred title.
- `<ORIGINAL_IDEA>` -- byte-identical value of the idea below. Preserve line breaks, trailing \
newline, and all formatting. Do NOT paraphrase or re-indent.
- `<PRIMARY_NAME>` -- primary direction's short name.
- `<PRIMARY_RATIONALE>` -- primary direction's rationale (from Phase 2).
- `<PRIMARY_APPROACH_SUMMARY>` -- primary proposal's `APPROACH_SUMMARY`.
- `<PRIMARY_OBJECTIVE_EVIDENCE>` -- primary proposal's `OBJECTIVE_EVIDENCE`, rendered as a \
bullet list. If the subagent returned only the literal sentinel `exploratory, no concrete \
precedent`, render it as a single bullet: `- exploratory, no concrete precedent`.
- `<PRIMARY_KNOWN_RISKS>` -- primary proposal's `KNOWN_RISKS`, rendered as a bullet list.
- `<ALTERNATIVES>` -- for each non-primary survivor at its Alt index `i` (1-based, sequential \
per Step 4.1), emit:

  ```markdown
  ### Alt-<i>: <name>
  - Gist: <one-paragraph summary derived from APPROACH_SUMMARY>
  - Objective Evidence:
    - <bullet from OBJECTIVE_EVIDENCE>
    - ...
  - Why not primary: <one sentence stating the tradeoff vs PRIMARY>
  ```

  Separate consecutive Alt entries with a single blank line.

- `<SYNTHESIS_NOTES>` -- one paragraph describing which elements from the alternatives could \
fold into the primary if the user chose a different direction. This is the lead's own \
synthesis note, not a subagent output.

### Step 4.4: Write the Draft File

Write the finalized content to `{{OUTPUT_FILE}}` using the `Write` tool. Single write; no \
progressive edits.

### Step 4.5: Report

Report:
- Path written.
- Primary direction name.
- Requested `N` and the actual direction count (note if reduced due to degradation).

---

## Error Handling

- Phase 2 degradation follows the retry-once + >=2 minimum rule stated above.
- Phase 3 degradation follows the drop-and-continue + >=2 minimum rule stated above.
- Never fabricate repo references or prior art. The `exploratory, no concrete precedent` \
sentinel from subagents is preserved verbatim in the draft.
- If any phase stops with an error, do not write a partial output file.

---

The idea:

{{IDEA_BODY}}
"""


# ======================================================================================
# gen-plan -- commands/gen-plan.md, as the phases each agent is given
# ======================================================================================

#: prompt-template/plan/gen-plan-template.md, verbatim, less its own note about the output
#: file convention -- which is about the plugin's config loading rather than about the plan.
GEN_PLAN_TEMPLATE = """# <Plan Title>

## Goal Description
<Clear, direct description of what needs to be accomplished>

## Acceptance Criteria

Following TDD philosophy, each criterion includes positive and negative tests for \
deterministic verification.

- AC-1: <First criterion>
  - Positive Tests (expected to PASS):
    - <Test case that should succeed when criterion is met>
    - <Another success case>
  - Negative Tests (expected to FAIL):
    - <Test case that should fail/be rejected when working correctly>
    - <Another failure/rejection case>
  - AC-1.1: <Sub-criterion if needed>
    - Positive: <...>
    - Negative: <...>
- AC-2: <Second criterion>
  - Positive Tests: <...>
  - Negative Tests: <...>
...

## Path Boundaries

Path boundaries define the acceptable range of implementation quality and choices.

### Upper Bound (Maximum Acceptable Scope)
<Affirmative description of the most comprehensive acceptable implementation>
<This represents completing the goal without over-engineering>
Example: "The implementation includes X, Y, and Z features with full test coverage"

### Lower Bound (Minimum Acceptable Scope)
<Affirmative description of the minimum viable implementation>
<This represents the least effort that still satisfies all acceptance criteria>
Example: "The implementation includes core feature X with basic validation"

### Allowed Choices
<Options that are acceptable for implementation decisions>
- Can use: <technologies, approaches, patterns that are allowed>
- Cannot use: <technologies, approaches, patterns that are prohibited>

> **Note on Deterministic Designs**: If the draft specifies a highly deterministic design with \
no choices (e.g., "must use JSON format", "must use algorithm X"), then the path boundaries \
should reflect this narrow constraint. In such cases, upper and lower bounds may converge to \
the same point, and "Allowed Choices" should explicitly state that the choice is fixed per the \
draft specification.

## Feasibility Hints and Suggestions

> **Note**: This section is for reference and understanding only. These are conceptual \
suggestions, not prescriptive requirements.

### Conceptual Approach
<Text description, pseudocode, or diagrams showing ONE possible implementation path>

### Relevant References
<Code paths and concepts that might be useful>
- <path/to/relevant/component> - <brief description>

## Dependencies and Sequence

### Milestones
1. <Milestone 1>: <Description>
   - Phase A: <...>
   - Phase B: <...>
2. <Milestone 2>: <Description>
   - Step 1: <...>
   - Step 2: <...>

<Describe relative dependencies between components, not time estimates>

## Task Breakdown

Each task must include exactly one routing tag:
- `coding`: implemented by the builder
- `analyze`: executed via the reviewer

| Task ID | Description | Target AC | Tag (`coding`/`analyze`) | Depends On |
|---------|-------------|-----------|----------------------------|------------|
| task1 | <...> | AC-1 | coding | - |
| task2 | <...> | AC-2 | analyze | task1 |

## Claude-Codex Deliberation

### Agreements
- <Point both sides agree on>

### Resolved Disagreements
- <Topic>: builder vs reviewer summary, chosen resolution, and rationale

### Convergence Status
- Final Status: `converged` or `partially_converged`

## Pending User Decisions

- DEC-1: <Decision topic>
  - Claude Position: <...>
  - Codex Position: <...>
  - Tradeoff Summary: <...>
  - Decision Status: `PENDING` or `<User's final decision>`

## Implementation Notes

### Code Style Requirements
- Implementation code and comments must NOT contain plan-specific terminology such as "AC-", \
"Milestone", "Step", "Phase", or similar workflow markers
- These terms are for plan documentation only, not for the resulting codebase
- Use descriptive, domain-appropriate naming in code instead
"""

#: agents/draft-relevance-checker.md, as the prompt its model is given. The plugin runs it as
#: a haiku subagent of Claude's; here it is one turn of the reviewer, which is the agent that
#: reads this repository without having watched the draft be written.
RELEVANCE = """You are a specialized agent that determines whether a user's draft document is \
relevant to the current repository.

## Your Task

1. **Quickly explore the repository** to understand what it does:
   - Check README.md, CLAUDE.md, or other documentation files
   - Look at the directory structure
   - Identify the main technologies, languages, and purpose

2. **Analyze the draft content** to determine if it relates to this repository:
   - Does the draft mention concepts, technologies, or components in this repo?
   - Is the draft about modifying, extending, or using this codebase?
   - Is the draft about learning from or understanding this codebase?
   - Does the draft reference file paths, functions, or features that exist here?

3. **Return a clear verdict**:
   - If relevant: Output `RELEVANT: <brief explanation>`
   - If not relevant: Output `NOT_RELEVANT: <brief explanation>`

## Important Notes

- Be lenient in your judgment - if the draft could reasonably be connected to this repository, \
mark it as relevant
- The draft may be informal, written in any language, or contain rough ideas - that's okay
- Focus on semantic relevance, not syntactic similarity
- If in doubt, lean toward marking as relevant

Do not spend too much time on this check. As long as the draft is not completely unrelated to \
the current project - not like the difference between ship design and cake recipes - it passes.

The draft is at @{{INPUT_FILE}}. Its content:

{{DRAFT_CONTENT}}
"""

#: commands/gen-plan.md phase 3, which the plugin sends through `ask-codex.sh`.
GEN_PLAN_ANALYSIS = """A coding agent is about to write an implementation plan for this \
repository from the draft below, and you are the first planning pass over it -- before any \
plan exists.

Read this repository for context: what it is for, how it is built, how it is tested, and the \
files the draft would touch. Then read the draft and critique its assumptions, identify \
missing requirements, and propose stronger plan directions.

Your output MUST follow this format, under these headings and no others:

- `CORE_RISKS:` highest-risk assumptions and potential failure modes
- `MISSING_REQUIREMENTS:` likely omitted requirements or edge cases
- `TECHNICAL_GAPS:` feasibility or architecture gaps
- `ALTERNATIVE_DIRECTIONS:` viable alternatives with tradeoffs
- `QUESTIONS_FOR_USER:` questions that need explicit human decisions
- `CANDIDATE_CRITERIA:` candidate acceptance criteria suggestions

You are not writing the plan and you are not choosing the direction again.

The draft is at @{{INPUT_FILE}}. Its content:

{{DRAFT_CONTENT}}
"""

#: commands/gen-plan.md phase 4, given to the builder with the reviewer's analysis.
GEN_PLAN_CANDIDATE = """Read and execute below with ultrathink.

## Hard Constraint: No Coding During Plan Generation

This MUST ONLY generate a plan document. It MUST NOT implement tasks, modify repository source \
code, or make commits/PRs while producing the plan. The only file you may write is \
{{OUTPUT_FILE}}.

The plan file has been created for you at {{OUTPUT_FILE}}: it holds the plan template followed \
by the original design draft, between `--- Original Design Draft Start ---` and `--- Original \
Design Draft End ---`. Write the plan into it, keeping the draft where it is.

## Your Task: Candidate Plan v1

Use the draft plus the analysis below -- which comes from a reviewer that read this repository \
without seeing your reasoning -- to produce an initial candidate plan and issue map.

Deeply analyze the draft for potential issues. Use Explore agents to investigate the codebase.

Alongside candidate plan v1, prepare a concise implementation summary covering scope, \
boundaries, dependencies, and known risks.

### Analysis Dimensions

1. **Clarity**: Is the draft's intent and goals clearly expressed?
   - Are objectives well-defined?
   - Is the scope clear?
   - Are terms and concepts unambiguous?

2. **Consistency**: Does the draft contradict itself?
   - Are requirements internally consistent?
   - Do different sections align with each other?

3. **Completeness**: Are there missing considerations?
   - Use Explore agents to investigate parts of the codebase the draft might affect
   - Identify dependencies, side effects, or related components not mentioned
   - Check if the draft overlooks important edge cases

4. **Functionality**: Does the design have fundamental flaws?
   - Would the proposed approach actually work?
   - Are there technical limitations not addressed?
   - Could the design negatively impact existing functionality?

### Exploration Strategy

Use the Task tool with `subagent_type: "Explore"` to investigate:
- Components mentioned in the draft
- Related files and directories
- Existing patterns and conventions
- Dependencies and integrations

> **Critical**: The draft document contains the most valuable human input. NEVER discard or \
override any original draft content. All clarifications are incremental additions that \
supplement the draft, not replacements.

Answer with the path you wrote and nothing else: the plan will be read from the file.

The analysis:

{{ANALYSIS}}
"""

#: commands/gen-plan.md phase 5, the second Codex pass, one round of it.
GEN_PLAN_CONVERGENCE = """A coding agent has written the candidate plan at @{{OUTPUT_FILE}} \
for this repository. Review it for reasonability against the repository itself, rather than \
against how a plan usually looks.

Your output MUST follow this format, under these headings and no others:

- `AGREE:` points accepted as reasonable
- `DISAGREE:` points considered unreasonable and why
- `REQUIRED_CHANGES:` must-fix items before convergence
- `OPTIONAL_IMPROVEMENTS:` non-blocking improvements
- `UNRESOLVED:` opposite opinions needing user decisions

If nothing is required and nothing under DISAGREE would change the work, answer with the \
single word COMPLETE instead of the headings, and mean it: a plan is not improved by being \
asked for one more thing.

What was asked for:

{{TASK}}

{{PRIOR}}"""

#: commands/gen-plan.md phase 5 step 2, the builder's revision of its own plan.
GEN_PLAN_REVISION = """Revise the plan at {{OUTPUT_FILE}} against the review below, and answer \
with the path you wrote and nothing else.

Address everything under `REQUIRED_CHANGES` or argue with it in the plan itself, saying why. \
What is under `OPTIONAL_IMPROVEMENTS` is yours to take or leave. Document accepted and \
rejected suggestions with rationale in the `Claude-Codex Deliberation` section, and update the \
per-round convergence matrix: topic, your position, the reviewer's position, resolution status \
(`resolved`, `needs_user_decision`, `deferred`), and the round-to-round delta.

Keep the plan the shape it already has, keep the original draft where it is, and do not start \
the work.

Review:

{{REVIEW}}
"""

#: commands/gen-plan.md phases 6 and 7 -- the consolidation of what only a person can settle,
#: and the final plan.
GEN_PLAN_FINAL = """Deeply think and finish the plan at {{OUTPUT_FILE}} now.

## Consolidate Pending User Decisions

Before anything else, consolidate all user-facing questions from the planning so far into the \
plan's `## Pending User Decisions` section:

1. Extract `QUESTIONS_FOR_USER` items from the first analysis
2. Extract items with status `needs_user_decision` from the final convergence matrix -- the \
last round's state, not intermediate rounds
3. Deduplicate: if the same topic appears in both sources, merge into one entry
4. For each collected item, check if it was substantively resolved during the plan refinement \
(you addressed it and the reviewer agreed in a subsequent round). Remove only items with clear \
evidence of resolution.
5. Write all remaining unresolved items into `## Pending User Decisions`. Use `DEC-N` \
identifiers. Set `Decision Status` to `PENDING`.
   - For disagreements: fill `Claude Position`, `Codex Position`, and `Tradeoff Summary`
   - For open questions (no opposing positions): set `Claude Position` to your tentative answer \
(if any), `Codex Position` to `N/A - open question`, and `Tradeoff Summary` to the question's \
context

{{DECISIONS}}
## Final Plan

The plan must follow the template it was created from, with every section filled in. In \
particular:

- **Acceptance Criteria**: each AC carries positive tests (expected to PASS) and negative \
tests (expected to FAIL). A number the draft stated is a requirement to be met, not a \
direction to move in, unless it said otherwise.
- **Path Boundaries**: the most that would be worth doing, the least that would still be the \
thing, and what is allowed either way.
- **Task Breakdown**: every task carries exactly one routing tag, `coding` or `analyze`, and \
names the AC it serves.
- **Claude-Codex Deliberation**: what was agreed, what was disagreed and how it resolved, and \
`Convergence Status` set to `{{CONVERGENCE_STATUS}}`.

Keep the original design draft at the end of the file, between its own markers, exactly as it \
is.

Answer with the path you wrote and nothing else: the plan will be read from the file.
"""

#: commands/gen-plan.md phase 8, the translated variant.
GEN_PLAN_TRANSLATE = """Write a full translation of {{OUTPUT_FILE}} into {{LANGUAGE}}, to \
{{VARIANT_FILE}}.

All identifiers (`AC-*`, task IDs, file paths, API names, command flags) remain unchanged, as \
they are language-neutral. Change nothing about the plan itself.

Answer with the path you wrote and nothing else.
"""
