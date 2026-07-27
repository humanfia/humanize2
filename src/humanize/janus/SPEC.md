# Janus

## File Structure

```
.
├── __init__.py
├── agents
└── runner.py
```

Each subdirectory has a SPEC of its own.

## `__init__.py`

Expose `Runner`, `NotAFlow`, and everything `agents` exposes.

## `runner.py`

```python
class NotAFlow(ValueError): ...


def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]:
    """What the flow calls each agent it drives, in the order it takes them."""


class Runner:
    def __init__(self, flow: str | os.PathLike[str], agents: Sequence[AgentBase]): ...

    def run(self, task: str) -> None:
        """Runs the flow, until it returns.

        Args:
            task: What the flow is to have its agents do.
        """
```

- A flow MUST be a Python file whose entry point is `run(agents: tuple[...], task: str)`, and
  that tuple MUST be of a fixed length, which is how many agents the flow drives: it is the one
  thing about a flow a command line running it cannot otherwise know. It MUST be readable where
  the flow runs rather than only where a type checker looks, since a count nothing can read
  back is not one a command line can be held to.
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
