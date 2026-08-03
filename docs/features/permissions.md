# Permissions

What an agent may do at all: one rung of a four-rung ladder, loosest last, set per agent.

The rungs are named the way these CLIs name them rather than in a vocabulary of humanize's own.

| Rung | What it means |
| --- | --- |
| `read-only` | It may look at anything and change nothing — no edits, no commands. |
| `workspace-write` | It may change the workspace it was given, and is stopped at the edge of it. |
| `auto` | It may reach for anything, and what it asks for is granted. |
| `bypass` | Nothing is asked and nothing is checked. **The default.** |

## Why `bypass` is the default

That is what a flow driving an agent unattended has always run it at. A flow watches its agent
rather than gating it, and a turn waiting on an approval nobody is there to give is a flow that
has stopped.

Anything tighter is a choice. Make it deliberately — see [Security](/guide/security).

## Setting it

::: code-group

```sh [command line]
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review the current change"
```

```python [Python]
CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission="read-only")
```

:::

`permission=` is available in the **written-out** form of `-a` only; there is no short spelling
for it. A misspelling is refused before any agent runs:

```console
hmz exec: error: bad agent 'cli=codex,model=gpt-5.6-sol,effort=high,permission=rdonly':
permission must be one of read-only, workspace-write, auto, bypass, not 'rdonly'
```

At the prompt it is the `permission` row of the sheet an agent is set up on, stepped on **←/→**.

## What each backend actually does

Every backend has a ladder of its own and none of them has the same four rungs, so each driver
reaches for whichever of its own settings says the same thing:

| Rung | Claude Code | Codex | Kimi Code | pi | opencode, mimocode |
| --- | --- | --- | --- | --- | --- |
| `read-only` | `plan` mode | `read-only` sandbox | plan mode | without `bash`, `edit`, `write` | `edit` and `bash` denied |
| `workspace-write` | `acceptEdits` mode | `workspace-write` sandbox | plan mode off | — | `webfetch` denied |
| `auto` | Claude's own `auto` mode | `workspace-write`, approvals on request | — | — | nothing denied |
| `bypass` | `bypassPermissions` | `danger-full-access` | `yolo` mode | — | — |

**Codex is the one backend here with a sandbox of its own**, so its rungs are the real thing
rather than an approximation of one.

Where a backend cannot tell two rungs apart it says so rather than pretending: **a dash is the
rung above it, run again**. Asking Kimi for `auto` gets you `workspace-write` behaviour, not a
quiet promotion to `bypass`; asking pi for anything above `read-only` gets you the same agent
three times over.

## `auto` is the rung where a hook gets a say

It is the one setting under which a backend actually asks before it acts *and waits for the
answer*. So it is the one rung where a [hook](/features/hooks) hung on `PERMISSION_REQUEST` can
refuse something and have the agent hear it:

```python
def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None

agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push)
```

Claude Code and Codex both run that moment; the rest have nothing to hang it on. The optional
`tool=` filter is **the backend's own name for what it asked about** — `Bash` on Claude Code,
`commandExecution`, `fileChange` or `permissions` on Codex — so a hook meant for both leaves it
off and reads `occasion.about`, as the one above does. A flow built on
it says so where it declares its agents, and is refused before its first turn if given one that
cannot:

```python
class Agents(NamedTuple):
    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
    reviewer: AgentBase
```

## A worked pair

A reviewer that cannot touch the change it is reading:

```sh
hmz exec -f official/rlar \
    -a claude/claude-opus-5:max \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "$(cat TASK.md)"
```

The actor is at `bypass` and does the work; the reviewer is at `read-only` and can only look.
Two agents, two rungs, one flow.

## What it does not bound

A rung bounds the **tools the agent reaches for**. It does not confine the process: an agent at
`workspace-write` that runs a command which itself writes elsewhere has written elsewhere.
For a real boundary, put the agent in [a container of its own](/features/containers).

## See also

- [Hooks](/features/hooks) — refusing one thing rather than a whole rung
- [Containers](/features/containers)
- [Security](/guide/security)
