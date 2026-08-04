# 4 · Run it unattended

**Ten minutes.** The same flows, with nobody watching — which is what a script, a cron entry or a
CI job wants.

::: tip Before you start
[Two agents at once](/guide/tutorial-two-agents).
:::

## The shape of the line

```sh
hmz exec -f <flow> -a <agent> [-a <agent>...] "<task>"
```

| | |
| --- | --- |
| `-f` | the flow, by name or by path |
| `-a` | **one agent**, repeated once for each the flow drives, in the order it takes them |
| the last argument | the task, as the text itself |

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
```

## Step 1 — write an agent

An agent is a CLI, a model and an effort. Two spellings, meaning exactly the same thing:

```
claude/claude-opus-4-8:high
cli=claude,model=claude-opus-4-8,effort=high
```

The written-out form exists because a model or an effort may hold the punctuation the short form
separates on — and because some settings have no unambiguous short spelling.

Read from **both ends**: the CLI from the front, the effort from after the **last** colon. Which
is why a model with slashes in it works:

```sh
hmz exec -f ralph_loop -a kimi/kimi-code/k3:swarmmax "$(cat TASK.md)"
hmz exec -f ralph_loop -a pi/openai-codex/gpt-5.5:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a opencode/opencode/big-pickle:high "$(cat TASK.md)"
```

`<model>` and `<effort>` are whatever the CLI is asked for. humanize does **not** check them
against a list, so a model your account has and this documentation does not still works.

## Step 2 — narrow what an agent may do

Only in the written-out form:

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review this repository and write the findings to REVIEW.md"
```

Four rungs: `read-only`, `workspace-write`, `auto`, `bypass`. `bypass` is the default. A
misspelling is refused before any agent runs. See [Permissions](/features/permissions).

## Step 3 — nobody is at a prompt

That is the whole difference, and it has one consequence: **an agent that stops to ask a question
is told nobody answered and carries on**, rather than waiting forever on a reply that is not
coming.

There is nothing to switch. It is [`/afk`](/features/afk) always.

Two things follow:

- A flow whose other side is [the person](/features/human-agent) — `chat`, for instance — answers
  nothing and so does the one thing it was given, once.
- A flow that asks you for [an answer in a shape](/features/shapes) gets `None`, and had better
  handle it.

## Step 4 — everything that is checked first

Run these on purpose. Each is refused before a single turn:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-5:max "fix the build"
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given

$ hmz exec -f ralph_loop -a claude:high "fix the build"
hmz exec: error: bad agent 'claude:high': expected CLI[@PROVIDER]/MODEL:EFFORT or
cli=CLI,model=MODEL,effort=EFFORT[,provider=PROVIDER][,permission=PERMISSION]

$ hmz exec -f nosuchflow -a claude/claude-opus-5:max "fix the build"
hmz exec: error: nosuchflow: no flow to read: a flow is a directory with an __init__.py in it
```

Everything that can be known before the first turn is checked before the first turn. That is a
deliberate property: an hour into a loop is the wrong place to find out you miscounted.

![hmz exec refusing a malformed agent, the wrong agent count, and a flow that is not there](/demo/checks.gif)

## Step 5 — a task that starts with a dash

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high -- "--force is not a flag here"
```

## Step 6 — a flow with settings

For a flow that says it [can be set up](/reference/flows#settings-of-the-flow-s-own), write a YAML
file of what choosing the flow would have asked for:

```yaml
# setup.yaml
rounds: 9
mode: slow
```

```sh
hmz exec -f official/humanize1:rlcr -c setup.yaml \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:xhigh "add undo"
```

The flow's own model checks it **before the first turn**, so a combination the flow will not run
is refused where you wrote it. See [tutorial 8](/guide/tutorial-flow-settings).

## Step 7 — exit statuses

| | |
| --- | --- |
| `0` | it did what it was asked |
| `1` | it could not — no such provider, target unreachable, a turn that could not be supervised |
| `2` | the command line was wrong |
| `130` | interrupted |

Which is enough to script:

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)" || {
    echo "the loop did not finish" >&2
    exit 1
}
```

## Step 8 — stopping one

**ctrl+c.** The interrupt reaches the whole process group, so the agent's own process takes it
too: the turn under way dies with it, what it was doing is left where it got to, and the
command exits `130`.

The [cycle](/features/tracing#what-a-run-writes-down) records that run as **`failed`**.
`stopped` is for an agent [told to stop by hand](/features/stopping) — esc in the interface, or
`agent.stop()` from inside the flow — and nothing on a command line tells one.

## Opening the interface already set up

`hmz` with `-f`, `-a` and `-c` — but no `exec` — opens the **interface** on that setup rather than
running it. Nothing is started; the first thing you say is still what starts it.

```sh
hmz -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high
```

Useful for a run that is always the same run, and for checking a line before committing it to
cron: what the line says is checked before the interface opens.

## What you now know

- `-a` is positional and repeated; `-f` takes a name or a path.
- The written-out form is where `permission=` and `provider=` live.
- Unattended means questions are answered "nobody is there".
- Everything knowable up front is checked up front.

## Next

[Read the run back](/guide/tutorial-trace).
