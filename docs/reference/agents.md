# Agents

Driving a coding agent from Python. An agent is settings; a
[session](/guide/concepts.md#session) is memory. Which of the two a [flow](/reference/flows.md) holds decides what
it remembers.

Everything here is importable from `hmz.agents`.

## Making one

Each backend has an agent class and a config class, and they take the same calls:

```python
from hmz.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))
```

| Backend | Agent | Config | Session |
| --- | --- | --- | --- |
| Claude Code | `ClaudeCodeAgent` | `ClaudeCodeAgentConfig` | `ClaudeCodeSession` |
| Codex | `CodexAgent` | `CodexAgentConfig` | `CodexSession` |
| DeepSeek Harness | `DshAgent` | `DshAgentConfig` | `DshSession` |
| Kimi Code | `KimiCodeCLIAgent` | `KimiCodeCLIAgentConfig` | `KimiCodeCLISession` |
| pi | `PiAgent` | `PiAgentConfig` | `PiSession` |
| opencode | `OpencodeAgent` | `OpencodeAgentConfig` | `OpencodeSession` |
| mimocode | `MimoCodeAgent` | `MimoCodeAgentConfig` | `MimoCodeSession` |
| you | `HumanAgent` | — (takes only `name=`) | `HumanSession` |

pi, opencode and mimocode name a model as `provider/id` — `openai-codex/gpt-5.5`,
`opencode/big-pickle`, `xiaomi/mimo-v2.5` — because a model there belongs to the provider that
serves it, and the CLI is asked for the pair.

DeepSeek Harness is an optional Python SDK backend. Install it with the `dsh` extra as shown
in [Installation](/guide/installation#install-humanize). It supports API-key login only:
leave `provider` empty to use the credentials and base URL saved by dsh (or its environment),
or make a `key` account from `/agents` with **ctrl+n** and give its name as `provider`. Then
construct it like any other agent:

```python
from hmz.agents import DshAgent, DshAgentConfig

agent = DshAgent(DshAgentConfig(model="deepseek-v4-flash", effort="high"))
```

It also offers `deepseek-v4-pro`. The SDK and bundled runtime are currently a developer
preview; humanize supports `deepseek-harness-sdk>=0.1.0rc6,<0.2`.

A config takes `model`, `effort`, an optional [`machine`](#where-the-turns-land), the
[skills it is loaded with](#which-skills-an-agent-is-loaded-with),
[what it may do](#what-an-agent-may-do), [which account it runs as](#which-account-it-runs-as),
and nothing else. It is frozen,
because a session resumes under the settings it opened with — a config that changed mid-flow
would silently split one conversation across two models.

An agent takes an optional `name=`:

```python
actor = ClaudeCodeAgent(config, name="actor")
```

## Turns

Calling the agent runs one turn in a session of its own and keeps nothing:

```python
agent("Read TASK.md and get started.")   # a Ralph turn: nothing carries over
```

Calling a session runs one turn *in* that session:

```python
session = agent.new()
session("Read TASK.md and get started.")   # opens the session
session("continue")                        # resumes it, the task still in context
```

Both return what the agent answered, stripped.

A turn that fails raises `subprocess.CalledProcessError` — whatever it was actually run
through, so a flow catches turns rather than transports — and leaves the session unopened, so
the next call retries the turn rather than resuming something that may not exist.

`suppress=True` turns a failed turn into an empty answer:

```python
agent(task, suppress=True)   # "" if it failed, and the loop goes round again
```

It catches a turn that failed and **nothing else**: not an agent that has been
[stopped](#stopping), and not a backend with no [goal](#goals) feature, which is a flow to
correct rather than a turn to retry.

## Sessions

```python
session = agent.new()        # nothing has been opened with the backend yet
session("first turn")        # now it has
session.id                   # the backend's id for it, e.g. "0a1b2c3d-…"
session.named                # the same id, or None before the backend has said one
session.close()              # ends whatever it was holding
```

`id` raises `RuntimeError` before a turn has landed, because the backend has not named the
session yet. `named` answers `None` instead — which is earlier and therefore more useful while
a first turn is still running, since that is when the backend is already writing the log.

A session runs one turn at a time. Two threads calling one session hold one conversation rather
than interleaving two.

Discarding a session is how a flow forgets. They are held weakly by the agent, so a Ralph loop
running for days does not grow one by a session a turn.

## The directory a session works in

A session is opened *at* a directory, and every turn of it runs there:

```python
session = agent.new(worktree)     # this conversation works in that directory
session("pwd")                    # and so does every turn of it
session.cwd                       # where that is, as an absolute path
```

It is a **session's** setting rather than a turn's, because that is what it is to these backends:
a conversation is rooted at a directory. Leave it out — the default — and the session works in
the directory the flow is running in, which is what every session was before there was anywhere
else to put one.

Every call that opens a session takes it, since opening one is what it settles:

```python
agent.new(worktree)                          # the session, to hold and to keep talking to
agent("fix the tests", cwd=worktree)         # one turn in a session of its own, there
agent.pursue(objective, cwd=worktree)
await agent.aturn(task, cwd=worktree)        # and await agent.apursue(objective, cwd=…)
agent.batch(prompts, cwd=worktree)           # every turn of the batch, there
await agent.abatch(prompts, cwd=worktree)
agent.batch_new(200, worktree)               # two hundred conversations, all in that one
```

The pattern that matters is **one agent working in several places at once** — a worktree per
task, a checkout per shard — which is a session apiece and their turns going together:

```python
held = [agent.new(worktree) for worktree in worktrees]
said = await asyncio.gather(*(one.aturn(task) for one in held))
```

`cwd=` on a batch is one directory for all of its turns; a batch *across* directories is the
gather above. Either way the agent is one agent: one set of settings, one id, one
[trace](/reference/tracing.md) — what differs is where each conversation is rooted.

For an agent whose turns land on [another machine](/reference/machines.md), the directory is **that
machine's** path, and it must be inside the workspace the anchor names. humanize puts the agent
in this machine's mirror of it and tells the anchor to run the work in the directory itself, so a
flow says where the work happens in the only names the far end has.

A directory that is not there, or one outside that workspace, raises `ValueError` before the turn
is run:

```text
/srv/nowhere: no directory to open a session in
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

which is a flow to correct rather than a backend that failed to start.

## Awaiting a turn

Every call that runs a turn has a twin that is awaited, for a flow written as
[`async def run`](/reference/flows.md#a-flow-that-waits-for-more-than-one-thing):

```python
await agent.aturn(task)                  # agent(task), in a session of its own
await session.aturn("continue")          # session("continue")
await agent.apursue(objective)           # agent.pursue(objective)
```

Same arguments, same answers, same `suppress` and `schema`. The difference is where the waiting
happens: the turn runs on a thread of its own and the loop is handed straight back, so a flow
can have as many turns going as it likes and none of them holds up the rest.

```python
acted, reviewed = await asyncio.gather(
    agents.actor.aturn(task),
    agents.reviewer.aturn(REVIEW + task),
)
```

A session is still a sequence: two turns awaited on one session are one after the other, as two
called on it are. Two turns on two sessions are two turns at once.

## Many at once

`batch` is calling the agent, as many times over as there are prompts, all of them going at the
same time — one session apiece, none of them kept, and the answers in the order they were asked
for:

```python
answers = agent.batch([f"Review {path}" for path in paths])       # blocking
answers = await agent.abatch([...])                               # awaited
reviews = agent.batch(prompts, schema=Review, suppress=True)      # shaped, and || true
```

`batch_new` opens sessions rather than running turns, however many are wanted. A session costs
nothing until a turn lands in one, so ten thousand of them is a list of ten thousand
conversations that have not started:

```python
sessions = agent.batch_new(10_000)
await asyncio.gather(*(one(f"shard {at}") for at, one in enumerate(sessions)))
```

How wide to go is a question about the machine, not about this library, so nothing here caps it:
what a batch is given is what it runs at once. `at_once` is where a flow says otherwise, and
every prompt lands either way — the rest queue behind the ones running:

```python
agent.batch(prompts, at_once=32)         # thirty-two turns going, however many prompts
```

A batch that is not suppressing raises the first failure **once every turn of it has landed**: a
turn already running cannot be taken back, and a batch that let the failure out from under the
others would leave them running with nobody waiting for them. `suppress=True` answers with `""`
(or `None`, with a schema) in that prompt's place and lets the rest through.

An agent [stopped](#stopping) mid-batch raises `Stopped`, which `suppress` deliberately does not
catch.

## Watching a turn as it happens

`stream` is the primitive; calling the session is a shell around it.

```python
for event in session.stream("write the tests"):
    print(event.kind, event.text)
```

An `Event` has `kind`, `text`, and — on a `result` from a backend that says — `tokens`, a
mapping of model to tokens spent.

| `kind` | |
| --- | --- |
| `text` | The agent talking. |
| `reasoning` | The agent thinking aloud. |
| `tool` | The agent using one. |
| `result` | The answer the turn ends on. **Exactly one closes a turn**, and it is what calling the session returns. |
| `failed` | The turn closed the other way, carrying what went wrong in place of an answer. |
| `took` | A word [put into the running turn](#talking-to-a-turn-already-running) is now in front of the model, and is what the event carries. |

A watcher sees three more that a stream does not: `begins` and `ends`, which bracket the turn,
and `asks`, which is the agent stopping to ask its user something.

```python
def looking(agent, session, event):
    if event.kind in ("begins", "ends"):
        print(f"--- {agent.id} {session and session.named} {event.kind}")

agent.watch(looking)
```

The **session** is which of that agent's conversations said it — an agent may be holding ten at
once, so a watcher that could not tell them apart would be reading ten interleaved and would
have nowhere to say the next thing back to. It is `None` only for something the agent said
rather than one of them: a question put by a server that serves every session of it at once.

A watcher that raises is the watcher's own problem: a flow must not fail because something
looking at it did.

This is the only place a run is visible. A flow drives the sessions and answers to nobody, so
the turns going past are all there is — which is what the interface's status column is built
from.

## Talking to a turn already running

```python
session.interject("actually, use pathlib")
```

The agent reads it when it next looks, so the turn already under way takes it into account
rather than being restarted with it. Landing it is not the agent having it: the word comes back
as a `took` event once it is in front of the model, which is what tells a flow it was heard.

- On a backend that takes a turn's whole prompt up front, this raises `NotImplementedError`.
- On a backend that can be talked to, it raises `RuntimeError` when nothing is running to hear
  it.

What "into the turn" means per backend is in [What each backend can do](#what-each-backend-can-do).

## Goals

A session can be given a goal instead of a prompt. This is the backend's *own* goal feature —
the one its `/goal` command reaches — not a prompt that asks for one:

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

The agent decides for itself when the objective has been met, and until it does, a turn that
would have ended starts another. A goal is as many turns of the model as it takes, and the
backend starts them itself; `pursue` follows the goal across all of them and answers with the
last. A session that has gone quiet is a goal that has stopped only once the goal itself says
so.

A flow that loops over `pursue` is running the objective again, rather than nudging an agent
that stopped early.

On a backend with no goal feature it raises `NotImplementedError`, whether or not `suppress` is
set: asking for a feature that is not there is a flow to correct.

## Hooks

A turn passes through a handful of **moments**, and a hook is a Python callable hung on one of
them. Claude Code, Codex and Kimi Code each take a table of shell commands for the same moments;
these are the same idea held here instead — hung on a live agent, taken down again while it
runs, and written in the language the flow is written in.

```python
from hmz.agents import Moment, Occasion, Verdict

def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None

agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push, tool="Bash")
```

`on` answers with a handle, so a hook wanted only for a while says so in one line:

```python
with agent.hooks.on(Moment.STOP, keep_going):
    agent(task)              # and it is down again after the block
```

`hung.off()` takes one down by hand; taking down what is already down is not an error. Hooks are
on the **agent**, so one covers every session it holds, and hanging one mid-run is the point.

### The moments

| Moment | When | What a verdict does |
| --- | --- | --- |
| `SESSION_START` | a session is about to take its first turn | — |
| `USER_PROMPT_SUBMIT` | a prompt is about to go to the agent | `refused` skips the turn; `adds` goes into the prompt |
| `PRE_TOOL_USE` | the agent has reached for a tool | — |
| `PERMISSION_REQUEST` | the backend is asking whether a tool may run | `refused` denies it, with `because` as the reason |
| `NOTIFICATION` | the agent has stopped to ask its user something | — |
| `STOP` | a turn has ended | `refused` sends the agent on, with `because` as the next prompt |
| `SESSION_END` | a session has been closed | — |

A refused `STOP` is what a [goal](#goals) is, written by hand: the turn is not over until the
hook lets it be. `occasion.again` counts how many times this turn has already been sent on, so a
hook that keeps refusing can decide to stop.

```python
def keep_going(occasion: Occasion) -> Verdict | None:
    if occasion.again < 3 and "TODO" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="There is still a TODO in TASK.md.")
    return None
```

A hook is told an `Occasion` — `moment`, `agent`, `session`, `prompt`, `tool`, `about`, `input`,
`said`, `again` — and answers with a `Verdict` or with `None`, which says nothing. Two hooks on
one moment are one verdict: refused if either refused, and adding everything either added.

A hook that raises has said nothing. A flow must not fail because something hung off it did —
with one exception: a hook that drove an agent which has been [stopped](#stopping) lets
`Stopped` out, so a run ended by hand reads as ended by hand rather than as one that finished.

### Not every backend runs every moment

`agent.moments` is what this one runs, and `hooks.on` refuses a moment that is not in it —
where the hook is hung, rather than by quietly never firing.

| Moment | Claude Code | Codex | Kimi Code | you |
| --- | --- | --- | --- | --- |
| everything above except `PERMISSION_REQUEST` | yes | yes | yes | no |
| `PERMISSION_REQUEST` | yes | yes | no | no |

Claude Code and Codex ask before they use a tool — Claude over the same stream the turn is read
from, Codex through its app server — and wait for the answer, so those are the two backends
here where a refusal reaches the agent. It also wants the [`auto` rung](#what-an-agent-may-do),
which is the one setting under which either of them asks at all. The rest are driven
unattended, which is what a flow watching its agent rather than gating it means.
`HumanAgent` runs none of them: a moment is a point in a turn of a model, and the person takes
no such turn.

A flow says which moments it needs where it declares the agents it drives, and is refused before
its first turn if it was given one that cannot run them — see
[Flows](/reference/flows.md#asking-for-an-agent-that-can-do-something).

## Questions

An agent may stop mid-turn to ask its user something. Set `ask` and it reaches you:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

A `Question` has `text` and `options` — the answers the agent offered, if it offered any. An
answer is not held to them; every backend that offers options takes something else too. But
they are what the agent expects, and what an interface has to show for the question to read as
one.

Leave `ask` unset — as a flow run from the command line does — and the backend is told **nobody
answered** rather than being left waiting. A turn waiting on an answer that is not coming is a
flow that has stopped.

Whatever happens, the question also reaches anything [watching](#watching-a-turn-as-it-happens)
the agent as an `asks` event.

Two more hooks, both set by whatever is driving the agent and both left unset on a command
line:

| | |
| --- | --- |
| `agent.waiting` | Asked as each turn starts for anything said to this agent while no turn was open. What it returns goes into that turn. |
| `agent.prompting` | Asked between turns for the next thing to say, so a flow can be a conversation rather than a loop. `None` once there will be nothing more. |

`agent.prompted()` is the call a flow makes; it raises [`Stopped`](#stopping) for an agent
stopped while it waited, so a run ended by hand is written down as ended by hand rather than as
one that finished.

## Stopping

```python
agent.stop()      # take no further turn, and end the one being taken
agent.stopped     # whether that has happened
```

The turn under way is closed out and every later call raises `Stopped`. What the turn was doing
is left where it got to; what ends is the agent's part in it. A stop that waited for a turn
would not read as a stop — a model can think for minutes.

`Stopped` is not a `CalledProcessError`, so the loops that carry on past a turn that failed do
not carry on past this.

## Names, and what a run left behind

Two agents at one model and one effort are still two agents — an actor and the reviewer that
reads its work. `id` is what tells them apart, and what a [trace](/reference/tracing.md) groups their
sessions under:

```python
agent.id       # the name you gave it, the name the flow calls it, or one nothing else answers to
agent.backend  # "claude", "codex", "dsh", "kimi", "pi", "opencode" or "mimo"
agent.opened   # the backend's id for every session this agent ever opened, oldest first
agent.sessions # the ones somebody still holds
agent.config   # what it runs at
```

`opened` is ids rather than sessions, so a flow running for days remembers them in a list of
strings — including the ones a Ralph loop dropped a turn later. It is what a trace is handed to
say which trajectories were this agent's:

```python
from hmz.tracing import collect

collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

A [flow](/reference/flows.md#how-many-agents-and-what-they-are-for) that declares its agents as a
`NamedTuple` names them for you, and a run started through `Runner` writes all of this into its
[cycle](/reference/tracing.md#cycles) — so this is only needed for agents built and driven by hand.

## The person as an agent

A flow that is a conversation rather than a loop has two sides, and the second is you.

```python
from hmz.agents import HumanAgent

person = HumanAgent()                      # takes only an optional name=, defaulting to "human"
person("Here is what I did. What next?")   # asks, and answers with what was typed
```

It is not a coding agent: it runs no model, spends nothing, and its turns are not bracketed by
the `begins`/`ends` that say whose turn it is — counting them would put the person in the graph
of who handed to whom and spin a clock at them while they thought.

In a flow, declare one among the agents and it is handed over like the rest — see
[Flows](/reference/flows.md#the-person-at-the-prompt). Nobody is asked what it runs, so it is not one of
the agents `-a` names.

### Asking them for a shape, which is a questionnaire

Given a [`schema`](#answering-in-a-shape), the person is not shown a JSON Schema — they are
asked **a question per field**, and the model is built out of what they typed:

```python
class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")

settled = person("How should I do this?", schema=Settled, suppress=True)
if settled is not None and settled.tests:
    ...
```

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers it offers |
| `bool` | `yes` and `no` |
| a default | “or `-` for 3” — and a dash takes it |
| `list[str]` | one line, separated by commas |

Each question goes the road a coding agent's own question takes — `AgentBase.asked`, which the
interface shows and answers — so it is a real question there, options and all, and `/afk` or a
command line answers it the way it answers any other: nobody is there. What the model refuses is
put back on the field it was refused for, in the model's own words, a bounded number of times;
a questionnaire nobody filled in answers with `None` under `suppress`.

This is the same thing a coding agent's `AskUserQuestion` is, reachable from a flow — and more,
since the flow states the shape of the whole answer once, in the model it is going to use.

## Efforts

`effort` is passed to the backend in the backend's own wording. humanize does not check it
against a list, so a value your account has and this page does not still works.

| Backend | Efforts |
| --- | --- |
| Claude Code | `low`, `medium`, `high`, `xhigh`, `max`, and `ultracode` |
| Codex | `low`, `medium`, `high`, `xhigh`, and `max`/`ultra` on the models that take them |
| DeepSeek Harness | `off`, `high`, `max` |
| Kimi Code | `low`, `medium`, `high`, `max`, each also as `swarm…` |
| pi | `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| opencode, mimocode | the model variant: `minimal`, `low`, `medium`, `high`, `xhigh` |

**`ultracode`** is Claude Code's `xhigh` thinking with the turn opted into orchestrating a fleet
of its own. It is more work than any single-agent effort, which is why it sits above `max`.

**Kimi Code's effort says how wide to run as well as how hard to think.** `max` is one agent;
`swarmmax` is the same thinking at the width of a fleet of subagents. The prefix is exported as
`hmz.agents.SWARM` for anything that has to take it apart.

Codex's models differ from each other — `gpt-5.6-sol` takes `ultra`, `gpt-5.5` does not — so
the interface offers each model only the efforts it takes.

## Moving the effort while it runs

A config is frozen, because a session resumes under the settings it opened with. The effort is
the one of them a flow may move as it goes:

```python
agents.builder.effort = "low"       # every session of this agent, from its next turn
session.effort = "max"              # this conversation alone
session.effort = ""                 # and back to whatever the agent runs at
```

Reading it back is the same property. `agent.config.effort` stays what the agent was
*configured* with; `agent.effort` is what its turns actually run at.

**It takes hold on the next turn.** The turn already under way keeps the effort it started at:
a model does not think harder halfway through an answer, and a flow that changed it mid-turn
would be describing a turn that never happened.

Each backend carries it the way that backend takes it. Codex, Kimi Code, opencode and mimocode
take the effort with each turn, so the next turn simply carries the new one. Claude Code and
DeepSeek Harness take it when their runtime starts, so moving it restarts that runtime and
resumes the same conversation at the new effort. pi has a command for it, and is told.

A `swarm` prefix moves with it on Kimi Code: `agent.effort = "swarmmax"` is `max` thinking at
the width of a fleet, from the next turn on.

## What it has cost, and how fast

Every session and every agent says what it has spent and how fast it is spending it:

```python
session.spent()          # Usage(input=41230, output=2180, cache_read=980100)
session.rate()           # tokens a second, by kind, over the last five minutes
session.rate(over=60)    # over the last minute instead
session.juice(over=60)   # output tokens an average turn of the model came out with
agent.spent()            # every session this agent has opened, dropped ones included
agent.rate(over=60)
agent.juice()
```

A `Usage` is a **mapping of kind to tokens**. `input` and `output` are the two every backend
counts, and are on it as attributes; the rest — a cache read, a cache write, the reasoning a
backend counts beside the output rather than inside it — differ from CLI to CLI, so a kind
that is not there is one that backend does not report:

```python
spent = session.spent()
spent.input, spent.output, spent.total       # always
spent.get("cache_read", 0)                   # for a backend that counts one
dict(spent)                                  # everything it does count
```

**A rate is tokens a second over seconds on the clock**, not seconds an agent was talking: a
flow sleeps between rounds, commits, reads what the last turn wrote, and that time is time the
tokens were spent over. The window defaults to five minutes — `hmz.agents.WINDOW`, the
same one the interface's readout is over — and a run younger than the window is measured over
the run, so a rate read a minute in is what that minute came to rather than a fifth of it.

**It moves while the turn is still running.** A turn is minutes long, so a number that only
moved when one ended would stand still for all of them: every backend here is read as it says
what each request to the model cost — Claude Code and pi on the message it answered with,
Codex on `thread/tokenUsage/updated`, DeepSeek Harness and pi on finalized assistant messages,
opencode and mimocode on each step, Kimi Code from the session it is polling anyway.

**`juice()` is the third reading, and it is not a clock at all.** It is what one turn of the
*model* came out with — one request and the answer to it, of which a turn a flow asks for is
many. That average is what an effort moves: a model asked to think harder writes more in each
answer and takes longer over it. So it is the number to steer by when what is being held is
how hard the thing is thinking rather than how fast a bill is running up, and it is what
[`fixed_juice_ralph`](/reference/flows.md#the-official-flowverse) governs on. A window with no
turn in it reads as `0.0`: nothing to go on, which a flow tells apart from a turn that said
nothing.

A backend that states a whole turn's cost after having said what each request in it came to
is settling up rather than taking another turn, and is not counted as one — or the average
would be halved by the accounting.

The `result` event a turn ends on carries the same reckoning as `spent`, beside the per-model
`tokens` it already carried: the two are the same spending counted two ways, and
`result.spent.total` is what `result.tokens` comes to.

## What each backend can do

| | Claude Code | Codex | DeepSeek Harness | Kimi Code | pi | opencode, mimocode |
| --- | --- | --- | --- | --- | --- | --- |
| Driven through | its command line, held open | its app server | its Python SDK | its app server | its command line, held open | its command line, one run per turn |
| [`interject`](#talking-to-a-turn-already-running) | yes — answered within the same turn | yes — a steer on the running turn | no | yes — queued, then steered in | yes — a steer on the running turn | no — a run per turn has ended |
| [`pursue`](#goals) | yes | yes | yes | yes | no | no |
| [`PERMISSION_REQUEST`](#not-every-backend-runs-every-moment) | yes | yes | no | no | no | no |
| Sub-agents in a trace | yes | yes | no | yes | no | no |

DeepSeek Harness currently accepts only `permission="bypass"` and `skills=None`. Its preview
SDK exposes neither a per-session sandbox/approval control nor exact per-agent skill selection;
another value is rejected before the runtime starts rather than silently ignored.

opencode and mimocode keep a session in a database rather than in a log file, so there is
nothing for `hmz collect` to gather and nothing for the interface to read a running cost out
of. What their turns cost still reaches a flow: each backend says it as the turn lands.

A backend is driven through its command line where that can express what an agent is configured
with, and through the app server it serves its own client from where it cannot. A model, an
effort, a mode or a goal that has no flag is a setting of a session there — and asking the model
for it in the prompt is not the same feature.

A turn that must stay open to be talked to is such a case: a command line run per turn has ended
by the time there is anything to say to it.

## Answering in a shape

A turn given a `schema` answers with that pydantic model instead of with text:

```python
from pydantic import BaseModel, Field

class Review(BaseModel):
    """What a review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, word for word.")

review = agent(asked, schema=Review)   # a Review, not a str
if review.done:
    ...
```

The model *is* the question: its fields, their types, which are required and the line each was
declared with are what the backend is given, so nothing has to be repeated in the prompt.

Where the backend can be held to it, it is: Claude Code gets `--json-schema` and validates the
answer itself, and Codex gets the turn's `outputSchema`. A backend that has no such setting is
asked in the prompt instead, and what it says is read back — `SessionBase.shapes` is which of
the two a backend is. The person is asked neither way: they get
[a question per field](#asking-them-for-a-shape-which-is-a-questionnaire). Either way the
answer arrives as the model or not at all.

`suppress=True` answers `None` rather than `""`, and covers both a turn that failed and one
whose answer is not the shape it was asked for — an answer that is not what was asked for is a
turn that did not do what it was told. Without it, the second raises `ValueError`.

Claude's is an argument of the process rather than of the turn, so asking one session for a
shape it was not started with ends that process and starts one that resumes the conversation.
The conversation is not restarted with it.

## What an agent may do

A config's `permission` is one rung of a four-rung ladder, loosest last — named the way these
CLIs name them rather than in a vocabulary of humanize's own:

| Rung | What it means |
| --- | --- |
| `read-only` | It may look at anything and change nothing — no edits, no commands. |
| `workspace-write` | It may change the workspace it was given, and is stopped at the edge of it. |
| `auto` | It may reach for anything, and what it asks for is granted. |
| `bypass` | Nothing is asked and nothing is checked. |

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", permission="read-only")
```

The command line names the same setting in an agent's written-out form:

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review the current change"
```

`bypass` is the default, because that is what a flow driving an agent unattended has always
run it at: a flow watches its agent rather than gating it, and a turn waiting on an approval
nobody is there to give is a flow that has stopped. Anything tighter is a choice, and in the
interface it is made on `/agents` with `ctrl+p`.

Every backend has a ladder of its own and none of them has the same four rungs, so each driver
reaches for whichever of its own settings says the same thing:

| Rung | Claude Code | Codex | DeepSeek Harness | Kimi Code | pi | opencode, mimocode |
| --- | --- | --- | --- | --- | --- | --- |
| `read-only` | `plan` mode | `read-only` sandbox | — | plan mode | without `bash`, `edit`, `write` | `edit` and `bash` denied |
| `workspace-write` | `acceptEdits` mode | `workspace-write` sandbox | — | plan mode off | — | `webfetch` denied |
| `auto` | Claude's own `auto` mode | `workspace-write`, approvals on request | — | — | — | nothing denied |
| `bypass` | `bypassPermissions` | `danger-full-access` | supported | `yolo` mode | — | — |

**Codex is the one backend here with a sandbox of its own**, so its rungs are the real thing
rather than an approximation of one. Where a backend cannot tell two rungs apart it says so
here rather than pretending: a dash is the rung above it, run again.

**`auto` is the rung where a hook gets a say.** It is the one setting under which a backend
actually asks before it acts and waits for the answer, so it is the one where a hook hung on
[`PERMISSION_REQUEST`](#hooks) can refuse something and have the agent hear it. Claude Code
and Codex both run that moment; the rest have nothing to hang it on.

## Which skills an agent is loaded with

A config's `skills` names the skills of its CLI this agent is to **have**:

```python
ClaudeCodeAgentConfig(model=…, effort=…, skills=("code-review", "run"))
```

`None` — the default — is the CLI as it comes, which is every skill it finds. A tuple is
exactly those and nothing else, whatever is installed afterwards. It is a setting of the
agent, so two agents of one flow may be loaded differently, and neither touches the settings
of the CLI itself.

Every backend is told the other way round — a CLI comes with its skills loaded and has to be
talked out of one — so what actually goes on the wire is the rest of them, worked out by
looking at what is installed:

```python
from hmz.agents.skills import leaving, skills

skills("claude")                       # what it would load here: yours, and this project's
leaving("claude", ("code-review",))    # what to switch off so that only that one is left
```

| Backend | How it is told | What it comes to |
| --- | --- | --- |
| `claude` | `--disallowedTools "Skill(<name>)"` | the agent is refused the skill. Claude still lists it — no flag takes one off that list |
| `codex` | `-c skills.config=[{name="<name>", enabled=false}]` on its app server | the skill is not loaded for that server, and the user's own `config.toml` is untouched |
| `dsh` | — | the preview SDK cannot select an exact skill set; `skills` must be `None` |
| `kimi` | — | `kimi web` takes no `--skills-dir`, so a skill it finds is one it loads |
| `pi` | — | it is told which skills to load by path, and finds none of its own to choose between |
| `opencode`, `mimo` | — | neither offers a way of switching one off for a single run |

Where each CLI keeps them is written down in `hmz.backends`; nothing is asked of the CLI
itself, for the reason nothing else is either. The interface asks which to have on the
[`/agents` sheet](/reference/tui.md#what-each-agent-is-loaded-with).

## Where the turns land

A config's `machine` says where an agent's work goes. `None` — the default — is this machine.

```python
from hmz.machines import AnchoredConfig, DockerConfig

ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

`agent.anchor` is where its turns land, and brings the machine up the first time it is asked
for — which is the first turn. Constructing an agent pulls no image and starts no container.
See [Machines](/reference/machines.md).

**Which agents may be given one at all is the flow's to say.** An agent handed to a flow whose
place for it says nothing is refused before its first turn, because a flow is written for one
shape of work — see [Flows › Where each agent works](/reference/flows.md#where-each-agent-works). Setting a
`machine` here is what fills a place the flow declared `Remote`; a place it declared `Isolated`
is settled by the flow itself and takes no `machine` from anyone.

## Which account it runs as

A config's `provider` names one of the [providers](/reference/providers.md) made for its CLI. `""` — the
default — is the CLI as you already run it, signed in the way you already signed in.

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", provider="deepseek")
```

A turn of such an agent is given that provider's variables, and reads its credentials out of
that provider's own directory rather than the CLI's — so two agents of one backend can be two
accounts at the same time, one on a subscription and one on somebody's gateway. Only the
credential files move: the sessions, the settings and the skills are the CLI's own.

```python
agent.provider       # Provider | None -- the account, read once and kept
agent.environment()  # what its turns are run with, on top of what they inherit
```

`agent.provider` raises `ValueError` the first time a turn needs an account that is not there,
naming the agent and what it was called. An agent that cannot find the account it was told to
run as does not quietly run as yours.

## API summary

```python
type Where = str | os.PathLike[str] | None   # a directory, or None for the one the flow is in

class AgentBase:
    moments: ClassVar[frozenset[Moment]]   # the ones a hook may be hung on here

    id: str                 # what this agent is called
    backend: str            # "claude", "codex", "kimi", "pi", …
    config: AgentConfig     # model, effort, machine, skills, permission, provider
    opened: list[str]       # the backend's id for every session it ever opened
    sessions: list[SessionBase]
    stopped: bool
    anchor: AnchorConfig | None
    provider: Provider | None
    hooks: Hooks            # what is hung on its moments

    # `cwd` is the directory the session it opens works in, or None for the flow's own.
    def __call__(prompt: str, *, suppress: bool = False, schema: type[T] = …, cwd: Where = None) -> str | T | None
    def pursue(objective: str, *, suppress: bool = False, cwd: Where = None) -> str
    def new(cwd: Where = None) -> SessionBase

    async def aturn(prompt: str, *, suppress: bool = False, schema: type[T] = …, cwd: Where = None) -> str | T | None
    async def apursue(objective: str, *, suppress: bool = False, cwd: Where = None) -> str

    def batch_new(count: int, cwd: Where = None) -> list[SessionBase]
    def batch(prompts, *, suppress: bool = False, schema: type[T] = …, at_once: int = 0, cwd: Where = None) -> list[...]
    async def abatch(prompts, *, suppress: bool = False, schema: type[T] = …, at_once: int = 0, cwd: Where = None) -> list[...]

    def rename(name: str) -> None
    def stop() -> None
    def watch(listener: Callable[[AgentBase, SessionBase | None, Event], None]) -> None
    def asked(question: Question) -> str | None
    def prompted() -> str | None

    ask: Callable[[Question], str | None] | None
    waiting: Callable[[], list[str]] | None
    prompting: Callable[[], str | None] | None

class SessionBase:
    id: str                 # raises until a turn has landed
    named: str | None       # the same, or None
    cwd: str                # where this conversation works, as the machine it lands on names it

    shapes: ClassVar[bool]  # whether the backend can be held to a schema

    def __call__(prompt: str, *, suppress: bool = False, schema: type[T] = …) -> str | T | None
    def stream(prompt: str, *, schema: type[BaseModel] | None = None) -> Iterator[Event]
    def pursue(objective: str, *, suppress: bool = False) -> str

    async def aturn(prompt: str, *, suppress: bool = False, schema: type[T] = …) -> str | T | None
    async def apursue(objective: str, *, suppress: bool = False) -> str

    def interject(text: str) -> None
    def close() -> None

@dataclass(frozen=True)
class Event:
    kind: str               # text | reasoning | tool | result | failed | took | begins | ends | asks
    text: str
    tokens: Mapping[str, int]

@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[str, ...]

class Stopped(Exception): ...

class Hooks:
    moments: frozenset[Moment]

    def on(moment: Moment, hook: Hook, *, tool: str = "") -> Hung
    def off(hung: Hung) -> None
    def hooked(moment: Moment) -> bool
    def fire(occasion: Occasion) -> Verdict

class Hung:                 # what `on` answers with, and a context manager
    def off() -> None

@dataclass(frozen=True)
class Occasion:
    moment: Moment
    agent: str
    session: str
    prompt: str
    tool: str
    about: str
    input: Mapping[str, Any]
    said: str
    again: int

@dataclass(frozen=True)
class Verdict:
    refused: bool
    because: str
    adds: str

class Unhooked(ValueError): ...   # a moment this backend does not run
```

`CommandSessionBase` and `StreamSessionBase` are the two shapes a backend is driven in — one
command per turn, or one long-lived process spoken to a line at a time. Subclass them to add a
backend; `src/hmz/agents/SPEC.md` is the contract they have to keep.
