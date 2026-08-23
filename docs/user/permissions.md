# Permissions

Permissions set what an agent may do at all. Each agent sits on one rung of a four-rung ladder,
loosest last, named the way these CLIs already name them. Set a rung when you want to bound
what an agent can touch.

| Rung | What it means |
| --- | --- |
| `read-only` | It may look at anything and change nothing — no edits, no commands. |
| `workspace-write` | It may change the workspace it was given, and is stopped at the edge of it. |
| `auto` | It may reach for anything, and what it asks for is granted. |
| `bypass` | Nothing is asked and nothing is checked. **The default.** |

## Try it

Run a flow with the agent set to `read-only` — it can look at anything and change nothing:

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review the current change"
```

`permission=` is available in the **written-out** form of `-a` only; there is no short spelling
for it. A flow's Python config takes the same word:

```python
CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission="read-only")
```

A misspelling is refused before any agent runs:

```console
hmz exec: error: bad agent 'cli=codex,model=gpt-5.6-sol,effort=high,permission=rdonly':
permission must be one of read-only, workspace-write, auto, bypass, not 'rdonly'
```

At the prompt, it is the `permission` row of the sheet an agent is set up on. Step through it
with **←/→**.

## Why `bypass` is the default

A flow watches its agent rather than gating it, and a turn that waits on an approval nobody is
there to give is a flow that has stopped. Anything tighter is a choice — make it deliberately.
See [Security](/user/security).

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

A reviewer that cannot touch the change it is reading:

```sh
hmz exec -f official/rlar \
    -a claude/claude-opus-5:max \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "$(cat TASK.md)"
```

The actor sits at `bypass` and does the work. The reviewer sits at `read-only` and can only
look. Two agents, two rungs, one flow.

## What it does not bound

A rung bounds the **tools the agent reaches for**. It does not confine the process: an agent at
`workspace-write` that runs a command which itself writes elsewhere has written elsewhere. For
a real boundary, put the agent in [a container of its own](/user/containers).

## Where a hook gets a say

This section is the weaver's — whoever wrote the flow.

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
