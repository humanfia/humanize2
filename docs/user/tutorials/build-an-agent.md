# Build a coding agent

**An afternoon.** You will take one loose sentence — "a small terminal coding agent for
`deepseek-v4-flash`" — through [`official/humanize1`](https://github.com/humanfia/flowverse)'s
three phases, and end with a repository that did not exist when you started.

The three phases are three separate flows. That is the point of them: each is set up on its
own, stops on its own, and hands the next one a file rather than a conversation.

::: tip Before you start
Finish the [quickstart on the home page](/#run-a-flow). The third phase needs a builder that
can run permission hooks, which today means Claude Code or Codex; the first two run on
anything,
including DeepSeek Harness.
:::

## The shape of work this is for

The other two tutorials point an agent at code that already exists. This one starts from
nothing, and starting from nothing is where agents go wrong in a particular way: they build the
first thing that matches the words in your sentence, and you find out an hour later that it was
not the thing you meant.

`humanize1` is humanize's rebuild of [the humanize Claude Code
plugin](https://github.com/humanfia/humanize-plugin), and its answer is to spend two phases
before any code is written:

| | | |
| --- | --- | --- |
| **`gen-idea`** | 1 agent | Opens a loose idea into a repo-grounded draft, by exploring several directions at once and picking one |
| **`gen-plan`** | 2 agents | Turns that draft into a plan, with a second agent arguing against it until they converge |
| **`rlcr`** | 2 agents + you | Builds the plan under review, round after round, until the reviewer has nothing left |

What passes between them is a file — the draft, then the plan. So you can open an idea on one
model, plan it on another, build it on a third, and read and edit both files in between.

## Step 1 — make a repository

```sh
mkdir -p ~/tmp/flashagent && cd ~/tmp/flashagent
git init -q
echo "# flash-agent" > README.md
git add -A && git commit -qm "nothing yet"
```

`rlcr` needs a git repository, because it anchors the work to the commit the plan was fixed in
and reads every review against what came after.

## Step 2 — open the idea

```sh
export DEEPSEEK_API_KEY=sk-…
hmz exec -f official/humanize1:gen-idea \
    -a dsh/deepseek-v4-pro:high \
    "A small terminal coding agent for deepseek-v4-flash. One Python package, one entry point, no framework. It talks to the DeepSeek API with the OpenAI-compatible chat completions endpoint, holds a message list, and offers the model three tools: read a file, write a file, run a shell command. It loops until the model answers without asking for a tool. It is meant for a fast, cheap model, so it must keep the context small and the tool schemas short."
```

One agent, because there is only one job here. It generates several distinct directions the
idea could be taken in — six by default — explores each against the actual repository, and
writes up one as the primary with the rest recorded as alternatives.

The draft lands in `.humanize/ideas/`:

```sh
ls .humanize/ideas/
```

```console
a-small-terminal-coding-agent-for-20260817-020714.md
```

```sh
head -20 .humanize/ideas/*.md
```

```console
# Stdlib OpenAI-Compatible DeepSeek Chat Client

## Original Idea

A small terminal coding agent for deepseek-v4-flash. …

## Primary Direction: Stdlib HTTP client

### Objective Evidence

- Import checks confirm `openai`, `httpx`, and `requests` are all MISSING in this
  environment, while `urllib.request` is present in Python 3.12.13 stdlib — stdlib is
  both necessary and sufficient for a zero-dependency client.
- `git ls-files` shows only `README.md`, so there is no existing HTTP/API layer to
  reconcile with.
```

Read the "Objective Evidence" lines. Each direction had to be justified against something the
agent checked in this repository or this environment, not against what usually makes a good
design. That is what "repo-grounded" means, and it is the difference between a draft and a
plausible essay.

::: tip Change how wide it explores
`--n` is a field on the flow's settings, so `-c setup.yaml` with `n: 3` narrows it and `n: 10`
widens it. In the interface, the same fields are on `/config`. See [A flow with settings of its
own](/weaver/flow-settings).
:::

**Read the draft before going on.** It is a file, and editing it is expected. If it picked the
wrong primary direction, promote one of the alternatives yourself — that is much cheaper here
than after the plan is written.

## Step 3 — argue it into a plan

```sh
hmz exec -f official/humanize1:gen-plan \
    -a dsh/deepseek-v4-pro:high \
    -a dsh/deepseek-v4-pro:high \
    "A small terminal coding agent for deepseek-v4-flash. …"
```

Two agents this time: **the planner**, which writes, and **the analyst**, which reads what the
planner wrote and says what is wrong with it. They go round until the analyst has nothing
required left — up to three rounds — and the task you pass is what those rounds are judged
against. The planner holds one session for the whole of the planning, so it remembers how the
plan got to where it is; the analyst arrives fresh.

This phase takes a while, and what it produces is long:

```sh
wc -l docs/plan.md
```

```console
478 docs/plan.md
```

The plan is not prose. It is an issue map, a numbered list of acceptance criteria, and a set of
decisions with their alternatives recorded:

```console
| ID | Finding | Dimension | Severity | Resolution in this plan |
|----|---------|-----------|----------|-------------------------|
| I-2 | Draft assumes OpenAI-identical `tool_calls`; DeepSeek adds `reasoning_content`,
  non-OpenAI `finish_reason` values, and documents `function.arguments` as "not always
  valid JSON". | Functionality | High | Full `finish_reason` set, `reasoning_content`/
  `usage` surfaced, tolerant multi-tool parsing (AC-2/AC-6/AC-10). |
| I-10 | `thinking` defaults to `enabled`; hidden reasoning tokens undermine the "fast,
  cheap, small context" premise. | Functionality | High | Explicit `thinking` toggle,
  candidate default `disabled` … |
```

Neither of those came from your sentence. They came from an analyst reading a draft and going
to look at what the DeepSeek API actually returns.

**Read `docs/plan.md` now.** This is the last cheap moment. From here the plan is fixed: the
third phase treats it as the contract and will not let the builder edit it.

::: details Skipping the argument
`mode: direct` in a `-c setup.yaml` writes the plan once with no convergence rounds. Faster,
and worse — the round trip is where the analyst finds the things the planner assumed.
:::

## Step 4 — build it under review

```sh
hmz exec -f official/humanize1:rlcr \
    -a claude/claude-opus-4-8:high \
    -a codex/gpt-5.6-sol:high \
    "build it"
```

Two `-a` flags — **the builder** and **the reviewer**. The flow also drives a third agent, the
person at the prompt, and that one is not named on the command line: with nobody there, they
answer with nothing and the run carries on.

The task string is not put to any agent. `docs/plan.md` is what the loop runs on; `"build it"`
is only what the run is called wherever you watch it.

The builder must be Claude Code or Codex because this phase hangs a hook on the
`PERMISSION_REQUEST` moment, and those are the two backends that run it. The hook is what keeps
the plan fixed and the loop's own state out of the builder's hands. Any backend can review.

### The loop is a hook

The builder is not asked "is it finished?". It is left to work until it believes the plan is
done and tries to **stop** — and a `Stop` hook catches that. What the reviewer says is what the
builder hears instead of stopping.

That is the same sentence as the original Claude Code plugin, which blocks Claude's exit and
puts the round to Codex there. See [Hooks](/weaver/hooks).

### What a round looks like

The builder works, tries to stop, gets a code review instead. The reviewer is asked for
`[P0-9]` findings, and the loop reads those rather than looking for a verdict in a paragraph.
Every fifth round, the reviewer is asked a different question — whether what has been built
still matches the plan at all. The loop stops after 42 rounds unless you set `max` otherwise.

The loop keeps its own state where the plugin keeps it, so you can watch it from another
terminal:

```sh
ls .humanize/rlcr/*/
```

```console
goal-tracker.md  plan.md  round-0-contract.md  round-0-prompt.md  round-0-summary.md  state.md
```

```sh
head -8 .humanize/rlcr/*/state.md
```

```console
---
current_round: 0
max_iterations: 42
codex_model: gpt-5.6-sol
codex_effort: high
codex_timeout: 5400
push_every_round: false
full_review_round: 5
```

One `round-N-summary.md` per round, and the round the builder is on. The plan's acceptance
criteria are what to check the work against, because they are what the reviewer checks it
against.

## Step 5 — see what it built

Every round commits, so you can look at the work a round at a time:

```sh
git log --oneline
```

```console
f835006 Round 1: close reviewer P1 contract gaps across the agent
e21d3a7 Implement end-to-end flash_agent DeepSeek coding agent (Round 0)
f0e8d2d init
```

That is round zero building the whole thing and round one closing what the reviewer marked
`P1`. The numbers below are from that point; the loop was still going.

```sh
wc -l flash_agent/*.py tests/*.py
```

```console
  451 flash_agent/client.py
   98 flash_agent/cli.py
   95 flash_agent/context.py
   39 flash_agent/__init__.py
   94 flash_agent/loop.py
   10 flash_agent/__main__.py
  193 flash_agent/tools.py
   …
 1882 total
```

```sh
python -m pytest -q
```

```console
........................................................................ [100%]
72 passed in 0.35s
```

By the end of round one that was 118 tests, which is what a reviewer that will not say `done`
does to a suite.

Now use it — the thing at the end runs:

```sh
mkdir -p /tmp/flashtry && printf 'def add(a, b):\n    return a - b\n' > /tmp/flashtry/calc.py
python -m flash_agent --workdir /tmp/flashtry --allow-shell \
    "Read calc.py, fix the bug in it, and say what you changed."
```

```console
Fixed. **What changed:** In `add()`, changed `return a - b` to `return a + b`. The
function was subtracting instead of adding.
```

```sh
cat /tmp/flashtry/calc.py
```

```console
def add(a, b):
    return a + b
```

A coding agent, built from one sentence, that just fixed a bug in a file.

Look at `--allow-shell` in that command. You never asked for it. It came out of the draft's
fifth direction — "guarded shell execution" — became a decision in the plan, and turned into an
environment gate the builder implemented. That is the two planning phases earning their time.

## Step 6 — read the whole thing back

```sh
hmz trace collect
```

Three runs happened here, one per phase, and each is its own **epic** — a directory under
`~/.humanize/epics/`. `hmz trace collect` collects the last one; `/epics` in the interface
lists all of them and collects whichever you pick.

The `rlcr` trace is the interesting one. The builder is a single long track, and the reviewer
is a row of short ones — and the gaps between them are where the hook fired.

## What to change

- **Run the phases on different models.** They are three flows precisely so you can. Plan on
  the strongest model you have, build on a cheaper one, review on a third.
- **Stop between phases and edit the file.** The draft and the plan are both files, and both
  are meant to be read. The plugin this is a rebuild of has a `refine-plan` command; here you
  have a text editor, which is the same thing.
- **Point `rlcr` at a plan you wrote yourself.** `plan_file` in a `-c setup.yaml` names it.
  Nothing about the third phase requires the first two — it requires a plan.

## Next

You have now run three flows somebody else wrote. Whoever writes one is a **weaver**, and the
[Weaver Guide](/weaver/) teaches that — starting with [Build under
test](/weaver/tutorials/checked-build).
