"""A flow that says what it can be set up with, and what is done with what it says.

The third argument of `run` is the whole of it: annotated with a pydantic model, the flow is
one that can be configured, and the model is what asks. A flow without one is every flow
written before there was such a thing, and is called with two arguments as it always was.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, Field

from hmz.agents import AgentConfig, CodexAgentConfig
from hmz.runner import (
    NotAFlow,
    Runner,
    configures,
    flow_and_agents,
    set_up_from,
)
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that can be set up, and writes down what it was set up with.
SETTABLE = '''
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from hmz.agents import AgentBase
from hmz.flows import flow


class Config(BaseModel):
    """What this flow takes."""

    loud: bool = Field(default=False, description="say it twice")
    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")


@flow
def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps({"task": task, "config": None if config is None else config.model_dump()})
    )
'''

#: The same flow, taking nothing at all, which is what a flow used to be.
PLAIN = """
import json
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(json.dumps({"task": task}))
"""

#: A flow whose third argument is not a model, which is a flow that takes no setting up.
NOT_A_MODEL = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str, config: str = "") -> None:
    pass
"""


def _flow(tmp_path: Path, source: str) -> Path:
    """Writes a flow out and answers with its path."""
    where = tmp_path / "flow.py"
    where.write_text(source)
    return where


def test_a_flow_says_what_it_can_be_set_up_with(tmp_path: Path) -> None:
    """The model is read off the annotation, without the flow being run."""
    model = configures(_flow(tmp_path, SETTABLE))

    assert model is not None
    assert set(model.model_fields) == {"loud", "rounds", "mode"}
    assert model.model_fields["rounds"].description == "how many times round"


@pytest.mark.parametrize("source", [PLAIN, NOT_A_MODEL])
def test_a_flow_that_takes_no_setting_up_says_so(tmp_path: Path, source: str) -> None:
    """Two arguments, or a third that is not a model, is a flow with nothing to ask about."""
    assert configures(_flow(tmp_path, source)) is None


def test_what_it_was_set_up_with_reaches_the_entry_point(tmp_path: Path) -> None:
    """The instance the runner was given is the one the flow is called with."""
    where = _flow(tmp_path, SETTABLE)
    model = configures(where)
    assert model is not None

    Runner(where, [ShellAgent(CONFIG)], model(loud=True, rounds=7)).run("go")

    said = json.loads(where.with_suffix(".json").read_text())
    assert said["config"] == {"loud": True, "rounds": 7, "mode": "fast"}


def test_a_flow_left_alone_is_called_with_none(tmp_path: Path) -> None:
    """Which is what the flow's own default means, and is the run nobody set up."""
    where = _flow(tmp_path, SETTABLE)

    Runner(where, [ShellAgent(CONFIG)]).run("go")

    assert json.loads(where.with_suffix(".json").read_text())["config"] is None


def test_a_flow_that_takes_nothing_is_called_as_it_always_was(tmp_path: Path) -> None:
    """No third argument is passed, so every flow written before this still runs."""
    where = _flow(tmp_path, PLAIN)

    Runner(where, [ShellAgent(CONFIG)]).run("go")

    assert json.loads(where.with_suffix(".json").read_text()) == {"task": "go"}


def test_being_set_up_with_something_else_is_refused_before_anything_runs(
    tmp_path: Path,
) -> None:
    """A config of the wrong model is a caller to correct, not a flow to start."""

    class Other(BaseModel):
        wrong: bool = Field(default=True, description="not this flow's")

    where = _flow(tmp_path, SETTABLE)

    with pytest.raises(NotAFlow, match="the flow takes a Config"):
        Runner(where, [ShellAgent(CONFIG)], Other())


def test_the_fields_alone_are_enough_to_set_a_flow_up(tmp_path: Path) -> None:
    """Which is what a YAML file of them is, and what `hmz exec -c` hands over."""
    where = _flow(tmp_path, SETTABLE)

    Runner(where, [ShellAgent(CONFIG)], {"rounds": 7, "mode": "slow"}).run("go")

    said = json.loads(where.with_suffix(".json").read_text())
    assert said["config"] == {"loud": False, "rounds": 7, "mode": "slow"}


def test_fields_the_flow_will_not_take_are_refused_before_it_runs(
    tmp_path: Path,
) -> None:
    """The flow's own model is what refuses them, at the moment the flow is about to run."""
    where = _flow(tmp_path, SETTABLE)

    with pytest.raises(NotAFlow, match="validation error"):
        Runner(where, [ShellAgent(CONFIG)], {"rounds": 99})


def test_a_config_is_read_off_a_yaml_file_as_it_is_written(tmp_path: Path) -> None:
    """One field per line, under the names the flow declared, and nothing else in it."""
    said = tmp_path / "setup.yaml"
    said.write_text("rounds: 7\nmode: slow\n")

    assert set_up_from(said) == {"rounds": 7, "mode": "slow"}
    # An empty file is a flow left as it comes, which is what writing nothing means.
    (tmp_path / "empty.yaml").write_text("")
    assert set_up_from(tmp_path / "empty.yaml") == {}


@pytest.mark.parametrize(
    ("held", "because"),
    [("- one\n- two\n", "not a list"), ("just a string\n", "not a str")],
)
def test_a_config_file_that_is_not_a_mapping_is_said_to_be(
    tmp_path: Path, held: str, because: str
) -> None:
    """A flow is set up field by field, so a file holding anything else is one to correct."""
    said = tmp_path / "setup.yaml"
    said.write_text(held)

    with pytest.raises(ValueError, match=because):
        set_up_from(said)


def test_a_config_file_that_cannot_be_read_is_said_to_be(tmp_path: Path) -> None:
    """Rather than a traceback out of the command line that named it."""
    with pytest.raises(ValueError, match="cannot read"):
        set_up_from(tmp_path / "nowhere.yaml")


def test_the_exec_line_reads_the_config_it_names(tmp_path: Path) -> None:
    """`hmz exec -c` is the whole of it: the file, unchecked, for the flow to check."""
    (tmp_path / "setup.yaml").write_text("rounds: 7\n")

    _, agents, task, held = flow_and_agents(
        ["-f", "flow", "-c", str(tmp_path / "setup.yaml"), "-a", "claude/m:high", "go"]
    )

    assert held == {"rounds": 7}
    assert len(agents) == 1
    assert task == "go"


def test_the_exec_line_gives_a_codex_agent_its_own_overrides() -> None:
    """`config.KEY` is that `-a`, not a flag of the process starting every agent."""
    _, agents, _, _ = flow_and_agents(
        [
            "-f",
            "flow",
            "-a",
            (
                "cli=codex,model=gpt-5.6-sol,effort=high,"
                "config.model_context_window=1000000,"
                "config.model_auto_compact_token_limit=900000"
            ),
            "go",
        ]
    )

    held = agents[0].config
    assert isinstance(held, CodexAgentConfig)
    assert held.overrides == (
        ("model_context_window", "1000000"),
        ("model_auto_compact_token_limit", "900000"),
    )


def test_the_exec_line_without_a_config_says_nothing_about_one(tmp_path: Path) -> None:
    """Which is every line written before there was such a thing, and is a flow as it comes."""
    _, _, _, held = flow_and_agents(["-f", "flow", "-a", "claude/m:high", "go"])

    assert held is None


def test_a_flow_that_takes_nothing_refuses_being_set_up(tmp_path: Path) -> None:
    """Handing a config to a flow that declared none is the same mistake the other way."""

    class Other(BaseModel):
        wrong: bool = True

    where = _flow(tmp_path, PLAIN)

    with pytest.raises(NotAFlow, match="the flow takes no config"):
        Runner(where, [ShellAgent(CONFIG)], Other())
