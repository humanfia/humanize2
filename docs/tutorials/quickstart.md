# 1 · Quickstart

**Fifteen minutes.** You will install humanize, talk to a coding agent through it, put a loop
around that agent, and open the whole run as a timeline you can scroll.

Nothing here assumes you have used humanize before. Every term is defined the first time it
turns up.

::: warning Use a scratch directory
humanize runs every agent with permission prompts disabled. An agent under it edits files
without asking. Do this in a throwaway git repository, and read [Security](/guide/security)
before you point it at work you care about.
:::

## What you need

Python 3.12 or newer, and **one coding agent CLI you have already logged into**. Any of these
will do:

```sh
command -v agy claude codex grok kimi pi qwen opencode mimo
```

humanize drives the CLI you already have. It holds no API key and talks to no model provider
itself, so whichever of those you use, you log in the way you already log in.

If you have none of them, humanize also ships DeepSeek Harness, which needs a DeepSeek API key
and nothing else installed. See [Installation](/guide/installation).

## Step 1 — install it

```sh
pip install git+https://github.com/humanfia/humanize2.git
```

The command is `hmz`:

```sh
hmz --version
```

```console
hmz 0.1.0
```

## Step 2 — make somewhere to work

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo
git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
printf 'A tiny calculator.\n' > README.md
git add -A && git commit -qm "a calculator with a bug in it"
```

`calc.py` subtracts where it should add. That bug is the work.

Now name the agent you are going to use. An agent is written `cli/model:effort` — the CLI that
runs the turn, the model it asks for, and how hard that model should think. Put yours in a
shell variable, and every command below is one you can paste:

```sh
AGENT=claude/claude-opus-4-8:high
```

Pick the row for the CLI you have:

| CLI | Write it as |
| --- | --- |
| Claude Code | `claude/claude-opus-4-8:high` |
| Codex | `codex/gpt-5.6-sol:high` |
| Kimi Code | `kimi/kimi-code/k3:high` |
| Qwen Code | `qwen/qwen3-coder-plus:high` |
| Grok Build | `grok/grok-4.6:high` |
| Antigravity CLI | `agy/gemini-3.7-flash-high:high` |
| pi | `pi/openai-codex/gpt-5.6-luna:high` |
| opencode | `opencode/opencode/big-pickle:high` |
| mimocode | `mimo/mimo/mimo-auto:high` |
| DeepSeek Harness | `dsh/deepseek-v4-flash:high`, with `export DEEPSEEK_API_KEY=sk-…` |

Those are examples, not a fixed list. A model id is whatever that CLI shipped this week, and
which ones you may name depends on the account you are logged in as — so `pi`, `opencode` and
`mimo` write a model as `provider/id`, which is why their rows have an extra slash in them. To
see what yours actually offers, open `/flow` in the interface and turn to its agents: humanize
asks each CLI once and keeps the answer.

If you get the id wrong, the backend says so on the first turn:

```console
[claude-code:unrecognized_model] {"model":"not-a-real-model","query_source":"sdk"}
```

## Step 3 — open the prompt

```sh
hmz
```

That is the only way into the terminal interface. There is no `hmz tui`.

```
┌──────────────────────────────────────────────────────────────────────┐
│  the transcript: one conversation, a turn after another              │
├──────────────────────────────────────────────────────────────────────┤
│              assistant · claude/claude-opus-4-8:high                 │  ← what you are talking to
│ ❯ type here                                                          │  ← the editor
├──────────────────────────────────────────────────────────────────────┤
│ ⠋ chat  ~/tmp/humanize-demo             enter say · / commands       │  ← the status line
└──────────────────────────────────────────────────────────────────────┘
```

The line above the editor names what you are about to talk to, written `cli/model:effort`: the
CLI that runs the turn, the model it asks for, and how hard that model should think.

The right-hand end of the status line lists the keys that do something right now. That is the
whole of what you have to remember.

::: details It says `no coding agent is installed here`
humanize offers exactly the CLIs on your `PATH`, plus DeepSeek Harness when a key is set. See
[Troubleshooting](/guide/troubleshooting#no-coding-agent-is-installed-here).
:::

## Step 4 — say something

Type this and press enter:

```
Read calc.py and tell me what it does. Do not change anything yet.
```

The agent takes a **turn** — one exchange with the model, which may run tools and may take
minutes. The reply arrives a word at a time as the model writes it.

Three things to try while it is still going:

- **Type another line and press enter.** It goes *into* the turn already running rather than
  starting a new one. See [Talk to a running turn](/guide/steering).
- **`/details`** toggles between showing tool calls and thinking, or only what the agent says.
- **`/status`** shows who is working, who handed to whom, and what it has cost.

Type `/` on its own and every command appears under the editor with a line about each. **tab**
takes the highlighted one.

Underneath, humanize is running a **flow** called `chat` — a directory of Python that says
which agents are driven, what each is asked, and when to stop. `chat` is the simplest one there
is: one agent, one conversation, and every line you type is the next turn of it.

Leave with `/exit`.

## Step 5 — run the same thing without the interface

Every flow also runs unattended:

```sh
hmz exec -f chat -a "$AGENT" "What does calc.py do?"
```

Three things to know about that line:

- `-f` names the flow, either one humanize ships or a path to one of your own.
- `-a` describes one agent, written `cli/model:effort`. You repeat it once for every agent the
  flow drives, in the order the flow takes them.
- The last argument is the task.

Get the count wrong and humanize refuses before any agent runs, rather than failing hours in:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-4-8:high "fix the build"
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given
```

## Step 6 — put a loop around it

One conversation with an agent is a chat window. Most work is not that shape. A **Ralph loop**
gives the agent the same task over and over, in a fresh conversation each time, so it restarts
from the task and the repository instead of from a context window full of its own earlier
attempts:

```sh
hmz exec -f ralph_loop -a "$AGENT" "Fix the bug in calc.py."
```

Everything the agent says streams past, and the flow prints one line of its own as each round
opens:

```console
round 1
…
round 2
…
```

::: warning A Ralph loop does not stop on its own
That is what it is for — you leave one running for hours. Press **ctrl+c** twice in the interface, or
**ctrl+c** at a command line, when you have seen enough. Every round is written down, so
stopping loses nothing.
:::

Check the work:

```sh
git diff
```

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

It made that edit with **no permission prompt**. humanize runs every agent with them disabled
and there is no setting that turns them back on. That is the one thing to have understood
before pointing this at a real repository.

## Step 7 — read the whole run back

Every run writes down what it was: the flow, the agents, and the id of every conversation they
opened. Turn all of that plus the backends' own transcripts into one timeline:

```sh
hmz trace collect
```

```console
~/.humanize/cycles/-tmp-humanize-demo/20260817T021608.271Z-e000e6/traces/20260817T022635Z.trace.json of 20260817T021608.271Z-e000e6: 15 sessions, 240 slices
```

Drag that file into [ui.perfetto.dev](https://ui.perfetto.dev). Each agent becomes a process,
each row of its conversations a track, and each slice one thing the agent did — with the
prompt, the reasoning, the tool input and the tool output attached to it.

For a nine-hour run it is the only view that fits on a screen.

## What you now know

| | |
| --- | --- |
| **turn** | one exchange with the model |
| **session** | a conversation held across turns |
| **flow** | a directory of Python driving one or more agents |
| **cycle** | one run of a flow, written down under `~/.humanize/cycles/` |
| `hmz` | the interface |
| `hmz exec -f FLOW -a CLI/MODEL:EFFORT "task"` | the same flows, unattended |
| `hmz trace collect` | the run as a timeline |
| **ctrl+c** twice | stops the flow |

## Where to go next

The next three tutorials each take a real piece of work from start to finish:

- [Beat a benchmark](/tutorials/take-home) — two agents take turns optimising a kernel.
- [Port a project](/tutorials/port-a-project) — an agent works, a reviewer reads it back.
- [Build a coding agent](/tutorials/build-an-agent) — idea, plan, then build under review.

If you would rather write your own flow first, go to [Build under
test](/tutorials/flow-checked-build).

For the words used above, properly defined, read [Concepts](/guide/concepts).
