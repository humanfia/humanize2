# Agents

Driving a coding agent from Python. An agent is settings; a
[session](/user/concepts#session) is memory. Which of the two a [flow](/reference/flows) holds decides what
it remembers.

Everything here is importable from `hmz.agents`. This is the layer under a flow rather than the
one a flow is written against: `AgentBase` and `SessionBase` answer to the `Agent` and `Session`
interfaces [flows](/reference/flows#what-a-flow-drives) declares, and a flow imports those from
`hmz.flows`. Reach for this page when you are building agents yourself — from a script, from a
test that stands in for one — rather than weaving a flow.

## Making one

Each backend has an agent class and a config class, and they take the same calls:

```python
from hmz.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))
```

A backend is named here by the command it is installed as, which is the name `-a` takes and the
name the interface shows. The classes keep the product's own full name.

| Backend | Agent | Config | Session |
| --- | --- | --- | --- |
| `agy` | `AntigravityCLIAgent` | `AntigravityCLIAgentConfig` | `AntigravityCLISession` |
| `claude` | `ClaudeCodeAgent` | `ClaudeCodeAgentConfig` | `ClaudeCodeSession` |
| `codex` | `CodexAgent` | `CodexAgentConfig` | `CodexSession` |
| `cursor` | `CursorAgent` | `CursorAgentConfig` | `CursorSession` |
| `dsh` | `DshAgent` | `DshAgentConfig` | `DshSession` |
| `grok` | `GrokBuildAgent` | `GrokBuildAgentConfig` | `GrokBuildSession` |
| `kimi` | `KimiCodeCLIAgent` | `KimiCodeCLIAgentConfig` | `KimiCodeCLISession` |
| `pi` | `PiAgent` | `PiAgentConfig` | `PiSession` |
| `qwen` | `QwenCodeAgent` | `QwenCodeAgentConfig` | `QwenCodeSession` |
| `opencode` | `OpencodeAgent` | `OpencodeAgentConfig` | `OpencodeSession` |
| `mimo` | `MimoCodeAgent` | `MimoCodeAgentConfig` | `MimoCodeSession` |
| `zcode` | `ZcodeAgent` | `ZcodeAgentConfig` | `ZcodeSession` |
| whatever you added | `AcpAgent` | `AcpAgentConfig` | `AcpSession` |
| you | `HumanAgent` | — (takes only `name=`) | `HumanSession` |

## When an account goes down

A key gets revoked, a gateway starts refusing, a subscription runs out of quota — and what a
flow would otherwise see is a turn that failed. Two things happen first.

**It is tried again.** How many times over a failed turn is taken again, how long to wait
between tries, and how long the whole of that may go on for are said about the **place** the
turn runs at — the CLI, the account and the model — rather than about the credentials:

```sh
hmz fallback retry claude@mine/claude-opus-5 3 -p exponential-jitter -t 120
```

Nothing is retried by default — a turn is taken once, as it always was — because a prompt the
model refused is the same refusal every time, and only you know which of your places fails the
other way. The waits are the ones everybody uses: `none`, `constant`, `linear`, `exponential`,
`exponential-jitter` (full jitter, which is what keeps a flow's agents from all coming back on
the same second) and `fibonacci`.

**Some failures are taken once whatever the step says.** A backend that knows its own
failure cannot come out differently says so by raising `hmz.agents.Unrecoverable`, and that
one is neither retried nor carried to the next account in the chain. A conversation longer
than the model's context window is that long again on the next try; a backend that will not
answer under the session id it was opened with will not answer under it a second later. An
account set to retry would otherwise take those on its own schedule for as long as anybody
left the flow running. It is a `subprocess.CalledProcessError` like every other failed turn,
so a flow that catches turns catches it.

**Then the chain moves on.** This half is said on the account rather than on the agent: it is
the account that goes down, and each account names the one to carry on under when it has
failed, and that one names the next:

```sh
hmz providers falls-back claude/subscription key
hmz providers falls-back claude/key gateway
```

so a subscription that runs out falls to a key, and a key that is refused falls to a gateway.
`/providers`, cursor on the account, then **enter**: *falls back to* asks the same thing.

**An agent with no account has a chain too.** The account this machine is already signed into
is an account here as well — `claude/`, a backend and no name at all — so it is where the
chain of an agent nobody configured begins:

```sh
hmz providers falls-back claude/ spare     # your own login, then the key
```

It is an account for that purpose and nothing else: humanize did not make it, keeps no
credentials for it, and a turn under it is exactly the turn it always was — nothing added to
the environment, nothing taken out of it, no path answered by another. Nothing may fall back
*to* it, either: an agent that is to try it is an agent given no account, which is where its
chain already starts.

## When the place has nowhere left to run

Some failures no account answers. The model was retired this morning, the CLI will not start,
the region has gone dark, the rate limit is on the whole account rather than on one request.
Another key for the same backend is another way of asking the same thing that is not there.

What answers those is another **place** — a CLI, an account and a model — and it is written
down [between the two](/user/fallback) rather than on either:

```sh
hmz fallback add claude@work/claude-opus-5 codex@key/gpt-5.6-sol
```

```python
agent.spec          # 'claude@work/claude-opus-5' -- the place it runs at
agent.stands_in()   # the agent that takes its turns, or None where nothing was written down
```

It is the last thing a turn tries, after the retries and after the account chain, and the
reason is the conversation. No backend takes another backend's session id, so the turn that
moves is taken in a **new session** at the place it moved to — by an agent configured exactly
as the one it left, carrying that agent's effort, its permission rung and the flow's skills,
and answering back through the session that asked, so the flow sees one turn either way.

That session is opened once and held for as long as the one that asked for it, and ends when
it does. The conversation is lost at the move and not every turn after it: a stateful loop
that moved is one conversation on the other side.

The stand-in is built the first time a turn has nowhere left to go, and kept: an agent that
went down is not one to try again each turn, and a chain of four agents all started when the
run was would be three CLIs held open for a failure that never came. An `Unrecoverable` is
still taken once — it is not carried here either.

It all happens on the **same** conversation: the session is the backend's own and is named by
an id, so the account it moves to picks it up where the last one left off. The agent stays
there for every turn after — an account that has gone down is not one to try again each turn —
and the last failure of the last account in the chain is what the turn raises. A chain that
comes round on itself ends at the second sight of an account.

What the failed attempts already put on the transcript stay there — it is how somebody reading
it finds out the account went down, how many times it was tried, and where the turn went next.

Two edges worth knowing. A model is the account's: a chain that lands on an account whose
catalogue does not hold this agent's model fails for a second, unrelated reason, and moving an
agent's account is not moving its model. And whatever the agent was holding open — a Claude
process, a Codex server, a DeepSeek Harness runtime — was started as the account it has left,
so it is let
go of as the agent moves and the next turn opens one as whoever the agent now is.

## A CLI of your own

Any coding agent that speaks the [Agent Client Protocol](https://agentclientprotocol.com) can
be driven from here without humanize knowing anything else about it. Add one in the interface:
`/providers`, then **a**, then *a CLI of your own*, which is the last row of the backends a new
account may be for — the row for somebody who has got that far and cannot find their agent in
the list. Give the command that starts it — `my-agent --acp`, `grok agent stdio`, `qwen --acp`.
It is written down under humanize's own home, so it is a backend from the next prompt on, in
this workspace and every other, and `-a my-agent/...` names it.

humanize spawns that command and speaks JSON-RPC to it over its own stdin and stdout:
`session/new` opens the conversation, `session/prompt` takes each turn, and what the agent says
while a turn runs arrives as `session/update` notifications. Each tool call it asks permission
for is granted — by the **kind** of the option it offers rather than by the option's id, since
the ids are each agent's own words.

The protocol says nothing about which models an agent runs or how hard it can be asked to
think, so neither is offered: both rows read `as configured`, and the agent runs as whoever
installed it set it up. It cannot be steered mid-turn either — every agent spells that
extension its own way — and it has no goal feature, no permission rungs and no logs for
`hmz trace collect` to read.

`cursor` names one out of its own catalogue — `cursor-agent --list-models` prints them — and
its models take their parameters in brackets after the name, which is where humanize writes the
effort and the service tier: `composer-2.5[effort=high,fast=false]`. A model already written
with a bracket of its own is passed exactly as it was written, so a flow that wanted
`claude-opus-4-8[context=1m,effort=high]` gets it.

`pi`, `opencode`, `mimo` and `zcode` name a model as `provider/id` — `openai-codex/gpt-5.5`,
`opencode/big-pickle`, `xiaomi/mimo-v2.5`, `zai/glm-5.3` — because a model there belongs to the
provider that serves it, and the CLI is asked for the pair. `qwen` names whatever id the
OpenAI-compatible endpoint behind it serves, and `grok` names one out of its own catalogue:
`grok models` lists them.

DeepSeek Harness is driven through its own Python SDK, which arrives with humanize rather
than as an extra — there is nothing to install for it. It supports API-key login only:
leave `provider` empty to use the credentials and base URL saved by dsh (or its environment),
or make a `key` account from the `provider` row of an agent with **a** and give its name as
`provider`. Then
construct it like any other agent:

```python
from hmz.agents import DshAgent, DshAgentConfig

agent = DshAgent(DshAgentConfig(model="deepseek-v4-flash", effort="high"))
```

It also offers `deepseek-v4-pro`. The SDK and bundled runtime are currently a developer
preview; humanize supports `deepseek-harness-sdk>=0.1.0rc6,<0.2`.

Its runtime composition turns on the runtime's own automatic compaction, at the plugin's
default threshold of 0.8 of the model's context window. One conversation driven for long
enough otherwise reaches a turn the model refuses for length, and a loop that keeps talking
to the same conversation never gets past it: the next turn is the same conversation and the
same refusal. That refusal, and a session id the runtime will not answer under, are the two
`Unrecoverable` failures of this backend — [taken once](#when-an-account-goes-down) rather
than retried. A turn that fails without taking its runtime with it leaves that runtime up, so
the conversation carries on into the turn after it.

A config takes `model`, `effort`, `service_tier`, an optional
[`machine`](#where-the-turns-land),
[what it may do](#what-an-agent-may-do), [which account it runs as](#which-account-it-runs-as),
whether [goals](/weaver/goals) are available to it,
[whether it may search the web](#whether-an-agent-may-search-the-web), and nothing else — the
[skills it carries](#the-skills-an-agent-carries) are not among them, being its CLI's own and
its flow's. Codex also takes `overrides`, the app-server `-c` keys that are not already one
of those fields. Claude takes `allowed_tools`, exact native `--allowedTools` rules for a
bounded unattended flow. It is frozen,
because a session resumes under the settings it opened with — a config that changed mid-flow
would silently split one conversation across two models.

### An agent that is not quite the one you were handed

What an agent is, is settled where it is made. A flow is handed agents and drives them; what
each runs, where its turns land, what it is called and which of the flow's skills it carries
are answers somebody already gave — at a prompt, on a command line, in a settings file — and a
flow that could change one of them would be a flow rewriting the choice its run was started
with.

So there is one way to have an agent that differs, and it makes one:

```python
from dataclasses import replace

careful = agent.clone(config=replace(agent.config, effort="max"))
```

Everything the call does not name is the agent it came from, the skills it carries included.
Everything a *run* puts on an agent is not: the clone has opened no conversation, spent
nothing, is watched by nobody, has nothing hung on its moments and is written down nowhere —
and it is not stopped for the one it came from having been. Two agents, which is what they are,
so it gets a name of its own unless you give it one. A trace that read a clone as its original
would read a comparison of two efforts as one agent changing its mind.

There is nowhere to say any of it again. `reconfigure`, `runs_on`, `loads`, `rename` and
`disable_goals` are still there, on the interface *whoever hands an agent to a flow* holds —
`hmz.flows.Driven` — because somebody does settle them: the runner before the first turn, the
calling of one flow by another, and the interface when you say a running agent is to go on as
something else. A flow declares `hmz.flows.Agent` and reaches none of them.

### Whether an agent may search the web

`web_search` is `True` unless asked for otherwise, because reaching the web is what a coding
agent has always been able to do. Off is a choice, and one worth having: a run that must read
only this repository, one under a per-query rate limit somebody is paying for, one whose
answers have to be reproducible tomorrow.

```python
config = ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", web_search=False)
```

It means the same thing on every backend that can express it, which means it is sent in both
directions rather than only one. Claude searches the web unless told not to, so off adds
`WebSearch,WebFetch` to `--disallowedTools`; Codex searches nothing until it is asked to, so on
sends `-c tools.web_search=true`. If it were only ever sent one way, `on` would mean two
different things.

| backend | how it is said |
| --- | --- |
| `claude` | `--disallowedTools WebSearch,WebFetch` when off |
| `codex` | `-c tools.web_search=true\|false`, both ways |
| `grok` | `--disallowed-tools web_search,web_fetch` when off |
| `qwen` | `--exclude-tools web_search,web_fetch` when off |
| `opencode`, `mimo` | `webfetch: deny` in its permission table when off |
| `zcode` | `WebSearch` and `WebFetch` in the session's `toolDenylist` when off |
| `agy`, `cursor`, `dsh`, `kimi`, `pi` | no way of being told — off is refused |

A backend with no way of being told **refuses it off**, wherever the config arrives — where the
agent is made, and where one already running is set up as something else. An agent that quietly
went on searching would be a setting that lies. It composes with
[what an agent may do](#what-an-agent-may-do) rather than overriding it: a rung that already
withholds the reaching-out tools goes on withholding them whatever this says.

`service_tier` is `default` unless asked for otherwise. Claude and Codex also take `fast`:
Claude receives `fastMode: true`, and Codex receives its native `priority` service tier. It
does not lower `effort` or choose a smaller model. A backend that cannot express `fast`
refuses it before the first turn rather than silently running at another tier.

The field records and sends the requested tier; provider availability still decides the
effective tier. Claude subscription sessions require usage credits for fast mode and may
report standard service when credits are disabled or fast mode is cooling down. Provider
usage records, rather than the request alone, are authoritative for the tier actually served.

```python
from hmz.agents import CodexAgent, CodexAgentConfig

agent = CodexAgent(
    CodexAgentConfig(
        model="gpt-5.6-sol",
        effort="max",
        service_tier="fast",
        overrides=(
            ("model_context_window", "1000000"),
            ("model_auto_compact_token_limit", "900000"),
        ),
    )
)
```

On a command line the common tier is a top-level agent field, while backend-native settings
remain that agent's `config.KEY=VALUE`, not flags of `hmz exec`:

```sh
hmz exec -f flow.py:run \
    -a 'cli=codex,model=gpt-5.6-sol,effort=max,service_tier=fast,config.model_context_window=1000000' \
    task
```

Codex takes only `model_context_window` and `model_auto_compact_token_limit` as native
overrides. The user's `~/.codex/config.toml` is left as it was.

Claude's exact native allow rule is configured the same way and is handed to
`--allowedTools`; it does not widen the agent's permission rung:

```sh
hmz exec -f flow.py:run \
    -a 'cli=claude,model=claude-opus-5,effort=max,permission=workspace-write,config.allowed_tools=Bash(git diff *)' \
    task
```

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
the next call retries the turn rather than resuming something that may not exist. One that
failed for a reason no other try could come out differently on raises `Unrecoverable`, which
is a `CalledProcessError` too and is described [above](#when-an-account-goes-down).

It says **why**, which a bare `CalledProcessError` does not:

```console
Command '['mimo']' returned non-zero exit status 1. MiMo free API service has ended.
    Sign in or configure a third-party API.
```

Most of what stops a turn is about the account rather than about humanize — a model this
account may not name, a region a snapshot is not served in, a subscription that has lapsed, a
key that is not there — and each of those is one sentence the CLI already writes. Both streams
are said where they say different things, since a CLI may warn on one and fail on the other,
and each is clipped: the sentence it failed with is worth having and the transcript it failed
part way through is not.

`suppress=True` turns a failed turn into an empty answer:

```python
agent(task, suppress=True)   # "" if it failed, and the loop goes round again
```

It catches a turn that failed and **nothing else**: not an agent that has been
[stopped](#stopping), not a backend with no [goal](#goals) feature, which is a flow to correct
rather than a turn to retry, and not an `Unrecoverable`. That last one for the reason a stop is
not caught: a `while True` that swallowed a failure no other try could come out differently on
would go round on the same failure until somebody stopped it.

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
[trace](/reference/tracing) — what differs is where each conversation is rooted.

For an agent whose turns land on [another machine](/reference/machines), the directory is **that
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
[`async def run`](/reference/flows#a-flow-that-waits-for-more-than-one-thing):

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
set: asking for a feature that is not there is a flow to correct. Which backends have one is
`type(agent).pursues` — a class attribute rather than a question anybody asks the CLI — and it
is what a flow's `Goal` annotation is checked against before its first turn.

An agent whose goals were switched off raises `RuntimeError` from `pursue` instead, and is
refused the tools that would carry work past the turn humanize is holding: Codex starts its
server with its goal tools disabled, and Claude Code is given `--disallowedTools` naming
`Agent`, `ScheduleWakeup`, `CronCreate`, `CronDelete` and `CronList`.

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
| `SUBAGENT_START` | the agent has started an agent of its own | — |
| `SUBAGENT_STOP` | one of those has come back | — |
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

A hook is told an `Occasion` — `moment`, `agent`, `session`, `prompt`, `tool`, `about`, `under`,
`input`, `said`, `again` — and answers with a `Verdict` or with `None`, which says nothing. Two
hooks on one moment are one verdict: refused if either refused, and adding everything either
added.

The two moments about a **fleet** are the agents an agent starts of its own — Claude's `Task`,
Codex's collab agent, Cursor's task tool. `tool` is what that agent is called, `about` is what
it was asked to do, and `under` is the backend's own id for it, which is what pairs the one
that started with the one that came back:

```python
def counted(occasion: Occasion) -> None:
    started[occasion.under] = occasion.about

agent.hooks.on(Moment.SUBAGENT_START, counted)
```

They are told rather than answered: no backend here waits to be told whether it may start one,
so a refusal would be a verdict that goes nowhere. The same events reach a watcher as
`subagent` and `subagent-ends`, and the interface draws them
[under the agent that started them](/user/status).

A hook that raises has said nothing. A flow must not fail because something hung off it did —
with one exception: a hook that drove an agent which has been [stopped](#stopping) lets
`Stopped` out, so a run ended by hand reads as ended by hand rather than as one that finished.

### Not every backend runs every moment

`agent.moments` is what this one runs, and `hooks.on` refuses a moment that is not in it —
where the hook is hung, rather than by quietly never firing.

| Moment | Claude Code | Codex | Cursor | Kimi Code | ZCode | you |
| --- | --- | --- | --- | --- | --- | --- |
| everything above except the three below | yes | yes | yes | yes | yes | no |
| `PERMISSION_REQUEST` | yes | yes | no | no | yes | no |
| `SUBAGENT_START`, `SUBAGENT_STOP` | yes | yes | yes | no | no | no |

Claude Code, Codex and ZCode ask before they use a tool — Claude over the same stream the turn
is read from, Codex and ZCode each through the app server it is driven over — and wait for
the answer, so those are the three backends here where a refusal reaches the agent. It
also wants the [`auto` rung](#what-an-agent-may-do), which is the one setting under which any
of them asks at all. The rest are driven unattended, which is what a flow watching its agent
rather than gating it means.

Claude Code, Codex and Cursor each say on the stream a turn is read from when they start an
agent of their own and when that one comes back, so those are the three where a fleet is
visible. The rest either have none or do not say, and a hook hung on it there is refused where
it is hung.

`HumanAgent` runs none of them: a moment is a point in a turn of a model, and the person takes
no such turn.

A flow says which moments it needs where it declares the agents it drives, and is refused before
its first turn if it was given one that cannot run them — see
[Flows](/reference/flows#asking-for-an-agent-that-can-do-something).

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
reads its work. `id` is what tells them apart, and what a [trace](/reference/tracing) groups their
sessions under:

```python
agent.id       # the name you gave it, the name the flow calls it, or one nothing else answers to
agent.backend  # "agy", "claude", "codex", "cursor", "dsh", "grok", "kimi", "mimo",
               # "opencode", "pi", "qwen", "zcode" — or whatever an ACP CLI of your own
               # was added under
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

A [flow](/reference/flows#how-many-agents-and-what-they-are-for) that declares its agents as a
`NamedTuple` names them for you, and a run started through `Runner` writes all of this into its
[epic](/reference/tracing#epics) — so this is only needed for agents built and driven by hand.

### The name nobody gave it

An agent nobody named still needs one nothing else answers to, and what it gets is a codename out
of Amphoreus — a Greek word for what a Chrysos Heir was made to be, and three digits behind it:

```text
NeiKos496   PhiLia093   SkeMma720   KykLos204   MetaKratos881
```

Twelve of those are codes *Honkai: Star Rail* says out loud, and while any of the twelve is still
free they come up half the time — against the once in eleven thousand the written-down words alone
would give them by chance, since a name is only a joke to somebody who recognises it. The rest are
those same roles under some other number: another epic of a story that has run 33,550,336 of
them, which is the fifth perfect number, as 496 is the third.

The word is built rather than looked up. Morphemes join at the capital — `Apo` and `Ria` are
`ApoRia`, which is an heir's, so `Meta` and `Kratos` are `MetaKratos`, which is a word the same
rule makes and the story merely never needed. That is what makes the supply endless: a process
that has used the short words up is answered with a longer one built the same way, and **never
with a hex tail**. There is no last code, so there is nothing to fall back to.

No code is handed out twice in one process either. Two agents left unnamed are two agents, and a
trace that read them as one would read a flow reviewing its own work as a flow arguing with
itself.

A name given where the agent was made is kept, and `builder` says what `NeiKos496` does not — so
name the ones whose roles matter and let the rest be heirs.

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
[Flows](/reference/flows#the-person-at-the-prompt). Nobody is asked what it runs, so it is not one of
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
against a list, so a value your account has and this page does not still works — with one
exception: `dsh` is driven through an SDK that takes three, and an agent of it is refused
before the runtime starts unless its effort is `max`, `high` or `off`.

| Backend | Efforts |
| --- | --- |
| `agy` | `low`, `medium`, `high` |
| `claude` | `low`, `medium`, `high`, `xhigh`, `max`, and `ultracode` |
| `codex` | `low`, `medium`, `high`, `xhigh`, and `max`/`ultra` on the models that take them |
| `cursor` | `low`, `medium`, `high` — written into the model rather than sent beside it |
| `dsh` | `off`, `high`, `max` |
| `grok` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` — the levels the model itself advertises |
| `kimi` | `low`, `medium`, `high`, `max`, each also as `swarm…` |
| `pi` | `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| `qwen` | `low`, `medium`, `high`, `xhigh`, `max` |
| `opencode`, `mimo` | the model variant: `minimal`, `low`, `medium`, `high`, `xhigh` |
| `zcode` | `nothink`, `low`, `high`, `max` on the models that take a thinking budget — `disabled`, `enabled` on the ones that only think or not |

**Antigravity CLI has one switch for what an agent may do** — approve every tool, or stop and
ask — and nobody is at a prompt to be asked, so `read-only` and `workspace-write` are refused
where the agent is made rather than quietly run as the rung above.

**Grok Build refuses a level the model does not advertise** rather than ignoring it, so a turn
asked for one fails with the list of the ones that model takes. The shipped models take
`low`, `medium`, `high` and `xhigh`.

**Qwen Code has no flag for the effort.** It is a setting of its own `settings.json`, so a turn
is pointed at a file of humanize's own through `QWEN_CODE_SYSTEM_SETTINGS_PATH` — two agents of
one flow may think at two efforts, and neither is a reason to rewrite what you have configured.

**`ultracode`** is Claude Code's `xhigh` thinking with the turn opted into orchestrating a fleet
of its own. It is more work than any single-agent effort, which is why it sits above `max`.

**Kimi Code's effort says how wide to run as well as how hard to think.** `max` is one agent;
`swarmmax` is the same thinking at the width of a fleet of subagents. The prefix is exported as
`hmz.agents.SWARM` for anything that has to take it apart.

**ZCode's ladder is two vocabularies in one**, because its models have two. The ones that take
a thinking budget answer `max`, `high` and `low` — and `nothink` for the bottom of that one —
while the ones that only take thinking-or-not answer `enabled` and `disabled`. humanize asks
the backend which of them a model said it takes and narrows the ladder to those, so a model is
offered one vocabulary rather than both.

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
resumes the same conversation at the new effort. pi has a command for it and ZCode a call on
the session, and each is told between turns.

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
moved when one ended would stand still for all of them: most backends here are read as they
say what each request to the model cost — Claude Code on the message it answered with,
Codex on `thread/tokenUsage/updated`, DeepSeek Harness and pi on finalized assistant messages,
opencode and mimocode on each step, Kimi Code from the session it is polling anyway, ZCode on
the row its log gains per model request. Antigravity, Grok Build and Qwen Code are the
exception: each is one run per turn that states its usage only at the end, so what they spent
lands on the closing `result` and their rate moves a turn at a time rather than a request at a
time.

**`juice()` is the third reading, and it is not a clock at all.** It is what one turn of the
*model* came out with — one request and the answer to it, of which a turn a flow asks for is
many. That average is what an effort moves: a model asked to think harder writes more in each
answer and takes longer over it. So it is the number to steer by when what is being held is
how hard the thing is thinking rather than how fast a bill is running up, and it is what
[`fixed_juice_ralph`](/flows/fixed-juice-ralph) governs on. A window with no
turn in it reads as `0.0`: nothing to go on, which a flow tells apart from a turn that said
nothing.

A backend that states a whole turn's cost after having said what each request in it came to
is settling up rather than taking another turn, and is not counted as one — or the average
would be halved by the accounting.

The `result` event a turn ends on carries the same reckoning as `spent`, beside the per-model
`tokens` it already carried: the two are the same spending counted two ways, and
`result.spent.total` is what `result.tokens` comes to.

## What each backend can do

| | `agy` | `claude` | `codex` | `cursor` | `dsh` | `grok` | `kimi` | `pi` | `qwen` | `opencode`, `mimo` | `zcode` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Driven through | its command line, one run per turn | its command line, held open | its app server | its command line, one run per turn | its Python SDK | its command line, one run per turn | its app server | its command line, held open | its command line, one run per turn | its command line, one run per turn | its app server |
| [`interject`](#talking-to-a-turn-already-running) | no — a run per turn has ended | yes — answered within the same turn | yes — a steer on the running turn | no — a run per turn has ended | no | no — a run per turn has ended | yes — queued, then steered in | yes — a steer on the running turn | no — a run per turn has ended | no — a run per turn has ended | no — a second prompt is refused while one is running |
| [`pursue`](#goals) | no | yes | yes | no | yes | no | yes | no | no | no | yes |
| [`PERMISSION_REQUEST`](#not-every-backend-runs-every-moment) | no | yes | yes | no | no | no | no | no | no | no | yes |
| [`SubagentStart`/`SubagentStop`](#not-every-backend-runs-every-moment) | no | yes | yes | yes | no | no | no | no | no | no | no |
| [Callbacks as tools](#callbacks-of-the-flow-s-own) | no | `--mcp-config` | `-c mcp_servers…` | no | no | no | no | no | no | no | no |
| A turn held to a shape | `--json-schema` | `--json-schema` | `outputSchema` | in the prompt | in the prompt | `--json-schema` | in the prompt | in the prompt | `--json-schema` | in the prompt | in the prompt |
| Sub-agents in a trace | no | yes | yes | no | no | no | yes | no | no | no | no |

DeepSeek Harness currently accepts only `permission="bypass"`. Its preview
SDK exposes neither a per-session sandbox/approval control nor exact per-agent skill selection;
another value is rejected before the runtime starts rather than silently ignored.

opencode and mimocode keep a session in a database rather than in a log file, so there is
nothing for `hmz trace collect` to gather and nothing for the interface to read a running cost out
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
interface it is the `permission` row of the sheet an agent is set up on, stepped on the arrows.

Every backend has a ladder of its own and none of them has the same four rungs, so each driver
reaches for whichever of its own settings says the same thing:

| Rung | `agy` | `claude` | `codex` | `cursor` | `dsh` | `grok` | `kimi` | `pi` | `qwen` | `opencode`, `mimo` | `zcode` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `read-only` | refused | `plan` mode | `read-only` sandbox | `--mode plan` | — | only `read_file`, `grep`, `list_dir` | plan mode | without `bash`, `edit`, `write` | without `edit`, `write_file`, `run_shell_command` | `edit` and `bash` denied | `plan` mode |
| `workspace-write` | refused | `acceptEdits` mode | `workspace-write` sandbox | `--sandbox enabled` | — | `web_search` and `web_fetch` denied | plan mode off | — | `web_fetch` denied | `webfetch` denied | `edit` mode |
| `auto` | `--dangerously-skip-permissions` | Claude's own `auto` mode | `workspace-write`, approvals on request | `--auto-review`, its own classifier | — | — | — | — | — | nothing denied | `build` mode, which asks before a tool with side effects |
| `bypass` | `--dangerously-skip-permissions` | `manual` mode, every request answered here | `danger-full-access` | `--force --sandbox disabled` | supported | `--yolo` | `yolo` mode | — | `--approval-mode yolo` | — | `yolo` mode |

**Codex is the one backend here with a sandbox of its own**, so its rungs are the real thing
rather than an approximation of one. Where a backend cannot tell two rungs apart it says so
here rather than pretending: a dash is the rung above it, run again.

**A Codex whose rules are somebody else's runs a rung down rather than not at all.** An
installation can be given requirements — an enterprise policy that arrives with the account, a
`requirements.toml` the platform that packages Codex puts on its machines — and one that
forbids `danger-full-access` refuses every call that asks for it: `` `approval_policy =
"never"` cannot be used because requirements do not allow `sandbox_mode =
"danger-full-access"` ``. Which would be every turn of a flow at the default rung failing on
such a machine. So humanize takes the answer: it runs that agent at `auto` instead — the same
freedom with the asking turned back on, and the asking is granted — and says so once, where a
turn's own words go when nothing is watching the agent:

```
codex: this machine will not run an agent at bypass, so it runs at auto, where what it asks
for is granted
```

It is found out once per agent rather than once per turn, and the rung you chose is what is
tried first: an agent set to `auto` in `/agents` asks for `auto` and never sees this.

**Claude Code's `bypass` is humanize doing the asking, not Claude skipping it.** The flag that
skips it — `--dangerously-skip-permissions` — is one an account can be told to refuse: managed
settings carrying `"disableBypassPermissionsMode": "disable"` do not reject the flag the way
Codex rejects a forbidden sandbox, they quietly start the turn at a mode where every edit is
declined and the turn ends successfully with nothing changed. So humanize does not send that
flag. It runs the agent at Claude's `manual` mode — where Claude asks before every tool that
would change something — and routes those asks to itself with `--permission-prompt-tool stdio`,
answering each one `allow`. `manual` is a mode every account permits, so `bypass` runs the same
on an account somebody else set up as on your own; and a yes here is a yes to what the account
leaves decidable, since the hard `deny` list an organisation ships is the CLI's to refuse
before it ever asks. The rung means the same thing it always did — an agent nobody was asked
about, allowed what a person at the prompt would have allowed — reached by standing in for that
person rather than by turning the question off.

**ZCode has a mode for each of these**, so nothing in its column is a repeat of the one above
it. `plan` refuses an edit and refuses a command it reads as high-risk. `edit` changes the
workspace without asking, and stops at a high-risk tool to ask — which is answered no at that
rung, because an agent allowed its workspace is not allowed more for asking. `build`, the mode
its own terminal opens in, asks the same question, and `auto` is the rung where the answer is
yes. `yolo` asks nothing at all. ZCode's own `auto` mode is not this `auto` and is nobody's
rung here: in that mode its permission service refuses every tool, saying the mode is reserved
and not implemented yet.

**`auto` is the rung where a hook gets a say — and on Claude Code, `bypass` is too.** A hook
hung on [`PERMISSION_REQUEST`](#hooks) can refuse something only where a backend actually asks
before it acts and waits for the answer. `auto` is that rung everywhere it exists; Claude Code,
Codex and ZCode run the moment there. Claude Code runs it at `bypass` as well, because `bypass`
there is `manual` mode with the asking routed home — so a hook can refuse a tool even an agent
nobody was asked about reached for, and the agent hears it. The rest have nothing to hang it
on.

## The skills an agent carries

**A skill installed on this machine is its CLI's own.** humanize does not switch one off, does
not write the CLI's settings, and has no per-agent list of them: what you installed is what
every agent of that CLI carries, installed and switched off where that CLI keeps them. The
list is readable — the [`skills` row](/reference/tui#what-each-agent-carries) of the sheet an
agent is set up on shows what it will be carrying — and that is all it is:

```python
from hmz.agents.skills import skills

skills("claude")   # what it would load here: yours, and this project's

agent.loaded       # the skills the flow driving it brings, mounted onto every session
agent.loads(...)   # what the runner calls to say so; a flow cannot call this itself
```

Which of the flow's skills **one conversation** carries is that conversation's own answer, and
may be said again while it runs:

```python
session = agent.new()
session.skills             # every one the flow brought, until it is told otherwise
session.loads(["writing"]) # from its next turn on
session.loads(None)        # all of them again
```

An agent is what it was made as; a conversation is a thing that gets somewhere. One that has
finished reading the codebase and started writing the tests wants the skill about writing them
and no longer wants the eight about reading it — and it is the same conversation either way.

What is put where the backend reads it is settled as a turn opens, not when `loads` is called:
a session may not have a directory yet, and a turn already running must not have what it is
working by moved underneath it. A name the flow does not bring is ignored rather than refused,
so a session asking for one a fork of the flow no longer has carries the rest.

What humanize *does* add is [the skills a flow brings](/reference/flows#the-skills-a-flow-brings).
Those are mounted onto every session the flow's agents open — copied where that backend reads
a project's own skills for as long as the session lives, and taken away again after:

| Backend | Where a flow's skills are mounted |
| --- | --- |
| `claude` | `.claude/skills/` in the workspace |
| `codex`, `grok`, `kimi`, `mimo`, `opencode`, `qwen`, `zcode` | `.agents/skills/`, the directory more than one of these agreed to read |
| `cursor` | `.cursor/skills/` in the workspace |
| `agy`, `dsh`, `pi` | — none: none of them reads such a directory the way humanize drives it |

A project's own skill of that name wins: a flow does not write over what the project keeps.
They go into the workspace on this machine, so an agent [whose turns land
elsewhere](#where-the-turns-land) is given them only where that machine reads this directory —
a container that was handed this workspace does; one across a network keeps its own.

## Callbacks of the flow's own

A flow drives an agent by saying things to it. **Tools are the other direction**: a function
the flow wrote, put in front of the agent, so that the agent reaching for it is the flow's own
code running — in the flow's process, with the flow's variables — and what it answers is what
the agent reads back.

```python
from pydantic import BaseModel, Field
from hmz.agents import Tool


class Reviewing(BaseModel):
    path: str = Field(description="the file to have read")


session = agent.new()
session.offers(
    [
        Tool(
            name="review",
            about="have the reviewer read a file and say what is wrong with it",
            takes=Reviewing,
            call=lambda said: reviewer(f"review {said.path}"),
        )
    ]
)
session("write the parser, and have your work reviewed before you stop")
```

Which is what makes an agent able to **call a flow**: a callback whose body is
`load("official/rlar")(agents, said.task)` is an agent that starts a loop of its own and waits
for what it comes to, and nothing about that is written into any backend.

| | |
| --- | --- |
| `name` | what the agent calls it |
| `about` | what it is for, said to the model — the whole of what it knows about when to reach for it |
| `takes` | a pydantic model of what it is called with, or `None` for a tool that takes nothing. The model is the whole of what the agent is told: its fields, their types, which are required and each description are already in it |
| `call` | what to run — given the model, and nothing where `takes` is `None`. What it answers goes back as text; `None` is a tool that did something |

`session.offers(None)` takes them back. It is said on a **conversation**, because that is where
a flow is when it has something to offer — but a CLI is told about its tools where it is
started, and some of these are started once per agent, so what is actually offered is the
agent's: two conversations offering a tool of one name are offering one tool.

The road between the two is the **Model Context Protocol**, that being the one way every one of
these CLIs takes a tool it was not shipped with. What a backend is handed is a command to run —
`hmz tools --at <socket>` — which relays its pipe back to the flow's process. Nothing is
started until something is offered: an agent whose flow hands it no callbacks has no socket, no
thread and no bridge.

**A callback that raises is the tool failing, not the flow.** The model is told what went
wrong, in words, and may call it again correctly; a flow must not end because a model called
one of its tools wrongly.

`session.takes_tools` is `False` on a backend with no way of being told, and `offers` raises
`NotImplementedError` there rather than quietly never offering it — see
[what each backend can do](#what-each-backend-can-do).

## Where the turns land

A config's `machine` says where an agent's work goes. `None` — the default — is this machine.

```python
from hmz.machines import AnchoredConfig, DockerConfig

ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

`agent.anchor` is where its turns land, and brings the machine up the first time it is asked
for — which is the first turn. Constructing an agent pulls no image and starts no container.
See [Machines](/reference/machines).

**Which agents may be given one at all is the flow's to say.** An agent handed to a flow whose
place for it says nothing is refused before its first turn, because a flow is written for one
shape of work — see [Flows › Where each agent works](/reference/flows#where-each-agent-works). Setting a
`machine` here is what fills a place the flow declared `Remote`; a place it declared `Isolated`
is settled by the flow itself and takes no `machine` from anyone.

## Which account it runs as

A config's `provider` names one of the [providers](/reference/providers) made for its CLI. `""` — the
default — is the CLI as you already run it, signed in the way you already signed in.

```python
ClaudeCodeAgentConfig(model="claude-opus-5", effort="max", provider="deepseek")
```

A turn of such an agent is given that provider's variables, and reads its credentials out of
that provider's own directory rather than the CLI's — so two agents of one backend can be two
accounts at the same time, one on a subscription and one on somebody's gateway. Only the
credential files move: the sessions, the settings and the skills are the CLI's own.

```python
agent.provider       # Provider | None -- the account, read once and kept; None is the
                     #   account this machine is already signed into
agent.node()         # the same as an account, never None, which is where a chain starts
agent.walks()        # that account and whatever it falls back to, in the order tried
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
    config: AgentConfig     # model, effort, machine, permission, provider
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
