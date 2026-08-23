# Four agents on a maths problem

**An hour.** You will write a flow with four kinds of agent in it, several turns running at
once, and answers held to a shape. The problem is a mathematical one — no compiler, no test
suite, no exit code — so the flow has to build its own way of telling a good answer from a
plausible one. It is the longest flow in these tutorials, and every part of it is there for a
reason you can state.

::: tip Before you start
Finish [Build under test](/weaver/tutorials/checked-build). This tutorial assumes you know what
`@flow`, `agent.new()` and `schema=` do.
:::

## The problem with maths problems

Every flow up to here leaned on something outside the agent: a cycle count in
[`flame_chase`](/user/tutorials/take-home), a test suite in
[`rlar`](/user/tutorials/port-a-project) and in the
[`checked_build`](/weaver/tutorials/checked-build) you just wrote. The first two are flows
somebody else wrote, run rather than written in the [User Guide](/user/) tutorials; all three
caught a wrong answer with something that was not a language model.

A proof has none of that. And a model asked whether its own proof is correct will nearly always
say yes — not out of dishonesty, but because the same reasoning that produced the gap is the
reasoning that would have to notice it.

So this flow is built on one rule: **no session ever both writes and judges.** Everything else
follows from it.

## The design

Four kinds of agent.

| | |
| --- | --- |
| **reader** | States, once, exactly what has to be established — and never solves anything. |
| **solver** | Several attempts at a full proof, all at the same time, each in a session that has seen only the problem. |
| **checker** | Reads one attempt and stops at the first step that does not follow. Has not seen the other attempts and does not know who wrote this one. |
| **mender** | The only agent that remembers. Takes the attempt that got furthest, plus the fault the checker found, and repairs it. |

And one arrangement that matters more than the four roles: **an attempt survives only if two
separate checkers, asked separately, both call it sound.** One checker is a coin toss.

`solver` and `checker` are one agent each, not several: an agent opens as many sessions as it
likes, and what makes two attempts independent is that neither session has seen the other, not
that they run different models.

## Step 1 — make a project and a problem

```sh
mkdir -p ~/tmp/mathlab && cd ~/tmp/mathlab
git init -q
cat > PROBLEM.md <<'EOF'
Let a_1 = 1 and a_{n+1} = a_n + 1/a_n for every n >= 1.

Prove that a_100 > 14.
EOF
mkdir -p .humanize/flows/prove/skills/reading-a-proof
```

That problem has a short right answer and several plausible wrong ones, which is what you want
while you are still testing the flow.

## Step 2 — say who the agents are, and what the run can be set up with

In `.humanize/flows/prove/__init__.py`:

```python
from typing import NamedTuple

from hmz.flows import Agent
from pydantic import BaseModel, Field


class Agents(NamedTuple):
    """The four kinds this drives."""

    reader: Agent
    solver: Agent
    checker: Agent
    mender: Agent


class Setup(BaseModel):
    """What the run can be set up with, as `/config` asks for it or `-c setup.yaml` gives it."""

    model_config = {"frozen": True}

    attempts: int = Field(default=4, ge=1, le=12, description="solvers going at once")
    rounds: int = Field(default=4, ge=1, le=20, description="rounds before it gives up")
    output: str = Field(default="solution.md", description="where the proof is written")
```

A flow whose third argument is annotated with a pydantic model has **settings**: fields on
`/config` and lines in a `-c setup.yaml` file, with the `description` as the label and
`ge`/`le` enforced before the run starts. See [A flow with settings of its
own](/weaver/flow-settings).

## Step 3 — say what you are asking each agent for

Two more shapes. The first is what the reader hands the rest of the flow:

```python
class Statement(BaseModel):
    """The problem, restated by somebody who is not about to solve it."""

    model_config = {"extra": "forbid"}

    claim: str = Field(
        description="Exactly what is to be established, in one or two sentences, with every "
        "quantifier and every condition made explicit. No solution, no hint of one."
    )
    answer_form: str = Field(
        description="What a complete answer has to look like -- a closed form, a set, a "
        "number, an existence proof, an if-and-only-if -- and what would leave it incomplete."
    )
    traps: list[str] = Field(
        description="Three to six specific ways a plausible-looking solution to this problem "
        "is usually wrong: a case not covered, a step that needs an argument, a converse "
        "assumed. Each one a sentence."
    )
```

`traps` is the interesting field. The reader writes down how solutions to *this* problem
usually fail before anybody has attempted one, and that list goes into both the solver's prompt
and the checker's. Naming the traps of a problem you are not trying to solve is much easier.

The second is one checker's reading of one attempt:

```python
from typing import Literal


class Verdict(BaseModel):
    """One checker's reading of one attempt."""

    model_config = {"extra": "forbid"}

    verdict: Literal["sound", "gap", "wrong"] = Field(
        description="sound: every step follows and the claim is established. gap: the "
        "approach works but a step is asserted rather than argued. wrong: the conclusion or "
        "an essential step is false. When unsure between sound and gap, say gap."
    )
    first_fault: str = Field(
        description="The FIRST step that does not follow, quoted, and one sentence on why. "
        "Empty only when the verdict is sound."
    )
    repair: str = Field(
        description="What would have to be shown to close that first fault. Empty when the "
        "verdict is sound or the whole approach is wrong."
    )
```

Three outcomes rather than a boolean, with the tie-break in the description: *when unsure
between sound and gap, say gap*. A checker that gives the benefit of the doubt passes wrong
proofs, the only failure mode here that costs anything. And `first_fault` asks for the
**first** and nothing else: a list of six is not actionable when the first invalidates the
rest.

## Step 4 — send the solvers off in different directions

```python
#: The angles the solvers are sent off on. One session apiece, and none of them is told that
#: the others exist: an attempt that hedges towards what another might be doing is an attempt
#: that has been contaminated. Index `attempts` into this; it wraps.
ANGLES = (
    "Work directly from the definitions. Take the shortest route you can see and make every "
    "step airtight.",
    "Look for the structure first -- an invariant, a symmetry, a monotone quantity, something "
    "conserved -- and let the proof fall out of it.",
    "Try the extremes and the small cases by hand until you can see the pattern, then prove "
    "the pattern rather than the cases.",
    "Assume the conclusion fails and chase the contradiction. If that leads nowhere, say so "
    "and prove it directly instead.",
    "Find the strongest statement you can actually prove, then show it implies what was "
    "asked. A generalisation is often easier than the instance.",
    "Reduce it to a problem you already know how to do, and prove the reduction as carefully "
    "as you prove the rest.",
)
```

Four copies of one prompt fail the same way. Four different opening moves fail differently, and
a checker only has to find one that does not fail at all.

## Step 5 — make "sound" mean two people said so

```python
async def sound(checker: Agent, asked: str) -> tuple[bool, Verdict | None]:
    """Two independent readings of one attempt, and whether both called it sound.

    Two sessions rather than two questions in one: a checker that has just said "sound" is
    being asked to disagree with itself, which is not the same question.
    """
    read = await checker.abatch([asked, asked], suppress=True, schema=Verdict)
    both = [one for one in read if one is not None]
    if len(both) < 2:
        return False, next(iter(both), None)
    if all(one.verdict == "sound" for one in both):
        return True, both[0]
    # The harsher of the two is the one worth mending against.
    return False, next(one for one in both if one.verdict != "sound")
```

`abatch` is the agent called once per prompt, all at the same time, one session apiece and none
kept. Here, the same prompt twice: two conversations that have never met, answering the same
question.

## Step 6 — write the loop

The flow is `async def` because it has more than one turn going at a time. Nothing else about
running it changes.

```python
import asyncio
from pathlib import Path

from hmz.flows import flow


@flow(about="A maths problem, attacked from several angles and checked by somebody else")
async def run(agents: Agents, task: str, config: Setup | None = None) -> None:
    setting = config or Setup()

    stated = await agents.reader.aturn(READ + task, suppress=True, schema=Statement)
    if stated is None:
        raise RuntimeError("the reader could not state the problem; nothing to solve")
    traps = bulleted(stated.traps)
    print(f"To prove: {stated.claim}\n")

    mending = agents.mender.new()
    carried = ""

    for round_ in range(setting.rounds):
        # One session per angle, all of them at once, none of them told about the others.
        asked = [
            SOLVE.format(
                task=task,
                claim=stated.claim,
                form=stated.answer_form,
                traps=traps,
                angle=ANGLES[at % len(ANGLES)],
            )
            for at in range(setting.attempts)
        ]
        attempts = [one for one in await agents.solver.abatch(asked, suppress=True) if one]
        # What the mender rescued last round is read again beside this round's fresh angles,
        # so a repair has to survive the same two checkers rather than being trusted.
        if carried:
            attempts.insert(0, carried)
        if not attempts:
            continue

        read = await asyncio.gather(
            *(
                sound(
                    agents.checker,
                    CHECK.format(task=task, claim=stated.claim, traps=traps, attempt=one),
                )
                for one in attempts
            )
        )
        for attempt, (passed, _) in zip(attempts, read, strict=True):
            if passed:
                Path(setting.output).write_text(attempt + "\n", encoding="utf-8")
                print(f"Round {round_ + 1}: two checkers agree. Written to {setting.output}.")
                return

        # Nothing survived. Mend the one that got furthest -- a gap is a proof with a hole in
        # it, and a wrong one is a proof to abandon.
        nearest = next(
            (
                (attempt, verdict)
                for attempt, (_, verdict) in zip(attempts, read, strict=True)
                if verdict is not None and verdict.verdict == "gap"
            ),
            None,
        )
        if nearest is None:
            print(f"Round {round_ + 1}: no attempt worth mending; going again.")
            carried = ""
            continue
        attempt, verdict = nearest
        print(f"Round {round_ + 1}: {verdict.first_fault[:120]}")
        carried = mending(
            MEND.format(
                task=task,
                claim=stated.claim,
                attempt=attempt,
                fault=verdict.first_fault,
                repair=verdict.repair,
            ),
            suppress=True,
        )

    print(f"{setting.rounds} rounds and nothing two checkers would both sign off. Nothing written.")
```

Follow one round through it. Four solvers go off at once on four angles; each attempt then gets
two checkers, running at once too — eight checker sessions in parallel. An attempt called sound
twice is written out and the run is over. Otherwise the *first attempt with a gap* — not one
called wrong, which is a dead end rather than a hole — goes to the mender, and its repair faces
the same two checkers next round. The mender holds the only session, being the only agent that
gains by remembering.

::: details The four prompts, in full
One helper and four constants. Put them above `run`.

```python
def bulleted(lines: list[str]) -> str:
    """The traps, as the prompt wants them."""
    return "\n".join(f"- {one}" for one in lines)


READ = """Read this problem and do NOT solve it. Somebody else is about to. Your job is to say \
exactly what has to be established, what a complete answer looks like, and where solutions to \
this kind of problem usually go wrong.

Problem:
"""

SOLVE = """Solve this problem and write a complete, self-contained proof.

Problem:
{task}

What has to be established:
{claim}

What a complete answer has to look like:
{form}

Known ways to get this wrong -- your proof must not do any of these:
{traps}

How to go at it:
{angle}

Write the proof itself and nothing else: no preamble, no summary of your approach, no note \
about what you tried. Every step that is not immediate must carry its reason. If you cannot \
finish it, write what you have and say plainly which step is missing rather than papering over \
it."""

CHECK = """Check this proof. You did not write it and you do not know who did.

Problem:
{task}

What has to be established:
{claim}

Known ways to get this wrong:
{traps}

The proof:
{attempt}

Read it one step at a time and stop at the first step that does not follow from what came \
before it. Do not fix it, do not finish it, and do not give it the benefit of the doubt: an \
assertion with no argument behind it is a gap even when it is true."""

MEND = """Here is an attempt at the problem and what a checker said was wrong with it.

Problem:
{task}

What has to be established:
{claim}

The attempt:
{attempt}

The first fault, according to the checker:
{fault}

What would close it:
{repair}

Rewrite the proof with that fault closed. Keep whatever was already sound. If the fault cannot \
be closed because the approach itself is wrong, say so in one line and start again from a \
different one. Write the proof and nothing else."""
```
:::

## Step 7 — give the flow a skill

A **skill** is a directory with a `SKILL.md` in it, and a flow's own skills live inside the
flow. Every session any of the four opens gets it mounted.

Write `.humanize/flows/prove/skills/reading-a-proof/SKILL.md`:

```markdown
---
name: reading-a-proof
description: How to read a proof you did not write, and how to write one that will be read that way. Use when checking, mending or writing a mathematical argument.
---

# Reading a proof

A proof is read one step at a time, in order, and the reading stops at the first step that does
not follow. Everything after that step is unread.

## Checking

These are gaps, not quibbles:

- **"Clearly", "obviously", "it is easy to see".** Each one is a step somebody decided not to
  write.
- **"Similarly", "the other case is analogous".** Check that the other case *is* analogous.
- **An unstated boundary.** `n = 0`, the empty set, the equal case in a strict inequality, a
  denominator that can be zero.
- **A converse used as if it were the statement.**
- **An existence claim with no witness and no argument.**
- **Induction with no base case.**

Say where the *first* one is, quote it, and stop.
```

Why a skill rather than more prompt? Because it is shared: the checker needs it to judge, the
solver to write something that will survive judging, the mender both. One file, mounted on
every session, is one place to change your mind about what a gap is — and editing it changes
how the whole flow reads proofs without touching the Python. See [Skills](/user/skills).

## Step 8 — run it

```sh
export DEEPSEEK_API_KEY=sk-…
hmz exec -f prove \
    -a dsh/deepseek-v4-pro:high -a dsh/deepseek-v4-pro:high \
    -a dsh/deepseek-v4-pro:high -a dsh/deepseek-v4-pro:high \
    "$(cat PROBLEM.md)"
```

Four `-a` flags, in the order `Agents` declares them: reader, solver, checker, mender.

```console
To prove: For the unique sequence (a_n)_{n >= 1} defined by a_1 = 1 and a_{n+1} = a_n + 1/a_n
for every integer n >= 1, prove that the hundredth term satisfies a_100 > 14.

Round 1: two checkers agree. Written to solution.md.
```

```sh
cat solution.md
```

```console
We prove first, by induction, that every term is defined and positive.
…
Now square the recurrence. For every n >= 1,

    a_{n+1}^2 = (a_n + 1/a_n)^2 = a_n^2 + 2 + 1/a_n^2.

Since a_n > 0, we have 1/a_n^2 > 0, and therefore

    a_{n+1}^2 > a_n^2 + 2.                                    (1)

We now prove by induction that a_n^2 > 2n - 1 for every n >= 2.
…
Applying the inequality with n = 100, we obtain a_100^2 > 199. Because a_100 > 0, taking
square roots gives a_100 > sqrt(199). Finally, since 199 > 196 = 14^2, we have a_100 > 14.
```

The proof squares the recurrence to find the invariant, the one move the problem is about. Note
what the flow did *not* do: no agent graded itself, and nothing was accepted for sounding
confident.

## Step 9 — give it something harder

Two more problems, run exactly the same way. The first has a plausible wrong opening move; the
second is a competition problem.

```sh
cat > PROBLEM.md <<'EOF'
Let a, b, c be positive real numbers with a + b + c = 3.

Prove that

    a/(1 + b^2) + b/(1 + c^2) + c/(1 + a^2) >= 3/2.
EOF
```

The obvious first thought — "by symmetry the minimum is at `a = b = c`" — is wrong, because the
expression is cyclic rather than symmetric, and a solver that takes it writes something that
reads well and proves nothing. The run above bounded `x²/(1+x²) ≤ x/2` instead, so
`a/(1+b²) ≥ a − ab/2`, and summed the three.

Then IMO 2024, problem 1:

```sh
cat > PROBLEM.md <<'EOF'
Determine all real numbers alpha such that, for every positive integer n, the
integer

    floor(alpha) + floor(2*alpha) + ... + floor(n*alpha)

is a multiple of n. Prove that your answer is complete: that every alpha you
give works, and that no other alpha does.
EOF
```

```console
To prove: Determine exactly the set of all real numbers alpha such that … the solution must
establish both that every alpha in the proposed set has this property for all n and that any
real alpha with this property for all n lies in the proposed set.

Round 1: two checkers agree. Written to solution.md.
```

169 lines, correct answer (`α = 2m` for integer `m`), and both directions proved — the half
that the reader's `answer_form` field was there to insist on.

All three ended in round one, on four solvers apiece. The mending path is for the rounds that
do not, and what it prints then is the checker's `first_fault`, quoted back to you before the
mender is handed it.

::: tip Reading a round that did not end
`Round n: <quoted fault>` means no attempt survived two checkers and the nearest one has gone
to the mender. `Round n: no attempt worth mending; going again` means every attempt was called
*wrong* rather than *gapped* — the approach is the problem, not a step in it, so there is
nothing to repair and the next round starts clean.
:::

## What to change

**Widen it.** `attempts: 8` doubles the solvers and the checkers with them. Nothing here caps
how many turns run at once, so how wide to go is a question about your rate limits — `abatch`
takes `at_once=` when you want the flow to queue rather than the API to refuse.

**Make the checkers disagree on purpose.** Give `checker` a different backend from `solver`
with a second `-a`. Two models that fail differently is the strongest version of this design.

**Require three of three.** Change `[asked, asked]` to `[asked, asked, asked]` and the `all(…)`
still holds — a straight trade of cost against confidence.

**Point it at something checkable.** If your problems have machine-checkable answers — Lean, a
numeric result, a program — replace the second checker with the machine. A proof assistant that
says yes is worth more than any number of agents that say yes.

## Next

You have written both shapes of flow. What is left is a page per thing a weaver reaches for in
the [Weaver Guide](/weaver/), and the Python these two called: [Flows](/reference/flows) and
[Agents](/reference/agents).
