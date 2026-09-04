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
humanize runs every agent with permission prompts disabled: an agent under it edits files
without asking. Do this in a throwaway git repository, and read [Security](/user/security)
before you point it at work you care about.
:::

You need Python 3.12 or newer and **one coding agent CLI you have already logged into**.
humanize holds no API key and talks to no model provider itself, so you log in the way you
already log in.

```sh
pip install git+https://github.com/humanfia/humanize2.git
```

Then make something for it to fix. `calc.py` subtracts where it should add, and that bug is the
work:

```sh
mkdir -p ~/tmp/humanize-demo && cd ~/tmp/humanize-demo && git init -q
printf 'def add(a, b):\n    return a - b\n' > calc.py
git add -A && git commit -qm "a calculator with a bug in it"
```

Both ways below run the same flow, `ralph_loop`: it gives the agent the same task over and over
in a fresh conversation each time, so it restarts from the task and the repository rather than
from a context window full of its own earlier attempts. Pick the tab for the CLI you have.

### At the prompt

::: code-group

```sh [Claude Code]
hmz -f ralph_loop -a claude/claude-opus-4-8:high
```

```sh [Codex]
hmz -f ralph_loop -a codex/gpt-5.6-sol:high
```

```sh [Antigravity CLI]
hmz -f ralph_loop -a agy/gemini-3.7-flash-high:high
```

```sh [Qwen Code]
hmz -f ralph_loop -a qwen/qwen3-coder-plus:high
```

```sh [Kimi Code]
hmz -f ralph_loop -a kimi/kimi-code/k3:high
```

```sh [Grok Build]
hmz -f ralph_loop -a grok/grok-4.6:high
```

```sh [ZCode]
hmz -f ralph_loop -a zcode/zai/glm-5.3:high
```

:::

That opens the terminal interface, set up and waiting. Type the task and press enter:

```
Fix the bug in calc.py.
```

The agent takes a **turn** — one exchange with the model, which may run tools and may take
minutes — and then the loop gives it the same task again. Type another line while it is working
and it goes *into* the running turn rather than starting a new one. `/` lists every command,
**ctrl+c** twice stops the loop, and `/exit` leaves.

### Or without the interface

The same flow, the same agent, with the task on the line instead:

::: code-group

```sh [Claude Code]
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "Fix the bug in calc.py."
```

```sh [Codex]
hmz exec -f ralph_loop -a codex/gpt-5.6-sol:high "Fix the bug in calc.py."
```

```sh [Antigravity CLI]
hmz exec -f ralph_loop -a agy/gemini-3.7-flash-high:high "Fix the bug in calc.py."
```

```sh [Qwen Code]
hmz exec -f ralph_loop -a qwen/qwen3-coder-plus:high "Fix the bug in calc.py."
```

```sh [Kimi Code]
hmz exec -f ralph_loop -a kimi/kimi-code/k3:high "Fix the bug in calc.py."
```

```sh [Grok Build]
hmz exec -f ralph_loop -a grok/grok-4.6:high "Fix the bug in calc.py."
```

```sh [ZCode]
hmz exec -f ralph_loop -a zcode/zai/glm-5.3:high "Fix the bug in calc.py."
```

:::

`-f` names the flow and `-a` names one agent, written `cli/model:effort` — the CLI that runs
the turn, the model it asks for, and how hard that model should think. A Ralph loop does not
stop on its own, which is what it is for: **ctrl+c** at the command line when you have seen
enough. Every round is written down, so stopping loses nothing.

Either way, check the work:

```sh
git diff
```

```diff
 def add(a, b):
-    return a - b
+    return a + b
```

It made that edit with **no permission prompt**, and there is no setting that turns them back
on. That is the one thing to have understood before pointing this at a real repository.

::: details The model id is wrong, or your CLI is not above
A model id is whatever that CLI shipped this week, and which ones you may name depends on the
account you are logged in as. Open `/flow` in the interface and turn to its agents: humanize
asks each CLI once and keeps the answer. Every backend it drives, including the ones not in
those tabs, is in [Many backends, one agent](/features/backends);
[Installation](/user/installation) is how to sign each one in.
:::

**Next.** [`hmz trace collect`](/user/tracing) turns the whole run into one timeline you can
open in Perfetto. The [User Guide](/user/) has a page per thing humanize does, and its
tutorials each take a real piece of work start to finish: [Beat a
benchmark](/user/tutorials/take-home), [Port a project](/user/tutorials/port-a-project), and
[Build a coding agent](/user/tutorials/build-an-agent). For the words above, properly defined,
read [Concepts](/user/concepts).

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
every [flowverse](/weaver/flowverses) fetched here, and your own — the ones in
`.humanize/flows` as `local`, the ones in `~/.humanize/flows` as `user`.

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
    <span>Running flows: a page per thing humanize does, opening with something to
    paste.</span>
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
<a :href="withBase('/user/security')">Security</a> before you point one at a repository you
care about.
</p>
