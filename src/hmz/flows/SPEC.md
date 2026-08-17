# Flows

## File Structure

```
.
├── __init__.py
├── agent.py
├── builtin
├── checking.py
├── driving.py
├── skills.py
└── verses.py
```

What a flow is: what it drives, what it is called, where it is found, which of the ones it
holds was asked for, what it brings with it, and what it takes for one flow to run another.
Nothing here reads a command line and nothing here opens a cycle: `hmz.runner` does both, and
asks this what the flow it was named says about itself. A call asks the cycle already open for
a record to be written into, which is not a second cycle: it is part of the one run.

This MUST be the whole of what a flow imports. A flow is content -- somebody else's
repository, forked and edited -- and one that named `hmz.agents` for the type of what it
drives and `hmz.backends` for a fact about a CLI would be a flow that breaks whenever
humanize moves either. So the one import a flow writes MUST be `hmz.flows`, and whatever a
flow legitimately needs that is written down in another layer MUST be handed through from
here rather than reached for. What is handed through MUST be fetched when a flow names it
rather than imported with this module: this is also what a list of flows is drawn from and
what `hmz exec --help` loads, neither of which MUST pay for every coding agent driver there
is.

A flow MUST be a module, and there MUST be two shapes of one: a directory with an
`__init__.py` in it -- beside whatever it imports and a `skills/` of the skills it works by --
and a single `.py` file, which is what a flow that is one function still is. The directory MUST
win a name a file also uses, being the one that says most about itself.

Everything a flow needs MUST live inside its own directory, so that a flow can be copied,
forked and edited whole: a flow whose parts are elsewhere is a flow with a hole in it wherever
it is copied to. A flow that is a single file therefore brings no skills -- what is beside it
is the other flows, and none of it came with that one.

## `builtin/`

The flows humanize itself ships: a directory of flows and nothing else.

- Its flows MUST be read where they stand rather than from a `flows/` inside it. A fetched
  flowverse needs that directory to tell its flows from the repository around them; there is
  no repository around these, and a directory holding nothing else has nothing to tell them
  from.

- It MUST hold only the flows that show what a flow is -- one agent talking, and the shapes a
  loop over one agent takes. Everything else humanize offers MUST live in the official
  flowverse: a flow is content, and content that can change without a release is content that
  keeps up.

## `__init__.py`

```python
@dataclass(frozen=True, slots=True)
class Flow:
    name: str = ""
    about: str = ""
    skills: tuple[str, ...] = ()
    resumable: bool = False
    selectable: bool = True


class Offer(NamedTuple):
    whose: str
    name: str
    about: str = ""


def flow[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...


def loaded(where_: str | os.PathLike[str]) -> dict[str, Any]: ...


def held(where_: str | os.PathLike[str]) -> list[Flow]: ...


def at(named_: str) -> str: ...


def offers(one: Flowverse) -> list[Offer]: ...


def found() -> list[Offer]: ...


def find(named_: str) -> str: ...


def inside(named_: str) -> str: ...


def about(named_: str) -> str: ...


def __getattr__(name: str) -> object: ...
```

- A flow MUST be a function marked with `flow`, and nothing else MUST be one: a flow is read by
  running its entry point, and which of the functions that leaves behind is a flow is the
  flow's to say rather than something to read off a name. One flow MAY hold several: `flow`
  with no name MUST be the one it holds under its directory's own name, and `flow(name=...)`
  MUST be one of its own, called `<flow>:<name>` -- so that three phases of one thing are one
  thing to write and three to run, each asking only for the agents it drives and only for the
  settings it takes.
- `flow` MUST mark rather than wrap. A flow is called the way it always was, and a decorator
  between the flow and whatever reads its arguments would be a decorator that has to answer for
  them. What it marks with MUST travel on the function, since a file is read by running it.
- A name MUST be what the mark was told and nothing else: a name written down where a flow is
  run -- a command line, a settings file, another flow asking for this one -- MUST NOT change
  under whoever renames the function. A file that marks two flows with one name MUST answer
  with the first of them, that being a file to correct rather than a choice to make at random.
- A flow MAY say that it can be picked up where the last run of it left off, which is what a
  loop meant to run for a week is: it is stopped and started, by a machine going down or by
  somebody pressing esc. Such a flow MUST be handed a dict as its last argument, holding what
  it wrote there last time -- so that what it is keeping track of is the flow's own handful of
  things rather than a second copy of the transcript, which the backends already keep.
- What a flow says about itself MUST be the first line of its docstring where the decorator was
  not told one, and for a file that is one flow MUST fall back to the file's own docstring: a
  file that is one flow is documented as that flow.
- A name MUST resolve to the `__init__.py` of the directory called that, else to the `.py`
  file called that. A path given outright MAY be either, and MUST be taken in both shapes:
  a path with the extension left off is how a single-file flow is written down everywhere a
  name is not, and one shape resolving where the other does not is a flow that is offered and
  cannot be run.
- A flow MUST be found by name: the ones humanize ships by a bare name, and every other by the
  place it came from -- `official/rlar`, `local/scheduler`. The flows of your own MUST be a
  place like any other, so that one rule says what a flow is called and one list says where
  they are. Nearest MUST win -- this project's flows, then yours, then whatever there is to
  run -- so that a project may mean its own `chat` by `chat`. A name qualified by the place it
  came from MUST be that place's, and MUST NOT be stood in for.
- A flow MUST be run to be read, with its own directory and the directory the flows are in
  importable while it runs and only while: what a flow imports is not something the rest of
  the process should be able to.
- It MUST be run afresh each time it is read or run, and MUST NOT be cached: a flow rewritten
  between two runs of it -- by hand, or by an agent it is itself driving -- MUST be run as it
  is now. That is what makes a flow, and the skills it brings, a thing a run can improve.
- Reading what a file holds MUST answer with nothing for a file that will not run: it is asked
  while a list is being drawn, and a file that will not import is one line of that list rather
  than the end of it.
- A file that runs and holds no flow MUST NOT be offered as one -- a directory of flows holds
  what they import and what sets their tests up -- but one that will not run MUST be, under the
  name it would have had: it is a flow somebody named, and saying so where it is picked beats
  hiding it.
- What one place offers MUST be worked out in `offers` and nowhere else, and `found` MUST be
  that asked of each place in turn -- the flows of your own included, which is what makes them
  a place rather than an exception. Anything wanting a single one's flows MUST ask it too
  rather than building a name from a filename: a file may hold several flows and the file
  beside it none, so a name spelled out anywhere else is a name `-f` would refuse -- and two
  places deciding what a flow is called is two places to drift.
- A flow MAY say it is not to be offered in a list of them. A flow reached only by another
  flow -- one phase of a thing, an engine two flows share -- is a flow to call by name and not
  a flow to start, and one that appeared in the picker would be a line nobody can act on.
- This module MUST be everything a flow imports, which is the interfaces beside it, the mark,
  the finding, the calling, the checking, and what is written down in another layer handed
  through: the vocabulary a turn is described in, the facts about the CLIs and what each of
  them runs, and
  where humanize keeps what outlives a run. What is handed through MUST be the same object the
  layer it is written in holds, so that a flow and humanize are talking about one thing.
- What is handed through MUST be fetched when it is asked for. Importing this module MUST cost
  no more than reading a directory: a menu of flows is drawn from it, and a command line is
  routed through it before it knows whether it names a flow at all.

## `agent.py`

```python
class Session(Protocol): ...


class Agent(Protocol): ...


class Driven(Agent, Protocol): ...


class Person(Agent, Protocol): ...
```

What a flow drives, written as interfaces and nothing else.

- What a flow may ask of an agent MUST be written down here and MUST be the whole of what a
  flow is written against. A flow that named the class behind it would be a flow written
  against which CLI is being driven, how a turn is spelled to that CLI and where its logs go,
  none of which is a flow's business and all of which moves.
- It MUST hold what a flow asks of an agent, and what whoever hands an agent to a flow settles
  on it: a turn, a session, a goal, a batch, what the run has cost, what is hung on the moments
  of a turn, what the agent is configured with, the run it is part of, and where its turns
  land. Nothing about starting a process, reading a stream or falling back to another account
  MUST be here, being how an agent is driven rather than what a flow drives -- and nothing here
  MUST be reachable only through the class, since a flow that called another hands over what it
  was given and the called flow is handed the same thing.
- The two MUST be two interfaces. What an agent *is* -- what it runs, where its turns land,
  what it is called, which of a flow's skills it carries -- is an answer somebody already
  gave, at a prompt or on a command line or in a settings file, and a flow that could change
  one of them would be a flow rewriting the choice its run was started with. So `Agent` MUST
  be what a flow may ask and MUST NOT include the settling, and `Driven` MUST be `Agent` plus
  it: whoever hands an agent over holds one of those, and a flow declares the other. What is
  written down here MUST be the whole of both, and the drivers MUST answer to both.
- A flow that wants an agent set up differently MUST make one, which MUST be `Agent.clone`:
  it says what is to differ and there MUST be nowhere to say it again. What it answers MUST be
  another agent rather than this one changed -- its own name where none was given, having
  opened nothing, spent nothing, watched by nobody, hooked to nothing and written down
  nowhere -- since two agents at two efforts are two agents, and a trace that read them as one
  would read a comparison as one agent changing its mind. Everything the call does not name
  MUST be the agent it came from, the skills it carries included.
- The drivers MUST answer to it structurally, and `hmz.agents` MUST NOT import it. The arrow
  points one way -- a flow names what it drives, and a driver is written without ever naming a
  flow -- and a driver that inherited from this would be the layer below reaching up. That
  they answer MUST be stated once, where a type checker reads it, so that a driver which stops
  answering reads as a driver to correct rather than as a flow that fails on its first turn.
- A flow MUST declare the places it drives with these, and what it writes beside one -- a
  moment, a `Goal`, a `Remote`, an `Isolated`, an `AgentDefaults` -- MUST go on meaning what it
  means. What is annotated is which interface, not which class.
- A flow MUST be able to put callbacks of its own in front of an agent as tools it may reach
  for, said on the conversation and taking effect from its next turn -- which is where a flow
  is when it has something to offer. The callback MUST run in the process the flow is in, so
  that an agent reaching for one is the flow's own code running and may do whatever the flow
  may do, up to and including running another flow and waiting for it. A backend with no way of
  being given a tool it was not shipped with MUST refuse one where it is offered, and MUST say
  beforehand which it is, so that a flow may ask rather than catch. What that comes to is
  `hmz.agents.tools`.
- Which of a flow's skills one conversation carries MUST be the session's own to say, and
  MUST be sayable again while the conversation runs: an agent is what it was made as, and a
  conversation is a thing that gets somewhere -- one that has finished reading and started
  writing wants the skill about writing and no longer wants the eight about reading. A session
  nobody has said anything about MUST carry every one the flow brought, which is what every
  session of every flow has always carried, and a name the flow does not bring MUST be ignored
  rather than refused: what a session may carry is the flow's to say, and a fork that dropped
  a skill is a session carrying the rest rather than a turn that will not run.
- `Person` MUST be what a flow declares for the person at the prompt, and the class that
  answers to it MUST be read as the same place: a flow written before there was an interface
  named the class, and it is the same place either way. The class itself MUST be reachable
  too: a place is annotated with the interface, and a person is made rather than annotated.
- A `Person` MUST carry a board -- named lines the flow and the person both write on, which
  neither waits at. Saying something to them stops the turn until they answer, and that is
  right for a question and wrong for what there is to do next and how far through it is. Which
  lines are one side's alone MUST be sayable, and the other side MUST be refused where it
  writes. What that comes to is `hmz.agents.board`.
- What is true of a backend rather than of one agent -- which moments it runs, whether it has
  a goal feature, whether it can be held to a shape -- MUST be declared on the class. It is
  read off the class where a flow is checked against the agents it was given, before any of
  them has been made, so anything answering to this MUST say it the same way, annotation and
  all.

## `driving.py`

```python
type Entry = Callable[..., Awaitable[None] | None]


class NotAFlow(ValueError): ...


class Place(NamedTuple):
    name: str
    person: bool
    moments: frozenset[Moment]
    where: type[Remote] | Remote | Isolated | None = None
    goal: bool = False
    goals_default: bool = True


class Running(NamedTuple):
    flow: str
    since: float


def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]: ...


def container() -> Mapped | None: ...


@contextlib.contextmanager
def contained(
    image: str, workspace: str = ""
) -> Generator[MachineConfig | None]: ...


def lands_in(agents: Sequence[Agent], where_: MachineConfig) -> None: ...


def wanted(flow: str | os.PathLike[str]) -> tuple[Place, ...]: ...


def configures(flow: str | os.PathLike[str]) -> type[BaseModel] | None: ...


def resumes(flow: str | os.PathLike[str]) -> bool: ...


def carries(flow: str | os.PathLike[str], agents: Sequence[Agent]) -> None: ...


def load(flow: str | os.PathLike[str], *, inherit_skills: bool = False) -> Entry: ...


def running() -> tuple[Running, ...]: ...


def declares(
    flow: str | os.PathLike[str],
) -> tuple[
    Entry,
    tuple[Place, ...],
    Callable[..., tuple[Agent, ...]],
    type[BaseModel] | None,
    Flow,
]: ...


def set_up(
    flow: str | os.PathLike[str],
    setting: type[BaseModel] | None,
    config: BaseModel | dict[str, Any],
) -> BaseModel: ...


def lands(flow: str | os.PathLike[str], agent: Agent, place: Place) -> None: ...


def entered(flow: str, agents: Sequence[Agent] = ()) -> Running: ...


def left(one: Running) -> None: ...
```

What a flow says it drives, read off its own entry point, and what it takes for one flow to
run another. `hmz.runner` asks this and then opens a cycle around the answer.

- A flow's entry point MUST take `(agents: tuple[...], task: str)`, and that tuple MUST be of
  a fixed length: how many agents the flow drives is the one thing about a flow that a command
  line running it cannot otherwise know. It MUST be readable where the flow runs rather than
  only where a type checker looks, since a count nothing can read back is not one a command
  line can be held to.
- A `NamedTuple` of agents MUST be accepted in its place, and MUST additionally say what the
  flow calls each of them. `drives` MUST report those names, so that whatever asks for the
  agents asks for them by what they are for rather than by their place in a line; a plain tuple
  MUST report a name apiece that is empty, having said nothing but how many.
- A flow that runs one of its agents under the backend's own goal feature MUST say so where it
  declares the place, by writing `Goal` beside the type, and an agent whose backend has none
  MUST be refused before the first turn -- for the reason a moment it cannot run is: a loop
  built on `pursue` finds out in the middle of a turn otherwise, hours in. What each backend
  has MUST be said on the agent rather than asked of it, so that whoever is choosing one can
  offer only the ones that would work.
- Where an agent works MUST be the flow's to say rather than a setting anybody may reach for,
  and MUST be settled here: a place that says nothing runs on this machine and MUST refuse an
  agent pointed anywhere else.
- A whole run MAY be put in one container from outside, which is a convenience and not a second
  way of saying where an agent works: it is said once, about all of them, by whoever started
  the run. One container MUST be started for the run rather than one per agent -- the agents are
  working on one thing, and two containers under one run would be two workspaces the second
  agent could not see the first's work in -- and it MUST be taken down however the run ends.
- Every agent MUST be pointed at it, over whatever each was configured with, since that is what
  saying it once about all of them means. Two MUST be left alone: a place the flow itself
  declared `Isolated`, where an agent works being the flow's to say, and the person at the
  prompt, who takes no turn anywhere.
- The flow's own reads, writes and commands MUST be able to reach it too. A container is handed
  the project directory at the path it already has, so a file the flow opens is already the
  file a turn opened; a command it runs is not, being run by this machine's shell against this
  machine's tools, which is the thing a container was reached for to avoid. So the run's
  container MUST be askable for, and MUST answer with the workspace as that machine has it --
  `hmz.machines.Mapped`. A run on this machine MUST answer with nothing, a flow there doing
  what it always did.
- Everything here MUST read the flow as it is now, by running it. A flow rewritten between two
  readings -- by hand, or by an agent it is itself driving -- MUST be read as it is now, which
  is what makes a run that improves its own flow a run that then drives the improved one.
- Anything the flow itself raises as it is read MUST be left alone. `NotAFlow` MUST be for a
  line to correct and nothing else, so that a flow whose own setup fails is not reported as a
  command line to fix.
- `load` MUST answer with one flow ready for another flow to run, found by the same name `-f`
  takes: a flow is a loop over agents, and a loop worth having is one another loop can reach
  for. A name nothing answers to MUST be refused where it is asked for rather than where the
  answer is called, so that a flow which asks for another by the wrong name says so at once
  rather than an hour into a loop. What it answers MUST be called the way the flow itself is --
  the agents, the task, and the config for one that takes one -- and MUST answer with whatever
  the flow answers with, so that a flow written as a coroutine is awaited by whoever called it.
- A called flow MUST be handed the agents it declares, as the tuple it declared them as, and
  MUST be handed one fewer where it talks to the person, whom nothing chooses. It MUST NOT
  rename them: they belong to the run that was started, and a name changed under it would
  change what has already been written down.
- A called flow MUST carry its own skills and no others, and the agents MUST be handed back
  carrying what they carried before it: the skills are the flow's, and a flow that called
  another goes on being driven by its own. A caller MAY say the ones it carries stay reachable,
  and the called flow MUST still win a name they both use.
- A called flow that says it can be picked up MUST be handed its own kept state, under its own
  name, in the cycle of the run that called it: a flow that called another is two flows, each
  with its own to keep, and both of them part of one run.
- A called flow MUST be written into a record of its own, in the cycle of the run that called
  it, and what it opens while it runs MUST go there rather than into the record of whatever
  started the run: a flow that called another is two flows, and each of them ran. Its agents
  MUST be pointed back at what they were writing to when the call returns, however it returns,
  the way they are handed back the skills they carried. A call from a flow that nothing is
  keeping a record of MUST run and write nothing rather than fail.
- `running` MUST report every flow running now, the one that was started first and whatever it
  called after it. Nothing else can say: a flow is a Python file that may branch any way it
  likes, so what it is doing is only visible where it was started and where it asked for
  another. A flow MUST leave that list however it ends, and a call MUST be written into the
  cycle at both ends, saying which record it was written to, a run being what it did as well
  as what it was started as.
- What is running MUST be checked against the threads running it. A flow says it has ended as
  it ends, but only one that got the chance to: a flow abandoned where it stood -- an interface
  taken down under it -- would otherwise be reported as running for the life of the process,
  and everything that reads this would name a flow that is no longer there.
- What a report of a failure says about the run it happened in MUST be registered here, and
  MUST be names and never contents: which flow, how long it has been going, and for each of its
  agents what it drives and at what. What the flow was told, what any agent said and what is in
  any file MUST NOT be there nor reachable from what is.
- `resumes` MUST answer whether a flow says so now, read by running the flow rather than off
  what a run of it recorded: a flow is a directory on disk, and what can happen next is what it
  says today.
- `configures` MUST answer with the model a flow says it can be set up with, which is the whole
  of what may be asked: the fields, their types, what each is for and the combinations the flow
  refuses are already written down in it, so whatever is starting a flow can put the questions
  without knowing what any of them mean.
- `set_up` MUST read a config back through the model this reading of the flow declared rather
  than take one as it comes: a flow is loaded by running its file, so the class it declared last
  time is a stranger to the class it declares this time, and what survives that is the fields.

## `checking.py`

```python
class Finding(NamedTuple):
    code: str
    severity: Literal["error", "warning"]
    where: Path
    line: int
    said: str


def checked(flow: str | os.PathLike[str]) -> tuple[Finding, ...]: ...


def surface(protocol: type) -> frozenset[str]: ...


def offered() -> frozenset[str]: ...
```

The static read of a flow's legality: what will not run, said before anything runs it.
`driving.py` refuses a flow as it loads it, and loading a flow means running its file -- so
this is the reading for a flow nobody has read yet, generated or fetched or forked, and it is
the first of two: what only running the file can show is `proving.py`'s, in a process of its
own.

- `checked` MUST NOT import or execute anything of the flow it reads. It is pointed at
  untrusted code -- that is what it is for -- and a checker that ran what it was checking
  would be the attack it exists to catch. Every file the flow's directory holds MUST be read,
  except what is under its `skills/`, which is content for the agents rather than code.
- It MUST answer with findings rather than raise, and every finding MUST carry a code, a
  severity, a file and a line: a checker is asked so that everything wrong can be said at
  once, and a finding that cannot say where it is is a finding nobody can act on.
- `error` MUST be kept for a flow that cannot run, cannot be answered, or cannot end --
  something no run of it survives -- and `warning` for a flow that runs and may be regretted.
  A flow with no error findings MUST be one `driving.py` would load, as far as reading can
  tell; nothing here MUST refuse a flow for style.
- Every rule MUST be the proof of an absence, worked out one function at a time: no exit in
  this loop, no bound in this function, no guard on this name. Nothing MUST claim an exit
  reachable or a bound tight, and nothing MUST follow a value through a call -- a flow that
  keeps its loop in one function and its bound in another is a flow this reading trusts,
  since a rule that guessed further would refuse flows that run.
- What an agent may be asked MUST be read off the interfaces in `agent.py` themselves, which
  is `surface`, and what a flow may import MUST be read off this package's own tables, which
  is `offered`: the checker states what the interface is, so a second copy of either would be
  the drift it checks for.

## `verses.py`

```python
@dataclass(frozen=True, slots=True)
class Flowverse:
    name: str
    url: str
    at: Path
    fetched: bool
    fixed: bool


def flowverses() -> list[Flowverse]: ...


def nearest() -> list[Flowverse]: ...


def holds(one: Flowverse) -> Path: ...


def add(url: str, name: str = "") -> Flowverse: ...


def fetch(name: str) -> Flowverse: ...


def remove(name: str) -> bool: ...


def flows(one: Flowverse) -> list[str]: ...


def plain(url: str) -> str: ...


def clone(url: str, at: Path) -> None: ...


def refresh(at: Path) -> None: ...
```

- A flowverse MUST be a git repository with a `flows/` directory in it, cloned into
  `~/.humanize/flowverses/<name>/`, and every flow in it MUST be offered under that name. A
  directory with no entry point in it, or one whose name starts with an underscore, MUST NOT
  be one of them: it is what the flows beside it import.
- The flows of your own MUST be two places here like any other, `local` for `.humanize/flows`
  where humanize is being run and `user` for the one in your home directory. They are
  directories rather than repositories -- nothing fetches them, and what is in one is whatever
  you put there -- so they MUST be read where they stand the way `builtin` is, and MUST NOT be
  fetched, added under, or taken away. Everything that goes looking for a flow MUST have one
  list to look in: a place of yours that had to be listed separately is a second rule for what
  a flow is called, which is a name that will not resolve.
- These places MUST have two orders, and both MUST be written down here: the order they are
  offered in, which is humanize's own first and yours last, and the order a name is looked up
  in, which is nearest first. A place missing from either is a flow that is offered and cannot
  be run, or one that runs and is nowhere to be seen.
- Fetching a repository MUST be written down once and reached for by everything that fetches
  one -- a flowverse, and a repository of skills a flow named -- so that a clone and a fetch
  mean the same thing whichever asked for it.
- Only that directory MUST be read for flows, and a fetched flowverse with none MUST hold
  none. A repository is a repository -- a README, a pyproject, a test suite, whatever sets the
  tests up -- and reading a flow means running it, so what is run MUST be what somebody put
  where the flows go rather than every `.py` file that came down with it.
- Where the flows of one are MUST be worked out in one place, `builtin`'s reading of its own
  directory included: everything that goes looking for a flow asks that one place, so an
  exception written down once is an exception rather than a rule to remember.
- Four MUST always be listed: `builtin`, which is the package's own and is fetched from
  nowhere, `official`, which is humanize's repository of the rest, and the two the flows of
  your own live in. None MUST be removable, and `official` MUST be listed whether or not it has
  been fetched -- a list that only mentioned it once somebody had thought to add it would be a
  list that hid what there is to run.
- A name MUST be one directory name, and one that could climb out of the directory they are
  kept in MUST be refused wherever it is given.
- None of the four that are always listed MUST be a name a flowverse can be added under.
  Cloned into `builtin` a repository would be in nobody's list, since that name is skipped when
  they are listed; cloned into `official` it would be shown against humanize's own URL; cloned
  into either of yours it would be listed under a name that is read from a directory somewhere
  else and never looked at. All MUST be refused where the name is given rather than discovered
  afterwards.
- Fetching one again MUST take what the repository says now rather than merge into it: a
  flowverse is a copy of somebody else's repository, not a branch of your own, and a merge
  nobody asked for is a fetch that fails the next time it is run.
- A fetch that failed MUST leave the list as it was and say what git said. Nothing here MUST
  wait on the network without a limit -- and since a clone called off for reaching that limit
  is killed rather than allowed to fail, what it had written by then MUST be taken away here:
  git tidies up after its own failures and cannot tidy up after being killed, and a name held
  by a flowverse that is not there is a name that cannot be used again.
- Where a flowverse came from MUST be scrubbed of whatever was signed into it in one place,
  which everything that shows one asks: a private flowverse is added as
  `https://x-access-token:$TOKEN@...`, git keeps that verbatim, and it is shown by a command
  line and at a prompt both. Two places doing it is one place to forget.
- Where a flowverse came from MUST be read without interpolation. A `%` in a URL is ordinary --
  a percent-encoded password, or a path with one in it -- and reading it as the start of a
  substitution would raise where every listing of the flowverses passes.

## `skills.py`

```python
def brought(at: Path | str, declared: Iterable[str] = ()) -> list[Loaded]: ...


def cached(url: str) -> Path: ...


def fetched(url: str) -> Path: ...
```

The skills a flow works by: the ones in its own `skills/`, and the ones it named that live
somewhere else. Nothing here installs anything, and nothing here mounts anything -- what a
session does with them is `hmz.agents.skills`.

- A flow's own skills MUST be the `skills/` inside it, read as a directory apiece each holding
  a `SKILL.md`, which is the layout every one of these CLIs already reads a skill in. A flow
  MUST NOT have to declare them: they are in it, and looking is what finds them.
- A skill that lives somewhere else MUST be named where the flow is declared, as a git URL
  anything can clone with an optional `#<skill>` saying which of that repository's `skills/*`
  is wanted. Without one, every skill that repository holds MUST be brought.
- Such a repository MUST be cloned under humanize's own home and fetched again the next time a
  run asks for it, so that a skill somebody else maintains is a skill that keeps up -- and one
  already fetched MUST go on working when the network is down.
- The flow's own MUST win a name a repository also uses: a fork that edited a skill meant the
  edited one.
- A repository that cannot be fetched at all MUST stop the run where the flow is got ready
  rather than at the first turn: a flow that works by a skill it has not got is not a flow to
  start and find out about an hour in.
