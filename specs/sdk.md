# SDK

## File Structure

```
.
├── __init__.py
└── daemons.py
```

How a tool that is not humanize reaches humanize. Not a layer humanize is built out of: what
is here is a way in from outside, and what it is a way in to is written in `runtime` and in
`daemon`.

## `__init__.py`

Expose both ways of reaching a run, and every type either hands back: `Hmz`, `Run`,
`Accounts`, `Epics`, `Fallbacks`, `Flows`, `Flowverses` out of `hmz.runtime`, and `Daemons`,
`Daemon`, `Held`, `Session` for a run held apart from a terminal.

- Both ways MUST be offered. `Hmz` is the runtime straight at it, in the process that asked;
  `Daemons` is a run held where a terminal closing cannot end it, reached over the socket
  beside it. A tool given only the first cannot look after a run it did not start, and one
  given only the second cannot run a flow without a daemon to hold it -- and humanize's own
  ways in have both, so a tool with something better in mind than an interface or a command
  line MUST have what it would need to write its own.
- It MUST be the same object humanize itself holds and MUST NOT be a copy of one. What is
  offered here is handed through from the front door it is written behind, so that a tool that
  named this and humanize are holding one class rather than two that agree for now.
- It MUST NOT restate what it hands through. Every answer is written where it is carried out;
  a shell here that did the composing again would be a second answer to a question `runtime`
  already answers, and the two would drift the first time one of them was fixed.
- It MUST be named by no layer. A layer that named this would make the way in from outside a
  seam every way in has to pass through, which is what this stopped being: a rule about how
  humanize is built and a promise to somebody else are two jobs, and one name doing both does
  the promise badly. `tests/test_layering.py` is what refuses it.
- Nothing MUST be loaded until it is asked for. A tool that only lists the places flows come
  from MUST NOT pay for the runs, the accounts and the traces to do it, so every layer MUST be
  reached from inside the call that needs it and never at the top of a module -- and each name
  offered here MUST cost the one module it is written in rather than all of them.
- What is offered MUST be spelled for somebody who does not know how humanize is laid out.
  A name here is a promise; where the thing behind it moves, the name MUST go on working.

## `daemons.py`

```python
class Daemons:
    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
    def all(self) -> list[Daemon]: ...
    def hold(
        self,
        opens: Callable[[Held], object],
        workspace: str | os.PathLike[str] | None = None,
        *,
        columns: int = 0,
        rows: int = 0,
    ) -> Daemon: ...
```

The runs humanize is holding apart from a terminal, as a tool outside reaches one.

- It MUST do none of it. `hmz.daemon` is where a run is held, found and stopped; this is the
  one object those are asked through, so that a tool holds one thing per way in rather than a
  module of functions apiece.
- What a run being held offers MUST be the daemon's own `Daemon` rather than something wrapped
  for out here: a tool that has one holds what humanize holds, and a wrapper would be a second
  list of what can be done to a held run.
- `hold` MUST be told what opens the run rather than what to run. What is held is a callable
  that opens something and returns when it is over, which is what lets a tool hold a flow, an
  interface of its own, or anything else it has written.
