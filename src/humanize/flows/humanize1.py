"""RLCR (humanize 1) -- PolyArch/humanize as one unattended run, set up before it starts.

    hmz exec -f humanize1 \
        -a claude/claude-opus-4-8:max -a claude/claude-opus-4-8:max \
        -a codex/gpt-5.6-sol:max -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max \
        "add undo/redo to the editor"

which is the drafter, the planner and the analyst that reads it, and the builder and the
reviewer that reads it, in that order, since that is the order the flow takes them. Add
`-c setup.yaml` to run it set up rather than as it comes, and `hmz -f humanize1 -c setup.yaml`
opens the interface on the same setup.

Three phases, which are the plugin's three commands: `gen-idea` opens a loose idea into a
repo-grounded draft, `gen-plan` turns that draft into a plan both sides have converged on, and
`start-rlcr-loop` builds the plan under review until nothing is left to say. Each of them can
be turned off, and everything either of them can be told is on `/config` -- one field per flag
the plugin takes, under the name the plugin gives it.

Run in a git repository: the work is anchored to the commit the plan was fixed in, and every
review reads what came after it.

Each phase is set up on its own: `/agents` asks what the drafter runs, what the planner and
the analyst that reads it run, and what the builder and the reviewer run. What passes between
the phases is a file, as it is in the plugin -- the draft, then the plan -- so a run may open
an idea on one model and build it on another.

The side that writes remembers and the side that reads does not. The planner holds one session
for the whole of the planning and the builder holds one for the whole of the loop; every review
is a session that has just started, reads the repository itself, and is told nothing about how
the work was arrived at.

The loop itself is a hook. The plugin blocks Claude's exit and puts the round to Codex there;
so does this -- a `Stop` hook on the builder, which is the same sentence: a round ends when the
builder believes the whole plan is done and tries to stop, and what the reviewer says is what
it hears instead of stopping. The plugin's tool validators are hooks too, on the one moment a
refusal reaches the agent, so the plan stays fixed and the state file stays the loop's. Every
gate its stop hook runs is run here, in the order it runs them, in its own words -- and what it
writes is written where it writes it, so `humanize monitor rlcr` reads a run of this.

Four things are the plugin's mechanism rather than its behaviour, and are done another way:

- `codex review --base <ref>` takes no prompt and is a Codex feature. Here the reviewer is
  whichever agent was chosen, so the code review is asked for -- in a prompt that asks for
  exactly the `[P0-9]` output the loop then reads the same way.
- `--codex-timeout` cannot cut a turn short from here: a review that ran over is treated as a
  review that failed, which is the state the plugin's own timeout leaves the round in.
- A task the plan tags `analyze` is `/humanize:ask-codex` there, which is a shell script the
  builder runs. Here the builder has no way to reach the reviewer mid-round, so it is told to
  put the question in its round summary, where the reviewer answers it.
- Its `PostToolUse` hook patches the session id into `state.md` so a later hook can tell whose
  loop it is. This flow is holding the loop, so there is nothing to look up.

`ask-codex`, `ask-gemini`, `refine-plan` and `cancel-rlcr-loop` are commands of their own
rather than phases of this one, and are not here: stopping the flow is what cancels it.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, NamedTuple

from pydantic import BaseModel, Field, model_validator

from humanize.agents import AgentBase, HumanAgent, Moment, SessionBase
from humanize.flows._rlcr import guards, loop, planning, prompts
from humanize.flows._rlcr.loop import Loop, State, git, spoken
from humanize.flows._rlcr.prompts import render

if TYPE_CHECKING:
    from pydantic.config import JsonDict


class Agents(NamedTuple):
    """One agent per side of each phase, and the person at the prompt.

    The plugin's three commands are three commands: `gen-idea` is one agent exploring, and
    `gen-plan` and `start-rlcr-loop` are each an agent writing against an agent reading. What
    passes between them is a file -- the draft, then the plan -- so each phase is set up on
    its own, and a run may open an idea on one model and build it on another.

    The builder has to run `PermissionRequest`: the plugin's validators are what keep the plan
    fixed and the loop's state out of the builder's hands, and a hook that cannot say no to a
    tool is not one of them. The plugin is a Claude Code plugin for the same reason.
    """

    drafter: AgentBase
    planner: AgentBase
    analyst: AgentBase
    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
    reviewer: AgentBase
    human: HumanAgent


#: Every language the plugin will write a translated plan in, by name and by ISO code.
LANGUAGES = {
    "chinese": "zh",
    "korean": "ko",
    "japanese": "ja",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt",
    "russian": "ru",
    "arabic": "ar",
}

#: How many rounds `gen-plan` gives its convergence loop, which is the plugin's own maximum.
CONVERGING = 3

#: Where a draft goes when nobody said, as `validate-gen-idea-io.sh` resolves it.
IDEAS = ".humanize/ideas"

#: What the plan is called when nobody said, which is what the plugin's own examples use.
PLAN = "docs/plan.md"

#: Which part of the setup sheet each setting is under, which is one part per command: a flag
#: only means anything against the phase it is a flag of, and twenty-three of them in one list
#: is a list nobody reads.
_IDEA_SECTION: JsonDict = {"section": "gen-idea  ·  open the idea into a draft"}
_PLAN_SECTION: JsonDict = {"section": "gen-plan  ·  turn the draft into a plan"}
_LOOP_SECTION: JsonDict = {"section": "rlcr  ·  build the plan under review"}


class Config(BaseModel):
    """Every flag PolyArch/humanize takes, under the name the plugin gives it.

    Three sections, one per command, which is how the sheet that asks about them is drawn:
    each field says which one it is under. What the plugin reads from `.humanize/config.json`
    is here too, since a config file and a flag are the same setting arrived at two ways --
    and this is the one way.

    What the plugin says with a model name is said here by choosing an agent: `codex_model`,
    `codex_effort`, `bitlesson_model` and `provider_mode` are all "which model does this
    half", which is `/agents` -- and this flow has five halves to answer for rather than one.
    `--allow-empty-bitlesson-none` and `--require-bitlesson-entry-for-none` are one switch
    written twice, and so are `--input`, `--output` and `--plan-file`: the draft and the plan
    are each one path, named once here and handed from phase to phase.
    """

    model_config = {"frozen": True}

    # -- gen-idea --------------------------------------------------------------------
    gen_idea: bool = Field(
        default=True,
        description="open the idea into a repo-grounded draft",
        json_schema_extra=_IDEA_SECTION,
    )
    n: int = Field(
        default=6,
        ge=2,
        le=10,
        description="--n: how many directions explore the idea",
        json_schema_extra=_IDEA_SECTION,
    )
    idea_output: str = Field(
        default="",
        description="--output: where the draft goes, blank for .humanize/ideas",
        json_schema_extra=_IDEA_SECTION,
    )

    # -- gen-plan --------------------------------------------------------------------
    gen_plan: bool = Field(
        default=True,
        description="turn the draft into a plan, against review",
        json_schema_extra=_PLAN_SECTION,
    )
    plan_output: str = Field(
        default="",
        description="--output: where the plan goes, blank for docs/plan.md",
        json_schema_extra=_PLAN_SECTION,
    )
    gen_plan_mode: Literal["discussion", "direct"] = Field(
        default="discussion",
        description="--discussion or --direct: converge, or write it once",
        json_schema_extra=_PLAN_SECTION,
    )
    auto_start_rlcr_if_converged: bool = Field(
        default=False,
        description="--auto-start-rlcr-if-converged: no review gate once converged",
        json_schema_extra=_PLAN_SECTION,
    )
    alternative_plan_language: str = Field(
        default="",
        description="a translated plan too: zh, ko, ja, es, fr, de, pt, ru, ar",
        json_schema_extra=_PLAN_SECTION,
    )

    # -- start-rlcr-loop -------------------------------------------------------------
    rlcr: bool = Field(
        default=True,
        description="build the plan under review",
        json_schema_extra=_LOOP_SECTION,
    )
    plan_file: str = Field(
        default="",
        description="--plan-file: the plan to build, blank for the one just made",
        json_schema_extra=_LOOP_SECTION,
    )
    max: int = Field(
        default=42,
        ge=0,
        description="--max: rounds before the loop stops",
        json_schema_extra=_LOOP_SECTION,
    )
    codex_timeout: int = Field(
        default=5400,
        ge=0,
        description="--codex-timeout: seconds one review may take",
        json_schema_extra=_LOOP_SECTION,
    )
    full_review_round: int = Field(
        default=5,
        ge=2,
        description="--full-review-round: rounds between alignment checks",
        json_schema_extra=_LOOP_SECTION,
    )
    base_branch: str = Field(
        default="",
        description="--base-branch: what the code review reads against",
        json_schema_extra=_LOOP_SECTION,
    )
    track_plan_file: bool = Field(
        default=False,
        description="--track-plan-file: the plan is in git and stays clean",
        json_schema_extra=_LOOP_SECTION,
    )
    push_every_round: bool = Field(
        default=False,
        description="--push-every-round: push after every round",
        json_schema_extra=_LOOP_SECTION,
    )
    skip_impl: bool = Field(
        default=False,
        description="--skip-impl: no building, straight to the code review",
        json_schema_extra=_LOOP_SECTION,
    )
    claude_answer_codex: bool = Field(
        default=False,
        description="--claude-answer-codex: the builder answers open questions",
        json_schema_extra=_LOOP_SECTION,
    )
    agent_teams: bool = Field(
        default=False,
        description="--agent-teams: the builder leads a team instead of coding",
        json_schema_extra=_LOOP_SECTION,
    )
    skip_quiz: bool = Field(
        default=False,
        description="--skip-quiz: do not check you have read the plan",
        json_schema_extra=_LOOP_SECTION,
    )
    yolo: bool = Field(
        default=False,
        description="--yolo: --skip-quiz and --claude-answer-codex together",
        json_schema_extra=_LOOP_SECTION,
    )
    privacy: bool = Field(
        default=False,
        description="--privacy: no methodology analysis when the loop exits",
        json_schema_extra=_LOOP_SECTION,
    )
    require_bitlesson_entry_for_none: bool = Field(
        default=False,
        description="--require-bitlesson-entry-for-none: a round records a lesson",
        json_schema_extra=_LOOP_SECTION,
    )

    @model_validator(mode="after")
    def _settles(self) -> Config:
        """Turns the aliases into what they alias, and refuses what cannot be run.

        Returns:
          The config, with `--yolo` spelled out as the two flags it is a name for.

        Raises:
          ValueError: If no phase is on, or if the phases that are on cannot hand to each
            other -- an idea opened for a loop that will build somebody else's plan is the
            drafting thrown away, and is a run nobody meant to ask for.
        """
        if self.yolo:
            object.__setattr__(self, "skip_quiz", True)
            object.__setattr__(self, "claude_answer_codex", True)
        if not (self.gen_idea or self.gen_plan or self.rlcr):
            raise ValueError("nothing to run: turn on gen_idea, gen_plan or rlcr")
        if self.gen_idea and self.rlcr and not self.gen_plan:
            raise ValueError(
                "gen_idea with rlcr and no gen_plan: the draft this would write is not a "
                "plan, so the loop would build whatever plan_file already says instead -- "
                "turn gen_plan on, or turn one of the other two off"
            )
        if self.skip_impl and not self.rlcr:
            raise ValueError("skip_impl is about the loop: turn rlcr on, or it off")
        if self.gen_plan and not self.gen_idea and not self.idea_output:
            raise ValueError(
                "gen_plan without gen_idea needs a draft to plan from: set idea_output to "
                "the draft you already have"
            )
        if (
            self.rlcr
            and not self.gen_plan
            and not self.plan_file
            and not self.skip_impl
        ):
            raise ValueError(
                "rlcr without gen_plan needs a plan to build: set plan_file, or turn on "
                "skip_impl, which reviews the branch without one"
            )
        return self


def _language(said: str) -> tuple[str, str]:
    """The language a translated plan would be written in, and its code.

    Args:
      said: What the config asked for, by name or by code, in any case.

    Returns:
      The language and its code, or two empty strings -- for nothing asked for, for English,
      and for anything the plugin's table does not hold, which it warns about and disables.
    """
    wanted = said.strip().lower()
    if not wanted or wanted in ("english", "en"):
        return "", ""
    for named, code in LANGUAGES.items():
        if wanted in (named, code):
            return named.capitalize(), code
    print(
        f'Warning: unsupported alternative_plan_language "{said}". Supported values: '
        + ", ".join(f"{one.capitalize()} ({code})" for one, code in LANGUAGES.items())
        + ". Translation variant will not be generated."
    )
    return "", ""


def _slug(task: str) -> str:
    """A short name for an idea, as `validate-gen-idea-io.sh` makes one.

    Args:
      task: The idea.

    Returns:
      Its first few words, lowercased, joined with dashes.
    """
    words = re.findall(r"[a-z0-9]+", task.lower())[:6]
    return "-".join(words) or "idea"


def _stamp() -> str:
    """Now, as the plugin stamps a file name."""
    import datetime

    return datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _head(root: Path) -> str:
    """The branch the work is on, or "" outside a git repository.

    Args:
      root: The workspace.

    Returns:
      The branch.
    """
    status, branch = git("rev-parse", "--abbrev-ref", "HEAD", at=root)
    return "" if status else branch


def _base(root: Path, asked: str) -> str:
    """What the code review reads the work against, as the setup script resolves it.

    Args:
      root: The workspace.
      asked: What the config said, or "" to work it out.

    Returns:
      The branch: what was asked for, else the remote's default, else `main`, else `master`,
      and "" where this repository has none of them -- which is a run without a code review.
    """
    if asked:
        return asked
    status, said = git("symbolic-ref", "refs/remotes/origin/HEAD", at=root)
    if not status and said:
        remote = said.rsplit("/", 1)[-1]
        if not git("show-ref", "--verify", "--quiet", f"refs/heads/{remote}", at=root)[
            0
        ]:
            return remote
    for named in ("main", "master"):
        if not git("show-ref", "--verify", "--quiet", f"refs/heads/{named}", at=root)[
            0
        ]:
            return named
    return ""


def _section(held: str, *headings: str) -> str:
    """One section of a plan, by any of the headings it might be under.

    Args:
      held: The plan.
      headings: The words the heading might start with, lowercased.

    Returns:
      What is under the first one that is there, or "" if none of them is.
    """
    lines = held.splitlines()
    for at, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        named = line[3:].strip().lower()
        if not any(named.startswith(one) for one in headings):
            continue
        found: list[str] = []
        for under in lines[at + 1 :]:
            if under.startswith("## "):
                break
            found.append(under)
        return "\n".join(found).strip()
    return ""


def _quiz(said: str) -> dict[str, str]:
    """The quiz an agent wrote, read back field by field.

    Args:
      said: What it answered.

    Returns:
      Every field it stated, or nothing at all where one is missing or an answer is not one
      of the four letters -- which the plugin warns about and carries on from.
    """
    found = {
        name: value.strip()
        for name, value in re.findall(
            r"^(QUESTION_[12]|OPTION_[12][A-D]|ANSWER_[12]|PLAN_SUMMARY):\s*(.*)$",
            said,
            re.MULTILINE,
        )
    }
    wanted = ["QUESTION_1", "QUESTION_2", "ANSWER_1", "ANSWER_2", "PLAN_SUMMARY"] + [
        f"OPTION_{n}{letter}" for n in "12" for letter in "ABCD"
    ]
    if any(name not in found for name in wanted):
        return {}
    if any(found[f"ANSWER_{n}"].upper() not in ("A", "B", "C", "D") for n in "12"):
        return {}
    return found


def _asked(human: HumanAgent, question: str, options: list[str]) -> str:
    """Puts one multiple-choice question to whoever is at the prompt.

    Args:
      human: The person, driven as an agent.
      question: What to ask.
      options: What they may answer, in order.

    Returns:
      The letter they picked, uppercased, or "" where nobody was there to pick one -- which
      is a command line, where the quiz is advisory and the run carries on.
    """
    listed = "\n".join(
        f"  {letter}. {one}" for letter, one in zip("ABCD", options, strict=False)
    )
    said = human(f"{question}\n{listed}\n\nAnswer with A, B, C or D.")
    return said.strip()[:1].upper() if said else ""


def _idea(drafting: SessionBase, task: str, config: Config, root: Path) -> Path:
    """`gen-idea`: opens the idea from N directions at once and closes it to one.

    Args:
      drafting: The session the drafter opens the idea in.
      task: The idea, as it was given.
      config: How this run was set up.
      root: The workspace.

    Returns:
      The draft the builder wrote.

    Raises:
      ValueError: If the draft cannot be written where it was asked for, which is what the
        plugin's IO validation exits on before anything runs.
    """
    where = Path(config.idea_output or f"{IDEAS}/{_slug(task)}-{_stamp()}.md")
    if not where.is_absolute():
        where = root / where
    if where.exists():
        raise ValueError(
            f"{where}: output file already exists - choose a different path"
        )
    where.parent.mkdir(parents=True, exist_ok=True)
    if not os.access(where.parent, os.W_OK):
        raise ValueError(f"{where.parent}: no write permission to output directory")
    spoken(
        drafting,
        render(
            planning.GEN_IDEA,
            N=config.n,
            OUTPUT_FILE=where,
            TEMPLATE=planning.GEN_IDEA_TEMPLATE,
            IDEA_BODY=task,
        ),
    )
    return where


def _plan(
    agents: Agents,
    writing: SessionBase,
    task: str,
    config: Config,
    root: Path,
    draft: Path,
) -> Path:
    """`gen-plan`: the reviewer reads first, the builder writes, and the two converge.

    Args:
      agents: The agents the flow drives.
      writing: The session the planner holds for the whole of the planning.
      task: What was asked for.
      config: How this run was set up.
      root: The workspace.
      draft: What the plan is written from.

    Returns:
      The plan.

    Raises:
      ValueError: If the draft is not there, is empty, does not belong to this repository, or
        the plan cannot be written where it was asked for.
    """
    if not draft.is_file():
        raise ValueError(f"{draft}: input file not found")
    held = draft.read_text(encoding="utf-8")
    if not held.strip():
        raise ValueError(f"{draft}: input file is empty")
    where = Path(config.plan_output or PLAN)
    if not where.is_absolute():
        where = root / where
    if where.exists():
        raise ValueError(
            f"{where}: output file already exists - please choose another path"
        )
    if not where.parent.is_dir():
        raise ValueError(f"{where.parent}: output directory does not exist")

    said = spoken(
        agents.analyst,
        render(planning.RELEVANCE, INPUT_FILE=draft, DRAFT_CONTENT=held),
    )[0]
    if said.strip().upper().startswith("NOT_RELEVANT"):
        raise ValueError(
            f"the draft does not appear to be related to this repository: {said}"
        )

    # The plan file starts as the template with the draft under it, which is what the plugin
    # copies into place before the builder writes a word: the draft is the human input, and
    # it stays in the file rather than being read once and paraphrased away.
    where.write_text(
        planning.GEN_PLAN_TEMPLATE
        + "\n--- Original Design Draft Start ---\n\n"
        + held
        + "\n--- Original Design Draft End ---\n",
        encoding="utf-8",
    )

    analysis = spoken(
        agents.analyst,
        render(planning.GEN_PLAN_ANALYSIS, INPUT_FILE=draft, DRAFT_CONTENT=held),
    )[0]
    spoken(
        writing,
        render(planning.GEN_PLAN_CANDIDATE, OUTPUT_FILE=where, ANALYSIS=analysis),
    )

    converged = False
    prior = ""
    if config.gen_plan_mode == "discussion":
        for _ in range(CONVERGING):
            review = spoken(
                agents.analyst,
                render(
                    planning.GEN_PLAN_CONVERGENCE,
                    OUTPUT_FILE=where,
                    TASK=task,
                    PRIOR=prior,
                ),
            )[0]
            if review.strip() == loop.COMPLETE:
                converged = True
                break
            prior = f"What was still open after the last round:\n\n{review}\n"
            spoken(
                writing,
                render(planning.GEN_PLAN_REVISION, OUTPUT_FILE=where, REVIEW=review),
            )

    # `--auto-start-rlcr-if-converged` is the one thing that skips the person: it is only
    # ever satisfied in discussion mode, with the plan converged and nothing left to decide.
    reviewing = not (
        config.auto_start_rlcr_if_converged
        and converged
        and config.gen_plan_mode == "discussion"
    )
    spoken(
        writing,
        render(
            planning.GEN_PLAN_FINAL,
            OUTPUT_FILE=where,
            CONVERGENCE_STATUS="converged" if converged else "partially_converged",
            DECISIONS=(
                "\nPut every remaining `PENDING` decision to the person at the prompt with "
                "`AskUserQuestion` before writing the final plan, and record what they "
                "decide in place of the `PENDING` status. Confirm every quantitative metric "
                "the draft states with them too: whether it is a hard requirement or a "
                "direction to move in, which changes how the acceptance criteria are "
                "written.\n"
                if reviewing
                else ""
            ),
        ),
    )
    language, code = _language(config.alternative_plan_language)
    if language:
        spoken(
            writing,
            render(
                planning.GEN_PLAN_TRANSLATE,
                OUTPUT_FILE=where,
                LANGUAGE=language,
                VARIANT_FILE=where.with_name(f"{where.stem}_{code}{where.suffix}"),
            ),
        )
    return where


def _rlcr(
    agents: Agents,
    building: SessionBase,
    config: Config,
    root: Path,
    plan: Path | None,
) -> None:
    """`start-rlcr-loop`: the plan is built under review until nothing is left to say.

    Args:
      agents: The agents the flow drives.
      building: The session the builder holds for the whole of the loop.
      config: How this run was set up.
      root: The workspace.
      plan: The plan to build, or None for a `--skip-impl` run that has none.

    Raises:
      ValueError: If the loop cannot start: not a git repository, no plan where one is
        needed, a plan that is not this repository's, or one that would move the branch.
    """
    if _head(root) == "":
        raise ValueError(
            "rlcr runs in a git repository: every review reads the work since the commit "
            "the plan was fixed in"
        )
    if (
        config.agent_teams
        and os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") != "1"
    ):
        raise ValueError(
            "agent_teams requires the CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS environment "
            "variable to be set:\n\n  export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
        )
    if config.push_every_round and not git("remote", at=root)[1]:
        raise ValueError(
            "push_every_round needs a remote to push to, and this repository has none"
        )
    held = ""
    if plan is not None:
        if not plan.is_file():
            raise ValueError(f"{plan}: no plan file to build")
        held = plan.read_text(encoding="utf-8")
        if len(held.splitlines()) < _ENOUGH:
            raise ValueError(f"{plan}: the plan file has almost nothing in it")

    # The plan is checked before anything is set up: a plan for another repository, or one
    # that would move the work to another branch, is one to say so about now.
    if plan is not None and not config.skip_impl:
        verdict = spoken(
            agents.reviewer,
            render(prompts.PLAN_COMPLIANCE, PLAN_FILE=plan, PLAN_CONTENT=held),
        )[0]
        if "FAIL_RELEVANCE" in verdict:
            raise ValueError(f"the plan is not related to this repository: {verdict}")
        if "FAIL_BRANCH_SWITCH" in verdict:
            raise ValueError(
                "the plan contains branch-switching instructions, which are incompatible "
                f"with RLCR: {verdict}"
            )

    if plan is not None and not (config.skip_quiz or config.skip_impl):
        _understood(agents, plan, held)

    stamp = loop.started()
    where = loop.directory(root, stamp)
    if plan is None:
        (where / "plan.md").write_text(
            "# Skip Implementation Mode\n\nThis RLCR loop was started with `skip_impl`, "
            "which skips the implementation phase and goes directly to code review.\n\n"
            "No implementation plan was provided - this is expected for skip-impl mode.\n",
            encoding="utf-8",
        )
        named = str((where / "plan.md").relative_to(root))
    else:
        shutil.copyfile(plan, where / "plan.md")
        named = str(plan.relative_to(root) if plan.is_relative_to(root) else plan)

    base = _base(root, config.base_branch)
    commit = git("rev-parse", base, at=root)[1] if base else ""
    state = State(
        current_round=0,
        max_iterations=config.max,
        codex_model=agents.reviewer.config.model,
        codex_effort=agents.reviewer.config.effort,
        codex_timeout=config.codex_timeout,
        push_every_round=config.push_every_round,
        full_review_round=config.full_review_round,
        plan_file=named,
        plan_tracked=config.track_plan_file,
        start_branch=_head(root),
        base_branch=base,
        base_commit=commit,
        review_started=config.skip_impl,
        ask_codex_question=not config.claude_answer_codex,
        agent_teams=config.agent_teams,
        privacy_mode=config.privacy,
        # Skip-impl does not use the BitLesson-aware summary template, so enforcing it
        # would block a review-only run on a section nothing asked it to write.
        bitlesson_required=not config.skip_impl,
        bitlesson_allow_empty_none=not config.require_bitlesson_entry_for_none,
        mainline_stall_count=0,
        started_at=_utc(),
    )
    running = Loop(agents.reviewer, where, root, state)
    _set_up(running, config, plan, held)
    if config.skip_impl:
        (where / loop.REVIEW_STARTED).write_text(
            "build_finish_round=0\n", encoding="utf-8"
        )

    told = _round_zero(running, config, held)
    running.prompt.write_text(told, encoding="utf-8")
    with (
        agents.builder.hooks.on(Moment.STOP, running),
        agents.builder.hooks.on(Moment.PERMISSION_REQUEST, guards.Guard(running, root)),
        agents.builder.hooks.on(
            Moment.USER_PROMPT_SUBMIT, guards.Prompted(running, root)
        ),
    ):
        spoken(building, told)


#: How few lines a plan may have before it is not a plan, as the setup script counts them.
_ENOUGH = 5


def _utc() -> str:
    """Now, as the state file records it."""
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _understood(agents: Agents, plan: Path, held: str) -> None:
    """The plan understanding quiz, which is advisory and never a gate.

    Two questions about how the plan will be built, put to whoever is at the prompt. Getting
    one wrong is not refused: what it earns is the summary of what the plan actually does,
    and the choice to go on or to stop and read it. Nobody at the prompt is nobody to quiz,
    so a command line runs straight through.

    Args:
      agents: The agents the flow drives.
      plan: The plan.
      held: What it says.

    Raises:
      ValueError: If the person read the summary and chose to stop and review the plan.
    """
    said = spoken(
        agents.reviewer,
        render(prompts.PLAN_UNDERSTANDING_QUIZ, PLAN_FILE=plan, PLAN_CONTENT=held),
    )[0]
    quiz = _quiz(said)
    if not quiz:
        print("Plan understanding quiz unavailable, continuing without it.")
        return
    answered = 0
    asked = 0
    for n in "12":
        options = [quiz[f"OPTION_{n}{letter}"] for letter in "ABCD"]
        picked = _asked(agents.human, quiz[f"QUESTION_{n}"], options)
        if not picked:
            return  # nobody is at the prompt, so there is nobody to quiz
        asked += 1
        answered += picked == quiz[f"ANSWER_{n}"].upper()
    if asked and answered == asked:
        print("Your understanding of the plan looks solid. Proceeding with setup.")
        return
    going = agents.human(
        f"{quiz['PLAN_SUMMARY']}\n\nThe answers were "
        + ", ".join(f"Q{n}: {quiz[f'ANSWER_{n}'].upper()}" for n in "12")
        + ".\n\nWould you like to proceed with the RLCR loop anyway, or stop and review "
        "the plan more carefully first?\n  A. Proceed with RLCR loop\n"
        "  B. Stop and review the plan first\n\nAnswer with A or B."
    )
    if going.strip()[:1].upper() == "B":
        raise ValueError(
            "stopping. Please review the plan file and run the flow again when ready"
        )


def _set_up(running: Loop, config: Config, plan: Path | None, held: str) -> None:
    """Writes everything a loop starts with: the tracker, the contract, the lessons, the state.

    Args:
      running: The loop.
      config: How this run was set up.
      plan: The plan, or None for a review-only run.
      held: What the plan says.
    """
    where = running.where
    lessons = running.root / running.state.bitlesson_file
    if not lessons.exists():
        lessons.parent.mkdir(parents=True, exist_ok=True)
        lessons.write_text(prompts.BITLESSON, encoding="utf-8")
    goal = _section(held, "goal", "objective", "overview")
    criteria = _section(held, "acceptance", "criteria", "requirements")
    if config.skip_impl and plan is not None:
        tracker = render(
            prompts.GOAL_TRACKER_SKIP_IMPL_ANCHORED,
            PLAN_GOAL_CONTENT=goal
            or f"Preserve the original plan scope from {running.state.plan_file} while "
            "resolving code review findings on the current branch.",
            PLAN_AC_CONTENT=criteria
            or f"- The current branch remains aligned with the original plan at "
            f"{running.state.plan_file}.\n- All blocking `[P0-9]` code review findings are "
            "resolved without widening scope beyond the original plan.\n- Non-blocking "
            "follow-up items are explicitly queued and do not block completion.",
            PLAN_FILE=running.state.plan_file,
        )
    elif config.skip_impl:
        tracker = prompts.GOAL_TRACKER_SKIP_IMPL
    else:
        tracker = render(
            prompts.GOAL_TRACKER,
            GOAL_SECTION=goal
            or "[To be extracted from plan by the builder in Round 0]\n\nSource plan: "
            + running.state.plan_file,
            AC_SECTION=criteria
            or "[To be defined by the builder in Round 0 based on the plan]",
        )
    running.tracker.write_text(tracker, encoding="utf-8")
    running.summary.write_text(
        render(prompts.SUMMARY_TEMPLATE, ROUND=0), encoding="utf-8"
    )
    if config.skip_impl:
        running.contract.write_text(
            render(
                prompts.ROUND_CONTRACT_SKIP_IMPL_ANCHORED,
                PLAN_FILE=running.state.plan_file,
            )
            if plan is not None
            else prompts.ROUND_CONTRACT_SKIP_IMPL,
            encoding="utf-8",
        )
    (where / "state.md").write_text(running.state.written(), encoding="utf-8")


def _round_zero(running: Loop, config: Config, held: str) -> str:
    """The prompt the builder starts on, as the setup script writes it.

    Args:
      running: The loop.
      config: How this run was set up.
      held: What the plan says, which round 0 is given in full.

    Returns:
      The prompt.
    """
    if config.skip_impl:
        return render(
            prompts.ROUND_0_SKIP_IMPL,
            BASE_BRANCH=running.state.base_branch,
            START_BRANCH=running.state.start_branch,
            PLAN_FILE=running.state.plan_file,
            GOAL_TRACKER_FILE=running.tracker,
            ROUND_CONTRACT_FILE=running.contract,
            SUMMARY_FILE=running.summary,
            ANCHOR=render(
                prompts.ROUND_0_SKIP_IMPL_ANCHORED, PLAN_FILE=running.state.plan_file
            )
            if held
            else prompts.ROUND_0_SKIP_IMPL_UNANCHORED,
        )
    teams = ""
    if config.agent_teams:
        teams = (
            "\n" + prompts.AGENT_TEAMS_INSTRUCTIONS + "\n" + prompts.AGENT_TEAMS_CORE
        )
    told = render(
        prompts.ROUND_0,
        GOAL_TRACKER_FILE=running.tracker,
        ROUND_CONTRACT_FILE=running.contract,
        SUMMARY_FILE=running.summary,
        TASK_LANES=prompts.TASK_LANES,
        PLAN_CONTENT=held,
        BITLESSON_SELECTION=render(
            prompts.BITLESSON_SELECTION,
            BITLESSON_FILE=running.root / running.state.bitlesson_file,
        ),
        AGENT_TEAMS=teams,
    )
    if config.push_every_round:
        told += prompts.PUSH_EVERY_ROUND_NOTE
    return told


def run(agents: Agents, task: str, config: Config | None = None) -> None:
    """Runs whichever of the three phases this was set up to run, in order.

    Args:
      agents: The drafter, the planner and its analyst, the builder and its reviewer, and
        whoever is at the prompt.
      task: The idea, as it was given.
      config: How the run was set up, or None for the plugin's own defaults -- which is all
        three phases, and every flag as the plugin ships it.

    Raises:
      ValueError: If a phase that is on cannot start: a draft that is not there, a plan that
        is not this repository's, a loop outside a git repository. Said before the first turn
        rather than found hours into one.
    """
    setting = config or Config()
    root = Path.cwd()
    if setting.gen_idea and not task.strip():
        raise ValueError("gen_idea opens an idea, and this run was given none")

    # One session per phase, held for the whole of it: the side that writes remembers how it
    # got there, and the next phase starts from the file rather than from the conversation --
    # which is what makes the three of them three commands rather than one long turn.
    draft = Path(setting.idea_output) if setting.idea_output else None
    if draft is not None and not draft.is_absolute():
        draft = root / draft
    if setting.gen_idea:
        draft = _idea(agents.drafter.new(), task, setting, root)

    plan = Path(setting.plan_file) if setting.plan_file else None
    if plan is not None and not plan.is_absolute():
        plan = root / plan
    if setting.gen_plan:
        if draft is None:
            raise ValueError(
                "gen_plan needs a draft: set idea_output, or turn gen_idea on"
            )
        plan = _plan(agents, agents.planner.new(), task, setting, root, draft)

    if setting.rlcr:
        _rlcr(
            agents,
            agents.builder.new(),
            setting,
            root,
            None if setting.skip_impl and plan is None else plan,
        )
