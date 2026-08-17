"""``hmz check``, held to its three exit statuses and to printing what a script can read.

What each reading finds is `test_checking.py`'s and `test_proving.py`'s business; what is
checked here is the command around them -- that a clean flow passes, a blocked one blocks,
`--strict` raises the bar, `--static` keeps the flow unloaded, a name nothing answers to is
a usage error, and `--json` says the same findings a script can parse back.
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING

import pytest

from hmz.cli.check import check
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

CLEAN = '''
"""A flow with nothing to say about it."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task, suppress=True)
'''

DEAD = '''
"""A flow whose loop nothing can end."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    while True:
        agents[0](task, suppress=True)
'''

#: rlar's shape: legal, and one warning -- the loop only its reviewer ends.
WARNED = '''
"""A flow whose loop waits on its reviewer."""

from hmz.flows import Agent, flow
from pydantic import BaseModel, Field


class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")


@flow
def run(agents: tuple[Agent], task: str) -> None:
    while True:
        review = agents[0](task, suppress=True, schema=Review)
        if review is not None and review.done:
            return
'''

#: Clean to the static reading, and refused the moment it is loaded.
UNLOADABLE = '''
"""A flow whose file will not run."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task, suppress=True)


raise RuntimeError("read no further")
'''


def test_a_clean_flow_passes_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    at = written(tmp_path, "one", textwrap.dedent(CLEAN))
    assert check([str(at)]) == 0
    assert "nothing to say about 1 flow" in capsys.readouterr().out


def test_a_blocking_finding_is_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    at = written(tmp_path, "one", textwrap.dedent(DEAD))
    assert check([str(at)]) == 1
    out = capsys.readouterr().out
    assert f"{at / '__init__.py'}:" in out
    assert "error: dead-loop:" in out
    assert "1 error, 0 warnings" in out


def test_a_warning_passes_until_strict_raises_the_bar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    at = written(tmp_path, "one", textwrap.dedent(WARNED))
    assert check([str(at)]) == 0
    assert "warning: unbounded-loop:" in capsys.readouterr().out
    assert check(["--strict", str(at)]) == 1


def test_static_keeps_the_flow_unloaded(tmp_path: Path) -> None:
    at = written(tmp_path, "one", textwrap.dedent(UNLOADABLE))
    # The static reading has nothing to say about it; loading it is what refuses it.
    assert check(["--static", str(at)]) == 0
    assert check([str(at)]) == 1


def test_a_name_nothing_answers_to_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        check([str(tmp_path / "nowhere")])
    assert stopped.value.code == 2
    assert "no flow called" in capsys.readouterr().err


def test_a_flag_it_does_not_take_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stopped:
        check(["--everything", str(tmp_path)])
    assert stopped.value.code == 2


def test_json_says_the_same_findings_a_script_can_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    at = written(tmp_path, "one", textwrap.dedent(DEAD))
    assert check(["--json", "--static", str(at)]) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    held = [json.loads(one) for one in lines]  # every line parses: no count under them
    assert [one["code"] for one in held] == ["dead-loop"]
    assert held[0]["severity"] == "error"
    assert held[0]["where"].endswith("__init__.py")
    assert held[0]["line"] > 0
    assert "cannot end" in held[0]["said"]


def test_several_flows_are_one_answer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = written(tmp_path, "good", textwrap.dedent(CLEAN))
    bad = written(tmp_path, "bad", textwrap.dedent(DEAD))
    assert check(["--static", str(good), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "dead-loop" in out
    assert "1 error, 0 warnings" in out
