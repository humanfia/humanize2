# Flows

## File Structure

```
.
├── __init__.py
├── builtin
└── verses.py
```

What a flow is called, where it is found, and which of the ones a file holds was asked for.
Nothing here runs one: `hmz.runner` does that, and reads a name through this.

## `builtin/`

The flows humanize itself ships: a directory of `.py` files and nothing else.

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


class Offer(NamedTuple):
    whose: str
    name: str
    about: str = ""


def flow[**P, T](
    call: Callable[P, T] | None = None, /, *, name: str = "", about: str = ""
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...


def loaded(where_: str | os.PathLike[str]) -> dict[str, Any]: ...


def held(where_: str | os.PathLike[str]) -> list[Flow]: ...


def offers(one: Flowverse) -> list[Offer]: ...


def found() -> list[Offer]: ...


def find(named_: str) -> str: ...


def inside(named_: str) -> str: ...


def about(named_: str) -> str: ...
```

- A flow MUST be a function marked with `flow`, and nothing else MUST be one: a file is read by
  running it, and which of the functions it leaves behind is a flow is the file's to say rather
  than something to read off a name. One file MAY hold several: `flow` with no name MUST be the
  flow that file holds under its own name, and `flow(name=...)` MUST be one of its own, called
  `<file>:<name>` -- so that three phases of one thing are one thing to write and three to run,
  each asking only for the agents it drives and only for the settings it takes.
- `flow` MUST mark rather than wrap. A flow is called the way it always was, and a decorator
  between the flow and whatever reads its arguments would be a decorator that has to answer for
  them. What it marks with MUST travel on the function, since a file is read by running it.
- A name MUST be what the mark was told and nothing else: a name written down where a flow is
  run -- a command line, a settings file, another flow asking for this one -- MUST NOT change
  under whoever renames the function. A file that marks two flows with one name MUST answer
  with the first of them, that being a file to correct rather than a choice to make at random.
- What a flow says about itself MUST be the first line of its docstring where the decorator was
  not told one, and for a file that is one flow MUST fall back to the file's own docstring: a
  file that is one flow is documented as that flow.
- A flow MUST be found by name: the ones humanize ships and the ones a flowverse holds by a
  bare name, one of yours by its path. Nearest MUST win -- this project's flows, then yours,
  then whatever there is to run -- so that a project may mean its own `chat` by `chat`. A name
  qualified by a flowverse MUST be that flowverse's, and MUST NOT be stood in for.
- A file MUST be run to be read, with its own directory importable while it runs and only
  while: a flowverse is a directory of flows and whatever they import beside them, and what a
  flow imports is not something the rest of the process should be able to.
- Reading what a file holds MUST answer with nothing for a file that will not run: it is asked
  while a list is being drawn, and a file that will not import is one line of that list rather
  than the end of it.
- A file that runs and holds no flow MUST NOT be offered as one -- a directory of flows holds
  what they import and what sets their tests up -- but one that will not run MUST be, under the
  name it would have had: it is a flow somebody named, and saying so where it is picked beats
  hiding it.
- What one flowverse offers MUST be worked out in `offers` and nowhere else, and `found` MUST
  be that asked of each flowverse in turn. Anything wanting a single flowverse's flows MUST ask
  it too rather than building a name from a filename: a file may hold several flows and the file
  beside it none, so a name spelled out anywhere else is a name `-f` would refuse -- and two
  places deciding what a flow is called is two places to drift.

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


def holds(one: Flowverse) -> Path: ...


def add(url: str, name: str = "") -> Flowverse: ...


def fetch(name: str) -> Flowverse: ...


def remove(name: str) -> bool: ...


def flows(one: Flowverse) -> list[str]: ...
```

- A flowverse MUST be a git repository with a `flows/` directory in it, cloned into
  `~/.humanize/flowverses/<name>/`, and every flow in it MUST be offered under that name. A
  file whose name starts with an underscore MUST NOT be one of them: it is what the flows
  beside it import.
- Only that directory MUST be read for flows, and a fetched flowverse with none MUST hold
  none. A repository is a repository -- a README, a pyproject, a test suite, whatever sets the
  tests up -- and reading a flow means running it, so what is run MUST be what somebody put
  where the flows go rather than every `.py` file that came down with it.
- Where the flows of one are MUST be worked out in one place, `builtin`'s reading of its own
  directory included: everything that goes looking for a flow asks that one place, so an
  exception written down once is an exception rather than a rule to remember.
- Two MUST always be listed: `builtin`, which is the package's own and is fetched from nowhere,
  and `official`, which is humanize's repository of the rest. Neither MUST be removable, and
  `official` MUST be listed whether or not it has been fetched -- a list that only mentioned it
  once somebody had thought to add it would be a list that hid what there is to run.
- A name MUST be one directory name, and one that could climb out of the directory they are
  kept in MUST be refused wherever it is given.
- Neither of the two that are always listed MUST be a name a flowverse can be added under.
  Cloned into `builtin` a repository would be in nobody's list, since that name is skipped when
  they are listed; cloned into `official` it would be shown against humanize's own URL. Both
  MUST be refused where the name is given rather than discovered afterwards.
- Fetching one again MUST take what the repository says now rather than merge into it: a
  flowverse is a copy of somebody else's repository, not a branch of your own, and a merge
  nobody asked for is a fetch that fails the next time it is run.
- A fetch that failed MUST leave the list as it was and say what git said. Nothing here MUST
  wait on the network without a limit -- and since a clone called off for reaching that limit
  is killed rather than allowed to fail, what it had written by then MUST be taken away here:
  git tidies up after its own failures and cannot tidy up after being killed, and a name held
  by a flowverse that is not there is a name that cannot be used again.
- Where a flowverse came from MUST be read without interpolation. A `%` in a URL is ordinary --
  a percent-encoded password, or a path with one in it -- and reading it as the start of a
  substitution would raise where every listing of the flowverses passes.
