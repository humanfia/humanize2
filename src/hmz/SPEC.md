# humanize

## File Structure

```
.
├── __init__.py
├── __main__.py
├── agents
├── backends.py
├── cli
├── coganchor
├── cycle.py
├── daemon
├── fallbacks.py
├── flows
├── kept.py
├── machines
├── models.py
├── providers
├── runner.py
├── sdk
├── settings.py
├── telemetry.py
├── tracing
└── tui
```

Each subdirectory is a library and has a SPEC of its own; the modules beside them are
specified here. None of them MUST have a command line: `cli` is the whole of it, one module
per command that takes a parser of its own, and it MUST reach a layer only from inside the
command carried out in it, so that a command pays for no layer but its own -- and so that the
same package serves as the target half of a session, where it is the only one installed.

There are four ways in and one thing under them. `sdk` is humanize as one object, and `cli`,
`daemon` and `tui` MUST each be a way of reaching it rather than a second copy of what it
does: a command line reads a line and prints what came of it, a daemon holds a run where a
terminal closing cannot end it, and the interface draws. What two of them would otherwise
each have written MUST be written in `sdk` instead, so that a thing that can be done one way
can be done every way and is refused the same way whichever way it was asked.

No two layers MUST name each other. A pair that does is two things put in one place, not one
thing above another, and is what `tests/test_layering.py` refuses.

Every module MUST be named for what it holds. `coganchor` alone is a name of its own, being a
program that ships to a target and could be lifted out whole.

## `__init__.py`

Expose `home`, and nothing else. A caller names the layer it wants.

## `settings.py`

```python
class Settings:
    def __init__(self, workspace: Path | None = None): ...

    @property
    def flow(self) -> str: ...

    @property
    def enable_sentry(self) -> bool | None: ...

    @property
    def profiling(self) -> bool: ...

    def profiles(self, *, on: bool) -> None: ...

    def agents(
        self, flow: str, goal_defaults: Sequence[bool] | None = None
    ) -> list[Runs]: ...

    def config(self, flow: str) -> dict[str, Any]: ...

    def flows(self) -> dict[str, Any]: ...

    def remember(
        self,
        flow: str,
        names: tuple[str, ...],
        models: Sequence[Runs],
        config: dict[str, Any] | None = None,
    ) -> None: ...

    def answers(self, *, enable_sentry: bool) -> None: ...

    def forget(self, workspace: str = "") -> bool: ...
```

What humanize remembers: what each workspace was last set up to run, and the settings that are
not a workspace's.

- It MUST be a leaf, for the reason `kept.py` is one: the interface writes these and a command
  line has to be able to read them without loading the interface to do it.
- A setting that is not a workspace's MUST live beside the workspaces rather than inside one,
  and MUST be tri-state where it is a question somebody has to answer: on, off, and the absence
  that means nobody has been asked. Reading one MUST NOT write it, or the absence -- which is
  what tells a first start from a deliberate no -- would be spent by looking.
- Writing MUST re-read and merge rather than dump what was read at construction: two of these
  are alive at once wherever a menu writes a setting while the interface goes on remembering
  flows, and a plain dump would put back a file missing whatever the other had written. What
  the writer holds MUST win for its own workspace and for the settings it has answered, and
  everything else MUST be whatever is on disk now.
- A file that is missing, unreadable or not what this writes MUST read as nothing remembered
  rather than as a reason to stop.

## `telemetry.py`

```python
SENT: tuple[str, ...]
KEPT: tuple[str, ...]


def enabled() -> bool | None: ...
def asked(*, enable_sentry: bool) -> None: ...
def start() -> bool: ...
def about(name: str, said: Callable[[], object]) -> None: ...
def held() -> dict[str, object]: ...
def crash(why: BaseException, **said: object) -> None: ...
def snag(name: str, **said: object) -> None: ...
```

What humanize reports about itself when something goes wrong, and what it never reports.

- Nothing MUST be sent by a machine nobody has been asked on. The answer MUST be asked once,
  by the interface, which is the one part of humanize with somebody at it; a headless run MUST
  report only where the answer is already yes and MUST NOT ask. An environment variable MUST
  answer for one process without writing anything down, so that a scripted install, a CI job
  and this suite are all silent without touching what a person answered.
- What is sent and what is not MUST both be written down in one place, MUST be shown where the
  question is asked, and MUST be readable again afterwards from the settings menu: a question
  nobody can answer knowing what it means is not consent.
- Nothing MUST be sent that a person would be surprised by. No prompt, no task, no line typed,
  nothing an agent said, no file, no path outside humanize, no directory name, no credential
  and no variable an account sets. The switches that would collect them MUST be off, and every
  string on the way out MUST be put through the same scrubbing whatever carried it there.
- This MUST be a leaf naming only the settings it reads. What goes with a report is the layers'
  own to say, and each MUST say it by handing over a callable, which MUST be run only when a
  report is actually being made: nothing MUST be gathered on a machine that reports nothing.
- What is not an error MUST be reportable too. A key that did nothing, a menu answered and then
  thrown away, a line refused, a run stopped seconds in: on a tool this young that is the half
  of the feedback a stack trace never carries, and it MUST be recorded as counts and names and
  never as anything anybody typed.
- Nothing here MUST be able to stop humanize running. A reporter that will not start, a
  callable that raises and a report that cannot be sent MUST each leave the run as it was.

## `backends.py`

Every fact about a coding agent CLI that is not code: what it is called, what a command line
may call it, how hard it can be asked to think, where it keeps its home, which files under it
a session is logged to, and which files under it and under a workspace are the skills it would
load.

- It MUST be the only place any of those is written down, and MUST import nothing but the
  standard library, so that reading a fact costs nothing of the layer the fact is about.
- Code that acts on a fact MUST live where its purpose does: driving a backend in `agents`,
  reading its logs back in `tracing`.
- A model id MUST NOT be written down here, nor anywhere else in this package. What a CLI
  runs is not a fact that keeps: it ships models without asking anybody, and which of them an
  account may name is that account's. `models.py` is what asks.
- The efforts MUST be written down, being that backend's own vocabulary rather than a
  catalogue of things that come and go. A rung the backend takes without documenting MUST be
  written down as one, since no listing of the backend's own will ever name it.
- Which credentials are the same credential MUST be written down here too, one entry per
  credential holding every name it goes by. A vendor's key is the vendor's rather than the
  CLI's -- an Anthropic key is one whether Claude Code, pi, opencode or mimocode holds it --
  and a CLI that named a vendor's credential after itself named the same thing. Which
  backends read each of them MUST NOT be written down again: it is already written, as what
  each backend's ways ask for and what it says it would take an account from.

## `models.py`

```python
def where(cli: str, provider: str = "") -> Path: ...
def offered(cli: str, provider: str = "") -> tuple[Model, ...]: ...
def asked(cli: str, provider: str = "") -> str: ...
def ask(
    cli: str, provider: str = "", seconds: float = WAITING
) -> tuple[Model, ...]: ...
```

What each backend runs, asked of that backend and kept until it is asked again.

- What a backend runs MUST be got from that backend itself, by whatever mechanism that
  backend offers for being asked -- its own control request, its own catalogue command, its
  own dump of what it is configured with. It MUST NOT be a list written down here: a list is
  wrong the day the CLI ships a model, and says nothing about which of them this account may
  actually name.
- It MUST be asked as the account whose it would be: under that provider's own credential
  paths and variables, and without the ones its backend would take another account from --
  which is how a turn of that account is run. What is kept MUST be kept per account, two
  accounts of one CLI being two catalogues.
- What is kept for a provider MUST be kept with that provider, so that taking the account
  away takes its catalogue with it. The account nobody chose keeps its own under humanize's
  home.
- Asking MUST NOT happen at a prompt: it is a coding agent starting up. Reading what was kept
  MUST cost one file read.
- An account MUST be asked as soon as it is made, since that is the first moment there is
  anything to ask. A backend that would not answer MUST leave the account made: an account
  whose models are not known yet is one to ask again, not one that failed.
- A model's efforts MUST be its backend's ladder narrowed to the rungs that backend said that
  model takes, in the ladder's own order, and MUST be the whole ladder where it said nothing
  of that model -- a model it says nothing about is one it will take any of them for.
- A catalogue that has never been asked for MUST be empty rather than guessed at.

## `kept.py`

```python
class Runs(NamedTuple):
    spec: str
    anchor: str = ""
    permission: str = ""
    provider: str = ""
    goals: bool = True
    web_search: bool = True


class Kept(NamedTuple):
    name: str
    runs: Runs


def written(runs: Runs) -> dict[str, Any]: ...
def read_back(held: dict[str, Any], *, goals: bool = True) -> Runs | None: ...


class Templates:
    def __init__(self, at: Path | None = None) -> None: ...
    def all(self) -> list[Kept]: ...
    def find(self, name: str) -> Kept | None: ...
    def keep(self, agents: Sequence[Kept]) -> None: ...
```

What an agent is, written down, and the ones written down under a name -- as `agents.yaml`
under humanize's own home.

- It MUST be here rather than beside the interface, and MUST name nothing but `hmz` itself:
  both ways in read it, and a command line that had to load a terminal interface to read a
  file of six lines would be paying for a layer it does not use.
- One agent MUST be written the same way wherever it is written down -- under a name here, and
  under a flow and a workspace in the interface's own settings -- so the shape is said once.
  What says nothing MUST be left out: an agent that works here, may do what an agent nobody
  was asked about may do and runs as this machine is signed in is one every field of which is
  that field's own silence. What an older file says about skills MUST be read past: they are
  the CLI's own now, and not a thing an agent is written down with.
- The agents kept under a name MUST NOT be a workspace's and MUST NOT be any flow's: what an
  agent is is not a thing about the project it happens to be working in, and a flow that
  imports one MUST take a copy rather than a link.
- A file that is missing, unreadable or not what this writes MUST read as nothing written down
  rather than as a reason to stop.

## `fallbacks.py`

```python
@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    about: str


POLICIES: tuple[Policy, ...]


@dataclass(frozen=True, slots=True)
class Falls:
    spec: str
    to: str = ""
    tries: int = 0
    policy: str = DEFAULT
    timeout: float = 0.0

    def says(self) -> bool: ...


def spec(backend: str, model: str, provider: str = "") -> str: ...


def reads(said: str) -> str: ...


def falls() -> list[Falls]: ...


def tried(said: str) -> Falls: ...


def points(said: str, at: str) -> Falls: ...


def retrying(said: str, tries: int, policy: str, timeout: float) -> Falls: ...


def clear(said: str) -> bool: ...


def chain(said: str) -> list[str]: ...


def named(policy: str) -> Policy | None: ...


def waits(policy: str, attempt: int, base: float = BASE) -> float: ...
```

The layer between an agent and its accounts: where a turn goes when the place taking it cannot
take it at all, and how many times over it is taken again first. A layer of its own because it
is about neither of the two places on its own, and not `hmz.providers` because what it answers
is not an account going down.

- A place MUST be three things and no more: the CLI, the account it runs as, and the model it
  runs, written `CLI[@ACCOUNT]/MODEL`. Those are what a turn can fail for having named. How
  hard an agent thinks, what it may reach for, whether it may search the web and which of a
  flow's skills it carries are what that agent *is* -- settled where it was made -- and MUST
  NOT be part of a place: an agent that fell back would otherwise be reconfigured by a file
  nobody meant as a configuration.
- A step MUST be written between two places rather than on either. It is about neither on its
  own -- it is what to do when this CLI, at this model, as this account, cannot run -- and two
  agents of one CLI on one account at two models are two things to say, which an answer
  written on the account could not say.
- An account's chain and this MUST be two things and MUST stay two. An account that goes down
  is answered by another account of the same backend, inside the conversation that was
  running, with the same agent at the same model throughout; that is a thing about the
  account and MUST go on being written on it. A model retired, a CLI that will not start, a
  rate limit on the whole account rather than one request: none of those is answered by
  another account, and what answers them MUST be another place.
- How many times over a failed turn is taken again MUST be written here and nowhere else. It
  is a thing about the place rather than about the credentials the turn ran with, and both it
  and where the turn goes next are answers to the one thing that happened -- so one row says
  both. Nothing MUST be retried by default: a turn is taken once, as it always was, since a
  prompt the model refused is the same refusal every time and only the caller knows which of
  its places fails the other way.
- The waits MUST be the ones everybody uses under the names everybody uses them by, and none
  MUST be invented here: no wait, a constant one, a linear one, exponential backoff, that with
  full jitter, and Fibonacci. A name that is not one of them MUST wait the way the default
  does rather than not at all, a setting nobody recognises MUST NOT become a loop that hammers
  whatever has just failed, and no single wait MUST be longer than a turn however far the
  backoff has climbed. The default MUST be exponential backoff with jitter, that being what
  keeps a flow's agents from all coming back on the same second. The time a place was given
  MUST be checked before a wait rather than after it, so that a turn is never started knowing
  it is already spent.
- A place's CLI MUST be read through `hmz.backends` rather than matched here: a name no
  backend answers to MUST be refused where it is written rather than found by the turn that
  needed it. A model MAY hold slashes of its own, so the first slash MUST be the one that
  separates them. An effort written after a colon MUST be read past rather than refused: a
  step written down before effort left this spelling is a step somebody still means.
- A step MUST NOT point at the place it is written against, and a chain that comes round on
  itself MUST end at the second sight of a place: either would otherwise be a turn that could
  never run out of places to go. One place MUST have one place to go -- writing one again MUST
  say the new thing and not both, a chain that forked being a chain nothing can walk.
- `chain` MUST answer with this place first whether or not anything was written down about
  it, so that whoever walks one walks a list rather than a list and a special case.
- What is written down MUST be read whole every time it is read: a chain is what a failed turn
  asks for, and the answer is the walk rather than the step. A file that cannot be read MUST
  hold nothing rather than end every run on the machine, and an entry naming a backend there
  is none of MUST be read past. An entry that says nothing at all -- no destination and no
  tries -- MUST NOT be kept.
- A turn MUST walk its account chain to the end before it walks this: the account chain keeps
  the conversation and this cannot, no backend taking another backend's session id. The turn
  that moves MUST be taken in a new session at the place it moved to, MUST carry the skills
  the flow gave the agent it left, and MUST be answered back through the session that asked --
  one turn is one turn, whoever took it. That session MUST be opened once and held for as
  long as the one that asked for it, and MUST end when it does: what the conversation was is
  lost at the move, and losing a second one every turn after it would be a stateful loop
  started over every round.
- The agent standing in MUST be configured exactly as the agent that could not run was, less
  what that backend was told in its own vocabulary: an override one CLI reads says nothing to
  another. A rung the CLI taking over has no word for MUST become the rung at the same depth
  of its own ladder, every ladder here being written hardest first. A setting the CLI taking
  over cannot be told at all MUST make it no stand-in: a setting quietly ignored would be a
  setting that lies, so the turn MUST fail the way it failed before anybody wrote a step down.
- The agent standing in MUST be made at most once and kept, for the reason an account that has
  moved stays moved: a place that went down is not one to try again each turn. It MUST be
  made only when a turn has nowhere left to go -- a chain of four places all started when the
  run was would be three CLIs held open for a failure that never came -- and MUST hold only
  the steps after its own, or a chain read from the top by each hop would walk the failed ones
  twice.

## `cycle.py`

What one run of one flow was, written down as it happens: which flow, on what, by which
agents, and which sessions each of them opened. Not what the sessions said -- the backend's
own log is the turn-by-turn record and this MUST NOT be a second copy of it.

- One cycle MUST be one run. It opens when the flow starts and closes when the flow stops,
  however it stops -- finished, failed, or interrupted. A closed cycle MUST NOT be reopened.
- One cycle MUST be one directory, holding the run's own record, a record per flow the run
  called, and a directory per session any of them opened. A run is more than a list of events
  now -- what its sessions were logged to, what it called, and what a flow that can be picked
  up again left behind -- and all of it is one run's.
- A flow the run called MUST be written down in a record of its own, in that same directory,
  and that record MUST be named for the flow and for that call of it. A flow that called
  another is two flows, and each of them opened sessions, kept its own state and may have
  called a third; a flow called twice is two runs of it, and one record for both would say
  neither. It MUST NOT be another cycle: a called flow is part of the run that called it.
- A call MUST be written into the record of whatever called it at both ends, and both ends
  MUST say which record the call was written to. Pairing by the order the lines are in is not
  enough: a flow written as a coroutine may have two calls going at once, and their ends
  interleave.
- A called flow's own record MUST hold what a run's record holds -- what it opened, what it
  called in turn, and how it ended -- and MUST say which record called it, so that a run reads
  back as the shape it ran in rather than as one flat list nothing can be attributed to. How
  it ended MUST be how the call ended: a call that raised inside a run that carried on is a
  call that failed and a run that did not.
- What a cycle opened MUST be read across every record it holds, and each session MUST say
  which flow opened it. One run is one run however many flows it took to run it: a trace of it
  is gathered from what the whole run opened, and which flow a session was opened inside is
  what a record of its own is for.
- A session MUST be written down as whose it was, what took its turns, which account those
  turns ran as and what the backend called it. The backend's own log says only the last of
  those: two agents at one configuration are one agent to anything reading the logs alone,
  and two accounts of one CLI are one account.
- A session MUST also be given a name of its own, which MUST hold the agent, the CLI, the
  account and the backend's id, and MUST be one directory name. An id alone says nothing
  about whose session it was, and a directory of forty of them is one nobody can read.
- Each session's own logs MUST be pointed at from inside the cycle, under that name, by a
  link apiece. A link rather than a copy, and for reading rather than for running: humanize
  MUST go on reading and writing every log where the backend keeps it, so that nothing here
  can be the reason one is written twice or read from the wrong place. A filesystem that
  refuses a link, a backend humanize knows no logs of, and a log written after the session
  was opened MUST each leave the run as it was -- the last of them by the links being made
  again when the run ends, which is when a sub-agent's transcript is finally there.
- What a flow that says it can be picked up again left behind MUST be kept here too, under
  the flow that left it: a flow that called another is two flows, and neither writes the
  other's. A flow that emptied what it had written MUST be where the search for something to
  pick up stops rather than a run to look past: clearing it says the next run starts clean,
  and answering that with the state of the run before would be answering the opposite. It
  MUST be saved as the flow writes it rather than when the run ends -- a run worth picking up
  is one that was stopped or killed, and state saved only at the end is state such a run has
  none of -- and MUST be saved again when the run ends, since something
  written inside a value it holds is a change no mapping can see.
- Nothing about keeping it MUST be able to stop a run: a value no JSON has a shape for, a
  directory that has gone, a file somebody wrote by hand as something else. State is what a
  flow may pick up, and a run that stopped because it could not save some is worse than one
  that carries on without it.
- Cycles MUST be named so that they sort in the order they were run, to the millisecond: what
  a flow is picked up from is the last run of it, and two started inside one second would
  otherwise be ordered at random.

## `runner.py`

```python
class Runner:
    def __init__(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
    ): ...

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent this drives, the person the flow talks to among them."""

    def run(self, task: str) -> None:
        """Runs the flow, until it returns.

        Args:
            task: What the flow is to have its agents do.
        """


def read_agent(
    spec: str,
) -> tuple[Profile, str, str, str, str | None, tuple[tuple[str, str], ...]]:
    """Reads and validates one command-line agent specification."""


def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None]:
    """Reads an `hmz exec` line into a flow, the agents, the task, and the flow's setup."""


def set_up_from(said: str | os.PathLike[str]) -> dict[str, Any]:
    """Reads what a flow is to be set up with out of a file of it."""
```

What starts a flow: the file it is in, the agents it takes, and the line naming both. What a
flow is and what it says it drives is `hmz.flows`, which this asks -- so a flow itself MUST
never have reason to name this module.

- `__init__` MUST load the flow and MUST raise `hmz.flows.NotAFlow` unless the file is there
  and has such an entry point, declaring as many agents as it was given, so that a flow started
  with the wrong number of them fails before its first turn rather than partway through a loop.
  The same MUST go for an agent that cannot run a moment the flow hangs a hook on, one run
  under a goal whose backend has no such feature, one pointed at a machine the flow does not
  send it to, and a config that is not what the flow asked for.
- An agent that was not named where it was made MUST take the name the flow gives it, before
  anything is written down about the run: a name is what a trace groups an agent's sessions
  under, and `builder` says what a hex tail does not. One named already MUST keep that name.
- The person at the prompt MUST be made here rather than given: nobody chooses what they run,
  so nothing upstream of this was ever asked about them. `agents` MUST answer with them among
  the rest, that being the one agent whatever started the flow could not have got any other way.
- What the flow works by MUST be carried onto its agents before the first turn, since a
  repository the flow named is fetched to get it: a run that cannot reach one MUST say so here
  rather than an hour into a loop.
- Whatever the flow itself raises as it is loaded MUST be left alone, so that a flow whose own
  setup fails is not answered with a command line to correct.
- `run` MUST call the entry point with the agents as the tuple the flow declared -- the named
  one where it named them -- in the order they were given, and the task. A flow written as a
  coroutine MUST be run to its return here too, on a loop of its own, so that whatever started
  one is holding a run rather than a coroutine somebody has to remember to await.
- The run MUST be written down as it happens, as a cycle: which agents were driven, at what,
  and which sessions each of them opened. The run MUST be over the moment `run` returns,
  however it returns.
- A flow that says it can be picked up MUST be handed a dict as its last argument -- after
  the config, for a flow that takes one -- holding what the run it is being picked up from
  left there. Which run that is MUST be the last run of that flow in this workspace unless
  one is named, so that running a resumable flow again means carrying on: a loop meant to run
  for a week is a loop that will be stopped and started. What it writes MUST be kept in the
  cycle of the run doing the writing rather than in the one it was picked up from: a closed
  cycle is not reopened, and a run is what that run did.
- Whether a run here is profiled as well as traced MUST be read from this workspace's own
  settings rather than from the cycle, which is the run written down rather than the settings
  under it.
- `flow_and_agents` MUST read the same `hmz exec` line the command takes, and MUST be here
  rather than in `cli`: the terminal interface starts a flow from that line and then keeps the
  agents, and a reader that lived in the command line would be one the interface reached up
  into. It MUST NOT load a flow to answer a `--help`, nor refuse a line for a flow it cannot
  read: what a place suggests about goals is a convenience, and reporting the flow is
  `Runner`'s one job.

## Commands

```shell
hmz [--no-daemon] [<command> [<args>...]]
```

- A line naming no command at all MUST open the terminal interface, which is every command at
  one prompt. There MUST be no command that opens it too: one way in is one way in. A line
  naming something that is not a command MUST be a usage error listing the commands there
  are. Everything after the command name MUST reach that command untouched, `--help`
  included, so that each answers for its own arguments.
- The interface MUST be opened on a run held apart from the terminal wherever there is a
  terminal to hand over to, so that closing the terminal is not what ends a day's work: a
  line naming no command MUST read whichever run is already being held in this directory, and
  MUST start one where none is. A line that also says what to run MUST be a line to correct
  where one is already being held -- a run that is set up is set up, and two answers to how it
  is set up is one of them silently losing.
- With no terminal on both ends -- output going to a file, a suite driving the interface
  itself -- it MUST be opened in this process exactly as it always was, and `--no-daemon` MUST
  say so outright. An environment variable MUST say the same thing for a whole machine without
  writing anything down, as it does for whether humanize reports its own failures: a scripted
  install and this suite are one variable rather than a flag each of them has to remember.
  Anything at all that stops a run being held MUST be said and then done without: what is lost
  is being able to walk away from it, which is not a reason to refuse to open.
- `__main__.py` MUST run this same command line, so that `python -m hmz` is `hmz`.

## `hmz exec`

```shell
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...]
         [--container <image>] <task>
```

Runs a flow in the current directory, on the agents it is given.

Args:

- `-f`, `--flow <flow>[:<name>]`: The flow: one of the ones humanize ships or a flowverse holds,
  by name, or a file of your own, by path. Required. A file that holds several flows MUST be
  said which, after a colon; a flowverse's own MAY be said which, `<flowverse>/<flow>`.
- `-a`, `--agent <cli>[@<provider>]/<model>:<effort>`: One agent to drive the flow with. Repeated once for
  each agent the flow drives, in the order it takes them -- which for a flow that drives none,
  because the only side it talks to is the person at the prompt, is not at all: the person is
  handed over rather than chosen. A line short of an agent the flow does drive is caught as
  every other miscount is, against what the flow declares. It MUST also be
  accepted written out as `cli=<cli>,model=<model>,effort=<effort>`, in any order, since a
  model or an effort that holds the punctuation the short form separates on has nowhere else
  to go. One `-a` MUST be one agent: a list in a single `-a` MUST NOT be split into several.
- `--container <image>`: Run the whole of it in one container of that image, which is
  `hmz.flows.contained`. A convenience rather than a second way of saying where an agent works:
  it is said once, from outside, about all of them.
- `<task>`: What the flow is to have the agents do, as the text itself.

- `<cli>` MUST be one of `claude`, `codex` and `kimi`, each of which MUST also answer to the
  longer name it is installed under, and `<model>` and `<effort>` MUST be what that CLI is
  asked for. A model MAY hold slashes of its own -- Kimi Code's and opencode's are written
  `provider/id` -- so the CLI MUST be read from the front and the effort from after the last
  colon.
- The CLI MAY be followed by `@<provider>`, which is the account that agent's turns run as: a
  CLI is never spelled with an `@` in it, so the two are told apart wherever an agent is
  written. `provider=` MUST say the same thing written out, and an `@` naming nothing MUST be
  a line to correct rather than a line saying nothing.
- Two agents of one spelling MUST be two agents, so that a flow of an actor and a reviewer at
  one configuration is what it says it is.
- A flow that is not there, has no entry point, does not say how many agents it drives, or
  drives a different number than were given MUST be reported as a usage error, before any
  agent has run. Whatever else a flow does as it is imported is the flow's own, and MUST fail
  as it would anywhere.
- A run put in a container MUST start one container for the whole of it and MUST take it down
  however the run ends, and MUST NOT do either where none was asked for: reading a flow must
  pull no image, and a run that never starts must leave nothing behind.

## `hmz trace`

```shell
hmz trace collect [<workspace>] [--cycle <cycle> | --session <session>[,<session>]... | --all] [--output <output>] [--start <start>] [--end <end>]
```

Collects and aggregates what a run left behind -- the agents' own trajectories, and the
programs they ran where the run was profiled -- into a Chrome JSON trace for visualization.

- It MUST be a command with what there is to do to a trace under it rather than a verb at the
  top level: a `collect` says what happens to the thing without ever saying what the thing is.
- A line naming no command under it MUST say which there are rather than doing one of them.
- A trace of a run MUST hold the sessions that run opened and no others, asked for by the ids
  the run wrote down rather than by the directory it ran in: a directory is run in over and
  over, and a trace filed inside one run holding the work of the others is a trace of nothing
  anybody asked about. By id and not by directory, so that a flow that worked in a machine's
  mirror is in its own trace as well. A run that opened nothing MUST be a trace of nothing.
- What a directory holds whoever opened it MUST also be collectable, since a session no flow
  ever drove is still a session to read back, and it MUST be asked for outright -- `--all`,
  or the sessions named. It is not a trace of any run and MUST NOT be written inside one, and
  a line naming a run as well MUST be a line to correct rather than one of the two silently
  winning. It MUST be here and not in the interface: `/cycles` is a list of runs, and a trace
  of what is not one has nothing there to be reached from.

Args:

- `<workspace>`: The path to the workspace directory to generate traces for. If not provided, the current working directory is used, unless sessions are named.
- `--cycle <cycle>`: Which run to trace, by the name of its directory or a leading part of it. If not provided, the last run of the workspace. That run says which sessions the trace holds and which agent opened each of them, its profile is drawn beside them, and its directory is where the trace lands. A name no run of it answers to MUST be a line to correct.
- `--session <session>[,<session>]...`: Sessions to trace instead of a run, comma separated and repeatable. A session is named by its whole id, by the key the trace shows it under, or by a leading part of either, and the sub-agents it started are collected with it. Named sessions are collected wherever they were recorded, and are cut down to the workspace when one is provided.
- `--all`: Every session of the workspace instead of a run, whichever run opened them and whether any did.
- `--output <output>`: The path to the output file where the aggregated trace will be saved. Its directory is created if it does not exist. If not provided, the trace is saved as `traces/<datetime>.trace.json` inside the run it is a trace of -- where `<datetime>` is the UTC moment it was collected, so that collecting twice keeps both -- and, for a trace that is of no one run, in the directory that workspace's runs are kept in. A trace of a run belongs with the run: the sessions it points at and the state it left are already there, and a trace written into whatever directory somebody was standing in is one they have to keep track of themselves. A file named outright still wins, a trace being also a thing to attach to an issue.
- `--start <start>`: The start time for filtering the session logs, in any wording dateparser understands. If not provided, up to earliest logs are included.
- `--end <end>`: The end time for filtering the session logs, in any wording dateparser understands. If not provided, up to latest logs are included.

Prints the output path, which run it is a trace of, and the number of sessions and slices it
holds -- and the number of programs, for a run that was profiled.

Environment Variables:

- `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME`: The path to agent home directories for discovering session logs. If not set, use the default paths of each agent. A home directory that does not exist is skipped.

## `hmz flowverses`

```shell
hmz flowverses [list [-q] | show <name> | add <url> [<name>] | fetch <name> | remove <name>]
```

Where flows come from: what places there are, what one of them holds, and the three things
that can happen to a flowverse -- added, fetched again, taken away.

- It MUST be the same store the interface's own `/flowverses` keeps, for the reason
  `hmz providers` is the same store as `/providers`: one place a thing is kept is one place it
  is kept, whichever way somebody reached it. What it added MUST be findable by `-f` at once.
- A flow MUST be listed under the name it is offered by, which is the one `-f` takes, and that
  name MUST be asked of `hmz.flows.offers` rather than worked out here. A name built from a
  filename is a name `-f` would refuse: a file may hold several flows, and the file beside it
  may hold none at all.
- Saying which places there are MUST NOT read a flow; saying what one of them holds MUST. What
  a file holds is not a fact its name carries, so the second question has no cheap answer -- but
  it MUST be asked only of the flowverse named, and MUST NOT be asked by a line that only
  listed them or only fetched one. A repository that has just been cloned off the internet MUST
  NOT be imported unasked: fetching one is not the same as saying to run it this second.
- One that has not been fetched MUST say so where it would have said what it holds, rather
  than saying it holds nothing.
- Nothing MUST print a secret. Where a flowverse came from MUST be printed with whatever was
  signed into the URL taken out: a private one is added as `https://x-access-token:$TOKEN@...`,
  git keeps that verbatim, and this line is printed every time the flowverses are listed -- so
  a token printed once is a token in the log of every job that ran it.
- Where one came from MUST be answered from which flowverse it is rather than from whether its
  URL is empty. An empty URL means both "the package's own" and "a directory whose origin could
  not be read", and answering the second with the first puts humanize's name on somebody else's
  flows.
- A line that could not be carried out -- a name none answers to, a name already taken, one of
  the two that are always there being removed or added over, a fetch git refused, a directory
  that will not go -- MUST say so where it can be read and exit non-zero, and MUST leave the
  list as it was. None of those MUST reach whoever typed the line as a traceback.

## `hmz check`

```shell
hmz check [--static] [--strict] [--json] <flow> [<flow>...]
```

Reads a flow for what will not run, before anything runs it.

- The two readings MUST run in their order: the static one over every file the flow holds,
  which MUST NOT import or execute anything of it -- the flow most worth checking is one
  nobody has read -- and then the flow loaded and its live config model read. The second MUST
  run only in a subprocess with a clock held over it, MUST NOT run where the first found an
  error, and `--static` MUST leave it out altogether: a flow that cannot run is not one to
  run to find out more about.
- Every finding MUST print one a line -- the file, the line, the severity, the code and what
  is wrong -- with a count under them, and `--json` MUST say the same as one JSON object a
  line for a script to read. Everything wrong MUST be said at once rather than first-failure
  first: a checker is asked so that one reading answers for the whole flow.
- It MUST exit 0 for flows with nothing blocking -- warnings print and pass -- 1 where any
  error was found, or any warning under `--strict`, and 2 for a line to correct or a name no
  flow answers to, refused as argparse refuses one.

## `hmz agents`

```shell
hmz agents [list [-q] | show <name> | add <name> <cli>[@<provider>]/<model>:<effort> [--anchor <target>] [--goals|--no-goals] [--web-search|--no-web-search] [--force] | remove <name>]
```

The agents written down under a name: what there is, what one of them is, and the two things
that can happen to one -- written down, taken away.

- It MUST be the same store the interface's own `/agents` walks, for the reason `hmz providers`
  is the same store as `/providers`: one place a thing is kept is one place it is kept,
  whichever way somebody reached it. What it wrote down MUST be there to be imported the next
  time a flow's agent is set up.
- What an agent runs MUST be said exactly as `-a` says it, permissions and account and all:
  a second spelling for one thing is a spelling to keep in step.
- A name already written down MUST be a refusal rather than a quiet overwrite, and MUST say
  which line means it: an agent somebody else set up is not a thing to lose to a typo.
- It MUST NOT be the agents of a flow. Which agent drives which flow is a thing about a
  workspace, and is `hmz` with `-f` and `-a` or the interface's own menu.
- Nothing here MUST reach the interface: reading a file of six lines MUST NOT cost a terminal
  interface, so the store is `kept.py` and this names that.

## `hmz providers`

```shell
hmz providers [list [<cli>] | ways <cli> | add <cli>/<name> [-w <way>] [-s VAR=VALUE]... [--no-login] | login <cli>/<name> [-s VAR=VALUE]... | show <cli>/[<name>] | falls-back <cli>/[<name>] [<name>] | retry <cli>/[<name>] [-n <tries>] [-p <policy>] [-t <seconds>] | remove <cli>/<name>]
```

The accounts an agent may be run as: what there is, how a backend can be signed into, and the
three things that can happen to one -- made, signed in again, taken away.

- `<cli>/` -- a backend and no name at all -- MUST be the account this machine is already
  signed into, for the three lines that say something about an account rather than making one:
  it is an account of every backend and one nobody made, so it is a thing to show, to point
  somewhere and to say how to retry, and not one to add, sign in or take away.
- It MUST be the same store the interface's own `/providers` walks: one place a thing is kept
  is one place it is kept, whichever way somebody reached it.
- Whatever a way asks that the line did not answer MUST be asked at the terminal, and a secret
  MUST NOT be echoed. A line run where nobody is at a terminal MUST answer everything itself:
  a question with no answer and no default MUST be reported rather than waited on.
- Nothing MUST print a secret. What one holds MUST be shown as the names of the variables it
  sets and never their values.
- An account that has just been made or signed in again MUST have its CLI asked what it runs
  as that account, and what it said MUST be reported. A CLI that would not answer MUST NOT
  make the line fail: the account was made, which is what the line was for. `--no-login` MUST
  ask nothing either -- a line that says not to run the backend does not run it.

## `hmz fallback`

```shell
hmz fallback [list [-q] | show <cli>[@<account>]/<model>:<effort> | add <cli>[@<account>]/<model>:<effort> <cli>[@<account>]/<model>:<effort> | remove <cli>[@<account>]/<model>:<effort>]
```

Where a turn goes when the agent taking it cannot take it at all.

- It MUST be a command of its own rather than a line of `hmz providers`: an account's chain is
  a thing about an account, and this is about neither of the two agents it names.
- An agent MUST be named exactly as `-a` names one, so that a fallback is written the way the
  thing it is about is written.
- `show` MUST print the whole walk rather than the one step, since the walk is what a failed
  turn does, and MUST say so where an agent falls back nowhere.
- It MUST be the same store the interface's own `/fallback` walks.

## `hmz daemon`

```shell
hmz daemon [list [-q] | status [<workspace>] | start [-f <flow>] [-a <agent>...] | attach [<workspace>] | stop [<workspace>] [--kill]]
```

The runs being held apart from a terminal: which there are, what one of them is doing, and the
two ways one ends.

- It MUST be about runs that are already being held rather than a second way of opening the
  interface. `hmz` is how one is opened and read; this is what is left to say about one from
  outside it -- which is why `attach` is here as the long way round of what `hmz` already
  does, and `start` is here for a machine being set up rather than sat at.
- What is running in one MUST be readable without attaching to it. A line asking is a line
  somebody typed instead of opening the interface, and answering it by opening the interface
  would be answering a different question.
- Stopping MUST mean what closing the interface means -- the flow stopped, the interface
  closed -- and MUST wait for it to go. Ending the process holding it MUST be asked for
  outright, and MUST be what is left when the first will not work.
- A directory nothing is being held in MUST say so and exit non-zero, rather than starting one.

## `hmz cred`

```shell
hmz cred --map <from>=<to> [--map ...] -- <command> [<args>...]
```

Runs a program with some of its paths answered by others, and exits with its status. What a
turn under a provider is spawned as, and what a login run for one is spawned as.

- It MUST be a command of its own rather than something the driver does in this process, for
  the reason `hmz anchor` is: the supervisor forks the program and takes the process's signal
  handling with it, which a flow pumping turns from threads of its own cannot lend it.
- It MUST NOT be one of the commands a listing shows, and MUST NOT be documented as a way in:
  it is a command line because a process is started by one, not because it is a thing anybody
  types. What it runs is whatever it is given, so a listing offering it would be offering a
  way to run something that is not humanize.
- A line naming nothing to answer MUST be a usage error: a run with nothing to redirect is a
  supervisor started for no reason.

## `hmz tools`

```shell
hmz tools --at <socket>
```

Carries the tool protocol between a coding agent and the flow whose callbacks it is: this
process's standard input into the flow's socket, and the flow's answers back out again.

- It MUST be a command of its own for the reason `hmz cred` is, the other way round: a CLI
  takes a tool by starting a program, so there has to be a program. It MUST NOT be one of the
  commands a listing shows and MUST NOT be documented as a way in.
- It MUST do nothing but carry lines. The callback belongs in the process the flow is in, and
  anything answered here would be a tool the flow never wrote.
- Both directions MUST be carried at once, and the end of either MUST end the other: a CLI that
  has closed its input must not leave this process reading a socket nobody will write to.
- A socket that is not there MUST be a status rather than a crash: it is a flow that has ended,
  and a CLI reads it as its tools being unavailable rather than as a turn that failed.
