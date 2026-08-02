# 1 · Your first run

**Ten minutes.** By the end you will have talked to a coding agent through humanize, put a line
into a turn that was already running, and stopped it.

::: tip Before you start
[Installation](/guide/installation), and at least one coding agent CLI logged in. Do this in a
scratch project — the agent is going to edit files without asking. See
[Security](/guide/security).
:::

## Step 1 — make somewhere to work

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo
git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
printf 'A tiny calculator.\n' > README.md
git add -A && git commit -qm "a calculator with a bug in it"
```

There is a deliberate bug in `calc.py`. Good.

## Step 2 — open the prompt

```sh
hmz
```

That is the only way in — there is no `hmz tui`. You get three things:

```
┌──────────────────────────────────────────────────────────────────────┐
│  the transcript: one conversation, a turn after another              │
├──────────────────────────────────────────────────────────────────────┤
│              assistant · claude/claude-opus-4-8:high                 │  ← what you are talking to
│ ❯ type here                                                          │  ← the editor
├──────────────────────────────────────────────────────────────────────┤
│ ⠋ chat  ~/tmp/humanize-demo             enter say · / commands      │  ← the status line
└──────────────────────────────────────────────────────────────────────┘
```

**The line above the editor** says what you are about to talk to, as `cli/model:effort`. The first
time, it opens on the first backend installed here that has said what it runs, at the first
model it named — that CLI's own idea of what it runs by default — and at
`high` — deliberately not the hardest setting.

**The status line's right-hand end** lists the keys that do something *right now*, and nothing
else. It is the whole of what you have to remember.

![Opening the interface, typing / for the commands, and picking a flow](/demo/tui.gif)

::: details Nothing offered, and it says `no coding agent is installed here`
humanize offers exactly the CLIs on your `PATH`. Check with
`command -v claude codex kimi pi opencode mimo`, and see
[Troubleshooting](/guide/troubleshooting#no-coding-agent-is-installed-here).
:::

## Step 3 — say something

Type this and press enter:

```
Read calc.py and tell me what it does. Do not change anything yet.
```

The agent takes a **turn**: one exchange with the model, which may run tools and may take
minutes. What it says arrives as it says it.

Underneath, humanize is running the flow called `chat` — one agent, one
[session](/guide/concepts#session), and every line you type is another turn of that same
conversation.

## Step 4 — see the working

```
/details
```

Type `/` first and the commands appear under the editor with a line about each; **tab** takes the
one highlighted. See [Completion](/features/completion).

`/details` toggles whether tool calls and thinking are shown, or only what the agent says. Say
something else and compare:

```
Now fix the bug in calc.py.
```

`/details` again puts it back. Nothing about the run changes — it is a
[screen setting](/features/details).

## Step 5 — talk to a turn that is already running

While that turn is still going, type another line and press enter:

```
and add a test for it
```

It goes **into** the turn already running rather than starting a new one. Watch the editor: the
line is *pinned* above the prompt, dimmed, until the agent says it has it —

```
❯ and add a test for it · with assistant
```

— and then it moves into the transcript in front of the turn that took it.

If no turn is open, it is held for the next one. A line to a running flow is never dropped. See
[Talking to a running turn](/features/steering).

::: warning Two backends cannot hear you mid-turn
`opencode` and `mimocode` run one process per turn, which has ended by the time there is anything
to say to it. The line waits for the next turn instead.
:::

## Step 6 — stop, and leave

```
esc
```

**esc** stops the flow — the whole flow, not just the turn. The turn under way is closed out and
what it was doing is left where it got to; a stop that waited for a turn would not read as a stop.

To leave: **ctrl+c** twice. One ctrl+c takes back what is half-typed if anything is, the flow if
not. Leaving is always two presses.

Or:

```
/exit
```

## What you now know

| | |
| --- | --- |
| `hmz` | opens on whatever this project was [last set up to run](/features/settings) |
| a **turn** | one exchange with the model |
| a **session** | a conversation held across turns — `chat` holds one |
| enter, mid-turn | goes *into* the turn |
| **esc** | stops the flow |
| **ctrl+c** ×2 | leaves |

## Check your work

```sh
git diff --stat
```

The agent should have changed `calc.py`. It did that with **no permission prompt**, because
humanize runs every agent with them disabled and there is no setting that turns them back on.
That is the one thing to be sure you have understood before pointing this at real work.

## Next

Talking to one agent is not the shape of most work. [Put a loop under
it](/guide/tutorial-ralph-loop).
