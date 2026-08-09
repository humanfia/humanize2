# Run it unattended

`hmz exec` runs a flow with nobody at a prompt — which is what a script, a cron entry or a CI
job wants. Below: how to write the agent line, narrow what an agent may do, pass settings in,
and read the exit status.

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

## Write an agent

An agent is a CLI, a model and an effort. Two spellings mean exactly the same thing:

```
claude/claude-opus-4-8:high
cli=claude,model=claude-opus-4-8,effort=high
```

The written-out form exists because a model or an effort may hold the punctuation the short
form separates on. It also exists because some settings have no unambiguous short spelling.

Read an agent from both ends. The CLI comes first; the effort comes after the **last** colon.
That is why a model with slashes in it works:

```sh
hmz exec -f ralph_loop -a kimi/kimi-code/k3:swarmmax "$(cat TASK.md)"
hmz exec -f ralph_loop -a pi/openai-codex/gpt-5.5:high "$(cat TASK.md)"
hmz exec -f ralph_loop -a opencode/opencode/big-pickle:high "$(cat TASK.md)"
```

`<model>` and `<effort>` are whatever the CLI is asked for. humanize does **not** check them
against a list, so a model your account has still works even when this documentation does not
mention it.

## Narrow what an agent may do

You can narrow what an agent may do only in the written-out form:

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review this repository and write the findings to REVIEW.md"
```

Four rungs exist: `read-only`, `workspace-write`, `auto`, `bypass`. `bypass` is the default. A
misspelling is refused before any agent runs. See [Permissions](/guide/permissions).

## Run with nobody at a prompt

The one difference is that nobody is at a prompt, and it has one consequence: **an agent that
stops to ask a question is told nobody answered and carries on**. It does not wait forever on a
reply that is not coming.

There is nothing to switch. It is [`/afk`](/guide/afk) always.

Two things follow:

- A flow whose other side is [the person](/guide/human-agent), such as `chat`, answers nothing.
  So it does the one thing it was given, once.
- A flow that asks you for [an answer in a shape](/guide/shapes) gets `None`, and it had better
  handle that.

## See what is checked first

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

Everything that can be known before the first turn is checked before the first turn. This is
deliberate: an hour into a loop is the wrong place to find out you miscounted.

![hmz exec refusing a malformed agent, the wrong agent count, and a flow that is not
there](/demo/checks.gif)

## Pass a task that starts with a dash

The `--` ends the flags, so a task that starts with a dash is read as the task:

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

The flow's own model checks the settings **before the first turn**. So a combination the flow
will not run is refused where you wrote it. See [tutorial 8](/guide/flow-settings).

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

The [cycle](/guide/tracing#what-a-run-writes-down) records that run as **`failed`**. `stopped`
is for an agent [told to stop by hand](/guide/stopping), with ctrl+c twice in the interface or
`agent.stop()` from inside the flow. Nothing on a command line tells the two apart.

## Opening the interface already set up

`hmz` with `-f`, `-a` and `-c`, but no `exec`, opens the **interface** on that setup rather
than running it. Nothing is started. The first thing you say is still what starts it.

```sh
hmz -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high
```

This is useful for a run that is always the same run, and for checking a line before committing
it to cron. What the line says is checked before the interface opens.

## See also

- [Permissions](/guide/permissions)
- [Flow settings](/guide/flow-settings)
- [What a run writes down](/guide/tracing#what-a-run-writes-down)
- [Stopping](/guide/stopping)
- [Read the run back](/guide/tracing)
