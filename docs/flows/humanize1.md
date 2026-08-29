---
pageClass: hmz-feature
---

# official/humanize1

[PolyArch/humanize](https://github.com/PolyArch/humanize) — the Claude Code plugin humanize
grew out of — as three flows, each set up on its own agents and stopping on its own. `gen-idea`
opens a loose idea into a repo-grounded draft, `gen-plan` turns that draft into a plan both
sides have converged on, and `rlcr` builds the plan under review until nothing is left to say.

```sh
hmz exec -f official/humanize1:gen-idea -a claude/claude-opus-5:max \
    "add undo/redo to the editor"
hmz exec -f official/humanize1:gen-plan \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "add undo/redo to the editor"
hmz exec -f official/humanize1:rlcr \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "build it"
```

Three rather than one because each is set up on its own: `/agents` asks one flow for the
drafter, one for the planner and the analyst that reads it, and one for the builder and the
reviewer. What passes between them is a file, as it is in the plugin — the draft, then the plan
— so an idea may be opened on one model, planned on another and built on a third, with whatever
reading and editing you like in between. They are [three flows in one
file](/reference/flows#several-flows-in-one-file).

Run it in a git repository: the work is anchored to the commit the plan was fixed in, and every
review reads what came after it.

## 1 · `gen-idea`

<HmzFlowShape flow="humanize1-gen-idea" />

One agent, `n` directions explored at once, one draft written out. `--n` and `--output` are the
two settings, under the names the plugin gives them.

## 2 · `gen-plan`

<HmzFlowShape flow="humanize1-gen-plan" />

The planner holds one session for the whole of the planning; the analyst arrives fresh each
time and reads the plan against the repository. They converge, or the round limit stops them.
`--input` names the draft to plan from, `--discussion` and `--direct` are the two modes, and
`alternative_plan_language` writes a translated plan beside the plan.

A plan that still says `PENDING` on a `Pending User Decisions` entry stops the run rather
than finishing it: `rlcr` never waits for a person, so a decision left undecided here would
idle the loop, not stop it. The plan stays on disk with every position written down —
answer each `Decision Status` in the file, or run `gen-plan` again with somebody at the
prompt.

## 3 · `rlcr`

<HmzFlowShape flow="humanize1-rlcr" />

The loop is a **hook**. The plugin blocks Claude's exit and puts the round to Codex there; so
does this — a [`Moment.STOP` hook](/features/hooks) on the builder, which is the same sentence.
A round ends when the builder believes the whole plan is done and tries to stop, and what the
reviewer says is what it hears instead of stopping. The plugin's tool validators are hooks too,
on `Moment.PERMISSION_REQUEST`, which is why the builder has to be a backend that runs them.

Every flag the plugin takes is a field on that phase's own settings, under the plugin's own
name for it: `--max`, `--full-review-round`, `--skip-impl`, `--agent-teams`, `--yolo`,
`--plan-file`, `--base-branch`, and the rest. `/config` is all of them.

It writes what the plugin writes, where the plugin writes it: `.humanize/rlcr/<timestamp>/`
with `state.md`, `goal-tracker.md`, and a prompt, summary, contract and review per round — so
`humanize monitor rlcr` reads a run of this.

## Four things done another way

The plugin's mechanism, where humanize's is not the same mechanism:

| | |
| --- | --- |
| `codex review --base <ref>` | Takes no prompt and is a Codex feature. Here the reviewer is whichever agent was chosen, so the code review is **asked for**, in a prompt that asks for exactly the `[P0-9]` output the loop then reads the same way. |
| `--codex-timeout` | Cannot cut a turn short from here: a review that ran over is treated as a review that failed, which is the state the plugin's own timeout leaves the round in. |
| `/humanize:ask-codex` | A task the plan tags `analyze` is a shell script the builder runs there. Here the builder has no way to reach the reviewer mid-round, so it is told to put the question in its round summary, where the reviewer answers it. |
| The plan quiz | Put to the person the way a coding agent's own question is put, so a run with nobody at the prompt is answered with nothing rather than waiting for a person who is not there. |

## What it keeps

`rlcr` is a loop meant to run for days, so a run of it can be picked up: it keeps **which**
`.humanize/rlcr/` directory the loop is in and the round it reached, and reads `state.md` back
as it stands rather than stamping a new directory beside a week of rounds. Everything else
about the loop is already in that directory in the plugin's own format, and a second copy here
would be a second place for it to be wrong.

A loop carries on with the settings it was set up with, which is what carrying on means. A run
set up differently is neither quietly overridden nor quietly ignored: it says which setting it
disagrees with the loop about, and starts a loop of its own. The agents are the one thing that
is not a setting — `/agents` chooses them per run, and the state file is brought up to date to
say who is reading the rounds.

`gen-idea` and `gen-plan` keep nothing. Each writes one file, running one again is meant to
write another, and between their turns there is nothing a second run could honestly carry on
from.

## See also

- [The moments of a turn](/features/hooks) — what a `STOP` hook is, and the six others
- [official/rlar](/flows/rlar) — the same actor-and-reviewer shape, without the plugin's format
- [A flow that calls a flow](/guide/calling-flows) — running one of these three from inside another flow
