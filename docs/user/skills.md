# Skills

Skills come in two kinds, and the difference between them is who they belong to. Use this page
to see which skills an agent loads, and to change what a flow brings.

| | |
| --- | --- |
| **the CLI's own** | installed on this machine, the way that CLI installs one. humanize reads the list and changes nothing |
| **the flow's own** | in the flow's `skills/`, mounted onto every session its agents open and taken away again after |

## Try it

The `skills` row of the sheet an agent is set up on reads `as its CLI finds them`. Opening it
is a reading:

```
     1. code-review    Review the current diff… (yours)
     2. dataviz        Use this skill whenever you… (yours)
     3. housekeeping   Tidies the tree (this project)

   These are claude's own: add one, or switch one off, where claude keeps them
```

To change what a **flow** brings instead, change the flow: press `f` on it in `/flow` to copy
it into `.humanize/flows/`, skills and all. From then on that name means your copy.

## The CLI's own skills

A skill you installed loads for every agent of that CLI. It switches off where that CLI
switches one off, and it is not a setting of any agent. Where each CLI keeps them is written
down in `hmz.backends`:

| Backend | Yours | This project's |
| --- | --- | --- |
| `agy` | `~/.gemini/antigravity-cli/skills/*/SKILL.md` | — a printed turn opens no project |
| `claude` | `~/.claude/skills/*/SKILL.md` | `.claude/skills/*/SKILL.md` |
| `codex` | `~/.codex/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md`, `.codex/skills/*/SKILL.md` |
| `cursor` | `~/.cursor/skills/*/SKILL.md`, `~/.config/cursor/skills/*/SKILL.md` | `.cursor/skills/*/SKILL.md` |
| `grok` | `~/.grok/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md`, `~/.claude/…`, `~/.cursor/…` | `.grok/skills/*/SKILL.md`, `.agents/…`, `.claude/…`, `.cursor/…` |
| `kimi` | `~/.kimi-code/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.kimi-code/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` |
| `mimo` | `~/.config/mimocode/skill(s)/*/SKILL.md`, `~/.agents/…`, `~/.claude/…`, `~/.codex/…` | `.mimocode/skill(s)/*/SKILL.md`, `.agents/…`, `.claude/…`, `.codex/…` |
| `opencode` | `~/.config/opencode/skill(s)/*/SKILL.md`, `~/.agents/…`, `~/.claude/…` | `.opencode/skill(s)/*/SKILL.md`, `.agents/…`, `.claude/…` |
| `pi` | `~/.pi/agent/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | — read only for a project you approved |
| `qwen` | `~/.qwen/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.qwen/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` |
| `zcode` | `~/.zcode/skills/*/SKILL.md`, `~/.agents/skills/*/SKILL.md` | `.zcode/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` |

Each backend's own home moves where that backend's variable moves it: `CODEX_HOME`,
`KIMI_CODE_HOME`, `GROK_HOME` and the rest. opencode and mimocode keep their skills beside
their configuration rather than their data, so theirs move with `XDG_CONFIG_HOME`. Antigravity
CLI and ZCode have no variable of their own, so what moves their home is the home itself.
DeepSeek Harness keeps
none: its command line reads skill directories, and the SDK humanize drives does not.

The same list from Python:

```python
from hmz.agents.skills import skills

skills("claude")   # what it would load here: yours, and this project's
```

humanize asks nothing of the CLI to find out, because asking would mean starting it. It writes
nothing either. What a person has installed is not something a flow is entitled to rewrite, and
a list that could be adjusted here while the CLI's own list said otherwise would be two answers
to one question.

## The flow's own skills

The rest of this page is the weaver's — whoever wrote the flow.

A flow is a directory. The `skills/` inside it is what that flow works by, in the same layout
every one of these CLIs already reads a skill in:

```
official/rlar/
├── __init__.py
└── skills/
    └── review-notes/
        └── SKILL.md
```

The flow's agents get those skills in every session they open. They are **mounted**: copied
where that backend reads a project's own skills for as long as the session lives, then taken
away again after. Nothing is installed, and nothing of yours is touched. See
[Flows › The skills a flow brings](/reference/flows#the-skills-a-flow-brings).

A flow may also name skills that live in somebody else's repository:

```python
@flow(skills=("https://github.com/humanfia/flowverse#review-notes",))
def run(agents: Agents, task: str) -> None:
    ...
```

The value is a git URL anything can clone. The part after the `#` names which of that
repository's `skills/*` is wanted, and without one, all of them are. It is cloned under
`~/.humanize/skills/` and fetched again the next time a run asks for it, so a skill somebody
else maintains is one that keeps up.

### Where they are mounted

| Backend | Where |
| --- | --- |
| `claude` | `.claude/skills/` in the workspace |
| `cursor` | `.cursor/skills/` in the workspace |
| `codex`, `grok`, `kimi`, `mimo`, `opencode`, `qwen`, `zcode` | `.agents/skills/`, the directory more than one of these agreed to read |
| `agy`, `dsh`, `pi` | — none: they carry what their CLI installs, and nothing else |

The three given none read no such directory the way humanize drives them. DeepSeek Harness's
SDK reads none at all; Antigravity CLI is run as `--print` and opens no project to read one
from; pi reads the
workspace's only for a project somebody has approved. A skill copied there would be one no turn
of that flow would ever load, which is worse than none.

A project's own skill of that name wins, and a flow does not write over what the project keeps.
Two sessions of one flow working in one directory share the mount until the last of them is
done with it, and a flow called by another flow follows the same rule: whatever is already
there under that name is what both of them read.

Skills are mounted into the workspace on this machine. An agent [whose turns land
elsewhere](/user/remote-execution) is given them where that machine reads this directory — a
container handed this workspace is such a place. Otherwise the agent works with the skills its
CLI installs.

### Which of them a conversation carries

Every session an agent opens carries all of the flow's skills — until it says otherwise:

```python
session = agent.new()
session.loads(["writing-tests"])   # from its next turn on
session.loads(None)                # all of them again
```

An agent is what it was made as. A conversation is a thing that gets somewhere, and this is the
one thing about what it works by that moves with it: a session that has finished reading the
codebase and started writing the tests wants the skill about writing them and no longer wants
the eight about reading it. Two conversations of one agent may carry different sets at once.

This is about the skills the flow brings. The ones the CLI installed are still that CLI's own,
and nothing here switches one of those on or off.

## See also

- [Flows › The skills a flow brings](/reference/flows#the-skills-a-flow-brings)
- [Permissions](/user/permissions) — a per-agent narrowing that *is* one
- [Agents › The skills an agent carries](/reference/agents#the-skills-an-agent-carries)
- [TUI › What each agent carries](/reference/tui#what-each-agent-carries)
