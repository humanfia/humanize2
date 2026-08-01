# Providers

## File Structure

```
.
├── __init__.py
├── _trace.py
├── login.py
├── redirect.py
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

    @property
    def at(self) -> Path: ...

    def swaps(self) -> tuple[tuple[str, str], ...]: ...

    def command(self, argv: Sequence[str]) -> list[str]: ...
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
- What a provider answers MUST be only the paths `humanize.backends` names as that backend's
  credentials. The sessions, the settings and the skills MUST be the ones the CLI already has,
  so that a turn under a provider still traces, still counts and still loads what is installed.
- `swaps` MUST also answer the same path with the links in it followed, where that is a
  different spelling: a home reached through one is the same file under two names.

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
  cooperate and does not know. The technique MUST be the one `humanize.coganchor` runs a whole
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
def make(cli: str, name: str, way: Way, answers: Mapping[str, str] | None = None) -> Provider: ...


def sign_in(provider: Provider, way: Way, answers: Mapping[str, str] | None = None) -> int: ...
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
