# Features

One page per thing humanize does. Each says what it is, how to reach it from the prompt, from a
command line and from Python, and what it will not do.

## At the prompt

| | |
| --- | --- |
| [Being away (`/afk`)](/features/afk) | Whether an agent may stop and ask you something. |
| [Showing the working (`/details`)](/features/details) | Tool calls and thinking, or only what the agent says. |
| [The shape of a run (`/status`)](/features/status) | Who is working, who handed to whom, what it cost. |
| [Talking to a running turn](/features/steering) | A line typed mid-turn goes *into* it, not after it. |
| [Many conversations at once](/features/conversations) | One transcript, **tab** between the agents that are working. |
| [Completion](/features/completion) | What a half-typed line could become, under the editor. |
| [History](/features/history) | Everything typed here before, on ↑ and ↓. |
| [Exporting a transcript](/features/export) | `/export` writes what is on screen, as it was written. |
| [What a project remembers](/features/settings) | Reopening finds it set up the way you left it. |
| [Stopping](/features/stopping) | **esc** ends the flow; what that does to a turn. |

## What an agent is

| | |
| --- | --- |
| [Efforts](/features/efforts) | How hard to think — and moving it while the flow runs. |
| [Permissions](/features/permissions) | Four rungs, from `read-only` to `bypass`. |
| [Skills](/features/skills) | Which of a CLI's skills this agent is loaded with. |
| [Goals](/features/goals) | The backend's own goal feature: it decides when it is done. |
| [Questions](/features/questions) | An agent stopping mid-turn to ask its user something. |
| [Answers in a shape](/features/shapes) | A turn that answers with a pydantic model instead of prose. |
| [Hooks](/features/hooks) | Python callables hung on the moments of a turn. |
| [Cost and rate](/features/tally) | What has been spent, how fast, and how hard it is thinking. |
| [The person as an agent](/features/human-agent) | You, driven by a flow like any other agent. |

## Where the work lands

| | |
| --- | --- |
| [Providers](/features/providers) | One CLI, two accounts, at the same time. |
| [Containers](/features/containers) | A container of the agent's own, up on the first turn. |
| [Remote execution](/features/remote-execution) | The agent here; its commands on the build box. |
| [Worktrees](/features/worktrees) | One agent working in several directories at once. |

## What a run leaves behind

| | |
| --- | --- |
| [Flowverses](/features/flowverses) | A git repository of flows, offered by name. |
| [Tracing](/features/tracing) | The whole run as one timeline you can open in Perfetto. |

---

Looking for the exhaustive list of flags and keys instead? [CLI](/reference/cli) and
[TUI](/reference/tui).
