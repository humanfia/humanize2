# TUI

## File Structure

```
.
├── __init__.py
├── app.py
├── form.py
└── monitor.py
```

## `__init__.py`

Expose `Amflows`.

## `app.py`

```python
class Amflows(App[None]):
    def __init__(self) -> None: ...
```

The terminal interface, which `amflows` with no command opens. It is a coding agent's own
terminal with a flow underneath: laid out as a transcript, a multi-line editor, and a status
line, with what the flow is doing beside the transcript.

- The editor MUST mean both things at once: a line beginning with `/` is a command, and any
  other line is said to the agent working right now, through `SessionBase.interject`, so that
  a turn already under way takes it into account rather than being restarted with it.
- Enter MUST send and `ctrl+j` MUST break the line, so that a long prompt can be written.
- A half-typed command MUST offer the rest of itself, greyed in after the cursor, and tab
  MUST take it. What is offered MUST be the commands there actually are, and MUST be
  reconsidered when the cursor moves: an offer made at the end of a line MUST NOT still stand
  once the cursor is back in the middle of it.
- A typed line MUST reach the agent that has a turn open, not whichever was named last: an
  agent between turns may still be holding a session that would take it silently.
- Every command of the command line MUST be reachable, and MUST be reached by carrying out
  that same command rather than by a second implementation of it. A command named with no
  arguments MUST be filled in rather than typed.
- A turn MUST be shown as it happens: which agent is taking it, each tool it uses as one
  compact row, and what it says. It MUST be shown once -- a backend teeing to stderr for the
  benefit of a plain terminal MUST NOT also be shown here.
- A line that cannot be carried out MUST be shown and MUST leave the interface up. Only
  `/quit` and the quit binding close it.

## `monitor.py`

```python
@dataclass(frozen=True, slots=True)
class Spend:
    model: str
    tokens: int
    rate: float


@dataclass
class Monitor:
    def begins(self, agent: str, model: str) -> None: ...
    def ends(self, agent: str) -> None: ...
    def spend(
        self,
        agent: str,
        tokens: int,
        model: str | None = None,
        now: float | None = None,
    ) -> None: ...
    def spending(self, now: float | None = None) -> list[Spend]: ...
    def now_working(self) -> list[str]: ...
    def graph(self) -> list[str]: ...
```

What a flow is doing, kept from the turns going past -- which is the only place it is visible,
a flow being a Python file that may branch any way it likes.

- MUST be written from `AgentBase.watch`, and MUST NOT ask anything of the flow.
- Every read and every write MUST hold the lock: the turns are on threads of their own and
  the interface reads while they run.
- `graph` MUST report every agent the flow has run, marking whichever are working, and every
  handover between them with how often it happened: that directed graph is the shape of the
  run.
- `spending` MUST be per model rather than per agent, since two agents at one model are one
  bill, and MUST report a rate over a recent window only -- a flow that has stopped reads as
  stopped rather than as whatever it once averaged.
- A backend that says what a turn cost MUST be believed over what its agent was configured
  with: a turn that reached for a sub-agent spent it on that model.

## `form.py`

```python
@dataclass(frozen=True, slots=True)
class Field:
    name: str
    flag: str = ""
    hint: str = ""
    value: str = ""
    choices: Sequence[str] = ()
    repeats: bool = False


class Form(ModalScreen[list[str] | None]):
    def __init__(self, command: str, fields: Iterable[Field]): ...
```

A command filled in rather than typed.

- MUST answer with the argument list the command line would have taken, or `None` if it was
  dismissed, so that there is one command underneath either way.
- A field left empty MUST reach the command line as nothing at all.
- Offering a choice MUST NOT cost the interface its responsiveness: the flows offered by
  `/run` are found by walking this directory, and a checkout with a virtualenv in it holds
  thousands of Python files that are not flows.
