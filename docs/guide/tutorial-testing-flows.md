# 14 · Testing a flow

**Ten minutes.** Drive your flow with something that is not a coding agent, so a test costs
nothing and takes a second.

::: tip Before you start
[Answers in a shape](/guide/tutorial-shapes).
:::

## Step 1 — check it loads and declares what it should

The cheapest test there is, and it catches the mistake everybody makes — an `agents` annotation
that cannot be read at runtime:

```python
from hmz.runner import drives, wanted


def test_it_drives_two() -> None:
    assert drives("pair") == ("actor", "reviewer")


def test_the_builder_must_be_gated() -> None:
    (builder, _) = wanted("pair")
    assert Moment.PERMISSION_REQUEST in builder.moments
```

`drives` gives the names; `wanted` gives one `Place` per agent somebody has to choose, with
`.name`, `.moments`, `.goal` and `.where`.

Put this in CI and a flow that stops loading is a red build rather than a red line at 3am.

## Step 2 — a fake agent

A flow is a function, so drive it with something that is not a coding agent:

```python
from collections.abc import Iterator

from pydantic import BaseModel

from hmz.agents import AgentBase, AgentConfig, Event, SessionBase


class FakeSession(SessionBase):
    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        yield Event(kind="result", text=f"answered: {prompt}")


class FakeAgent(AgentBase):
    def new(self) -> FakeSession:
        return FakeSession(self)


def test_it_runs() -> None:
    from .flows.twice import run

    run((FakeAgent(AgentConfig(model="m", effort="high")),), "the task")
```

`Event(kind="result", …)` is what closes a turn, and it is what calling the session returns.
Exactly one closes a turn.

## Step 3 — a fake that answers differently each time

Most flows are loops with a condition. Make the fake say what drives the branch:

```python
class Scripted(SessionBase):
    """Answers from a list, so a test spells the run out."""

    said: list[str] = []

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        yield Event(kind="result", text=self.said.pop(0) if self.said else "")
```

```python
def test_it_stops_when_the_reviewer_says_done() -> None:
    Scripted.said = ["built it", '{"done": false, "notes": "fix the imports"}',
                     "fixed", '{"done": true, "notes": ""}']
    run(Agents(actor=FakeAgent(...), reviewer=FakeAgent(...)), "the task")
    assert Scripted.said == []          # every answer was used: the loop went round twice
```

## Step 4 — an agent that really runs something

humanize's own suite has a shell-backed agent, so a test spells out exactly what the agent it
stands in for would do:

```python
class ShellSession(CommandSessionBase):
    """Runs the prompt as a shell script."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", prompt], None)


class ShellAgent(AgentBase):
    def new(self, cwd=None) -> ShellSession:
        return ShellSession(self, cwd)
```

Now a test can assert on what the "agent" did to the filesystem:

```python
def test_it_writes_the_file(tmp_path: Path) -> None:
    run((ShellAgent(AgentConfig(model="m", effort="high")),), f"touch {tmp_path / 'done'}")
    assert (tmp_path / "done").exists()
```

That is `tests/stubs.py` in the humanize checkout — worth reading.

## Step 5 — test the parts that are not turns

Most of what goes wrong in a flow is not the model. Pull those parts out as plain functions and
test them normally:

```python
def unfinished(text: str) -> bool:
    return "- [ ]" in text


def test_unfinished() -> None:
    assert unfinished("- [ ] a\n- [x] b")
    assert not unfinished("- [x] a")
```

Then the flow is three lines of glue around things that are already tested — which is the shape to
aim for.

The same goes for a [config model](/guide/tutorial-flow-settings): it is a pydantic model, so test
its validators directly.

```python
import pytest
from pydantic import ValidationError


def test_fast_and_careful_do_not_go_together() -> None:
    with pytest.raises(ValidationError):
        Config(fast=True, careful=True)
```

## Step 6 — testing a hook

A [hook](/guide/tutorial-hooks) is a function from an `Occasion` to a `Verdict | None`. Call it:

```python
from hmz.agents import Moment, Occasion


def test_it_refuses_a_force_push() -> None:
    verdict = no_force_push(Occasion(
        moment=Moment.PERMISSION_REQUEST,
        agent="builder", session="", prompt="", tool="Bash",
        about="git push --force origin main", input={}, said="", again=0,
    ))
    assert verdict is not None and verdict.refused
```

No agent, no backend, no tokens.

## Step 7 — the real thing, deliberately

When you do want a test that drives a real CLI, mark it and keep it out of the default run. That
is what humanize does:

```sh
uv run pytest                       # everything that does not need a real agent
uv run pytest --run-agents          # also drives the real coding agent CLIs
```

## What you now know

- `drives` and `wanted` test the contract without running anything.
- Subclass `SessionBase` and yield a `result` event: that is a whole fake backend.
- `CommandSessionBase` running `sh -c` is a fake that actually does things.
- Hooks and config models are ordinary functions and ordinary models — test them as such.

## Next

[Publish a flowverse](/guide/tutorial-flowverse).
