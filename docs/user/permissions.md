# Permissions

**This page is the weaver's** — whoever wrote the flow. What an agent may do is declared where
the flow declares the agent, and nobody running the flow is asked about it: a reviewer that may
not write is a reviewer whichever CLI fills the place, so it is a thing about the work.

Each agent sits on one rung of a four-rung ladder, loosest last, named the way these CLIs
already name them.

| Rung | What it means |
| --- | --- |
| `read-only` | It may look at anything and change nothing — no edits, no commands. |
| `workspace-write` | It may change the workspace it was given, and is stopped at the edge of it. |
| `auto` | It may reach for anything, and what it asks for is granted. |
| `bypass` | Nothing is asked and nothing is checked. **The loosest rung, and what a place that says nothing declares.** |

## Declaring one

Write an `AgentDefaults` beside the place, exactly as you write a `Goal` or an `Isolated`:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, AgentDefaults, flow


class Agents(NamedTuple):
    builder: Agent
    reviewer: Annotated[Agent, AgentDefaults(permission="read-only")]


@flow
def run(agents: Agents, task: str) -> None:
    agents.builder(task)
    agents.reviewer(f"review what was just done: {task}")
```

The rung reaches every agent handed to that place, over whatever it was set up with, before its
first turn. Run it with the ordinary line — a CLI, a model and an effort apiece:

```sh
hmz exec -f ./review.py -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

A rung no backend has a word for is caught by [`hmz check`](/reference/cli#hmz-check) without
running the flow, and again as the flow loads:

```console
review.py:9: error: unknown-permission: 'rdonly' is no rung there is -- what an agent may
do is one of read-only, workspace-write, auto, bypass, and a flow declaring anything else is
refused before its first turn
```

## A line cannot say it

`permission=` is not a setting of `-a`, and a line that writes one is a usage error naming the
flow as the place to say it:

```console
hmz exec: error: bad agent 'cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only':
permission is the flow's to say, written beside the agent where the flow declares it -- not on
the line that runs the flow
```

There is no row for it on the sheet an agent is set up on, either. An agent is a CLI, an
account, a model at an effort and how quickly it is served; what that agent is allowed to do
belongs to the flow driving it.

## A declaration only ever tightens

`bypass` is the loosest rung, and it is what a place that says nothing declares: a flow watches
its agent rather than gating it, and a turn that waits on an approval nobody is there to give
is a flow that has stopped. But declaring the loosest rung settles nothing. What an agent
already carries is never loosened to reach a declaration, so a flow that says nothing runs its
agents at exactly what they came with, and a flow you call runs at your rung or tighter --
never looser. Otherwise a run started at `read-only` would be at `bypass` the moment it called
a flow that mentioned nothing, and calling a flow you did not write would be how your
`read-only` gets undone. See [Security](/user/security).

**Tighter is not always more visible.** At `bypass` humanize answers each of Claude Code's
permission requests itself, so a flow's `PERMISSION_REQUEST` hooks see every one; at `auto`
Claude decides for itself and those hooks see nothing. Tightening `bypass` to `auto` therefore
buys restriction and costs visibility, so a flow written around watching what its agent asks
for says `bypass` and means it.

## What each backend actually does

Every backend has a ladder of its own, and none of them has the same four rungs. Each driver
reaches for whichever of its own settings says the same thing:

| Rung | Claude Code | Codex | Kimi Code | pi | opencode, mimocode | ZCode |
| --- | --- | --- | --- | --- | --- | --- |
| `read-only` | `plan` mode | `read-only` sandbox | plan mode | without `bash`, `edit`, `write` | `edit` and `bash` denied | `plan` mode |
| `workspace-write` | `acceptEdits` mode | `workspace-write` sandbox | plan mode off | — | `webfetch` denied | `edit` mode |
| `auto` | Claude's own `auto` mode | `workspace-write`, approvals on request | — | — | nothing denied | `build` mode, which asks before a tool with side effects |
| `bypass` | `manual` mode, humanize answers each request | `danger-full-access` | `yolo` mode | — | — | `yolo` mode |

These are the six backends whose rungs differ most; the whole set is in
[Agents › What an agent may do](/reference/agents#what-an-agent-may-do).

**A dash is the rung above it, run again.** Where a backend cannot tell two rungs apart it says
so rather than pretending: asking Kimi for `auto` gets you `workspace-write` behaviour, not a
quiet promotion to `bypass`, and asking pi for anything above `read-only` gets you the same
agent three times over.

**Codex is the one backend here with a sandbox of its own**, so its rungs are the real thing
rather than an approximation of one.

**ZCode has a mode for each of these.** `plan` refuses an edit and refuses a command it reads
as high-risk. `edit` changes the workspace without asking, and stops at a high-risk tool to
ask — which is answered no at that rung, since an agent allowed its workspace is not allowed
more for asking. `build`, the mode its own terminal opens in, asks the same question, and
`auto` is where the answer is yes. `yolo` asks nothing at all. ZCode's own `auto` mode is not
this one and is nobody's rung — in that mode it refuses every tool, saying the mode is reserved
and not implemented yet.

**A Codex whose rules were set by somebody else runs a rung down rather than not at all.** Some
installations arrive with requirements — an enterprise policy on the account, a
`requirements.toml` on a machine whose platform packages Codex — and one that forbids
`danger-full-access` refuses every call asking for it, which would be every turn at the default
rung. humanize asks again at `auto` instead: the same freedom, with Codex asking before it
reaches past the workspace and humanize granting what it asks. It is found out once per agent,
and the rung you chose is always what is tried first. See
[Troubleshooting](/user/troubleshooting#codex-this-machine-will-not-run-an-agent-at-bypass-so-it-runs-at-auto).

**Claude Code's `bypass` runs the same on an account somebody else set up.** The flag that
skips the asking, `--dangerously-skip-permissions`, is one managed settings can turn off — an
account carrying `disableBypassPermissionsMode` starts the turn at a mode where every edit is
declined and it ends successfully with the work not done. So humanize does not skip the asking:
it runs the agent at Claude's `manual` mode and answers each request itself, yes to whatever
the account leaves decidable, with the organisation's own hard `deny` list still enforced by
Claude before it asks. `manual` is a mode every account allows, so `bypass` needs nothing
special from yours.

## A worked pair

A reviewer that cannot touch the change it is reading, said once in the flow:

```python
class Agents(NamedTuple):
    actor: Agent
    reviewer: Annotated[Agent, AgentDefaults(permission="read-only")]
```

```sh
hmz exec -f ./rlar.py -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

The actor sits at `bypass` and does the work. The reviewer sits at `read-only` and can only
look. Two agents, two rungs, one flow — and the same two rungs whoever runs it, on whichever
CLIs they have.

## What it does not bound

A rung bounds the **tools the agent reaches for**. It does not confine the process: an agent at
`workspace-write` that runs a command which itself writes elsewhere has written elsewhere. For
a real boundary, put the agent in [a container of its own](/user/containers).

## Where a hook gets a say

A [hook](/weaver/hooks) hung on `PERMISSION_REQUEST` can refuse something and have the agent
hear it only where a backend asks before it acts *and waits for the answer*. `auto` is that
rung everywhere it exists. Claude Code runs the moment at `bypass` as well, since `bypass`
there is `manual` mode with the asking routed to humanize: the hook sees every tool an agent
nobody was asked about reaches for, and can still say no to one.

```python
def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None

agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push)
```

Claude Code, Codex and ZCode all run that moment; the rest have nothing to hang it on. The
optional `tool=` filter is **the backend's own name for what it asked about** — `Bash` on
Claude Code, `commandExecution`, `fileChange` or `permissions` on Codex. A hook meant for more
than one of them leaves it off and reads `occasion.about`, as the one above does.

A flow built on this says so where it declares its agents, and an agent that cannot run the
moment is refused before its first turn:

```python
class Agents(NamedTuple):
    builder: Annotated[Agent, Moment.PERMISSION_REQUEST]
    reviewer: Agent
```

## See also

- [Hooks](/weaver/hooks) — refusing one thing rather than a whole rung
- [Containers](/user/containers)
- [Security](/user/security)
