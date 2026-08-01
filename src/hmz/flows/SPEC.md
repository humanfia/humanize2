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

The flows humanize itself ships: a directory of `.py` files and nothing else, which is what
every flowverse is.

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


def found() -> list[Offer]: ...


def find(named_: str) -> str: ...


def inside(named_: str) -> str: ...


def about(named_: str) -> str: ...
```

- One file MAY hold several flows. A file with a `run` in it MUST be one flow under the file's
  own name, which is what every flow was; a function marked with `flow` MUST be one of its own,
  called `<file>:<name>`, so that three phases of one thing are one thing to write and three to
  run -- each asking only for the agents it drives and only for the settings it takes.
- `flow` MUST mark rather than wrap. A flow is called the way it always was, and a decorator
  between the flow and whatever reads its arguments would be a decorator that has to answer for
  them. What it marks with MUST travel on the function, since a file is read by running it.
- A name MUST default to the function's own with its underscores turned into dashes, which is
  how these read on a command line, and `name=` MUST say otherwise.
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


def add(url: str, name: str = "") -> Flowverse: ...


def fetch(name: str) -> Flowverse: ...


def remove(name: str) -> bool: ...


def flows(one: Flowverse) -> list[str]: ...
```

- A flowverse MUST be a git repository of flows, cloned into `~/.humanize/flowverses/<name>/`,
  and every flow in it MUST be offered under that name. A file whose name starts with an
  underscore MUST NOT be one of them: it is what the flows beside it import.
- Two MUST always be listed: `builtin`, which is the package's own and is fetched from nowhere,
  and `official`, which is humanize's repository of the rest. Neither MUST be removable, and
  `official` MUST be listed whether or not it has been fetched -- a list that only mentioned it
  once somebody had thought to add it would be a list that hid what there is to run.
- A name MUST be one directory name, and one that could climb out of the directory they are
  kept in MUST be refused wherever it is given.
- Fetching one again MUST take what the repository says now rather than merge into it: a
  flowverse is a copy of somebody else's repository, not a branch of your own, and a merge
  nobody asked for is a fetch that fails the next time it is run.
- A fetch that failed MUST leave the list as it was and say what git said. Nothing here MUST
  wait on the network without a limit.
