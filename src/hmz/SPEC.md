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
├── flows
├── kept.py
├── machines
├── models.py
├── providers
├── runner.py
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

## `cycle.py`

What one run of one flow was, written down as it happens: which flow, on what, by which
agents, and which sessions each of them opened. Not what the sessions said -- the backend's
own log is the turn-by-turn record and this MUST NOT be a second copy of it.

- One cycle MUST be one run. It opens when the flow starts and closes when the flow stops,
  however it stops -- finished, failed, or interrupted. A closed cycle MUST NOT be reopened.
- One cycle MUST be one directory, holding the run's own record and a directory per session
  it opened. A run is more than a list of events now -- what its sessions were logged to, and
  what a flow that can be picked up again left behind -- and all of it is one run's.
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
  other's. It MUST be saved as the flow writes it rather than when the run ends -- a run
  worth picking up is one that was stopped or killed, and state saved only at the end is
  state such a run has none of -- and MUST be saved again when the run ends, since something
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
class NotAFlow(ValueError): ...


def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]:
    """What the flow calls each agent it drives, in the order it takes them."""


def flow_and_agents(argv: list[str]) -> tuple[str, list[AgentBase], str]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, and the task."""


class Runner:
    def __init__(self, flow: str | os.PathLike[str], agents: Sequence[AgentBase]): ...

    def run(self, task: str) -> None:
        """Runs the flow, until it returns.

        Args:
            task: What the flow is to have its agents do.
        """
```

- A flow MUST be a Python file holding a function marked with `hmz.flows.flow` and taking
  `(agents: tuple[...], task: str)`. Nothing else MUST be one: which of a file's functions is a
  flow is the file's to say and not a name to guess at. That tuple MUST be of a fixed length,
  which is how many agents the flow drives: it is the one thing about a flow a command line
  running it cannot otherwise know. It MUST be readable where the flow runs rather than only
  where a type checker looks, since a count nothing can read back is not one a command line can
  be held to.
- One file MAY hold several flows: the one marked `@flow` is the flow the file holds under its
  own name, and each marked `@flow(name=...)` is addressed as `<flow>:<name>`. Which one was
  asked for MUST be read before the name is resolved to a file, and a name no flow in the file
  answers to MUST be reported as a usage error saying which ones it holds -- a file of three
  asked for by its own name is a colon away from what was meant.
- A flow that runs one of its agents under the backend's own goal feature MUST say so where it
  declares the place, by writing `Goal` beside the type, and an agent whose backend has none
  MUST be refused before the first turn -- for the reason a moment it cannot run is: a loop
  built on `pursue` finds out in the middle of a turn otherwise, hours in. What each backend
  has MUST be said on the agent rather than asked of it, so that whoever is choosing one can
  offer only the ones that would work.
- A `NamedTuple` of agents MUST be accepted in its place, and MUST additionally say what the
  flow calls each of them. `drives` MUST report those names, so that whatever asks for the
  agents asks for them by what they are for rather than by their place in a line; a plain
  tuple MUST report a name apiece that is empty, having said nothing but how many.
- `__init__` MUST load the flow and MUST raise `NotAFlow` unless the file is there and has
  such an entry point, declaring as many agents as it was given, so that a flow started with
  the wrong number of them fails before its first turn rather than partway through a loop.
- An agent that was not named where it was made MUST take the name the flow gives it, before
  anything is written down about the run: a name is what a trace groups an agent's sessions
  under, and `builder` says what a hex tail does not. One named already MUST keep that name.
- Whatever the flow itself raises as it is loaded MUST be left alone, so that a flow whose own
  setup fails is not answered with a command line to correct.
- `run` MUST call the entry point with the agents as the tuple the flow declared -- the named
  one where it named them -- in the order they were given, and the task.
- `calls` MUST answer with one flow ready for another flow to run, found by the same name `-f`
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
- `running` MUST report every flow running now, the one that was started first and whatever it
  called after it. Nothing else can say: a flow is a Python file that may branch any way it
  likes, so what it is doing is only visible where it was started and where it asked for
  another. A flow MUST leave that list however it ends, and a call MUST be written into the
  cycle at both ends, a run being what it did as well as what it was started as.
- What is running MUST be checked against the threads running it. A flow says it has ended as
  it ends, but only one that got the chance to: a flow abandoned where it stood -- an interface
  taken down under it -- would otherwise be reported as running for the life of the process,
  and everything that reads this would name a flow that is no longer there.
- A flow that says it can be picked up MUST be handed a dict as its last argument -- after
  the config, for a flow that takes one -- holding what the run it is being picked up from
  left there. Which run that is MUST be the last run of that flow in this workspace unless
  one is named, so that running a resumable flow again means carrying on: a loop meant to run
  for a week is a loop that will be stopped and started. What it writes MUST be kept in the
  cycle of the run doing the writing rather than in the one it was picked up from: a closed
  cycle is not reopened, and a run is what that run did.
- `resumes` MUST answer whether a flow says so now, read by running the flow rather than off
  what a run of it recorded: a flow is a directory on disk, and what can happen next is what
  it says today.
- `flow_and_agents` MUST read the same `hmz exec` line the command takes, and MUST be here
  rather than in `cli`: the terminal interface starts a flow from that line and then keeps the
  agents, and a reader that lived in the command line would be one the interface reached up
  into.

## Commands

```shell
hmz [<command> [<args>...]]
```

- A line naming no command at all MUST open the terminal interface, which is every command at
  one prompt. There MUST be no command that opens it too: one way in is one way in. A line
  naming something that is not a command MUST be a usage error listing the commands there
  are. Everything after the command name MUST reach that command untouched, `--help`
  included, so that each answers for its own arguments.
- `__main__.py` MUST run this same command line, so that `python -m hmz` is `hmz`.

## `hmz exec`

```shell
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...] <task>
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

## `hmz collect`

```shell
hmz collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects and aggregates agent trajectories and generates Chrome JSON trace files for visualization.

Args:

- `<workspace>`: The path to the workspace directory to generate traces for. If not provided, the current working directory is used, unless sessions are named.
- `--session <session>[,<session>]...`: The sessions to generate traces for, comma separated and repeatable. A session is named by its whole id, by the key the trace shows it under, or by a leading part of either, and the sub-agents it started are collected with it. If not provided, every session of the workspace is included. Named sessions are collected wherever they were recorded, and are cut down to the workspace when one is provided.
- `--output <output>`: The path to the output file where the aggregated trace will be saved. Its directory is created if it does not exist. If not provided, the trace is saved as `.humanize/<datetime>.trace.json` in the current working directory, where `<datetime>` is the UTC moment it was collected, so that collecting twice keeps both traces.
- `--start <start>`: The start time for filtering the session logs, in any wording dateparser understands. If not provided, up to earliest logs are included.
- `--end <end>`: The end time for filtering the session logs, in any wording dateparser understands. If not provided, up to latest logs are included.

Prints the output path with the number of sessions and slices it holds.

Environment Variables:

- `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME`: The path to agent home directories for discovering session logs. If not set, use the default paths of each agent. A home directory that does not exist is skipped.

## `hmz flowverses`

```shell
hmz flowverses [list [-q] | show <name> | add <url> [<name>] | fetch <name> | remove <name>]
```

Where flows come from: what places there are, what one of them holds, and the three things
that can happen to a flowverse -- added, fetched again, taken away.

- It MUST be the same store the interface's own `/flow` walks a tab at a time, for the reason
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

## `hmz agents`

```shell
hmz agents [list [-q] | show <name> | add <name> <cli>[@<provider>]/<model>:<effort> [--anchor <target>] [--goals|--no-goals] [--force] | remove <name>]
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
