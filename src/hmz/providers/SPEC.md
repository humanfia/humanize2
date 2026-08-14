# Providers

## File Structure

```
.
├── __init__.py
├── _trace.py
├── login.py
├── redirect.py
├── retry.py
└── store.py
```

Which account a coding agent runs as, kept apart from which CLI it is. A CLI signs in once and
every one of them started on this machine is whoever is signed in there, so a flow that drives
two agents of one CLI as two accounts has two accounts wanting one directory. A provider is the
second directory.

## `__init__.py`

Expose `Provider`, `ENV`, and the store: `providers`, `find`, `add`, `remove`, `ways`, `where`,
`ready`, `environ`, `env_of` and `filled`.

## `store.py`

```python
@dataclass(frozen=True, slots=True)
class Provider:
    cli: str
    name: str
    way: str
    env: Mapping[str, str]
    args: tuple[str, ...]
    made: str
    fallback: str
    retries: int
    policy: str
    timeout: float

    @property
    def at(self) -> Path: ...

    def swaps(self) -> tuple[tuple[str, str], ...]: ...

    def command(self, argv: Sequence[str]) -> list[str]: ...


def chain(provider: Provider) -> list[Provider]: ...


def alone(cli: str) -> Path: ...


def points(cli: str, name: str, at: str) -> bool: ...


def retrying(
    cli: str, name: str, retries: int, policy: str, timeout: float
) -> bool: ...
```

- One provider MUST be one directory, under `~/.humanize/providers/<cli>/<name>/`, holding what
  it was made by and what a turn under it runs with, and beside those the files the CLI itself
  writes when it signs in. The files MUST keep the names that CLI gave them, under `home/` for
  the ones inside its own directory and `user/` for the ones outside it: it is the CLI that
  wrote them, and it is the CLI that will read them back.
- A name MUST be one path component of letters, digits, dot, dash and underscore. A name that
  could climb out of the directory it names MUST be refused wherever it is given, and a
  directory under a name no provider could have MUST NOT be listed as one: what is listed is
  what can be run.
- The directory MUST be this user's alone, every level of it, and the file it is written down
  in MUST be too: it holds real credentials.
- What a provider answers MUST be only the paths `hmz.backends` names as that backend's
  credentials. The sessions, the settings and the skills MUST be the ones the CLI already has,
  so that a turn under a provider still traces, still counts and still loads what is installed.
- `swaps` MUST also answer the same path with the links in it followed, where that is a
  different spelling: a home reached through one is the same file under two names.
- The account this machine is already signed into MUST be an account here too, named `""` --
  which is what `AgentConfig.provider` and `Runs.provider` already call it -- and MUST be
  answered by `find` for every backend, whether or not anything has been written down about
  it. It is the CLI as whoever is at this machine runs it: humanize did not make it, keeps no
  credentials for it, cannot sign it in and cannot take it away, so the only things written
  down about it are what it does when it fails. It MUST NOT be one of the accounts `providers`
  lists -- those are the ones somebody made -- and `where` MUST go on refusing the name, since
  it is not a directory.
- What is written down about it MUST be kept under humanize's own home, one file per backend,
  and MUST NOT be kept in the tree of accounts humanize made: taking every account of a
  backend away MUST NOT leave a file behind among them, and MUST NOT take this with it.
- It MUST answer no swaps and no variables, so that a turn under it is the turn an agent with
  no account has always taken: nothing added to the environment, nothing taken out of it, no
  path answered by another and no supervisor at all.
- An account MUST be able to say which other backends could be run as it, and MUST be
  copyable to one. A vendor's credential is the vendor's rather than the CLI's, so an account
  made for one backend is often an account several others could be run as -- and making the
  same key four times by hand is four places to correct when it is rotated. Which backends
  those are MUST be worked out from what each of them reads rather than written down again.
- Such a copy MUST be written down under the same name and MUST write over one already there,
  that being what makes it a way of correcting several at once. It MUST be spelled as the
  backend it is copied to reads it, and MUST say it was made by that backend's own way where
  one asks for exactly those and by variables of your own where none does.
- An account that is not variables at all MUST be copyable nowhere: a subscription signed
  into writes the CLI's own credential store, in that CLI's own format, and nothing else
  reads it. So MUST one holding a credential the other backend has no name for -- every part
  of an account has to travel, or the account does not.
- Where a turn goes when an account fails MUST be said on the account rather than on the
  agent: it is the account that goes down, and whichever agent was running under one when it
  did is the agent that needs somewhere else to run. It MUST be the name of another account of
  that backend rather than a mark, so that each account names the next and what a turn walks
  is a chain -- a subscription that runs out falling to a key, and a key that is refused
  falling to a gateway.
- It MUST stay the account's, and MUST NOT be widened to cover the agent that has nowhere left
  to run at all -- a model retired, a CLI that will not start, a rate limit on the whole
  account rather than one request. None of those is answered by another account of that
  backend, what answers them is another agent entirely, and that is `hmz.fallbacks`. The two
  answer two failures, and one of them keeps the conversation where the other cannot.
- A chain MUST be walked inside the session that was running: the conversation is the
  backend's own and is named by an id, so it carries on under the next account rather than
  being handed back to the flow as a failure. An agent that has moved MUST stay moved -- the
  account that went down is not one to try again each turn.
- A chain that comes round on itself MUST end at the second sight of an account, and one
  naming an account that is not there MUST end there: either would otherwise be a run that
  never stopped. A name that would point at itself, or at an account of that backend there is
  none of, MUST be refused where it is written rather than found by the turn that needed it.
- A chain MAY begin at the account this machine is signed into, which is what gives an agent
  nobody configured with an account a chain at all. It MUST NOT end there: `""` in the
  fallback position is the end of the line, and an agent that is to try that account is an
  agent given no account, which is where its chain already starts.
- An account MUST also say how a turn under it is tried again before the chain moves on: how
  many times over, how long to wait between tries and how long the whole of it may go on for.
  Nothing MUST be retried by default -- a turn is taken once, as it always was -- since a
  prompt the model refused is the same refusal every time and only the caller knows which of
  its accounts fails the other way.
- The waits MUST be the ones everybody uses under the names everybody uses them by, and none
  MUST be invented here. The time an account was given MUST be checked before a wait rather
  than after it, so that a turn is never started knowing it is already spent.

## `redirect.py` / `_trace.py`

```python
@dataclass(frozen=True, slots=True)
class Swaps:
    pairs: tuple[tuple[str, str], ...] = ()

    def swap(self, path: str) -> str | None: ...


def command(swaps: Iterable[tuple[str, str]], argv: Sequence[str]) -> list[str]: ...


def run(swaps: Swaps, argv: Sequence[str]) -> int: ...
```

- A turn under a provider MUST be run with the paths that backend keeps its credentials at
  answered by the provider's own, and MUST be told nothing else: the CLI is not asked to
  cooperate and does not know. The technique MUST be the one `hmz.coganchor` runs a whole
  session under -- a seccomp filter over the syscalls that name a path, and a supervisor that
  rewrites the path an argument points at.
- Three shapes MUST be answered: the file itself, everything under it where it names a
  directory, and anything beside it under the same name and another suffix. The last is not a
  nicety: these CLIs rotate a token by writing `.tmp` and renaming it over, and a temp file
  left unanswered puts the new token in the store being redirected away from.
- A path that is answered but cannot be rewritten MUST fail the syscall rather than run against
  the path it named. A run that cannot be supervised at all MUST be refused rather than run
  unsupervised. A turn taken as the wrong account is worse than a turn that did not run.
- The supervisor MUST be spawned rather than called in this process, for the reason an anchored
  turn is: it forks the agent and takes the process's signal handling with it, which a flow
  pumping turns from threads of its own cannot lend it. A signal aimed at it MUST reach the
  program under it, so that a session taken down takes its agent down.
- A provider that answers no path MUST cost no supervisor: one that is only variables MUST run
  the backend's own command line unchanged.
- Two supervisors MUST NOT be nested -- a process has one tracer -- so a turn that is also
  anchored MUST hand its swaps to the anchor instead of wrapping it.

## `login.py`

```python
def make(
    cli: str, name: str, way: Way, answers: Mapping[str, str] | None = None
) -> Provider: ...


def sign_in(
    provider: Provider, way: Way, answers: Mapping[str, str] | None = None
) -> int: ...
```

- A CLI's own login MUST be what performs that CLI's login. It is a browser opened, a code read
  out, a token exchanged and refreshed on a schedule nobody else knows, so it MUST be run --
  its own command, on this terminal, under the provider's paths -- rather than reimplemented.
  What it writes when it succeeds is the provider, and it is the CLI that wrote it.
- A way that is only answers MUST be written down instead, as the variables that backend reads
  them under. An answer a way says is not kept MUST NOT be kept: a key read off stdin by the
  CLI's own login ends up inside that CLI's store, and a second copy of it in an environment
  would be a second place to leak it.
- Every place a credential of a provider will land MUST exist before anything writes one: a CLI
  writing its credentials file expects the directory it keeps its own in to be there.
- Nothing here MUST print a secret. What was typed MUST NOT be echoed, and what is shown of a
  provider MUST be the names of the variables it sets and never their values.

## `retry.py`

```python
@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    about: str


POLICIES: tuple[Policy, ...]


def waits(policy: str, attempt: int, base: float = BASE) -> float: ...
```

- What each policy is MUST be written down once, here, and MUST be the shapes every one of
  these services documents: no wait, a constant one, a linear one, exponential backoff, that
  with full jitter, and Fibonacci. A name that is not one of them MUST wait the way the
  default does rather than not at all: a setting nobody recognises MUST NOT become a loop that
  hammers whatever has just failed.
- No single wait MUST be longer than a turn, however far the backoff has climbed.
- The default MUST be exponential backoff with jitter, that being what keeps a flow's agents
  from all coming back on the same second.
