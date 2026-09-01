# Run it unattended

`hmz exec` runs a flow with nobody at a prompt — which is what a script, a cron entry or a CI
job wants. Reach for it once a run is the same run every time.

## The shape of the line

```sh
hmz exec -f <flow> -a <spec>[,<spec>...] [-a ...] "<task>"
```

| | |
| --- | --- |
| `-f` | the flow, by name or by path |
| `-a` | the agents, separated by commas and the option repeated as often as suits — one for each the flow drives, in the order it takes them |
| the last argument | the task, as the text itself |

A flow of four agents is one option or four, whichever reads better in the line you are
writing; every `-a` adds to the same list in the order they were written.

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
```

## Write an agent

An agent is a CLI, an account, a model and an effort, and there is one way to write one:

```
[<name>=]<cli>[@<provider>]/<model>:<effort>
```

```
claude/claude-opus-4-8:high
claude@deepseek/claude-opus-4-8:high
reviewer=codex/gpt-5.6-sol:max
```

`@` names the [account](/user/providers) the turns run as — the account, not the model. `=` in
front names **which of the flow's agents this one is**, by the name the flow calls that place:
name every agent on the line or none of them, since an agent with no name fills the flow's next
place, and that cannot be counted while the others are filled by name.

```console
$ hmz exec -f official/rlar -a actor=claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "fix the build"
hmz exec: error: name every agent or none of them: an agent that names no place fills the flow's next one, which cannot be counted while the others are filled by name
```

Read an agent from both ends: the CLI comes first, and the effort comes after the **last**
colon. That is why a model with slashes in it works:

```sh
hmz exec -f ralph_loop -a kimi/kimi-code/k3:swarmmax "$(cat TASK.md)"
hmz exec -f ralph_loop -a pi/openai-codex/gpt-5.5:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a opencode/opencode/big-pickle:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a zcode/zai/glm-5.3:high "$(cat TASK.md)"
```

`<model>` and `<effort>` are whatever the CLI is asked for. humanize does **not** check them
against a list, so a model your account has still works even when this documentation does not
mention it.

## Narrow what an agent may do

The flow says it, where it declares the agent — not the line that runs it:

```python
class Agents(NamedTuple):
    reviewer: Annotated[Agent, AgentDefaults(permission="read-only")]
```

```sh
hmz exec -f ./review.py \
    -a codex/gpt-5.6-sol:high \
    "review this repository and write the findings to REVIEW.md"
```

Four rungs exist: `read-only`, `workspace-write`, `auto`, `bypass`. A place that says nothing
declares `bypass`, the loosest of them, which leaves its agent at whatever it came with; a
declaration only ever tightens. A rung there is not is refused before any agent runs. See
[Permissions](/user/permissions).

## Run with nobody at a prompt

Nobody at a prompt has one consequence: **an agent that stops to ask a question is told nobody
answered and carries on**, rather than waiting forever on a reply that is not coming. There is
nothing to switch. It is [`/afk`](/user/afk) always.

Two things follow:

- A flow whose other side is [the person](/weaver/human-agent), such as `chat`, answers nothing.
  So it does the one thing it was given, once.
- A flow that asks you for [an answer in a shape](/weaver/shapes) gets `None`, and the weaver
  who wrote it had better have handled that.

## Watch it while it runs

At a terminal, the run is drawn as it happens — which agent is working, what it says, the
tools it runs, and what each turn cost when it lands. A turn thinks for minutes and says
nothing for most of them, so a clock sits at the foot of the screen while it does:

```console
$ hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
● builder is working
● Bash(pytest -q tests/)
● I fixed add() and the tests pass.
✻ input 40.0k · output 1.2k · $0.61 · claude-opus-4-8 · builder
✻ Worked for 74s · builder
```

Redirect it and the escape sequences go: the same lines, plain. What each turn **answered**
goes to stdout and the run itself to stderr, so a script reads one without the other:

```sh
hmz exec -f chat -a claude/claude-opus-4-8:high "summarise CHANGELOG.md" > summary.txt
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)" 2> run.log
```

`NO_COLOR` turns colour off outright; `FORCE_COLOR` turns it on for a log that renders it.

## Read it with a program

`--json` writes the run as [NDJSON](https://github.com/ndjson/ndjson-spec) — one object per
thing an agent says, on stdout, flushed as it is said:

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high --json "$(cat TASK.md)" \
    | jq -c 'select(.kind == "result")'
```

Every object carries the agent, the backend and model, the conversation, the kind of thing it
was, the words, what the turn cost and when — the keys are in the
[CLI reference](/reference/cli#watching-a-run). While `--json` is on, nothing else reaches
stdout: whatever the flow prints goes to stderr, so one stray line cannot break the stream.

## See what is checked first

Run these on purpose. Each is refused before a single turn:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-5:max "fix the build"
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given

$ hmz exec -f ralph_loop -a claude:high "fix the build"
hmz exec: error: bad agent 'claude:high': expected [NAME=]CLI[@PROVIDER]/MODEL:EFFORT

$ hmz exec -f nosuchflow -a claude/claude-opus-5:max "fix the build"
hmz exec: error: nosuchflow: no flow to read: a flow is a directory with an __init__.py in it
```

A line written the way the old one was gets told so in as many words rather than being read as
a CLI with an odd name in it:

```console
$ hmz exec -f ralph_loop -a cli=claude,model=claude-opus-5,effort=high "fix the build"
hmz exec: error: bad agent 'cli=claude': cli= is gone: an agent is written CLI[@PROVIDER]/MODEL:EFFORT, and `=` names the place it fills, as in reviewer=claude/MODEL:EFFORT
```

Everything that can be known before the first turn is checked before the first turn: an hour
into a loop is the wrong place to find out you miscounted.

![hmz exec refusing a malformed agent, the wrong agent count, and a flow that is not
there](/demo/checks.gif)

## Pass a task that starts with a dash

`--` ends the flags, so a task that starts with a dash is read as the task:

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high -- "--force is not a flag here"
```

## Run a flow with settings

For a flow that says it [can be set up](/reference/flows#settings-of-the-flow-s-own), write a
YAML file of what choosing the flow would have asked for:

```yaml
# setup.yaml
rounds: 9
mode: slow
```

```sh
hmz exec -f official/humanize1:rlcr -c setup.yaml \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:xhigh "add undo"
```

The flow's own model checks the settings **before the first turn**, so a combination the flow
will not run is refused where you wrote it. What the weaver may ask for, and how, is in [Flow
settings](/weaver/flow-settings).

## Read the exit status

| | |
| --- | --- |
| `0` | it did what it was asked |
| `1` | it could not — no such provider, target unreachable, a turn that could not be supervised |
| `2` | the command line was wrong |
| `130` | interrupted |

You can script on these statuses:

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)" || {
    echo "the loop did not finish" >&2
    exit 1
}
```

## Stop a run

Stop it with **ctrl+c**. The interrupt reaches the whole process group, so the agent's own
process takes it too. The turn under way dies with it, what it was doing is left where it got
to, and the command exits `130`.

The [epic](/user/tracing#what-a-run-writes-down) records that run as **`failed`**. `stopped`
is for an agent [told to stop by hand](/user/stopping), with ctrl+c twice in the interface or
`agent.stop()` from inside the flow. Nothing on a command line tells the two apart.

Either way, a flow that says it [can be picked up](/user/resuming) carries on from what that
run left behind: run the same line again, or type `/resume` in the interface, which takes the
last run in the directory rather than a flow you name.

## Checking a line before it goes into cron

There is no line that opens the interface on a setup: `hmz` with no command opens on whatever
that directory was [last set up to run](/reference/tui#what-it-remembers), and the flow, its
agents and its settings are chosen at the prompt. So a line bound for cron is checked by
running it — everything knowable before the first turn is refused before the first turn, which
is why the refusals above cost two seconds rather than forty minutes.

For a run that is always the same run, set it up once at the prompt and leave it: `hmz` in that
directory opens on it every morning, and the line stays in cron for the nights nobody is there.

## See also

- [Permissions](/user/permissions)
- [Flow settings](/weaver/flow-settings)
- [Tracing](/user/tracing) — what a run writes down, and reading it back
- [Stopping](/user/stopping)
- [Picking a run up](/user/resuming) — carrying a stopped loop on where it left off
- [humanize in CI](/user/ci)
