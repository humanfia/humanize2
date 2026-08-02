# Skills

Which of a CLI's skills an agent is loaded with — a setting of the **agent**, so two agents of
one flow may be loaded differently, and neither touches the settings of the CLI itself.

```python
ClaudeCodeAgentConfig(model=…, effort=…, skills=("code-review", "run"))
```

| Value | |
| --- | --- |
| `None` — the default | the CLI as it comes, which is every skill it finds |
| a tuple | exactly those and nothing else, whatever is installed afterwards |

## Why the tuple is exact

Every backend is told the other way round: a CLI comes with its skills loaded and has to be
talked *out* of one. So what actually goes on the wire is the rest of them, worked out by looking
at what is installed:

```python
from hmz.agents.skills import leaving, skills

skills("claude")                       # what it would load here: yours, and this project's
leaving("claude", ("code-review",))    # what to switch off so that only that one is left
```

An agent that has been asked has exactly those skills from then on — including against a skill
installed tomorrow.

## What each backend can be told

| Backend | How | What it comes to |
| --- | --- | --- |
| `claude` | `--disallowedTools "Skill(<name>)"` | the agent is refused the skill. Claude still **lists** it — no flag takes one off that list |
| `codex` | `-c skills.config=[{name="…", enabled=false}]` on its app server | the skill is not loaded for that server; the user's own `config.toml` is untouched |
| `kimi` | — | `kimi web` takes no `--skills-dir`, so a skill it finds is one it loads |
| `pi` | — | it is told which skills to load by path, and finds none of its own to choose between |
| `opencode`, `mimo` | — | neither offers a way of switching one off for a single run |

A backend with no way of being told anything is one where the setting has nothing to do. That is
why the interface offers the choice only where it means something: a list to choose from that
nothing acts on is a list that lies.

## At the prompt

On the model step of `/agents`, **ctrl+s**. A side question about the same agent, so a key rather
than a step of its own; the tuning line reads `◉ every skill · ctrl+s to choose`.

```
   ❯ 1. [✔] code-review    Review the current diff… (yours)
     2. [ ] dataviz        Use this skill whenever you… (yours)
     3. [✔] housekeeping   Tidies the tree (this project)
```

- The skills are found **where the CLI itself looks** — yours and this project's — read for the
  name and the line each describes itself with. Nothing is asked of the CLI, which would mean
  starting it.
- Every box starts ticked, which is how a CLI comes.
- **space** switches the one under the cursor, **enter** takes the lot, **esc** leaves the agent
  loaded as it was.

Where each CLI keeps its skills is written down in `hmz.backends`:

| Backend | Yours | This project's |
| --- | --- | --- |
| `claude` | `~/.claude/skills/*/SKILL.md` | `.claude/skills/*/SKILL.md` |
| `codex` | `~/.codex/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md`, `.codex/skills/*/SKILL.md` |

## On a command line

No `-a` spells a skill list. An agent loaded with a particular set is one
[built in Python](/reference/flows#building-the-agents-yourself) and handed to `Runner`, or one
set up on the `/agents` sheet — where the choice is
[remembered per agent, per flow, per project](/features/settings).

```python
from hmz.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.runner import Runner

reading = ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", skills=("code-review",))
writing = ClaudeCodeAgentConfig(model="claude-opus-5", effort="high")

Runner("official/rlar", [
    ClaudeCodeAgent(writing, name="actor"),
    ClaudeCodeAgent(reading, name="reviewer"),
]).run("$(cat TASK.md)")
```

The reviewer reading a change need not be carrying what the builder writing it was.

## See also

- [Permissions](/features/permissions) — the other per-agent narrowing
- [Agents › Which skills an agent is loaded with](/reference/agents#which-skills-an-agent-is-loaded-with)
- [TUI › What each agent is loaded with](/reference/tui#what-each-agent-is-loaded-with)
