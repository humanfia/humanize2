"""RLCR (humanize 1) -- an idea is opened, planned against review, then built against it.

    hmz exec -f humanize1 \
        -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max "add undo/redo to the editor"

Run in a git repository: the work is anchored to the commit the plan is committed in, and every
review reads what came after it.

The builder remembers and the reviewer does not. One session builds, holding the whole run from
the first reading of the idea; every review is a session that has just started, reads the
repository itself, and is told nothing about how the work was arrived at. The only thing read out
of a review is whether it is the word COMPLETE; anything else is the builder's next prompt, word
for word.
"""

import re
import time
from typing import NamedTuple

from humanize.janus import AgentBase, SessionBase


class Agents(NamedTuple):
    """The two the flow drives: one that remembers the run, and one that never does."""

    builder: AgentBase
    reviewer: AgentBase


#: Where the run keeps what outlives a turn. Named for the agents rather than opened here -- an
#: agent may be working on another machine, where this directory is the only one that exists.
PLAN = ".humanize/rlcr/plan.md"
TRACKER = ".humanize/rlcr/goal-tracker.md"

#: A reviewer with nothing to require. Matched against the whole answer rather than a line of it:
#: a review that quotes the word back while explaining what it would take to earn it would
#: otherwise end the run, where a review that meant to accept and said more only costs a round.
ACCEPTED = re.compile(r"\W*COMPLETE\W*", re.IGNORECASE)

RELAYED = """Otherwise write what is wrong and what to do about it, citing files, lines and \
commands. What you write is passed to that agent word for word and is all it will hear from you, \
so leave nothing to be inferred."""

IDEA = """Read this repository -- its README, its AGENTS.md or CLAUDE.md, its top-level layout -- \
and then open the idea below from six orthogonal directions.

A direction is an angle on the idea, not a restatement of it: two that would lead to the same \
code are one direction, and one of them should be replaced; "the same thing but better" is not a \
direction at all. Explore each against this repository and gather objective evidence -- paths \
that already do something like it, prior art to extend, the surface it would touch. Read only: \
write nothing, change nothing. This is the phase that decides what to build, and a repository \
that has already been changed decides it for you. Do not invent references; a direction with no \
precedent here says so plainly.

Then pick the one to build, and pick it on that evidence: how much of it is grounded in code that \
is already here, how well it extends what this repository already does, how small its surface is.

Answer with the direction you chose -- what to build, by what mechanism, what it touches, what \
could go wrong -- and then the ones you passed over, one line each, saying why. It will be read \
by someone who did not watch you choose.

Idea:
"""

ANALYSE = """A coding agent has chosen what to build in this repository and is about to plan it. \
Read the repository first -- what is there, how it is built, how it is \
tested -- and then say two things.

Whether its evidence holds: a path it names that is not there, a pattern it says it can extend \
that does not exist, a direction passed over for a reason this repository does not support.

Then what a plan for this would have to get right to be worth executing: what it cannot avoid \
touching, what it must not break, what has gone wrong here before if you can see it, and what \
would make it verifiable rather than merely plausible. You are not writing the plan and you are \
not choosing the direction again.

What was asked for:
"""

WRITE_PLAN = f"""Write the plan now, to {PLAN}, taking the analysis below into account -- it \
comes from a reviewer that read this repository without seeing your reasoning.

The plan states the goal, then the acceptance criteria, then the tasks that meet them. A \
criterion is deterministic or it is not a criterion: each one carries the tests that must pass \
when it holds and the tests that must fail -- what the work must refuse, not only what it must \
do. Number them AC-1, AC-2, and have every task name the criterion it serves. Bound the scope at \
both ends: the most that would be worth doing, and the least that would still be the thing. A \
number the idea stated is a requirement to be met, not a direction to move in, unless it said \
otherwise. The work stays on the branch it starts on, so nothing in the plan moves it to another.


Write the plan and nothing else: no code, no scaffolding, not one file of the work itself.

Answer with the path you wrote and nothing else: the plan will be read from the file.

Analysis:
"""

CHALLENGE = f"""Review the plan at {PLAN}, which a coding agent wrote for this repository. Read \
the repository and judge the plan against it, rather than against how a plan usually looks. What \
is worth catching here: a criterion that cannot be checked, \
a task that names no criterion, a scope that has quietly grown, a step that would move the work \
to another branch. The plan is fixed once this is over, so anything you do not say now is not said.

Judge it against what was asked for and the direction that was chosen, both below, and not only \
against the goal the plan states -- that goal was written by the same agent, so a plan that has \
drifted has drifted in both. The direction is allowed to be a departure from a literal reading of \
the task; the plan is not allowed to be a departure from the direction.

If nothing has to change before this is worth executing, answer with the single word COMPLETE, \
and mean it: a plan is not improved by being asked for one more thing. {RELAYED} Tell it too that \
where it thinks you are wrong it should say so in the plan, and say why, since nobody will \
arbitrate it later.

What was asked for:
"""

COMMIT = f"""Commit {PLAN} on its own now, saying in the message that it is the plan -- if this \
repository has no commit yet, this is its first. The work starts there and every review reads \
what came after, so the plan is fixed by being in the history rather than by anyone promising not \
to touch it.

Its directory is one a project may well have told git to ignore, so add it with `git add -f` and \
then check with `git ls-files --error-unmatch` that git really took it. A plan git never took is \
a plan nothing can tell has changed.

Answer with that commit's hash and nothing else.
"""

BUILD = f"""Build the plan in {PLAN} -- all of it. A round is not a task or a stage: work until \
you believe every acceptance criterion holds, and only then answer.

Commit as you go: the reviews read the change since the plan's own commit, and work left \
uncommitted is work they cannot tell from someone else's.

The plan is the contract you are judged against, and it is now fixed -- do not edit it. Keep \
{TRACKER} instead, starting it fresh from this plan: the goal and the criteria at the top, \
unchanged, and under them what is done, what is left, what you deferred and why, and every place \
the plan turned out to be wrong along with what you did instead. Deferring is not finishing: a \
criterion you have set aside is a criterion that does not hold, and the round is not over. Every \
review you are given goes in too, with what you did about it and where you disagreed: the \
reviewer after it will not have seen it, and that record is the only way it can know. Your \
summary covers one round; this covers all of them, and it is read by someone who was at none.

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
diff since that commit. Read {TRACKER} too, for what it says it \
has done -- as a claim to check, not as evidence. Be skeptical in one direction in particular: \
work stubbed out, tests weakened or special-cased to pass, criteria declared met by narrowing \
what they meant.

If every acceptance criterion genuinely holds, answer with the single word COMPLETE. {RELAYED}

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


def run(agents: Agents, task: str) -> None:
    builder, reviewer = agents
    building = builder.new()  # one session for the whole run: the builder remembers

    # The task is handed over rather than quoted back: a retelling by whoever chose the direction
    # is not what a reviewer needs to judge the direction against.
    direction = spoken(building, IDEA + task)
    chosen = f"{task}\n\nWhat it chose to build:\n{direction}"

    analysis = spoken(reviewer, ANALYSE + chosen)
    told = WRITE_PLAN + analysis
    while True:
        spoken(building, told)
        told = spoken(reviewer, CHALLENGE + chosen)
        if ACCEPTED.fullmatch(told):
            break

    # The one fact the run owns. Asked of the builder, because an agent working on another machine
    # is the only one that can see the repository the work happens in -- and held here, because a
    # plan that recorded its own commit could not match it, having grown the line that records it.
    base = spoken(building, COMMIT)

    told = BUILD
    while True:
        said = spoken(building, told)
        asked = f"{REVIEW}{base}\n\nIts summary of the round:\n{said}"
        told = spoken(reviewer, asked)
        if ACCEPTED.fullmatch(told):
            break

    # The claim is settled and is not asked again: a code review that sent the work back would
    # put it to a reviewer that was not there for the answer, and two reviewers that each
    # remember nothing can go on undoing one another for as long as they are both asked.
    while True:
        asked = f"{CODE_REVIEW}{base}\n\nWhat it says it has done:\n{said}"
        told = spoken(reviewer, asked)
        if ACCEPTED.fullmatch(told):
            return
        said = spoken(building, told)
