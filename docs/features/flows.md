---
pageClass: hmz-feature
---

# A flow is Python

A flow is a directory holding Python that takes the agents and the task. Most are ordinary
functions: a loop, a subprocess call, a file read between two turns, a condition on what the
last answer said. An **atlas** makes a different bargain: its deliberately narrow body is read
before it runs and compiled into a typed graph called a prophecy.

Both are Python, discovered the same way and driven by the same run. Choose an ordinary flow
when its shape should remain free; choose an atlas when the shape must be checked, compared or
resumed node by node before any agent starts.

<HmzLoops />

## What makes a function a flow

A mark on it, and nothing else. Which of a file's functions is the flow is the file's own to
say rather than a name to guess at, because a flow is read by running its file and a file may
leave several functions behind.

What the mark carries is what a command line cannot otherwise know:

- **How many agents it drives** — the length of the tuple it declares. A run started with the
  wrong number fails before its first turn rather than partway through a loop.
- **What it calls each of them.** Declared as a named tuple, a flow says `actor` and `reviewer`
  rather than "the first one" and "the second one" — and those names are what a
  [trace](/features/tracing) groups each agent's sessions under.
- **What it needs of them.** A flow that runs an agent under a [goal](/features/goals) says so
  beside the place, and an agent whose backend has no goal feature is refused before the first
  turn. Where an agent's turns may land is the flow's to say too: a place may be pointed at
  another machine, or fixed to a container of an image the flow itself names and configurable
  by nobody.
- **Whether it can be [picked up](/features/resuming)** where its last run left off.
- **One file, several flows.** Three phases of one thing are one thing to write and three to
  run, each asking only for the agents it drives and only for the settings it takes.

A flow may also declare **settings of its own** as a pydantic model, which become fields on the
sheet where it is set up and lines in a file a scripted run can hand it.

## Ordinary flows are loaded as code

There is no static description of an ordinary flow to run instead, and none is cached. A flow
rewritten between two runs — by hand, or by an agent that flow is itself driving — runs as it
is *now*. That is what makes a flow, and the skills it brings, a thing a run can improve.

The static checker can inspect a flow's source without importing it. An atlas goes further: its
body is the description, so compiling it produces a prophecy without executing that body. Its
node functions and the rest of its module remain ordinary Python, which is why a flowverse is
still trusted as code rather than treated as data.

Its own directory is importable while it runs and only while, since what a flow imports is not
something the rest of the process should be able to.

It is also why a flowverse is trusted the way a repository of code is trusted, and why
[Security](/user/security) is a page rather than a paragraph.

## The shapes a loop takes

The diagram above is the whole vocabulary, and each shape is a few lines:

- **A conversation.** The flow waits for the next thing to say, says it, and waits again.
  Between two turns it is a Python function sitting on a call that has not returned.
- **Ralph.** A session of its own each round: the agent starts from the task and the repository
  with nothing of the last round in context. The repository is the memory.
- **Stateful ralph.** One session, opened once and held, re-sent the task every round. The
  conversation is what the flow is — and is the one thing a run picked up again cannot have
  back.
- **An actor and a reviewer.** One works; the other is asked, in a session of its own, for an
  [answer in a shape](/features/shapes), so the loop reads a field rather than a paragraph.
- **A fan-out.** One agent, a session per file, [all of them going at
  once](/features/concurrency).

## A flow that calls a flow

A loop worth having is a loop another loop can reach for. A flow may ask for another by the
same name a command line takes, hand it agents it already holds, and take back whatever it
answers with — awaited, where the inner flow is a coroutine.

A name nothing answers to is refused where it is *asked for* rather than where the answer is
called, so a flow that asks for the wrong one says so at once instead of an hour into a loop.
The inner flow's agents are not renamed: they belong to the run that was started, and a name
changed under them would change what has already been written down. Both ends of the call go
into the run's own record — a run is what it did as well as what it was started as.

## Everything a flow needs lives inside it

So that it can be copied, forked and edited whole. A flow whose parts are elsewhere is a flow
with a hole in it wherever it is copied to.

Its own skills are the `skills/` directory inside it, and it does not have to declare them:
they are in it, and looking is what finds them. A skill maintained somewhere else is named as a
git URL where the flow is declared, cloned under humanize's own home and fetched again the next
time a run asks for it — so it keeps up, and goes on working when the network is down. The
flow's own wins a name a repository also uses, because a fork that edited a skill meant the
edited one. A repository that cannot be fetched at all stops the run **where the flow is got
ready**, not at the first turn: a flow that works by a skill it has not got is not one to start
and find out about an hour in.

## Where flows come from

A flowverse is a git repository with a `flows/` directory in it, offered under its own name,
and **only that directory is read** — a repository is a README, a pyproject and a test suite as
well, and reading a flow means running it.

Nearest wins: this project's flows, then yours, then whatever there is to run, so a project may
mean its own `chat` by `chat`. A name qualified by a flowverse is that flowverse's and is never
stood in for. Two are always listed — the package's own, and humanize's repository of the rest,
which is listed whether or not it has been fetched, because a list that only mentioned it once
somebody had thought to add it would be a list that hid what there is to run.

## Where the detail is

- [Writing a flow](/weaver/writing-a-flow) · [Loops](/weaver/loops) · [Testing a
  flow](/weaver/testing-flows)
- [An atlas](/weaver/atlas) · [Checking a flow](/weaver/checking-flows) · [Python becomes a
  prophecy](/features/prophecy)
- [Settings of its own](/weaver/flow-settings) · [A flow that calls a
  flow](/weaver/calling-flows) · [Flowverses](/weaver/flowverses)
- [Flows reference](/reference/flows) — the contract, in full
