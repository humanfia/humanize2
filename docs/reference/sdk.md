# SDK reference

humanize as one object. `Hmz` is a workspace and everything humanize can be asked to do in it,
and it is what the [command line](/reference/cli), the [daemon](/reference/daemon) and the
[terminal interface](/reference/tui) all go through — so a thing that can be done one way can be
done every way, and is refused the same way whichever way it was asked.

```python
from hmz.sdk import Hmz

hmz = Hmz()
hmz.run("chat", [], "say hello").run()
```

## `Hmz`

```python
Hmz(workspace: str | os.PathLike[str] | None = None)
```

| Argument | |
| --- | --- |
| `workspace` | The project directory this is about, or `None` for wherever humanize is being run. Kept exactly as it was given: a workspace nobody named follows a flow that changes directory, and one that was named is the directory it named, spelled the way it was named. |

Nothing is loaded until it is asked for. Holding one costs one import; asking it for the runs of
a workspace is what loads the tracer.

| Attribute | |
| --- | --- |
| `workspace` | The project directory, as a `Path`. |
| `home` | Where humanize keeps what outlives one run — `~/.humanize`, or `$HUMANIZE_HOME`. |
| `settings` | [What humanize remembers](/reference/tui#what-it-remembers) about this workspace, as `hmz.settings.Settings`. |
| `flows` | [The flows there are](#flows), and the places they come from. |
| `verses` | [Where flows come from](#flowverses) — the same object as `hmz.flows.verses`. |
| `agents` | [The agents written down under a name](#agents). |
| `accounts` | [The accounts an agent may be run as](#accounts), and what each backend runs as one. |
| `fallbacks` | [Where a turn goes](#fallbacks) when the place taking it cannot take it at all. |
| `cycles` | [The runs of this workspace](#cycles) that have already happened. |

| Method | |
| --- | --- |
| `backends()` | Every coding agent CLI humanize drives, as `hmz.backends.Profile`. |
| `reports()` | Starts [reporting humanize's own failures](/guide/reporting) where that has been answered yes. Returns whether anything is being reported. |
| `read(argv)` | Reads an `hmz exec` line into `(flow, agents, task, config, container)`. |
| `runner(flow, agents, config=None, resume=None, container="")` | Loads a flow and hands it the agents it was written for, as `hmz.runner.Runner`. |
| `run(flow, agents, task, config=None, resume=None, container="")` | The same, as a [`Run`](#run). |
| `exec(argv)` | The whole of `hmz exec`: reads the line, loads the flow, runs it to its return. |

## `Run`

One run of one flow. Making one starts nothing — whoever made it says which of the two they are
holding.

| | |
| --- | --- |
| `agents` | Every agent it drives, the person the flow talks to and any runtime-spawned agents among them. The tuple grows as the flow adds agents and remains inspectable after it ends. |
| `running` | Whether the flow is still going. `False` before it is started. |
| `raised` | Whatever the flow raised, for a run started on a thread and now over. |
| `run()` | Runs the flow here, until it returns. |
| `start()` | Runs it on a thread of its own, and returns at once. One run **in a container** at a time per process: the container a run works in is the process's, since a flow that called another is one run working in one place. Runs on this machine have no such limit. The second of two is refused where the container is settled — on the thread, so it arrives in `raised` rather than out of this call; `run()` raises it where it stands. |
| `wait(timeout=None)` | Waits for it to end. Returns whether it has. |
| `stop()` | Tells every agent to take no further turn, so the turn running now is closed out and the loop ends rather than handing on. |
| `close()` | Closes every conversation still open, which is the backend's process going. The last thing there is to do about a run. |

```python
from hmz.sdk import Hmz

hmz = Hmz()
flow, agents, task, config, container = hmz.read(
    ["-f", "ralph_loop", "-a", "claude/claude-opus-5:high", "fix the build"]
)
run = hmz.run(flow, agents, task, config, container=container)
run.start()
...
run.stop()
run.wait(timeout=60)
```

## Flows

`hmz.flows` — [what a flow is](/reference/flows) is the layer under this.

| | |
| --- | --- |
| `all()` | Every flow there is to run, by the name `-f` takes. |
| `find(named)` | The file one flow is written in. Raises `NotAFlow` for a name nothing answers to. |
| `about(named)` | The line a flow says about itself. |
| `places(named)` | Every agent it needs chosen for it, in the order it takes them. |
| `check(named, static=False)` | Reads it for what will not run, before anything runs it: one finding per thing found, errors and warnings. `static=True` keeps to the reading that executes nothing. |
| `prophecy(named)` | What an [atlas](/guide/atlas) compiles to, or `None` for a flow that is not one or does not compile — which `check` says the reasons for. |
| `foretell(named)` | Writes that prophecy into the flow's own directory, which every run of it walks from then on. |
| `configures(named)` | What it can be [set up with](/reference/flows#settings-of-the-flow-s-own), or `None`. |
| `resumes(named)` | Whether it says it can be [picked up](/guide/resuming). |
| `fork(named, into=None)` | Copies it into this project's own flows, whole. |
| `running()` | Every flow running in this process now, the one started first and whatever it called. |
| `set_up_from(path)` | Reads a flow's YAML setup file. |
| `verses` | [Where flows come from](#flowverses). |

## Flowverses

`hmz.verses` — the same store [`hmz flowverses`](/reference/cli#hmz-flowverses) and `/flowverses`
walk.

| | |
| --- | --- |
| `all()` | Every place there is, in the order their flows are offered. |
| `nearest()` | The same places, in the order a flow's name is looked up in. |
| `find(name)` | The place of that name, or `None`. |
| `add(url, name="")` | Fetches one and offers its flows under a name. |
| `fetch(name)` | Fetches one again, or for the first time. |
| `remove(name)` | Takes one away, flows and all. |
| `holds(one)` | What it holds, by the name each flow is offered under. **This reads the flows**, which means running them. |
| `where(name)` | The directory it is kept in. |
| `plain(url)` | A URL with whatever was signed into it taken out. |
| `whence(one, nowhere="-")` | Where it came from, as it may be shown to somebody — asked of which flowverse it is rather than of whether its URL is empty. |

## Agents

`hmz.agents` — [the agents written down under a name](/reference/tui#agents-kept-under-a-name),
which is the same store [`hmz agents`](/reference/cli#hmz-agents) and `/agents` walk. Not the
agents of a flow.

| | |
| --- | --- |
| `reads(spec)` | Reads one agent the way `-a` names one. Raises `ValueError` for one that is not. |
| `all()` | Every agent written down, in the order they were written down in. |
| `find(name)` | The one written down under this name, or `None`. |
| `keep(agents)` | Writes down exactly these and nothing else, which is what a menu saves. |
| `write(name, runs, *, force=True)` | Writes one down. One written over keeps its place in the list; one that is new goes on the end. |
| `add(name, spec, *, anchor="", goals=True, web_search=None, force=False)` | The same, out of the way a command line names one. |
| `remove(name)` | Takes one away. Returns whether there was one. |

`Taken` is raised — a `ValueError` — for a name already written down when `force` is off. What
to say about it is whoever asked's: a command line says which flag writes over one, and a menu
that has already asked which name to save over says nothing at all.

## Accounts

`hmz.accounts` — [the accounts an agent may be run as](/reference/providers), and what each
backend runs as one of them.

| | |
| --- | --- |
| `all(cli="")` | Every account somebody made, or one backend's. |
| `ways(cli)` | How one backend can be signed into. |
| `way(cli, name)` | The way in it offers under a name. |
| `find(cli, name)` | The account of that backend under that name. |
| `where(cli, name)` | Where it keeps its credentials, whether or not it has been made. |
| `local(cli)` | Where the account this machine is already signed into keeps what is written of it. |
| `write(cli, name, way="", env=None, args=())` | Writes one down as it now stands, without running anything. |
| `make(cli, name, way, answers=None)` | Writes one down out of what its way in was answered with. |
| `sign_in(provider, way, answers=None)` | Runs a backend's own way in, under this account's paths. |
| `asks(way, given)` | What a way in still has to be told. |
| `serves(one)` | The other backends this account's credentials could run. |
| `copies(one, cli, name="")` | Writes the same account down for another backend. |
| `chain(one)` | Every account a turn under this one would carry on under, this one first. |
| `points(cli, name, at)` | Says which account a turn under one carries on under when it fails. |
| `remove(cli, name)` | Takes one away, credentials and all. |
| `env(said)` | Reads `NAME=VALUE` lines into what a turn under an account is run with. |
| `environ(provider)` | What a turn under this account is run with. |
| `models(cli, provider="")` | What one backend last said it runs as one account. |
| `asked(cli, provider="")` | When it was last asked, and `""` for never. |
| `ask(cli, provider="", seconds=None)` | **Starts the backend** to find out, and keeps what it said. |

## Fallbacks

`hmz.fallbacks` — [where a turn goes](/reference/tui#where-a-turn-goes-when-it-cannot-be-taken)
when the place taking it cannot take it at all.

| | |
| --- | --- |
| `default` | How a failed turn waits unless somebody said otherwise. |
| `policies()` | The waits there are. |
| `named(policy)` | The wait one name means, or `None`. |
| `all()` | Every step, in the order they were written down. |
| `reads(said)` | One place as it is written down, and `""` for a spelling no place answers to. |
| `spec(backend, model, provider="")` | One place, out of the three things a place is. |
| `tried(said)` | What is written down against one place. |
| `chain(said)` | The places one turn would walk, the one it starts at first. |
| `points(said, at)` | Says where one place's turns go when it cannot run at all. |
| `retrying(said, tries, policy, timeout)` | Says how a failed turn there is taken again. |
| `clear(said)` | Takes one step away. |

## Cycles

`hmz.cycles` — [the runs of this workspace](/reference/tracing#cycles) that have already
happened.

| | |
| --- | --- |
| `under()` | The directory this workspace's runs are kept in. |
| `all()` | Every run, oldest first. |
| `read(cycle)` | What one run was: when, which flow, on what, how it went, what it opened. |
| `sessions(cycle)` | Every session it opened. |
| `opened(cycle)` | What each agent opened, by the name the run knew that agent as. |
| `resumed(flow)` | The last run of one flow here. |
| `state(cycle, flow="")` | What a [resumable](/guide/resuming) flow left behind in one run. |
| `traced(cycle, *, output=None, start=None, end=None)` | Gathers one run into a [trace](/reference/tracing) of that run — its own sessions, by the ids it wrote down, beside the programs it profiled — and answers with where it went and what is in it. It goes beside the run unless an output is named. |
| `trace(*, sessions=None, agents=None, output=None, start=None, end=None, profile=None)` | The same collector, asked for whatever sessions you name — which is how a session no run ever drove is read back. |

## Session

What is holding a run somewhere a terminal closing cannot reach, as the interface sees one — a
`Protocol` rather than the thing itself, so that the interface names no daemon.

| | |
| --- | --- |
| `attached` | How many terminals are reading this run right now. |
| `detach()` | Lets go of every terminal reading it, leaving the run running. Returns how many were let go of. |

[`hmz.daemon.Held`](/reference/daemon) is what implements it.
