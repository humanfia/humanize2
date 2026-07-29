"""RLCR (humanize 1) -- an idea is opened, planned against review, then built against it.

    hmz exec -f humanize1 \
        -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max "add undo/redo to the editor"

Written against PolyArch/humanize, which is the same three phases as a Claude Code plugin:
`gen-idea` opens a loose idea into a repo-grounded draft, `gen-plan` turns that draft into a
plan both sides have converged on, and `start-rlcr-loop` builds the plan under review until
nothing is left to say. Here they are one Python file and two agents.

Run in a git repository: the work is anchored to the commit the plan is committed in, and every
review reads what came after it.

The builder remembers and the reviewer does not. One session builds, holding the whole run from
the first reading of the idea; every review is a session that has just started, reads the
repository itself, and is told nothing about how the work was arrived at. The only thing read
out of a review is whether it is the word COMPLETE; anything else is the builder's next prompt,
word for word.

The loop itself is a hook. The plugin blocks Claude's exit and puts the round to Codex there;
so does this -- a `Stop` hook on the builder, which is the same sentence: a round ends when the
builder believes the whole plan is done and tries to stop, and what the reviewer says is what
it hears instead of stopping.
"""

import re
import time
from dataclasses import dataclass, field
from typing import NamedTuple

from humanize.agents import AgentBase, Moment, Occasion, SessionBase, Verdict


class Agents(NamedTuple):
    """The two the flow drives: one that remembers the run, and one that never does."""

    builder: AgentBase
    reviewer: AgentBase


#: Where the run keeps what outlives a turn. Named for the agents rather than opened here -- an
#: agent may be working on another machine, where this directory is the only one that exists.
DRAFT = ".humanize/rlcr/draft.md"
PLAN = ".humanize/rlcr/plan.md"
TRACKER = ".humanize/rlcr/goal-tracker.md"

#: How many orthogonal directions the idea is opened from, as `gen-idea --n` defaults to.
DIRECTIONS = 6

#: How many rounds each loop is given. Planning converges or it does not: three rounds of
#: challenge is the plugin's cap, and a fourth is a plan being polished rather than settled.
#: Building is given the plugin's own forty-two, which is a day of rounds and not a budget.
CONVERGING = 3
ROUNDS = 42

#: How often a round is a full alignment check rather than a review of the round: every fifth,
#: at rounds 4, 9, 14, as the plugin schedules them.
ALIGNING = 5

#: A reviewer with nothing to require. Matched against the whole answer rather than a line of it:
#: a review that quotes the word back while explaining what it would take to earn it would
#: otherwise end the run, where a review that meant to accept and said more only costs a round.
ACCEPTED = re.compile(r"\W*COMPLETE\W*", re.IGNORECASE)

RELAYED = """Otherwise write what is wrong and what to do about it, citing files, lines and \
commands. What you write is passed to that agent word for word and is all it will hear from you, \
so leave nothing to be inferred."""

IDEA = f"""Read this repository -- its README, its AGENTS.md or CLAUDE.md, its top-level layout \
-- and then open the idea below from {DIRECTIONS} orthogonal directions.

A direction is an angle on the idea, not a restatement of it: two that would lead to the same \
code are one direction, and one of them should be replaced; "the same thing but better" is not a \
direction at all. Explore each against this repository and gather objective evidence -- paths \
that already do something like it, prior art to extend, the surface it would touch. Explore them \
at once rather than one after another if you can: they are independent, and each is a reading of \
this repository under a different question. Read only: write nothing, change nothing, other than \
the one file this ends by writing. This is the phase that decides what to build, and a repository \
that has already been changed decides it for you. Do not invent references; a direction with no \
precedent here says so in those words -- exploratory, no concrete precedent -- rather than \
reaching for one.

Then pick the one to build, and pick it on that evidence, in this order: how much of it is \
grounded in code that is already here, how well it extends what this repository already does, \
how small its surface is, and how sure you are of it.

Write the draft to {DRAFT} -- and nothing else, no code, no scaffolding, not one file of the \
work itself. It holds, under headings:

- the idea as you were given it, word for word, unedited;
- the direction you chose: what to build, by what mechanism, what it touches, the objective \
evidence for it as a list of paths and prior art, the risks you know of, and how sure you are;
- the ones you passed over, Alt-1 upward, one gist and its own evidence apiece, each saying in \
one sentence why it is not the one;
- what could be folded back in from them if the direction turns out to be wrong.

It will be read by someone who did not watch you choose. Answer with the path you wrote and \
nothing else: the draft will be read from the file.

Idea:
"""

RELEVANT = f"""A coding agent has written the draft at {DRAFT} against this repository, from the \
idea below. Read the repository, then read the draft, and say whether the two belong together at \
all: a draft for another project, or for a repository that does not have what it says it will \
extend, is one to say so about now rather than after a plan has been written for it.

Then say whether its evidence holds -- a path it names that is not there, a pattern it says it \
can extend that does not exist, a direction passed over for a reason this repository does not \
support -- and whether the direction it chose is the one its own evidence points at.

If the draft belongs to this repository and its evidence holds, answer with the single word \
COMPLETE. {RELAYED}

The idea it was written from:
"""

ANALYSE = f"""A coding agent has chosen what to build in this repository, in the draft at \
{DRAFT}, and is about to plan it. Read the repository first -- what is there, how it is built, \
how it is tested -- then read the draft, and answer under these headings and no others:

CORE_RISKS: the assumptions this rests on that are most likely to be wrong, and how it fails \
when they are.
MISSING_REQUIREMENTS: what it will turn out to need that neither the idea nor the draft says.
TECHNICAL_GAPS: where it is not feasible as described, or where the architecture will not take it.
ALTERNATIVE_DIRECTIONS: the directions worth taking instead, with what each costs.
QUESTIONS_FOR_USER: what only a person can decide, which the plan will otherwise decide by \
guessing.
CANDIDATE_CRITERIA: the acceptance criteria this ought to be held to, each one something a \
command can check.

You are not writing the plan and you are not choosing the direction again.

What was asked for:
"""

STRUCTURE = """The plan states, under headings and in this order:

- the goal, in a paragraph: what will be true when this is done.
- the acceptance criteria, AC-1 upward. A criterion is deterministic or it is not a criterion: \
each one carries the tests that must pass when it holds and the tests that must fail -- what the \
work must refuse, not only what it must do. A number the idea stated is a requirement to be met, \
not a direction to move in, unless it said otherwise.
- the bounds of the path, at both ends: the most that would be worth doing, the least that would \
still be the thing, and the choices left open along the way that either side may take either way.
- how to approach it, and what in this repository to read first.
- the order: what depends on what, and the milestones the work passes through.
- the tasks that meet the criteria. Every task names the criterion it serves and carries one \
tag -- `coding` for work to do, `analyze` for a question to settle. The work stays on the branch \
it starts on, so no task moves it to another.
- what the two of you settled and what you did not: what was agreed, what was disagreed and how \
it was resolved, and anything still open.
- what a person still has to decide, if anything is left that only a person can.
"""

WRITE_PLAN = f"""Write the plan now, to {PLAN}, taking the analysis below into account -- it \
comes from a reviewer that read this repository and the draft without seeing your reasoning.

{STRUCTURE}
Write the plan and nothing else: no code, no scaffolding, not one file of the work itself.

Answer with the path you wrote and nothing else: the plan will be read from the file.

Analysis:
"""

CHALLENGE = f"""Review the plan at {PLAN}, which a coding agent wrote for this repository from \
the draft at {DRAFT}. Read the repository and judge the plan against it, rather than against how \
a plan usually looks. Answer under these headings and no others:

AGREE: what is settled and should not be reopened.
DISAGREE: what is unreasonable, and why.
REQUIRED_CHANGES: what must change before this is worth executing at all -- a criterion that \
cannot be checked, a task that names no criterion or carries no tag, a scope that has quietly \
grown, a step that would move the work to another branch.
OPTIONAL_IMPROVEMENTS: what would be better and does not block anything.
UNRESOLVED: where you and it disagree and neither can settle it, which a person will have to.

Judge it against what was asked for and the direction that was chosen, both below, and not only \
against the goal the plan states -- that goal was written by the same agent, so a plan that has \
drifted has drifted in both. The direction is allowed to be a departure from a literal reading of \
the task; the plan is not allowed to be a departure from the direction.

The plan is fixed once this is over, so anything you do not say now is not said. If nothing is \
required and nothing under DISAGREE would change the work, answer with the single word COMPLETE \
instead of the headings, and mean it: a plan is not improved by being asked for one more thing. \
{RELAYED} Tell it too that where it thinks you are wrong it should say so in the plan, and say \
why, since nobody will arbitrate it later.

What was asked for:
"""

REVISE = f"""Revise the plan at {PLAN} against the review below, and answer with the path you \
wrote and nothing else.

Everything under REQUIRED_CHANGES is to be met or argued with in the plan itself, saying why. \
What is under OPTIONAL_IMPROVEMENTS is yours to take or leave. What is under UNRESOLVED goes into \
the plan as still open, in the words both of you used, since nobody will arbitrate it later. Keep \
the plan the shape it already has, and do not start the work.

Review:
"""

SETTLED = f"""The plan at {PLAN} has been through {CONVERGING} rounds of review without both \
sides settling, which is as many as it gets: what is still open is open, and the plan says so.

Write the last version now. Everything still disagreed goes in under what was not settled, in \
the words both of you used, so that whoever reads it can see it was not agreed rather than \
finding out later. Change nothing else, and do not start the work.

Answer with the path you wrote and nothing else.

The last review:
"""

COMMIT = f"""Commit {PLAN} and {DRAFT} together now, saying in the message that they are the \
plan -- if this repository has no commit yet, this is its first. The work starts there and every \
review reads what came after, so the plan is fixed by being in the history rather than by anyone \
promising not to touch it.

Their directory is one a project may well have told git to ignore, so add them with `git add -f` \
and then check with `git ls-files --error-unmatch` that git really took them. A plan git never \
took is a plan nothing can tell has changed.

Answer with that commit's hash and nothing else.
"""

BUILD = f"""Build the plan in {PLAN} -- all of it. A round is not a task, a milestone or a stage: \
work until you believe every acceptance criterion holds, and only then answer. If the plan has \
stages, they are all done inside one round.

Commit as you go: the reviews read the change since the plan's own commit, and work left \
uncommitted is work they cannot tell from someone else's.

The plan is the contract you are judged against, and it is now fixed -- do not edit it. Keep \
{TRACKER} instead, starting it fresh from this plan, in two parts. The part that does not change: \
the goal and the acceptance criteria, copied over, and never touched again. The part that does: \
what is done, what is left, what you deferred and why, and every place the plan turned out to be \
wrong along with what you did instead. Deferring is not finishing: a criterion you have set aside \
is a criterion that does not hold, and the round is not over. Every review you are given goes in \
too, with what you did about it and where you disagreed: the reviewer after it will not have seen \
it, and that record is the only way it can know. Your summary covers one round; this covers all \
of them, and it is read by someone who was at none.

A task the plan tagged `analyze` is a question rather than work: settle it if the repository \
settles it, and otherwise put it in the round summary as a question. The reviewer reads the \
repository without having seen your reasoning, which is what makes its answer worth having.

A reviewer will read what you write and answer, and what it answers is what you will be told \
next. It reads the repository and not your reasoning, so it can be wrong: where you think it is, \
say so and say why, and say what you did instead. Doing what a review asked while believing it \
wrong is how two rounds become forty.

Then answer with a summary of the round: what you built, which criteria it meets, which files \
changed, what you tested and what it said -- every claim in it is a claim that reviewer will check.
"""

REVIEW = f"""A coding agent has been building the plan in {PLAN} in this repository and says it \
is finished.

The plan was committed, on its own, before the work began, and neither of you may change it now. \
Check that first: `git diff <the commit below> -- {PLAN}` should be empty, and a plan edited \
since is the whole of your answer: everything after it was judged against the wrong contract.

Then check the claim against the repository: read {PLAN}, read the code, run the tests, read the \
diff since that commit. Read {TRACKER} too, for what it says it has done -- as a claim to check, \
not as evidence. Be skeptical in one direction in particular: work stubbed out, tests weakened or \
special-cased to pass, criteria declared met by narrowing what they meant.

If its summary put a question to you, answer it: it is a task the plan left to be settled, and \
you are the one reading the repository without having watched the work.

If every acceptance criterion genuinely holds, answer with the single word COMPLETE. {RELAYED}

The commit the work starts from:
"""

ALIGN = f"""A coding agent has been building the plan in {PLAN} in this repository for several \
rounds. This is not a review of the round: it is a check that the work is still the work.

Read {PLAN} and {TRACKER}, then the diff since the commit below, and answer three questions. \
Is every acceptance criterion still accounted for -- is there one nothing has touched, or one \
quietly narrowed until it was met? Has anything been built that no criterion asked for? And of \
what has been deferred, how much would have to hold before this could be called done at all?

The plan is fixed. Where the work has departed from it, the departure is what has to be justified \
or undone -- not the plan.

If the work is still the plan's, answer with the single word COMPLETE. {RELAYED}

The commit the work starts from:
"""

CODE_REVIEW = f"""A coding agent has finished the work for the plan in {PLAN}. The question here \
is not whether it does what was asked, but whether what is now in the repository is any good.

Review the change as a whole -- everything since the commit below, which is the one that added \
the plan. The plan and its criteria are fixed, so do not ask for a change that would leave one of \
them unmet. The criteria were checked before this loop began and are not reopened -- but they \
still have to hold, so run the tests each one names, and a criterion that no longer holds is the \
whole of your answer. Then correctness, then the things a diff hides: an error path nothing \
takes, a case the tests do not reach, something duplicated rather than shared, a name that now \
lies.

Mark each thing you find with how much it matters, [P0] through [P9]: P0 is what must not ship, \
and P9 is what you would mention and not insist on. A finding with no marker reads as P0.

Read {TRACKER} for the reviews before yours and what the agent said back: a review already argued \
and reversed is not one to ask for again, and two reviewers who each remember nothing can undo \
one another for as long as they are both asked.

If there is nothing that should be fixed before this ships, answer with the single word COMPLETE: \
a review that finds something every time is not a review. {RELAYED}

The commit the work starts from:
"""


def spoken(agent: AgentBase | SessionBase, prompt: str) -> str:
    """What a turn answered, taking it again for as long as taking it keeps failing.

    A turn that failed is a turn to take again, and only that turn: a round here is hours of work
    and a review is one question about it, so letting a failed review send the round back would
    pay for the expensive half twice to recover from the cheap half.

    Args:
      agent: Whose turn it is -- a session, when the turns are to remember each other, and the
        agent itself for a review, which is a session that has just started.
      prompt: What to say to it.

    Returns:
      What it answered.
    """
    while True:
        said = agent(prompt, suppress=True)
        # A turn that exits clean having said nothing has not answered either, and passing that
        # on would spend a round asking the other side to reply to silence.
        if said:
            return said
        time.sleep(5)


@dataclass
class Loop:
    """The RLCR loop, as the thing the builder runs into every time it tries to stop.

    A round is the builder believing the whole plan is done, which is the moment it stops -- so
    that is where the review goes, and what the review says is what the builder hears instead of
    stopping. Two phases: the work is reviewed against the plan until nothing is left to require,
    and then what was built is reviewed as code until nothing is left to fix.

    Attributes:
      reviewer: Who reads each round, in a session that has just started every time.
      base: The commit the plan was fixed in, which every review reads the work since.
      rounds: How many rounds have been reviewed, counted here rather than taken from the turn:
        a turn that failed is taken again, and the round it was taking is the same round.
      building: Whether the work is still being built rather than read as code.
      told: Every review given, oldest first, which is what the run has to show for itself.
    """

    reviewer: AgentBase
    base: str
    rounds: int = 0
    building: bool = True
    told: list[str] = field(default_factory=list[str])

    def __call__(self, occasion: Occasion) -> Verdict | None:
        """Reviews the round the builder has just finished, and says whether it may stop.

        Args:
          occasion: The turn stopping, whose `said` is the summary of the round.

        Returns:
          What to send the builder on with, or None to let the round be the last one.
        """
        self.rounds += 1
        if self.rounds >= ROUNDS:
            return None  # as many rounds as the loop gets: what is not done is not done
        if self.building:
            # Every fifth round is a check that the work is still the work rather than a review
            # of the round: a loop that only ever reads the last round drifts one round at a time.
            asked = ALIGN if (self.rounds + 1) % ALIGNING == 0 else REVIEW
            said = self.review(
                f"{asked}{self.base}\n\nIts summary of the round:\n{occasion.said}"
            )
            if said is not None:
                return said
            # The claim is settled and is not asked again: a code review that sent the work back
            # to be judged against the plan would put it to a reviewer that was not there for
            # the answer, and two reviewers that each remember nothing can go on undoing one
            # another for as long as they are both asked.
            self.building = False
        return self.review(
            f"{CODE_REVIEW}{self.base}\n\nWhat it says it has done:\n{occasion.said}"
        )

    def review(self, asked: str) -> Verdict | None:
        """Puts one round to the reviewer, and reads its answer as a verdict.

        Args:
          asked: What to ask about the round.

        Returns:
          What the builder is to hear instead of stopping, or None for a reviewer that had
          nothing to require.
        """
        said = spoken(self.reviewer, asked)
        if ACCEPTED.fullmatch(said):
            return None
        self.told.append(said)
        return Verdict(refused=True, because=said)


def run(agents: Agents, task: str) -> None:
    builder, reviewer = agents
    building = builder.new()  # one session for the whole run: the builder remembers

    # gen-idea: the idea is opened from every direction at once and closed to one, and what
    # comes out is a file rather than a turn -- everything after this reads the draft.
    told = IDEA + task
    for _ in range(CONVERGING):
        spoken(building, told)
        told = spoken(reviewer, RELEVANT + task)
        if ACCEPTED.fullmatch(told):
            break
    # A draft still being argued with after three rounds goes to the planning anyway: the
    # reviewer reads this repository again before the plan is written and again after, so a
    # draft that does not belong to it is caught there rather than spun on here.

    # gen-plan: the reviewer reads the repository before the plan exists, the builder writes the
    # plan against that, and the two go round until neither has anything left to require.
    told = WRITE_PLAN + spoken(reviewer, ANALYSE + task)
    for _ in range(CONVERGING):
        spoken(building, told)
        told = spoken(reviewer, CHALLENGE + task)
        if ACCEPTED.fullmatch(told):
            break
        told = REVISE + told
    else:
        # Three rounds and still not settled: what is open is written down as open rather than
        # argued for a fourth time, and the plan goes to the work saying so.
        spoken(building, SETTLED + told.removeprefix(REVISE))

    # The one fact the run owns. Asked of the builder, because an agent working on another machine
    # is the only one that can see the repository the work happens in -- and held here, because a
    # plan that recorded its own commit could not match it, having grown the line that records it.
    base = spoken(building, COMMIT)

    # start-rlcr-loop: the loop is a hook, so a round ends where the builder would have.
    with builder.hooks.on(Moment.STOP, Loop(reviewer, base)):
        spoken(building, BUILD)
