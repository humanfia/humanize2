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
- `__init__` MUST load the flow and MUST raise `NotAFlow` unless the file is there and has
  such an entry point, declaring as many agents as it was given, so that a flow started with
  the wrong number of them fails before its first turn rather than partway through a loop.
- Whatever the flow itself raises as it is loaded MUST be left alone, so that a flow whose own
  setup fails is not answered with a command line to correct.
- `run` MUST call the entry point with the agents as a tuple, in the order they were given, and
  the task.
