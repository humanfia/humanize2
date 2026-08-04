# 3 · Two agents at once

**Fifteen minutes.** One agent builds; another reads its work and says what is wrong. You will
also learn to read two conversations on one screen.

::: tip Before you start
[Put a loop under it](/guide/tutorial-ralph-loop). Two CLIs logged in makes this more
interesting, but one is enough — two agents of the same CLI are still two agents.
:::

## Step 1 — fetch the official flowverse

The interesting flows are not in the package. They are in a
[flowverse](/features/flowverses) — a git repository of flows — and `official` is listed from the
start whether or not it has been fetched.

In `hmz`:

```
/flow
```

Walk down to the `official` heading. If it has nothing under it, press **r** to
fetch it. It keeps drawing while it clones, and says underneath what became of it.

::: danger Adding a flowverse is trusting that repository with this machine
A flow is Python, and listing what a flowverse holds **runs the entry point of every flow in its
`flows/`**.
`official` is [humanfia/flowverse](https://github.com/humanfia/flowverse). See
[Security](/guide/security).
:::

## Step 2 — take `rlar`

```
official/rlar
```

`rlar` drives two agents with names, and the names matter:

| Agent | What it is for |
| --- | --- |
| `actor` | works in **one session** and must remember |
| `reviewer` | arrives **fresh** each round and must not |

The review *is* the actor's next prompt, word for word. And the reviewer is also the one that says
the task is finished — which is what ends the run.

## Step 3 — set up each agent

Choosing the flow walks you straight into `/agents`, one agent at a time, **by the name the flow
calls it**. Each agent is three steps:

1. **Which CLI, and which account.** The CLI row, then the account row; `as local` is the first
   row. (Accounts are [providers](/features/providers) — [tutorial 16](/guide/tutorial-providers).)
2. **Which model, and at what effort.** Type a few letters to narrow. **←/→** adjusts the effort.
3. **Where it works** — only for an agent the flow says may be pointed at a machine. `rlar` does
   not, so this step does not exist here.

**esc is always the step before**, and off the first step of the first agent it leaves the walk
entirely, changing nothing.

Give the reviewer a different CLI if you have one. Give it the same one if you do not — two agents
at one configuration are still two agents, and that is the point.

::: tip Make the reviewer read-only
On the reviewer's sheet, the `permission` row → `read-only`. Now it can read the change and cannot
touch it. See [Permissions](/features/permissions).
:::

## Step 4 — run it

```
Work through TASK.md.
```

The line above the editor now has two rows:

```
   actor · claude/claude-opus-5:max · ● 1 of 1
   reviewer · codex/gpt-5.6-sol:high · ○ 3 · unread
```

| | |
| --- | --- |
| `●` | that agent has a turn open |
| `○` | it has stopped |
| `1 of 1` | which conversation of that agent's you are reading |
| `3` | the reviewer has opened three, one per round |
| `unread` | it has said something since you last looked at it |

## Step 5 — read the other conversation

**tab.**

The transcript writes a line saying which conversation is being read from there down, and draws
what it has said under it. **shift+tab** goes back; both wrap.

Three things to know:

- **They step between the ones that are working.** A conversation between its turns is read once
  you are on it, but is not stepped *onto*.
- **Nothing is taken off the screen.** A conversation ending under you says `that conversation has
  gone`; only `/clear` clears.
- **A line you type reaches the conversation you are reading** — not whichever agent happens to be
  working. Say something to the actor while reading the reviewer and you have said it to the
  reviewer.

See [Many conversations at once](/features/conversations).

## Step 6 — look at the handover graph

```
/status
```

Now it says something: every handover between agents, with how often it happened. A two-agent loop
that was supposed to alternate and is in fact one agent doing everything looks different here from
the first glance.

## Step 7 — the same thing without the interface

```sh
hmz exec -f official/rlar \
    -a claude/claude-opus-5:max \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "$(cat TASK.md)"
```

**One `-a` per agent the flow drives, in the order it takes them.** Get the count wrong and it is
refused before any agent runs:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-5:max "fix the build"
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given
```

That check exists so a two-agent flow started with one fails now rather than on an unpacking
hours into a loop, with a turn's work already behind it.

## Other two-agent flows to try

| | |
| --- | --- |
| `official/flame_chase` | two agents take turns on the same task; each reads the repository, not a history |
| `official/humanize1:rlcr` | builds a plan under review until nothing is left to say — run it in a git repository |

## What you now know

- A flow names its agents, and everything talks about them by those names.
- `/agents` is three steps per agent, and esc is always the step before.
- **tab** reads another conversation; a line goes to the one you are reading.
- `-a` is positional: one per agent, in the flow's own order.

## Next

[Run it unattended](/guide/tutorial-unattended).
