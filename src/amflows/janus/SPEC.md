# Janus

## File Structure

```
.
├── __init__.py
├── __main__.py
├── agents
├── cli.py
├── isolation
└── runner.py
```

Each subdirectory has a SPEC of its own.

## `__init__.py`

Expose `Runner`, `NotAFlow`, and everything `agents` exposes.

## Commands

```shell
amflows run -f|--flow <flow> -a|--agents <backend>/<model>/<effort>[,<backend>/<model>/<effort>...] <task>
```

Runs a flow in the current directory, on the agents it is given.

Args:

- `-f`, `--flow <flow>`: The Python file the flow is written in. Required.
- `-a`, `--agents <backend>/<model>/<effort>[,...]`: The agents to drive the flow with, comma
  separated and repeatable, in the order the flow takes them. Required.
- `<task>`: What the flow is to have the agents do, as the text itself.

- `<backend>` MUST be one of `claude`, `codex` and `kimi`, and `<model>` and `<effort>` MUST be
  what that backend is asked for. A model MAY hold slashes of its own -- Kimi Code's are
  `kimi-code/k3` -- so the backend MUST be read from the front and the effort from the back.
- Two agents of one spelling MUST be two agents, so that a flow of an actor and a reviewer at
  one configuration is what it says it is.
- A flow that is not there, has no entry point, does not say how many agents it drives, or
  drives a different number than were given MUST be reported as a usage error, before any
  agent has run. Whatever else a flow does as it is imported is the flow's own, and MUST fail
  as it would anywhere.
- `__main__.py` MUST run this same command line, so that `python -m amflows.janus` is
  `amflows run`.

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
