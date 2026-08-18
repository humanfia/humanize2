"""A flow driven by stubs against a clock: the reading only running the file can give.

:mod:`hmz.flows.checking` reads a flow without running it, and some of what a flow is only
running can show -- the annotation built at runtime, the config model declared in a helper,
the loop that looks bounded and is not. This is that second reading. The flow is loaded and
driven for real, in a subprocess of its own, by agents that are stubs: every turn lands at
once, answers deterministically, and costs what the scenario says a turn costs -- so a loop
held to a budget walks to the end of it in milliseconds, and what is being proved is the
flow's own shape rather than any model's mood.

The scenarios are the questions worth asking of a loop. `NEVER_DONE` is the reviewer that
never says the work is done: a flow with a bound of its own still ends, and one without is
caught by the turn cap or killed by the clock -- which is the executable proof that a run of
it can end. `ALWAYS_DONE` is the shortest road through. `SILENT` answers every turn with
nothing, which is what a turn that failed answers, so a flow that reads a field off an
unguarded answer falls over here rather than at hour three.

A subprocess per scenario, because loading a flow means running its file: whatever it does as
it is read -- imports, prints, mistakes -- happens in a process built to be killed, the parent
holds the clock, and nothing of the flow outlives its own proof.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    cast,
    get_args,
    get_origin,
)

from .checking import Finding

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator, Mapping, Sequence

    from pydantic import BaseModel

    from hmz.agents import AgentBase, Event

    from .driving import Place

__all__ = [
    "ALWAYS_DONE",
    "NEVER_DONE",
    "SILENT",
    "Outcome",
    "Proof",
    "Scenario",
    "proved",
]


class Scenario(NamedTuple):
    """One way the world answers a flow, held constant for the length of a proof.

    Attributes:
      name: What the scenario is called, which is what its outcome is filed under.
      verdict: What every boolean field of a shaped answer says -- False is the reviewer
        that never says done -- or None for a turn that answers with nothing at all, which
        is what a failed turn answers.
      answer: What a plain turn answers, and what every string field of a shaped one says.
      climb: What each turn adds to what the agent has spent, in output tokens, so that a
        loop held to a budget walks to the end of it in a handful of turns.
      turns: How many turns the flow may take before it is read as one that does not stop.
      seconds: How long the scenario's process may live before the clock kills it.
    """

    name: str
    verdict: bool | None
    answer: str
    climb: float = 100_000.0
    turns: int = 200
    seconds: float = 60.0


#: The reviewer that never says the work is done. A flow with a bound of its own -- a
#: budget, a cap on the rounds -- still ends here, and one that waits forever on a verdict
#: is caught by the turn cap: the executable proof that a run of it can end.
NEVER_DONE = Scenario("never-done", verdict=False, answer="did some of it")

#: The shortest road through: every verdict is yes, so what is proved is that the flow can
#: end the way it means to.
ALWAYS_DONE = Scenario("always-done", verdict=True, answer="did it")

#: Every turn answers with nothing, which is what a failed turn answers: a flow that reads
#: a field off an answer nobody guarded falls over here rather than hours into a run.
SILENT = Scenario("silent", verdict=None, answer="")


class Outcome(NamedTuple):
    """How one scenario ended.

    Attributes:
      scenario: Which scenario it was.
      finished: Whether the flow ended on its own -- returned, or raised what it meant to.
      turns: How many turns it took, as far as that was counted.
      said: Why it did not finish, for one that did not: the clock, the turn cap, or the
        tail of what it raised. "" for one that did.
    """

    scenario: str
    finished: bool
    turns: int
    said: str


class Proof(NamedTuple):
    """What driving one flow against the scenarios showed.

    Attributes:
      findings: What loading it refused or the live reading found, in the same shape the
        static reading answers with -- `refused-load` for a flow `driving.py` would not
        take, and the config findings only the declared model itself can show.
      outcomes: One per scenario, in the order they were asked.
    """

    findings: tuple[Finding, ...]
    outcomes: tuple[Outcome, ...]


#: How long the load-only proof is given, there being no scenario to say.
_PATIENCE = 60.0

#: What the stubbed flow is driven with. Constant, so a proof is a proof of the flow: what
#: the task says cannot matter to agents that answer the same thing whatever they are told.
_TASK = "the task this proof drives the flow on"


def proved(
    flow: str | os.PathLike[str],
    *,
    name: str = "",
    config: Mapping[str, object] | None = None,
    scenarios: tuple[Scenario, ...] = (NEVER_DONE, ALWAYS_DONE),
) -> Proof:
    """Loads a flow in a subprocess and drives it with stubs, once per scenario.

    Args:
      flow: The flow: its directory, its file, or the name `-f` takes.
      name: Which of the flows the file holds, or "" for the one it holds under its own
        name -- the half after the colon, for whoever has it separately.
      config: What to set the flow up with, read back through the flow's own model exactly
        as a run of it would, or None for a flow left to its defaults.
      scenarios: The worlds to drive it against, each in a process of its own. Empty proves
        only that it loads: the flow is declared and its config model read, and nothing
        takes a turn.

    Returns:
      The findings and one outcome per scenario. A finding is something to fix; an outcome
      that did not finish is a flow that could not end in that world, said with why.
    """
    from . import find, inside

    # Resolved here, where names still mean what the caller meant: the child runs in a
    # scratch directory of its own, against which a relative path names nothing.
    at = find(str(flow))
    wanted = name or inside(str(flow))
    where = Path(at)
    findings: list[Finding] = []
    outcomes: list[Outcome] = []
    seen: set[tuple[str, str]] = set()
    asked: tuple[Scenario | None, ...] = scenarios or (None,)
    for scenario in asked:
        told = _asked(at, wanted, config, scenario)
        if isinstance(told, Outcome):
            outcomes.append(told)
            continue
        for one in told.get("findings", ()):
            key = (str(one["code"]), str(one["said"]))
            if key not in seen:
                seen.add(key)
                severity: Literal["error", "warning"] = (
                    "error" if one["severity"] == "error" else "warning"
                )
                findings.append(Finding(key[0], severity, where, 0, key[1]))
        refused = told.get("refused")
        if refused is not None:
            key = ("refused-load", str(refused))
            if key not in seen:
                seen.add(key)
                findings.append(Finding(key[0], "error", where, 0, key[1]))
            if scenario is not None:
                outcomes.append(
                    Outcome(
                        scenario.name,
                        finished=False,
                        turns=0,
                        said="nothing ran: the flow could not be loaded",
                    )
                )
            continue
        if scenario is not None:
            outcomes.append(
                Outcome(
                    scenario.name,
                    finished=bool(told.get("finished")),
                    turns=int(told.get("turns", 0)),
                    said=str(told.get("said", "")),
                )
            )
    return Proof(tuple(findings), tuple(outcomes))


def _asked(
    flow: str,
    name: str,
    config: Mapping[str, object] | None,
    scenario: Scenario | None,
) -> dict[str, Any] | Outcome:
    """One scenario, asked of a child process holding the clock over it.

    Args:
      flow: The flow, as :func:`proved` was given it.
      name: Which of the file's flows.
      config: What to set it up with, or None.
      scenario: The world to drive it in, or None to only load it.

    Returns:
      What the child answered, or the outcome of a child that could not answer: one the
      clock killed, or one that died without saying why in the one line this reads.
    """
    called = scenario.name if scenario is not None else ""
    spec = json.dumps(
        {
            "name": name,
            "config": dict(config) if config is not None else None,
            "scenario": scenario._asdict() if scenario is not None else None,
        }
    )
    patience = scenario.seconds if scenario is not None else _PATIENCE
    # A scratch directory to work in, taken away with the process: what a flow writes while
    # it is being proved is part of the proof, not part of anybody's repository.
    with tempfile.TemporaryDirectory(prefix="hmz-proving-") as scratch:
        try:
            done = subprocess.run(
                [sys.executable, "-m", "hmz.flows.proving", flow, spec],
                capture_output=True,
                text=True,
                check=False,
                timeout=patience,
                cwd=scratch,
            )
        except subprocess.TimeoutExpired:
            return Outcome(
                called,
                finished=False,
                turns=0,
                said=f"still running after {patience:g}s -- nothing inside the flow "
                "ended it, so the clock did",
            )
    # The last line that is the child's: a flow prints whatever it prints, so the answer is
    # found from the end rather than trusted to be alone.
    for line in reversed(done.stdout.splitlines()):
        try:
            held = json.loads(line)
        except ValueError:
            continue
        if isinstance(held, dict) and "proving" in held:
            return cast("dict[str, Any]", held["proving"])
    tail = "\n".join(done.stderr.strip().splitlines()[-3:])
    return Outcome(
        called,
        finished=False,
        turns=0,
        said=f"the flow's process ended without answering -- {tail or 'and said nothing'}",
    )


# ---------------------------------------------------------------------------------------
# The child: loads the flow, builds the stubs, and drives it. Run as `-m hmz.flows.proving`
# with the flow and the scenario as its two arguments, and answers with one JSON line.
# ---------------------------------------------------------------------------------------


def _rested(seconds: float) -> None:
    """A sleep that has already happened, which is what the stubs' world does with rests.

    Args:
      seconds: How long the flow meant to wait, which the proof does not.
    """
    del seconds


async def _rested_for(seconds: float, result: Any = None) -> Any:
    """The same for a flow that rests the async way, which `asyncio.sleep` is.

    Args:
      seconds: How long the flow meant to wait, which the proof does not.
      result: What `asyncio.sleep` answers with, which it hands back untouched.

    Returns:
      That same thing, at once.
    """
    del seconds
    return result


class _Enough(BaseException):
    """The turn cap, raised past everything a flow catches: a proof is over when it is.

    A `BaseException`, so that a flow's own `except Exception` -- which is a fine thing for
    a loop to write around a turn -- does not swallow the one thing that ends its proof.
    """


class _Steps:
    """The turns taken so far, shared by every stub of one proof."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.taken = 0

    def step(self) -> None:
        """Counts one turn, and ends the proof on the one past the cap."""
        self.taken += 1
        if self.taken > self.cap:
            raise _Enough


def _driven(flow: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Loads one flow and, given a scenario, drives it with stubs to whatever end.

    Args:
      flow: The flow, as the parent was given it.
      spec: The parent's ask: the name inside the file, the config, and the scenario --
        or None for a proof that only loads.

    Returns:
      What the parent folds into the proof: `refused` for a flow that would not load,
      `findings` off the live config model, and how driving it went.
    """
    import asyncio
    import time

    from .driving import NotAFlow, declares, set_up

    # A proof's world sleeps for free. The rest a loop takes between rounds is part of its
    # manners and no part of its shape, and it is the shape on trial: a loop that rests
    # five seconds a round is not five hundred seconds more legal than one that does not.
    # Patched before the flow is even loaded, so a `from time import sleep` reads this one.
    time.sleep = _rested
    # And the other spelling of it: an async flow rests with `asyncio.sleep`, and one left
    # sleeping would be reported as a flow that cannot end when it was only resting.
    asyncio.sleep = _rested_for

    named = f"{flow}:{spec['name']}" if spec["name"] else flow
    scenario = Scenario(**spec["scenario"]) if spec["scenario"] else None
    try:
        run, places, make, setting, mark = declares(named)
    except NotAFlow as refused:
        return {"refused": str(refused)}
    except BaseException as raised:  # noqa: BLE001 -- reported, in a process built for it
        return {"refused": f"the flow's own file raised as it was read -- {raised}"}
    answered: dict[str, Any] = {"findings": _styled(setting)}
    given = None
    if spec["config"] is not None:
        try:
            given = set_up(named, setting, spec["config"])
        except NotAFlow as refused:
            answered["refused"] = str(refused)
            return answered
    if scenario is None:
        return answered
    steps = _Steps(scenario.turns)
    settings = () if setting is None else (given,)
    held: tuple[dict[str, Any], ...] = ({},) if mark.resumable else ()
    try:
        out = run(make(_crewed(places, scenario, steps)), _TASK, *settings, *held)
        if inspect.isawaitable(out):
            import asyncio

            asyncio.run(_awaited(out))
        finished, turns, said = True, steps.taken, ""
    except _Enough:
        finished, turns = False, scenario.turns
        said = (
            f"still going after {scenario.turns} turns -- nothing inside the flow "
            "ended it, and a loop is legal when something inside it can end it"
        )
    except BaseException:  # noqa: BLE001 -- the flow's own crash is the outcome
        import traceback

        tail = traceback.format_exc().strip().splitlines()
        finished, turns, said = False, steps.taken, "\n".join(tail[-3:])
    answered.update(finished=finished, turns=turns, said=said)
    return answered


async def _awaited(out: Any) -> None:
    """One awaitable flow, awaited: what `asyncio.run` takes is a coroutine."""
    await out


def _styled(setting: type[BaseModel] | None) -> list[dict[str, str]]:
    """The config findings only the live model can show, said as the static reading says.

    The model a flow declares may be built anywhere -- a helper module, a call -- and the
    static reading only checks the ones written in plain sight. This is the same two rules
    against the model `declares` actually resolved.

    Args:
      setting: The model, or None for a flow that takes no setting up.

    Returns:
      One finding per thing found, as plain values for the one JSON line home.
    """
    if setting is None:
        return []
    found: list[dict[str, str]] = []
    config = setting.model_config
    if not (config.get("extra") == "forbid" or config.get("frozen") is True):
        found.append(
            {
                "code": "loose-config",
                "severity": "warning",
                "said": "the config takes anything -- set model_config to extra: "
                "forbid or frozen: True, so a setting that is misspelled is refused "
                "rather than quietly ignored",
            }
        )
    for name, field in setting.model_fields.items():
        if not field.description:
            found.append(
                {
                    "code": "unsaid-field",
                    "severity": "warning",
                    "said": f"the config field {name!r} says nothing about itself -- "
                    "give it a Field(description=...), which is what whoever sets the "
                    "flow up is shown",
                }
            )
    return found


def _crewed(
    places: Sequence[Place], scenario: Scenario, steps: _Steps
) -> list[AgentBase]:
    """The stub agents for one flow's places, all of one scenario and one turn count.

    Built inside a function because the drivers are heavy and the parent half of this
    module is imported by `hmz.flows` itself: only a child actually proving a flow pays
    for them.

    The stubs claim every capability there is -- every moment, a goal feature, shapes,
    tools -- because what is being proved is the flow and not the agents: a flow legal on
    the widest backend is refused for a narrower one where the agents are chosen, which is
    `driving.py`'s job and not this one's. Everything else is the real base classes, so
    the hooks a flow hangs fire exactly as they would under a real backend -- a `Stop`
    hook that refuses sends a stub on again, and that continuation is a counted turn.

    Args:
      places: What the flow declared.
      scenario: The world the stubs answer from.
      steps: The shared turn count, whose cap ends a proof nothing else ends.

    Returns:
      One agent per place, the person's included.
    """
    from hmz.agents import (
        AgentBase,
        AgentConfig,
        Event,
        HumanAgent,
        Moment,
        SessionBase,
        Usage,
    )
    from hmz.agents.human import HumanSession

    class StubSession(SessionBase):
        """A turn that lands at once and answers what the scenario says."""

        shapes: ClassVar[bool] = True
        takes_tools: ClassVar[bool] = True

        def _stream(
            self, prompt: str, *, schema: type[BaseModel] | None = None
        ) -> Iterator[Event]:
            del prompt
            steps.step()
            if self._id is None:
                self._adopt(f"stub-{id(self)}-{steps.taken}")
            spent = Usage(output=scenario.climb)
            self._spends(spent)
            yield Event(kind="result", text=_said(schema, scenario), spent=spent)

        def _pursue(self, objective: str) -> str:
            del objective
            steps.step()
            self._spends(Usage(output=scenario.climb))
            return scenario.answer

    class StubAgent(AgentBase):
        """An agent claiming every capability, so only the flow is on trial."""

        moments: ClassVar[frozenset[Moment]] = frozenset(Moment)
        pursues: ClassVar[bool] = True

        def new(self, cwd: str | os.PathLike[str] | None = None) -> StubSession:
            return StubSession(self, cwd)

    class StubTalk(HumanSession):
        """The person's answers, deterministic: the scenario's, not a prompt's."""

        shapes: ClassVar[bool] = True

        def stream(
            self, prompt: str, *, schema: type[BaseModel] | None = None
        ) -> Iterator[Event]:
            # Overridden whole, as the real person's session is: their turn is not one
            # being watched, and not one bracketed by an agent's moments. It still counts
            # against the cap -- a flow that loops on asking forever is a flow that does
            # not stop, whoever it is asking.
            del prompt
            steps.step()
            yield Event(kind="result", text=_said(schema, scenario))

    class StubPerson(HumanAgent):
        """The person at the prompt, answering as the scenario has them answer."""

        def new(self, cwd: str | os.PathLike[str] | None = None) -> StubTalk:
            return StubTalk(self, cwd)

    return [
        StubPerson()
        if place.person
        else StubAgent(AgentConfig(model="stub", effort=""), name=place.name or None)
        for place in places
    ]


def _said(schema: type[BaseModel] | None, scenario: Scenario) -> str:
    """What one stub turn answers with, as the text the base classes read back.

    Args:
      schema: The shape the turn was held to, or None for a plain turn.
      scenario: The world answering.

    Returns:
      The scenario's answer for a plain turn; for a shaped one, the fabricated model as
      its own JSON -- or "", which the base reads back as no answer at all, for the silent
      scenario and for a shape nothing can be fabricated for.
    """
    if schema is None:
        return scenario.answer
    if scenario.verdict is None:
        return ""
    from pydantic import ValidationError

    try:
        return schema.model_validate(_made(schema, scenario)).model_dump_json()
    except ValidationError:
        return ""


def _made(schema: type[BaseModel], scenario: Scenario) -> dict[str, Any]:
    """A shaped answer fabricated field by field, deterministically.

    Every boolean says the scenario's verdict -- which is what makes `NEVER_DONE` the
    reviewer that never says done, whatever the field is called -- and every string says
    its answer. The rest is the quietest legal value: a default where the field has one,
    the first of a literal's few, an empty list, a zero, a nested shape made the same way.

    Args:
      schema: The shape.
      scenario: The world answering.

    Returns:
      The fields, ready to be read back through the model.
    """
    return {
        name: _filled(field.annotation, field, scenario)
        for name, field in schema.model_fields.items()
    }


def _unioned(kind: Any) -> tuple[Any, ...]:
    """One annotation and, for a union, what it is a union of.

    Only a union: the arguments of a `list[str]` are what is inside it, not what the field
    itself may be, and a list of strings answered as one string would be the confusion.
    """
    import types
    import typing

    if get_origin(kind) in (types.UnionType, typing.Union):
        return (kind, *get_args(kind))
    return (kind,)


def _filled(kind: Any, field: Any, scenario: Scenario) -> Any:
    """One field's value, off its annotation.

    Args:
      kind: What the field was annotated with, unions unwrapped as they are met.
      field: The field itself, for the default it may carry.
      scenario: The world answering.

    Returns:
      The value.
    """
    from typing import Annotated

    from pydantic import BaseModel

    if get_origin(kind) is Annotated:
        # The constraints ride along in the field itself; what is answered is the type.
        return _filled(get_args(kind)[0], field, scenario)
    for said in _unioned(kind):
        if said is bool:
            return scenario.verdict
        if said is str:
            return scenario.answer
        if get_origin(said) is Literal:
            return get_args(said)[0]
    if field is not None and not field.is_required():
        return field.get_default(call_default_factory=True)
    for said in _unioned(kind):
        if said in (int, float):
            return 0
        if get_origin(said) in (list, tuple, set, frozenset):
            # As many as the field says it takes at the least, each made the same way:
            # a shape that requires three lanes is answered with three, not refused.
            fewest = 0
            for bound in getattr(field, "metadata", None) or ():
                fewest = max(fewest, getattr(bound, "min_length", 0) or 0)
            inner = next(iter(get_args(said)), None)
            return [_filled(inner, None, scenario) for _ in range(fewest)]
        if get_origin(said) is dict:
            return {}
        if isinstance(said, type) and issubclass(said, BaseModel):
            return _made(said, scenario)
    return None


def _main(argv: list[str]) -> None:
    """The child's whole life: one flow, one spec, one JSON line back."""
    flow, spec = argv
    said = json.dumps({"proving": _driven(flow, json.loads(spec))})
    sys.stdout.write(said + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    _main(sys.argv[1:])
