# humanize

## File Structure

```
.
├── __init__.py
├── __main__.py
├── cli
├── coganchor
│   ├── agents
│   ├── backends.py
│   ├── fallbacks.py
│   ├── machines
│   ├── models.py
│   ├── prices.py
│   └── providers
├── daemon
├── flows
├── runtime
│   ├── epic.py
│   ├── exporting.py
│   ├── kept.py
│   ├── runner.py
│   ├── settings.py
│   ├── telemetry.py
│   └── tracing
├── sdk
└── tui
```

Nothing but `__init__.py` and `__main__.py` MUST sit at the top. Everything else is one of
the directories above, and a module MUST be inside the one whose question it answers rather
than beside it: a tree whose top is a list of files is one where nothing says which of them
belong together.

`coganchor` MUST be the whole of what humanize knows about driving a coding agent CLI --
what each one is, driving it, which account it runs as, where its turns land, where a turn
goes when the place taking it cannot, what its tokens cost, and the anchor that puts its
work on another machine. It MUST offer that as one capability, so that what is above it
schedules flows and drives nothing: a layer that reached past this to a driver would be a
second answer to a question this one already answers.

`runtime` MUST be what a run is: finding the flow, handing it the agents it declared,
driving it, writing it down as it happens, remembering what a workspace was set up with, and
reading the whole of it back afterwards. It MUST drive no coding agent itself.

Each subdirectory is a library; one with a contract of its own has a SPEC named for it, and
one no file is named for is bound by this one. The modules inside `coganchor` and `runtime`
are specified here, under the path each is written at. None of them MUST have a command
line: `cli` is the whole of it, one module per command that takes a parser of its own, and
it MUST reach a layer only from inside the command carried out in it, so that a command pays
for no layer but its own -- and so that the same package serves as the target half of a
session, where it is the only one installed.

There are four ways in and one thing under them. `sdk` is humanize as one object, and `cli`,
`daemon` and `tui` MUST each be a way of reaching it rather than a second copy of what it
does: a command line reads a line and prints what came of it, a daemon holds a run where a
terminal closing cannot end it, and the interface draws. What two of them would otherwise
each have written MUST be written in `sdk` instead, so that a thing that can be done one way
can be done every way and is refused the same way whichever way it was asked.

No two layers MUST name each other. A pair that does is two things put in one place, not one
thing above another, and is what `tests/test_layering.py` refuses.

Every module MUST be named for what it holds. `coganchor` alone is a name of its own, being
what the anchor inside it is: a program that ships to a target and could be lifted out whole.
What ships MUST be that half alone -- a target runs the serving half and never a coding
agent, so the drivers, the facts about them, the accounts and the prices MUST NOT be in the
bundle carried there.

## `__init__.py`

Expose `home`, and nothing else. A caller names the layer it wants.

## `runtime/settings.py`

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

## `runtime/telemetry.py`

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

## `coganchor/backends.py`

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
- Which one of a backend's variables says where a turn of it actually goes MUST be written
  down here, out of the several base URLs its ways and its ambient names between them list.
  It is a fact about the CLI -- which of them it reads to route a request -- and it is what
  lets `models.py` ask an account's own endpoint what it serves rather than ask a CLI that
  can only answer with the models it shipped with. It MUST be empty for a backend whose
  endpoint's ids are not ids a turn of it could name: one that spells a model `provider/id`
  out of several endpoints at once, or one whose endpoint speaks a protocol of its own.
- What a CLI can be told and what it cannot MUST be written down here rather than on the class
  that drives it -- whether it can be told its agents may not search the web, whether it can
  carry a conversation it is holding into a second one -- so that whatever refuses a flow the
  thing a backend has not got refuses it out of the one place that says what that backend is.
- The efforts MUST be written down, being that backend's own vocabulary rather than a
  catalogue of things that come and go. A rung the backend takes without documenting MUST be
  written down as one, since no listing of the backend's own will ever name it.
- How long a turn of a backend may say nothing before it is worth looking at MUST be written
  down here, and so MUST whether its transport can be put down and started again, whether a
  conversation of its survives that under the id it was opened with, and whether one transport
  serves every conversation with an agent rather than one apiece. They are facts about the CLI
  -- what it streams while it thinks, what it takes on the way back in, what shape it runs in
  -- and a watchdog that hard-coded them would be a second place for them to be wrong.
- Which credentials are the same credential MUST be written down here too, one entry per
  credential holding every name it goes by. A vendor's key is the vendor's rather than the
  CLI's -- an Anthropic key is one whether Claude Code, pi, opencode or mimocode holds it --
  and a CLI that named a vendor's credential after itself named the same thing. Which
  backends read each of them MUST NOT be written down again: it is already written, as what
  each backend's ways ask for and what it says it would take an account from.
- What a CLI says when a turn of it stops, and which kind of failure each of those makes it,
  MUST be written down here too. It is a fact about that CLI, and a regex in whichever driver
  met one first is a fact written down in the last place anybody would look for it. The kinds
  MUST be named here as well, since it is here that the sameness lives: every one of these
  CLIs speaks HTTP to a model provider, so a `429` is a `429` whichever of them was holding
  the socket, and what one says and no other does MUST go on that backend's own profile and be
  read before the shared ones.
- Reading a message MUST be the last thing tried and not the first. A process's exit status
  says on its own that there was nothing to run or that a signal ended it, and a backend that
  named the kind itself MUST be believed over any reading of what it printed.
- A CLI that keeps why a turn stopped somewhere other than the streams it answered on MUST
  have those files written down here, as globs under its home. Antigravity is the one that
  does. Nothing MUST be read from them for a backend that has none.
- The one line that installs each of these MUST be written down here, for the turn that failed
  because there was nothing to run: that line is the whole of what such a turn has to say, and
  a backend nobody has written one for MUST say so in general terms rather than say nothing.

## `coganchor/models.py`

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
- Except where the account points its backend at an endpoint of somebody else's, which the
  backend MUST NOT be asked about: a CLI handed a base URL answers with the models it ships,
  having nothing that goes and looks at the other end, so that answer is wrong the moment it
  is given and a refresh changes nothing. The endpoint MUST be asked instead -- `GET
  {base}/v1/models`, under that account's own credentials -- and what it serves is what a
  turn could name. Which variable carries that endpoint MUST be `backends.py`'s to say, one
  per backend, and MUST be empty for a backend whose endpoint's ids are not ids a turn of it
  could name.
- The backend MUST be asked where there is no such variable set, where the endpoint will not
  answer, and where what came back is not a list of models. An endpoint that is down is one
  to ask again, never a reason to leave an account with no catalogue at all.
- The credential the endpoint is asked under MUST be the account's own, read out of the
  environment a turn of it would run with, and MUST reach nothing but that one request: not
  the catalogue, not a log, not the message raised when the endpoint refuses, and not another
  host. A redirect off the host the account named MUST NOT be followed -- the headers go again
  wherever the request is sent, so following one would hand somebody's key to somewhere the
  account never named, and a catalogue is not worth that.
- It MUST be asked as the account whose it would be: under that provider's own credential
  paths and variables, and without the ones its backend would take another account from --
  which is how a turn of that account is run. That environment MUST be resolved once and read
  by both ways of asking, so that the endpoint asked and the backend started are the same
  account. What is kept MUST be kept per account, two accounts of one CLI being two
  catalogues.
- What is kept for a provider MUST be kept with that provider, so that taking the account
  away takes its catalogue with it. The account nobody chose keeps its own under humanize's
  home.
- Asking MUST NOT happen at a prompt: it is a coding agent starting up, or a request to
  somebody's endpoint, and neither is a thing to do while a sheet is being drawn. `ask` is
  the explicit refresh behind `r` and behind `/providers`, never the drawing of a list.
  Reading what was kept MUST cost one file read and MUST reach nothing.
- An account MUST be asked as soon as it is made, since that is the first moment there is
  anything to ask. A backend that would not answer MUST leave the account made: an account
  whose models are not known yet is one to ask again, not one that failed.
- A model's efforts MUST be its backend's ladder narrowed to the rungs that backend said that
  model takes, in the ladder's own order, and MUST be the whole ladder where it said nothing
  of that model -- a model it says nothing about is one it will take any of them for.
- A catalogue that has never been asked for MUST be empty rather than guessed at.

## `coganchor/prices.py`

```python
SOURCE: str
WHENCE: str
STALE: float


@dataclass(frozen=True, slots=True)
class Price:
    model: str
    provider: str
    per_million: Mapping[str, float]


def where() -> Path: ...
def price(model: str) -> Price | None: ...
def cost(usage: Mapping[str, float], model: str) -> float | None: ...
def money(dollars: float) -> str: ...
def refresh(*, wait: bool = False) -> bool: ...
```

What a token costs in money, so that everywhere tokens are counted can also say what they came
to.

- A unit price MUST NOT be written down here, for the reason a model id MUST NOT be written
  down in `backends.py`: the vendors move them without asking anybody, and a list written into
  this package is wrong the week after it is written. It MUST be fetched from a source that
  keeps them, and what was fetched MUST be kept under humanize's own home.
- Reading a price MUST cost one file read and no network at all. Nothing drawn at a prompt may
  cost the interface its responsiveness, and a bill is drawn beside every token count there is
  -- so `price` and `cost` MUST answer off what was already kept, and fetching MUST happen only
  where somebody asked for it and on a thread of its own.
- Every way the fetch can go wrong MUST leave what was kept still being served. No network, a
  source that is down, a document this cannot read: a price list able to stop a run, or to
  empty itself because somebody's wifi dropped, would be worth less than no price list.
  Fetching MUST be conditional on what is already here, the file being megabytes, and MUST be
  refusable outright by an environment variable -- an air-gapped install and this suite both
  need a humanize that reaches for nothing.
- **A model nobody lists MUST answer nothing rather than nothing spent.** Coverage is a few
  dozen models and humanize drives whatever CLI is installed, so the unlisted model is the
  ordinary case; `$0.00` beside its tokens would be a claim about a bill, and a false one.
  Whatever draws a figure MUST show the tokens alone.
- A price MUST be per kind of token and MUST be applied per kind. An input token and an output
  token of one model differ in price several times over, so a lump of tokens nobody broke down
  is a lump nobody may price, and MUST answer nothing rather than nought. A kind a backend
  counts beside the output rather than inside it MUST be bought as output.
- **Every figure MUST be a floor.** A kind that is not priced MUST add nothing rather than be
  guessed at, and a kind MUST only stand in for another where standing in cannot overstate: a
  cache write is an input token and a surcharge on it, so the input price is a floor on one,
  while a cache read is a tenth of an input token and a turn is mostly cache reads -- pricing
  one as input would put the bill several times over the truth, which is the one direction
  this must never go.
- Matching a humanize model to a listed one MUST be exact once both are stripped of what is
  not the model, and MUST promise no more than that. What is stripped MUST be the things that
  are known not to be the model: the provider, account or gateway route written in front, the
  cloud a route names, the release date or version written behind, and the punctuation two
  spellings disagree about. `claude-opus-5`, `anthropic/claude-opus-5`,
  `azure/anthropic/claude-opus-5`, `aws/anthropic/bedrock-claude-opus-5` and
  `us.anthropic.claude-opus-5-v1:0` are one model and one bill; `claude-haiku-4-5-20251001` is
  the model the source lists as `claude-haiku-4.5`.
- It MUST NOT guess beyond that, and a near miss MUST be a miss. `gpt-5` is not `gpt-5.6-sol`.
  The price of the neighbouring model is a wrong bill rather than an approximate one, and a
  gateway offering hundreds of models against a source listing dozens means most of what runs
  is unmatched -- which MUST read as tokens without a price, never as `$0.00`.
- Where a model is priced in tiers -- by context length, by how long a cache is held -- the
  first the source gives MUST be taken, that being the standard price. Nothing here knows how
  long a prompt was, and the tier above is the dearer one.
- Which version of the source is current MUST be settled by the date on it rather than by
  where it sits in the file. A source that one day appended its snapshots instead of
  prepending them would otherwise have humanize quietly serving three-year-old prices.
- A document that is not priced in dollars per million tokens MUST be refused whole and MUST
  leave what was kept in place. Showing the wrong money is worse than showing none.
- **What this works out is the least authoritative source there is of what a run cost.** It is
  a reckoning humanize made, from somebody else's list price, of tokens it was told about --
  where a backend states a turn's cost in money it is the vendor's own accounting, and MUST be
  believed over this wherever it does. That is the same ordering `tui.md` already holds to for
  the tokens: a backend that says what a turn cost is believed over what its agent was
  configured with, and a source that has seen further is believed over one that has not. This
  is a third source and it goes underneath both. What is drawn MUST therefore read as an
  estimate at list price rather than as a bill: a subscription is not metered by the token at
  all, and a negotiated rate is not the list one. Measured against Claude Code's own
  `total_cost_usd` on one real turn -- 10 in, 448 out, 35,188 cache-written -- this came to
  $0.0462 against its $0.0472, which is 2% low and low in the right direction.

## `runtime/kept.py`

```python
class Runs(NamedTuple):
    spec: str
    anchor: str = ""
    permission: str = ""
    provider: str = ""
    goals: bool = True
    web_search: bool = True


def written(runs: Runs) -> dict[str, Any]: ...
def read_back(held: dict[str, Any], *, goals: bool = True) -> Runs | None: ...
```

What an agent is, written down: a shape and the two directions it goes in, and nothing else.

- An agent MUST be a CLI, an account, a model at an effort and the machine its work lands on.
  What it may do, which goals it may reach for and whether it may search the web MUST be the
  flow's, said where the flow declares the place that agent fills; the skills it carries MUST
  be its CLI's. So there MUST be no store of agents kept under a name and nothing that writes
  one: what is left of an agent is short enough that a template is more to keep in step than
  it saves, and a flow is where an agent belongs anyway.
- It MUST be here rather than beside the interface, and MUST name nothing but `hmz` itself:
  the interface writes an agent down and a command line reads the same file back, and a
  command line that had to load a terminal interface to read a file of six lines would be
  paying for a layer it does not use.
- One agent MUST be written the same way wherever it is written down, so the shape is said
  once. What says nothing MUST be left out: an agent that works here, may do what an agent
  nobody was asked about may do and runs as this machine is signed in is one every field of
  which is that field's own silence. What an older file says about skills MUST be read past:
  they are the CLI's own now, and not a thing an agent is written down with.
- An entry written before there was a setting MUST read as what every agent did then, rather
  than as an entry that is not one: a file humanize wrote is a file humanize reads back.

## `coganchor/fallbacks.py`

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


@dataclass(frozen=True, slots=True)
class Answer:
    fault: str
    about: str
    tries: int = 0
    held: bool = False
    policy: str = ""
    least: float = 0.0
    accounts: bool = True
    reopen: bool = False
    fix: str = ""


ANSWERS: tuple[Answer, ...]


def answers(fault: str) -> Answer: ...
```

The layer between an agent and its accounts: where a turn goes when the place taking it cannot take
it at all, and how many times over it is taken again first. A layer of its own because it is about
neither of the two places on its own, and not `hmz.coganchor.providers` because what it answers is
not an account going down.

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
- What each kind of failure gets MUST be written down here, one row per kind, beside the waits
  it is written in terms of. A place says the shape a turn is retried in and that is the right
  thing for a place to say, but it is one answer and what stopped the turn is not one question:
  a rate limit wants a long wait and then another account, a credential that was refused wants
  no wait at all and the same account chain, a model that has been retired wants neither, and a
  local store that was busy wants three short goes and nothing else. Retried identically --
  which is what every one of them was -- three of those are a flow that makes no progress and
  one is a flow hammering a service that has just asked it to stop.
- A row MUST be able to floor the goes a place asked for and to take them away entirely, and
  MUST NOT cap them otherwise: a floor is what a failure that is worth another go needs, and a
  ceiling would be this file overruling somebody who asked for more. The waits MUST work the
  same way: a row MAY say the shortest any of them may be and MAY put a policy of its own under
  the place's, and MUST NOT shorten one -- the first second of an exponential backoff is a
  second the service has already refused, and a row that cut a place's backoff short would be
  this file overruling somebody in the one direction that hammers whatever has just failed.
- A kind nothing recognised MUST get the answer a turn has always had: the goes the place asked
  for, the place's own wait, and the account chain after them. Whoever is recovering a turn
  MUST read a row rather than a row and a special case, so `answers` MUST answer with that one
  rather than with nothing.
- Which kinds another account answers MUST be written here as well. A model that is gone is
  gone under every account of that CLI, and a CLI that is not installed is not installed under
  any of them, so a turn that met one MUST go straight to the chain of places rather than walk
  every account to be told the same thing again.
- The waits MUST be the ones everybody uses under the names everybody uses them by, and none
  MUST be invented here: no wait, a constant one, a linear one, exponential backoff, that with
  full jitter, and Fibonacci. A name that is not one of them MUST wait the way the default
  does rather than not at all, a setting nobody recognises MUST NOT become a loop that hammers
  whatever has just failed, and no single wait MUST be longer than a turn however far the
  backoff has climbed. The default MUST be exponential backoff with jitter, that being what
  keeps a flow's agents from all coming back on the same second. The time a place was given
  MUST be checked before a wait rather than after it, so that a turn is never started knowing
  it is already spent.
- A place's CLI MUST be read through `hmz.coganchor.backends` rather than matched here: a name no
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

## `runtime/epic.py`

What one run of one flow was, written down as it happens: which flow, on what, by which
agents, and which sessions each of them opened. Not what the sessions said -- the backend's
own log is the turn-by-turn record and this MUST NOT be a second copy of it.

- One epic MUST be one run. It opens when the flow starts and closes when the flow stops,
  however it stops -- finished, failed, or interrupted. A closed epic MUST NOT be reopened.
- One epic MUST be one directory, holding the run's own record, a record per flow the run
  called, and a directory per session any of them opened. A run is more than a list of events
  now -- what its sessions were logged to, what it called, and what a flow that can be picked
  up again left behind -- and all of it is one run's.
- A flow the run called MUST be written down in a record of its own, in that same directory,
  and that record MUST be named for the flow and for that call of it. A flow that called
  another is two flows, and each of them opened sessions, kept its own state and may have
  called a third; a flow called twice is two runs of it, and one record for both would say
  neither. It MUST NOT be another epic: a called flow is part of the run that called it.
- A call MUST be written into the record of whatever called it at both ends, and both ends
  MUST say which record the call was written to. Pairing by the order the lines are in is not
  enough: a flow written as a coroutine may have two calls going at once, and their ends
  interleave.
- A called flow's own record MUST hold what a run's record holds -- what it opened, what it
  called in turn, and how it ended -- and MUST say which record called it, so that a run reads
  back as the shape it ran in rather than as one flat list nothing can be attributed to. How
  it ended MUST be how the call ended: a call that raised inside a run that carried on is a
  call that failed and a run that did not.
- A run of flows calling flows MUST be readable back as the tree it ran as, however deep it
  went and however many of it ran at once: each record under the one that called it, and two
  gathered calls under neither. Read as a list it would be so many things one run did, with
  nothing saying which of them ran under which -- and a recursion five levels deep with
  siblings at every level is exactly the run nobody can hold in their head unaided. Two calls
  going at once MUST be told from one another by the record each was written to rather than by
  the flow's name, which is the same name.
- Each session MUST say which flow opened it and which record it was written into: a flow
  called five times in one run is five calls of it, and the name alone would make one flow of
  the five. What an epic opened MUST be read across every record it holds. One run is one run
  however many flows it took to run it: a trace of it is gathered from what the whole run
  opened, and which flow a session was opened inside is what a record of its own is for.
- A session MUST be written down as whose it was, what took its turns, which account those
  turns ran as and what the backend called it. The backend's own log says only the last of
  those: two agents at one configuration are one agent to anything reading the logs alone,
  and two accounts of one CLI are one account.
- A session forked from another MUST be written down as one, naming the conversation it was
  cut from. The backend's own log shows only a session that began knowing things, so nothing
  but the run can say where it knew them from -- and two branches of one conversation that
  nothing recorded as branches are a run that reads as two agents who happened to agree.
- A session MUST also be given a name of its own, which MUST hold the agent, the CLI, the
  account and the backend's id, and MUST be one directory name. An id alone says nothing
  about whose session it was, and a directory of forty of them is one nobody can read.
- Each session's own logs MUST be pointed at from inside the epic, under that name, by a
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
- Epics MUST be named so that they sort in the order they were run, to the millisecond: what
  a flow is picked up from is the last run of it, and two started inside one second would
  otherwise be ordered at random.

## `runtime/exporting.py`

```python
BUNDLE = "{epic}.epic.tar.gz"
MANIFEST = "manifest.json"
TRANSCRIPT = "transcript.md"
REDACTED = "[redacted]"
STRUCK: tuple[str, ...]


def bundle(
    epic: Path,
    at: str | os.PathLike[str] | None = None,
    *,
    transcript: str | None = None,
) -> tuple[Path, dict[str, Any]]: ...
def logged(epic: Path) -> dict[str, dict[str, Path]]: ...
def plain(said: str, struck: Sequence[str] = ()) -> str: ...
def sized(count: int) -> str: ...
```

One whole run, packaged up to send to somebody who was not there. An epic is written to be
read on the machine that ran it; this is the other reading of the same run, and it is what a
report of a bug is developed against.

- A bundle MUST hold everything the run wrote down about itself -- its own record, a record
  per flow it called, what a resumable flow left behind, the profile of a run that was
  profiled, and every trace gathered of it -- and MUST hold the session logs themselves rather
  than the links pointing at them. `epic.py` points at a backend's own log by a link on
  purpose; a directory of symlinks into somebody's home is an archive with nothing in it the
  moment it leaves their machine, and a bundle that carried the names alone would be a bundle
  the recipient cannot read a single turn out of.
- A session the bundle holds no log for MUST say why. A CLI that keeps its sessions in a
  database of its own writes nothing humanize can read, and an absence that means that reads
  exactly like an absence that means a log was lost -- only one of which is a bug worth
  chasing.
- It MUST be one archive. What is being asked for is a thing to attach to an issue, and a
  directory of forty files is not one.
- **No credential MUST ride along, in any file of it.** What a bundle carries is otherwise the
  user's -- what they typed, what the agents said, what was in the files those agents touched
  -- and that is the opposite of what `telemetry.py` promises about what humanize sends on its
  own initiative, deliberately: this is somebody sending their own run on purpose, and a
  report without the run in it is a report nobody can develop against. A key is nobody's to
  send. So every byte written MUST go through one scrubbing: the value of every variable any
  account here runs a turn with, struck literally, since no pattern knows what somebody
  pasted; the shapes the vendors mint keys in; whatever is signed into a URL, which is where
  `/flowverses` already takes one out; and any value a log named as a token, a secret, a
  key or a password.
- The scrubbing MUST NOT be the one `telemetry.py` does. That module keeps a promise about
  names and counts on humanize's behalf, and this keeps a promise about credentials on the
  user's; one regular expression serving both would be one promise quietly answering for the
  other.
- It MUST NOT strike out what the run is read by. `input_tokens` is how every one of these
  backends writes down what a turn cost, and an account may hold the model to ask for -- Kimi
  Code's does, and half the gateway configurations do. A bundle with the bill taken out of it,
  or with the model struck out because some other account had that name in a variable, is a
  bundle nobody can read.
- It MUST carry a manifest saying what this was: humanize's own version, the flow and how it
  was set up, each agent and what it ran -- CLI, model, effort, and the account by **name**
  only -- the workspace and the commit it is on where it is a repository, and per backend the
  version it says it is and the hash of the executable that took the turns. These CLIs move
  weekly and two installs of one version are not always one program; a run that cannot be
  pinned to a build is a run nobody can repeat.
- The manifest MUST say the shape the run ran in, not only the files it holds: every flow the
  run called at whatever depth, each saying which record called it, and every session saying
  which record it was opened in. A flow called twice is two records and two conversations, and
  a manifest that named only the flow would leave a reader unable to tell which of them a log
  belongs to. Read off the records rather than off the run's own, which says only what it
  called directly -- that would be the first branch of a tree offered as the tree.
- It MUST carry nothing about whoever made it beyond what the run already says. An archive
  records its writer's login name by default, and that is not a thing an export needs to hand
  anybody.
- It MUST be written whole and moved into place under a name nothing else would pick, and MUST
  leave nothing behind if it fails: an archive read while it is being written is one nothing
  can open, and two exports of one run at once must not be two streams into one file.
- It MUST be readable by whoever exported it and by nobody else. What is in it is their
  prompts and their agents' output, and a shared machine is a shared machine.
- Where it lands MUST be where somebody is standing rather than inside humanize's own home the
  way a trace of a run goes. A trace belongs with the run because the sessions it points at
  are already there; a bundle exists in order to leave, and one filed under a directory nobody
  can find is one nobody sends. A file or a directory named outright MUST win.
- It MUST be named for the run rather than for the moment it was written. A run has a name
  already and that name holds the moment it started, so exporting one run twice MUST replace
  the earlier archive rather than leave two nobody can tell apart -- the later one is the
  earlier one plus whatever has happened since.
- A directory holding no run MUST be refused rather than packaged up as an archive of nothing.
- What the manifest says the bundle holds MUST be what actually went in it. What each session
  was logged to MUST therefore be read once and written once: a log that rolls away between the
  reading and the writing would otherwise be named in the manifest and absent from the archive,
  which is the ambiguity above with the two sides swapped. Whatever asked for the bundle MUST
  say what is in it out of the manifest rather than by reading the run again afterwards -- for
  a run that is still going, the second reading is a different answer.

## `runtime/runner.py`

```python
class Runner:
    def __init__(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
    ): ...

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent this drives, the person the flow talks to among them."""

    def run(self, task: str) -> None:
        """Runs the flow, until it returns.

        Args:
            task: What the flow is to have its agents do.
        """


def read_agent(spec: str) -> tuple[str, Profile, str, str, str]:
    """Reads and validates one command-line agent specification."""


def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, bool]:
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
- What each agent may do, whether it has goals and whether it may search the web MUST be
  settled here from what the flow declared, before the first turn and over whatever the agent
  was made with: those three are the flow's and nobody else's, so the line that named a CLI, a
  model, an effort and an account says nothing about them. A backend that cannot be told what
  the flow said MUST be refused as `NotAFlow`, the way one that cannot run a moment is.
- An agent that was not named where it was made MUST take the name the flow gives it, before
  anything is written down about the run: a name is what a trace groups an agent's sessions
  under, and `builder` says what a codename does not. One named already MUST keep that name.
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
- The run MUST be written down as it happens, as an epic: which agents were driven, at what,
  and which sessions each of them opened. The run MUST be over the moment `run` returns,
  however it returns.
- A flow that says it can be picked up MUST be handed a dict as its last argument -- after
  the config, for a flow that takes one -- holding what the run it is being picked up from
  left there. Which run that is MUST be the last run of that flow in this workspace unless
  one is named, so that running a resumable flow again means carrying on: a loop meant to run
  for a week is a loop that will be stopped and started. What it writes MUST be kept in the
  epic of the run doing the writing rather than in the one it was picked up from: a closed
  epic is not reopened, and a run is what that run did.
- Whether a run here is profiled as well as traced MUST be read from this workspace's own
  settings rather than from the epic, which is the run written down rather than the settings
  under it.
- `flow_and_agents` MUST read the same `hmz exec` line the command takes, and MUST be here
  rather than in `cli`: the terminal interface starts a flow from that line and then keeps the
  agents, and a reader that lived in the command line would be one the interface reached up
  into. It MUST NOT load a flow to answer a `--help`, nor refuse a line for a flow it cannot
  read: what a place suggests about goals is a convenience, and reporting the flow is
  `Runner`'s one job.
- An `-a` naming several agents MUST be split into them before any one of them is read, so
  that a line naming three and mistyping one is answered about the one it got wrong rather than
  about all three. What each agent is MUST be read out of `backends`, an agent being a backend
  before it is anything else, so that one reading serves every way in and no layer above has a
  grammar of its own.
- A line that named the place each agent fills MUST be put in the flow's own order here, before
  anything runs, and MUST be refused here where the names are not one apiece of the ones the
  flow declares -- which is the same moment, and for the same reason, as a miscount. It MUST
  ask the flow what it declares only where the line named a place: a line that named none needs
  no answer, and a flow that cannot be read MUST be left to `Runner` to report rather than
  refused twice in two voices.
- A run given a container MUST start one for the whole of it and MUST take it down however the
  run ends, and MUST NOT do either where none was named: reading a flow must pull no image, and
  a run that never starts must leave nothing behind. It is not a thing a command line says --
  where an agent works is the flow's, said where it declares the place -- so what asks for one
  is whatever drove the run from Python.
- What the line says about who is reading the run MUST be read here too, and handed back with
  the rest of it. One grammar reads one line: a flag the command peeled off itself would be a
  flag `hmz exec --help` never listed, and a second reading would be a second way of refusing
  the same mistake. What is done with it is the command line's -- there is nobody at one when
  the interface starts a flow from this same line, so the interface ignores it.

## Commands

```shell
hmz [<command> [<args>...]]
```

- There MUST be one command anybody is offered -- `hmz exec`, which runs a flow in a
  directory -- and everything else humanize keeps MUST be reached at the prompt or through
  `sdk` rather than from a line of its own. What accounts there are, where flows come from,
  where a turn goes when it cannot be taken and what a run left behind are each a sheet at
  that prompt, and each would be a noun to learn here as well: a listing of them is a second
  interface, and the interface is the one with the sheets in it. A line is what a script, a
  CI job and a machine nobody is sitting at have instead of a prompt, and running a flow is
  what those ask for; whatever else one of them needs -- reading a flow for what will not
  run, gathering a trace, packaging a run up -- MUST be asked of `sdk`, which is the same
  object this line holds.
- What humanize spawns for itself MUST be reachable under one further command, `hmz internal`,
  and every command the line routes MUST be in the listing. There MUST be no name that is
  carried out but left out: a program whose help describes less than it runs is one nobody can
  debug from the outside, and each of these is exactly what a person sees in a process table
  when a run has gone wrong. Gathering them under one name is what keeps the listing readable
  -- one entry rather than four, saying what they are and that none of them is a line to type
  -- and is why the answer is a door rather than either four more entries or a trapdoor.
- A line naming no command at all MUST open the terminal interface, which is every command at
  one prompt. There MUST be no command that opens it too: one way in is one way in. A line
  naming something that is not a command MUST be a usage error listing the commands there
  are. Everything after the command name MUST reach that command untouched, `--help`
  included, so that each answers for its own arguments.
- The line that opens the interface MUST say nothing about what to run. Which flow, what
  drives it and what it is set up with MUST be chosen at the prompt, and what was chosen there
  MUST be what the next line opens on -- so a run that is always the same run is set up once
  rather than spelled out again by every line that reads it, and a run already being held here
  is read as it is rather than told something it would have to refuse.
- The interface MUST be opened on a run held apart from the terminal wherever there is a
  terminal to hand over to, so that closing the terminal is not what ends a day's work: a
  line naming no command MUST read whichever run is already being held in this directory, and
  MUST start one where none is.
- With no terminal on both ends -- output going to a file, a suite driving the interface
  itself -- it MUST be opened in this process exactly as it always was. That MUST be read off
  the terminal rather than asked for: holding a run is what makes closing the terminal
  survivable, so it is not a preference anybody expresses on the line. An environment variable
  MUST say the same thing for a whole machine without writing anything down, as it does for
  whether humanize reports its own failures: a scripted install and this suite are one variable
  rather than a flag each of them would have to remember.
  Anything at all that stops a run being held MUST be said and then done without: what is lost
  is being able to walk away from it, which is not a reason to refuse to open.
- `__main__.py` MUST run this same command line, so that `python -m hmz` is `hmz`.

### Who is reading

```python
def terminal(stream: IO[str] | None = None) -> bool: ...


def colours(stream: IO[str] | None = None) -> bool: ...
```

Every command is read twice over: by somebody at a terminal, and by a program. What each of
them is handed MUST be settled in one place rather than command by command.

- Whether escapes may be written MUST be a question about the stream rather than about the
  command, and the three conventions MUST answer it before the stream does: `NO_COLOR` says
  never and MUST win over everything, `TERM=dumb` is a terminal saying it could not read them,
  and `FORCE_COLOR` says to write them into something that is not a terminal -- which is what
  a CI log wants. Where none of them says anything, whether a terminal is reading MUST decide.
- `FORCE_COLOR` MUST NOT make a run believe somebody is watching it. Escapes in a log file are
  one thing; a piped run rendering itself as though it had a terminal to draw on is another,
  so the two questions MUST be asked apart.
- A run that is piped or redirected MUST be written with no escapes in it at all, and MUST
  stay exactly as scriptable as it was: what a turn answered MUST go on reaching stdout, since
  that is where every script written against `hmz exec` reads it.
- Anything a command has to say that is not the answer -- how a run is going, what it is
  working on, a hint -- MUST go to stderr, and `--json` MUST take stdout for the objects: a
  single line that is not JSON is a stream that will not parse, so whatever a flow or a layer
  under it prints MUST be put on stderr for as long as one is being written.
- `--json` MUST be NDJSON -- one object a line, flushed as it is written -- rather than a
  document at the end: a run takes an hour, and a program watching one is watching it as it
  happens. Every object MUST carry the same keys every time, since a schema a program has to
  guess at is not one it can read.
- Nothing written for a program MUST say anything a line written for a person would not. An
  account is still the names of the variables it sets and never their values, and where a
  flowverse came from is still the URL with whatever was signed into it taken out.
- Reaching `rich` MUST be left until escapes are actually wanted: a run written plainly, a
  `--json` run and every listing MUST pay nothing for it.

## `hmz exec`

```shell
hmz exec -f|--flow <flow> -a|--agent <spec>[,<spec>...] [-a ...]
         [-c|--config <config>] [--json] <task>

<spec> := [<name>=]<cli>[@<provider>]/<model>:<effort>
```

Runs a flow in the current directory, on the agents it is given.

Args:

- `-f`, `--flow <flow>[:<name>]`: The flow: one of the ones humanize ships or a flowverse holds,
  by name, or a file of your own, by path. Required. A file that holds several flows MUST be
  said which, after a colon; a flowverse's own MAY be said which, `<flowverse>/<flow>`.
- `-a`, `--agent <spec>[,<spec>...]`: The agents to drive the flow with. One `-a` MAY name
  several, separated by commas, and every `-a` on the line MUST add to the same list in the
  order they were written: what the line names is one list of agents however it was broken up,
  so that a flow of four is one option or four and reads the same either way. A flow that
  drives none -- because the only side it talks to is the person at the prompt -- is named none
  at all: the person is handed over rather than chosen. A line short of an agent the flow does
  drive is caught as every other miscount is, against what the flow declares.
- `-c`, `--config <config>`: A YAML file of what to set the flow up with, one field per line,
  under the names the flow declared. Only for a flow that says it can be set up, and what is in
  it is the flow's own model's to check rather than this line's.
- `--json`: Write the run for a program rather than for a person -- one JSON object on stdout
  for each thing an agent says, as it says it.
- `<task>`: What the flow is to have the agents do, as the text itself.

- A `<spec>` MAY name the place it fills, before an `=`. The names are the fields of the tuple
  of agents the flow declares, so `<name>` MUST be a Python identifier, and naming them MUST be
  all or nothing: either every agent on the line names its place or none does, since an agent
  that names none fills the flow's next place and there is no next place to count while others
  are filled by name. A name the flow does not declare, one given twice, a place left unfilled,
  and a line that names places to a flow that declared a plain tuple MUST each be a usage error
  before any agent has run, saying what the flow does declare. A line that names none of them
  fills the places in the order the flow takes them, which is what every line always did.
- The agent MUST NOT be sayable written out, one `<key>=<value>` to a comma: `=` and `,` are
  how a line says which place an agent fills, so the two spellings cannot both be read, and one
  spelling for one agent is what keeps an `-a` a thing that can be read at a glance. A line
  writing `cli=`, `model=`, `effort=`, `provider=`, `service_tier=` or `config.<key>=` MUST be
  a usage error saying the written-out form is gone and what to write instead. A latency tier
  and a backend-native override are still an agent's to carry: they are set where the agent is
  made -- from the SDK, or by the flow -- rather than on the line that names one.
- `<cli>` MUST be one of `claude`, `codex` and `kimi`, each of which MUST also answer to the
  longer name it is installed under, and `<model>` and `<effort>` MUST be what that CLI is
  asked for. A model MAY hold slashes of its own -- Kimi Code's and opencode's are written
  `provider/id` -- so the CLI MUST be read from the front and the effort from after the last
  colon.
- The CLI MAY be followed by `@<provider>`, which is the account that agent's turns run as: a
  CLI is never spelled with an `@` in it, so the two are told apart wherever an agent is
  written. An `@` naming nothing MUST be a line to correct rather than a line saying nothing.
- What an agent may do and whether it may search the web MUST NOT be sayable here. They are
  things about the work rather than about the agent, so the flow declares them where it
  declares the place, and a line that writes `permission=` or `web_search=` MUST be a usage
  error saying where it is said instead -- refused outright rather than parsed and applied,
  the way a config a flow does not take is refused. An agent is what a line names: a CLI, an
  account, a model at an effort, and which of the flow's places it fills.
- Two agents of one spelling MUST be two agents, so that a flow of an actor and a reviewer at
  one configuration is what it says it is.
- A flow that is not there, has no entry point, does not say how many agents it drives, or
  drives a different number than were given MUST be reported as a usage error, before any
  agent has run. Whatever else a flow does as it is imported is the flow's own, and MUST fail
  as it would anywhere.
- What a run looks like while it happens MUST be drawn from the agents' own event stream --
  the one the interface draws from -- rather than left to each backend teeing its raw progress
  to stderr: one run must read as one run, whichever CLIs it was given. Watching an agent is
  what stops those tees, so the two MUST NOT both be shown.
- It MUST say which agent is taking a turn and in which of its conversations, what the agent
  said, what it ran, what it started under it, what a turn cost when it lands, and -- while a
  terminal is reading -- something that goes on moving: a turn thinks for minutes and says
  nothing for most of them, and a run that looks hung is one somebody kills.
- What a turn cost MUST be said in money as well as in tokens, off `hmz.coganchor.prices`, for the
  reason the interface says it there: nobody is watching a token count for its own sake. A
  model nobody lists MUST show the tokens alone -- `$0.00` beside a turn that spent something
  is a claim about a bill, and a wrong one.
- `--json` MUST write every one of those as one object instead, carrying which agent said it,
  which backend and model it was said on, which conversation, what kind of thing it was, the
  words themselves, what the turn cost, and when. It MUST NOT write anything a terminal needed
  and a program does not.

## `hmz internal`

```shell
hmz internal <command> [<args>...]
```

The door onto what humanize spawns for itself. Behind it are the four lines humanize starts
processes with -- the anchor, the supervisor a turn under an account runs in, and the two
relays a coding agent reaches a flow's callbacks and hooks through -- and nothing else.

- Every one of them MUST be under this one command rather than beside `hmz exec` at the top.
  Four more entries in the top-level listing would read as four more things to do with
  humanize, which is the opposite of what they are: they name no capability a person wants,
  and a listing is read for what there is to do.
- It MUST be one of the commands a listing shows, and what is under it MUST be documented. A
  command nobody can discover is a command nobody can debug, and every one of these is what a
  person finds in a process table, a `ps` line or a backend's error when a run has gone wrong
  -- so hiding them costs exactly the people who most need them named. A listing that leaves
  out half of what a program runs is worse than one with a door marked `internal` on it: the
  first is untrue about the program, and the second is true and says where not to go.
- None of them MUST be a line anybody types by hand. Being listed is documentation of what
  humanize runs, not an invitation: each is a command line because starting a process needs
  one, each takes arguments only humanize knows how to render, and the help of each MUST say
  so.
- Everything after the name of one of them MUST reach it untouched, `--help` included, for
  the reason the top of the line works that way: each answers for its own arguments, and a
  parser here that ate one would be a second spelling of every line humanize renders.
- Reaching one of them MUST cost no module of any of the others, exactly as at the top of the
  line: the door is a lookup and not a layer.

## `hmz internal anchor`

```shell
hmz internal anchor [<options>] <agent> [<args>...]
hmz internal anchor serve --export <virtual>[:<real>] (--stdio | --listen [<host>:]<port>)
```

Runs an agent here whose work lands on another machine, and -- under `serve` -- is the half
that lands it. What each of the two takes is `coganchor`'s and is specified there.

- It MUST be a command of its own because a turn whose work lands elsewhere is a process of
  its own -- one holding a session to a target, with the agent under it. humanize spawns it
  for every such turn, the agent's own configuration rendering the line, and the zipapp
  bootstrapped onto a target runs `hmz internal anchor serve` to answer one. Neither is a line
  anybody types.
- Reaching it MUST load `coganchor` and nothing else of humanize, since `serve` is what runs
  on a target where it is the only layer there is and the architecture is whatever the target
  happens to be. That MUST hold through `internal` as well: the door is what the bundled
  target half is reached through.

## `hmz internal cred`

```shell
hmz internal cred --map <from>=<to> [--map ...] -- <command> [<args>...]
```

Runs a program with some of its paths answered by others, and exits with its status. What a
turn under a provider is spawned as, and what a login run for one is spawned as.

- It MUST be a command of its own rather than something the driver does in this process, for
  the reason `hmz internal anchor` is: the supervisor forks the program and takes the
  process's signal handling with it, which a flow pumping turns from threads of its own cannot
  lend it.
- It MUST be under `internal` rather than at the top of the listing: it is a command line
  because a process is started by one, not because it is a thing anybody types, and what it
  runs is whatever it is given -- an entry beside `hmz exec` would read as humanize offering
  to run something that is not humanize. What it is MUST still be written down, there and in
  the documentation: it is the process a turn under an account actually runs as, so it is the
  name on the failure when an account's credentials were not where it looked.
- A line naming nothing to answer MUST be a usage error: a run with nothing to redirect is a
  supervisor started for no reason.

## `hmz internal tools`

```shell
hmz internal tools --at <socket>
```

Carries the tool protocol between a coding agent and the flow whose callbacks it is: this
process's standard input into the flow's socket, and the flow's answers back out again.

- It MUST be a command of its own for the reason `hmz internal cred` is, the other way round:
  a CLI takes a tool by starting a program, so there has to be a program. It MUST be under
  `internal` with the rest, listed and documented as what it is: the line a backend's own tool
  configuration holds is this one, and somebody reading that configuration has to be able to
  look it up.
- It MUST do nothing but carry lines. The callback belongs in the process the flow is in, and
  anything answered here would be a tool the flow never wrote.
- Both directions MUST be carried at once, and the end of either MUST end the other: a CLI that
  has closed its input must not leave this process reading a socket nobody will write to.
- A socket that is not there MUST be a status rather than a crash: it is a flow that has ended,
  and a CLI reads it as its tools being unavailable rather than as a turn that failed.

## `hmz internal hook`

```shell
hmz internal hook --at <socket>
```

Carries one call of a coding agent's own hook table to the flow whose moment it is, and the
verdict back again. It is what makes a refusal at `PreToolUse` stop the tool rather than
describe one that has already run, and what it serves is specified in `agents.md`.

- It MUST be a command of its own for the reason `hmz internal tools` is: a CLI takes a hook by
  starting a program and waiting for what it says, so there has to be a program. It MUST be
  under `internal` with the rest, listed and documented: it is the line written into a CLI's
  own hook table, it is spawned once per tool call, and it is what shows up when a gate stops
  answering -- all of which is unreadable if the command has no name anybody may look up.
- It MUST do nothing but carry the one call. The hook belongs in the process the flow is in,
  and anything decided here would be a verdict the flow never gave.
- It MUST exit zero whatever the flow said, and MUST NOT exit with the status these CLIs read
  as the hook itself having refused: a relay that could not reach anybody would otherwise be
  refusing on a flow's behalf without having asked it.
- A socket that is not there MUST let the tool through, saying so where a person sees it: it is
  a flow that has ended, and every one of these CLIs shows a hook's error and goes on with the
  turn.
