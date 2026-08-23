---
layout: home
---

<script setup>
import { withBase } from 'vitepress'
</script>

<HmzHero />

## How it fits together

<HmzArch />

## Run a flow

::: warning Use a scratch directory
humanize runs every agent with permission prompts disabled. An agent under it edits files
without asking. Do this in a throwaway git repository, and read [Security](/user/security)
before you point it at work you care about.
:::

You need Python 3.12 or newer and **one coding agent CLI you have already logged into**.
humanize holds no API key and talks to no model provider itself, so you log in the way you
already log in.

```sh
pip install git+https://github.com/humanfia/humanize2.git
hmz --version
```

### Name an agent

An agent is written `cli/model:effort` — the CLI that runs the turn, the model it asks for, and
how hard that model should think. Put yours in a shell variable, and every command below is one
you can paste:

```sh
AGENT=claude/claude-opus-4-8:high
```

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
| ZCode | `zcode/zai/glm-5.3:high` |
| DeepSeek Harness | `dsh/deepseek-v4-flash:high`, with `export DEEPSEEK_API_KEY=sk-…` |

Those are examples, not a fixed list. A model id is whatever that CLI shipped this week, and
which ones you may name depends on the account you are logged in as — `pi`, `opencode`, `mimo`
and `zcode` write a model as `provider/id`, which is the extra slash in their rows. To see what
yours offers, open `/flow` in the interface and turn to its agents. Get the id wrong and the
backend says so on the first turn:

```console
[claude-code:unrecognized_model] {"model":"not-a-real-model","query_source":"sdk"}
```

### Say something

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo && git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
git add -A && git commit -qm "a calculator with a bug in it"
hmz
```

`calc.py` subtracts where it should add — that bug is the work. `hmz` is the only way into the
terminal interface; there is no `hmz tui`. Type a line and press enter, and the agent takes a
**turn**: one exchange with the model, which may run tools and may take minutes.

| While a turn is running | |
| --- | --- |
| Type another line | It goes *into* the turn rather than starting a new one — [Talking to a running turn](/user/steering) |
| `/details` | Show the tool calls and the thinking, or only what the agent says |
| `/status` | Who is working, who handed to whom, and what it has cost |
| `/` | Every command, with a line about each; **tab** takes the highlighted one |

Underneath, humanize is running a **flow** called `chat` — one agent, one conversation, and
every line you type is the next turn of it. `/exit` leaves. The run is [held apart from this
terminal](/reference/daemon), so it goes on running if you say to leave it, which is what
`/detach` says outright.

### Run it unattended

```sh
hmz exec -f chat -a "$AGENT" "What does calc.py do?"
```

`-f` names the flow, `-a` describes one agent and is repeated once for every agent the flow
drives in the order the flow takes them, and the last argument is the task. Get the count wrong
and humanize refuses before any agent runs, rather than failing hours in:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-4-8:high "fix the build"
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given
```

### Put a loop around it

A **Ralph loop** gives the agent the same task over and over, in a fresh conversation each
time, so it restarts from the task and the repository instead of from a context window full of
its own earlier attempts.

```sh
hmz exec -f ralph_loop -a "$AGENT" "Fix the bug in calc.py."
```

::: warning A Ralph loop does not stop on its own
That is what it is for — you leave one running for hours. Press **ctrl+c** twice when you have
seen enough. Every round is written down, so stopping loses nothing.
:::

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

It made that edit with **no permission prompt**. There is no setting that turns them back on.

### Read the whole run back

Every run writes down what it was: the flow, the agents, and the id of every conversation they
opened. Turn that plus the backends' own transcripts into one timeline:

```sh
hmz trace collect
```

```console
~/.humanize/epics/-tmp-humanize-demo/20260817T021608.271Z-e000e6/traces/20260817T022635Z.trace.json of 20260817T021608.271Z-e000e6: 15 sessions, 240 slices
```

Drag that file into [ui.perfetto.dev](https://ui.perfetto.dev). Each agent becomes a process,
each of its conversations a track, and each slice one thing the agent did — with the prompt, the
reasoning, the tool input and the tool output attached. For a nine-hour run it is the only view
that fits on a screen.

| What you now know | |
| --- | --- |
| **turn** | One exchange with the model |
| **session** | A conversation held across turns |
| **flow** | A directory of Python driving one or more agents |
| **epic** | One run of a flow, written down under `~/.humanize/epics/` |
| `hmz` | The interface |
| `hmz exec -f FLOW -a CLI/MODEL:EFFORT "task"` | The same flows, unattended |
| `hmz trace collect` | The run as a timeline |

**Next.** The [User Guide](/user/) has a page per thing humanize does, and its tutorials each
take a real piece of work from start to finish: [Beat a benchmark](/user/tutorials/take-home),
[Port a project](/user/tutorials/port-a-project), and [Build a coding
agent](/user/tutorials/build-an-agent). For the words above, properly defined, read
[Concepts](/user/concepts).

## Weave a flow

A **weaver** is whoever writes a flow. A flow is a directory whose `__init__.py` holds a
function marked `@flow`, and that function drives the agents. Write one when you want the same
agents run the same way again and again, rather than typed out afresh each time.

```sh
mkdir -p .humanize/flows/twice
```

```python
# .humanize/flows/twice/__init__.py
"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
```

Run it by name. humanize also offers it in the interface: `/flow` lists the flows it ships,
every [flowverse](/weaver/flowverses) fetched here, and your own — the ones in `.humanize/flows`
as `local`, the ones in `~/.humanize/flows` as `user`.

```sh
hmz exec -f twice -a claude/claude-opus-4-8:high "add a --dry-run flag to calc.py"
```

Three rules are the whole contract:

| | |
| --- | --- |
| The `@flow` mark makes it a flow | Not the function's name, which is yours to choose |
| The annotation on `agents` says how many it drives | `tuple[Agent]`, `tuple[Agent, Agent]` — `tuple[Agent, ...]` is refused |
| That annotation must be readable at runtime | Import `Agent` normally, **never** under `if TYPE_CHECKING` |

The command line cannot know the count any other way, so humanize checks it before the first
turn — and an annotation nothing can read back is not one it can hold you to.

Whether the second turn remembers the first is the other choice you are making:

```python
agent("do the task")     # a session of its own, dropped straight after: nothing carries over
session = agent.new()    # a session you hold
session("do the task")   # opens it
session("keep going")    # resumes it, the first turn still in context
```

Read a flow for what will not run, before anything runs it:

```sh
hmz check twice
```

```console
hmz check: 0 errors, 0 warnings
```

**Next.** The [Weaver Guide](/weaver/) is what a flow may do and how to write one — loops,
settings, goals, shapes, hooks, worktrees. [Build under
test](/weaver/tutorials/checked-build) is the shortest useful flow there is, start to finish.

## Work on humanize

```sh
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync
uv run pre-commit install
```

Installing the hooks once means every commit is checked before it is made. There are two gates
and both have to pass:

```sh
uv run pre-commit run --all-files   # the formatter, the linter and the type checker
uv run pytest                       # everything that does not need a real agent
uv run pytest --run-agents          # also drives the real CLIs, and spends real tokens
```

What the code is held to: **`pyright` in strict mode** over `src` and `tests`, with `# type:
ignore` switched off — a suppression names a rule; **`ruff` with every rule on**, less the ones
annotated in `pyproject.toml`; **Google-style docstrings**; and a popular, well-maintained
library in preference to a custom implementation.

Each package depends only downwards, and a test checks the layering —
[Architecture](/contributing/architecture) has the layers and the rules that keep them. Beside
most packages there is a `SPEC.md`. **Do not modify a `SPEC.md`** unless you were asked to: it
is the contract, and the code is what has to move.

**Next.** [Contributing](/contributing/) is the whole of it, and [Your first
patch](/contributing/tutorials/first-patch) takes one change from clone to pull request.

## Where to go next

<div class="hmz-paths by-three">
  <a :href="withBase('/features/')">
    <strong>Features</strong>
    <span>What humanize is, drawn rather than described — one diagram per capability.</span>
  </a>
  <a :href="withBase('/flows/')">
    <strong>Flows</strong>
    <span>What it can run out of the box, with the shape of each loop played.</span>
  </a>
  <a :href="withBase('/user/')">
    <strong>User Guide</strong>
    <span>Running flows: a page per thing humanize does, opening with something to paste.</span>
  </a>
  <a :href="withBase('/weaver/')">
    <strong>Weaver Guide</strong>
    <span>Writing flows: what a flow may ask of an agent, and how to write one.</span>
  </a>
  <a :href="withBase('/contributing/')">
    <strong>Contributing</strong>
    <span>Working on humanize itself: the layers, the gates, and these docs.</span>
  </a>
  <a :href="withBase('/reference/')">
    <strong>Reference</strong>
    <span>Every command, key, flag and Python call, spelled out.</span>
  </a>
</div>

<p class="hmz-warn">
humanize runs every agent with permission prompts disabled, and no setting turns them back on —
an agent under a flow edits files, runs commands and makes commits without asking. Read
<a :href="withBase('/user/security')">Security</a> before you point one at a repository you care
about.
</p>
