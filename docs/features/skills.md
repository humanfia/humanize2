# Skills

Two kinds, and the difference between them is who they belong to.

| | |
| --- | --- |
| **the CLI's own** | installed on this machine, the way that CLI installs one. humanize reads the list and changes nothing |
| **the flow's own** | in the flow's `skills/`, mounted onto every session its agents open and taken away again after |

## The CLI's own are the CLI's own

A skill you installed is loaded for every agent of that CLI, switched off where that CLI
switches one off, and is not a setting of any agent. humanize will show you the list:

```python
from hmz.agents.skills import skills

skills("claude")   # what it would load here: yours, and this project's
```

Where each CLI keeps them is written down in `hmz.backends`:

| Backend | Yours | This project's |
| --- | --- | --- |
| `claude` | `~/.claude/skills/*/SKILL.md` | `.claude/skills/*/SKILL.md` |
| `codex` | `~/.codex/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md`, `.codex/skills/*/SKILL.md` |
| `kimi` | `~/.kimi-code/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.kimi-code/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` |

Nothing is asked of the CLI to find out, which would mean starting it, and nothing is written:
what a person has installed is not something a flow is entitled to rewrite, and a list that
could be adjusted here while the CLI's own list said otherwise would be two answers to one
question.

## The flow's own travel with the flow

A [flow is a directory](/reference/flows#the-skills-a-flow-brings), and `skills/` inside it is
what that flow works by — the same layout every one of these CLIs already reads a skill in:

```
official/rlar/
├── __init__.py
└── skills/
    └── review-notes/
        └── SKILL.md
```

Every session the flow's agents open is given them: **mounted**, which is copied where that
backend reads a project's own skills for as long as the session lives, and taken away again
after. Nothing is installed, and nothing of yours is touched.

A flow may also name skills that live in somebody else's repository:

```python
@flow(skills=("https://github.com/humanfia/flowverse#review-notes",))
def run(agents: Agents, task: str) -> None:
    ...
```

A git URL anything can clone, and after the `#` which of that repository's `skills/*` is
wanted — without one, all of them. It is cloned under `~/.humanize/skills/` and fetched again
the next time a run asks for it, so a skill somebody else maintains is one that keeps up.

## Where a flow's skills can be mounted

| Backend | Where |
| --- | --- |
| `claude` | `.claude/skills/` in the workspace |
| `codex`, `grok`, `kimi`, `qwen` | `.agents/skills/`, the directory more than one of these agreed to read |
| `agy`, `dsh`, `mimo`, `opencode`, `pi` | — none: they carry what their CLI installs |

A project's own skill of that name wins — a flow does not write over what the project keeps —
and two sessions of one flow working in one directory share the mount until the last of them
is done with it. A flow called by another flow is the same rule: whatever is already there
under that name is what both of them read.

They are mounted into the workspace on this machine. An agent [whose turns land
elsewhere](/features/remote-execution) is given them where that machine reads this directory —
a container handed this workspace is — and otherwise works with the skills its CLI installs.

## At the prompt

The `skills` row of the sheet an agent is set up on reads `as its CLI finds them`, and opening
it is a reading:

```
     1. code-review    Review the current diff… (yours)
     2. dataviz        Use this skill whenever you… (yours)
     3. housekeeping   Tidies the tree (this project)

   These are claude's own: add one, or switch one off, where claude keeps them
```

To change what a flow brings, change the flow: `f` on it in `/flow` copies it into
`.humanize/flows/`, skills and all, and from then on that name means your copy.

## See also

- [Flows › The skills a flow brings](/reference/flows#the-skills-a-flow-brings)
- [Permissions](/features/permissions) — a per-agent narrowing that *is* one
- [Agents › The skills an agent carries](/reference/agents#the-skills-an-agent-carries)
- [TUI › What each agent carries](/reference/tui#what-each-agent-carries)
