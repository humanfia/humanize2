"""A run of a flow that never stops on its own, stopped by the allowance it was given.

End to end and out of process: `hmz exec` on a flow whose loop has no exit of its own, under
a stand-in CLI, with a budget in the file `-c` names. What is proved is the whole of what the
allowance is for -- that the process exits rather than looping for a week, that the epic says
the run was stopped rather than done, and that each of the three dimensions does it on its
own. A unit test can prove the reckoning; only this can prove the loop actually ends.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

#: How long one round of the stand-in CLI takes, and what it says it cost. Slow enough that a
#: budget in hours can be spelled without the test taking one, and dear enough that a budget
#: in tokens is reached in a handful of rounds.
PAUSE = 0.05
EACH = 4000

#: An `opencode run` that answers every prompt the same way and says what the answer cost, so
#: that a loop under it spends a known amount per round. Chosen for being the shortest of the
#: backends to stand in for: one command a turn, and the whole turn on stdout.
_OPENCODE = f"""
import json, sys, time

said = sys.stdin.read()
print(json.dumps({{"type": "text", "sessionID": "ses_one",
                  "part": {{"id": "prt_1", "type": "text", "text": "ok"}}}}), flush=True)
print(json.dumps({{"type": "step_finish", "sessionID": "ses_one",
                  "part": {{"id": "stp_1", "type": "step-finish",
                           "tokens": {{"input": 1, "output": {EACH}, "reasoning": 0,
                                      "cache": {{"read": 0, "write": 0}}}}}}}}), flush=True)
time.sleep({PAUSE})
"""

#: A flow whose loop has no way out at all. Every exit it could have had is deliberately
#: absent, so that anything which ends this run is the run's allowance and nothing else.
FOREVER = """
from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    at = 0
    while True:
        at += 1
        print(f"round {at}: {agents[0](task)}")
"""


@pytest.fixture
def stand_in(tmp_path: Path) -> dict[str, str]:
    """The environment a run of this gets: a stand-in CLI, and a home of its own."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "opencode"
    fake.write_text(f"#!{sys.executable}\n{_OPENCODE}")
    fake.chmod(0o755)
    flows = tmp_path / "flows" / "forever"
    flows.mkdir(parents=True)
    (flows / "__init__.py").write_text(FOREVER, encoding="utf-8")
    # One model, priced, put straight where a fetch would have left it: what a token costs is
    # somebody else's list, and a suite must never go and ask them for it. `m` at five dollars
    # a million out makes one round of the stand-in worth a known amount of money.
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "prices.json").write_text(
        json.dumps(
            {
                "models": {
                    "m": {
                        "provider": "nobody",
                        "per_million": {"input": 1, "output": 5},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return {
        **os.environ,
        "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
        "HUMANIZE_HOME": str(home),
        # The list is already here, so nothing fetches one, and nothing here reports.
        "HUMANIZE_PRICES": "off",
        "HUMANIZE_TELEMETRY": "off",
    }


def _ran(
    tmp_path: Path, said: dict[str, str], budget: str, *, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    """One `hmz exec` of the endless flow, under the budget written in a file."""
    (tmp_path / "b.yaml").write_text(budget, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "hmz",
            "exec",
            "-f",
            str(tmp_path / "flows" / "forever"),
            "-a",
            "opencode/m:high",
            "-c",
            str(tmp_path / "b.yaml"),
            "go",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=said,
        timeout=timeout,
    )


def _how(said: dict[str, str]) -> list[str]:
    """How every run written down under this home ended, oldest first."""
    from hmz.runtime.epic import JOURNAL

    epics = sorted((Path(said["HUMANIZE_HOME"]) / "epics").rglob(JOURNAL))
    ended: list[str] = []
    for at in epics:
        for line in at.read_text(encoding="utf-8").splitlines():
            held = json.loads(line)
            if held.get("event") == "ended":
                ended.append(str(held.get("how")))
    return ended


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("budget", "why"),
    [
        # An hour a hundredth of a second long, which a loop of twenty-millisecond rounds
        # reaches in the first of them.
        ("budget:\n  hours: 0.000003\n", "h spent"),
        # Two rounds' worth of output tokens, spelled in the millions this is counted in.
        (f"budget:\n  tokens: {2 * EACH / 1_000_000}\n", "output tokens spent"),
        # And two rounds' worth of money, at the five dollars a million the list above says.
        (f"budget:\n  dollars: {2 * EACH * 5 / 1_000_000}\n", "$0.04 spent"),
    ],
)
def test_a_loop_with_no_exit_of_its_own_is_stopped_by_its_allowance(
    tmp_path: Path, stand_in: dict[str, str], budget: str, why: str
) -> None:
    """The whole of what this is for: a flow that would otherwise run until somebody killed it.

    Out of process on purpose. A loop that ends because a unit test asserted it would is not
    the same claim as a loop whose process exits.
    """
    ran = _ran(tmp_path, stand_in, budget)

    assert why in ran.stderr + ran.stdout, ran.stderr
    # And the run is written down as stopped rather than as having finished what it set out
    # to do, because a run that ran out of money did not do what it was asked.
    assert _how(stand_in) == ["stopped"]


@pytest.mark.timeout(300)
def test_a_run_nothing_will_stop_says_so_and_runs_anyway(
    tmp_path: Path, stand_in: dict[str, str]
) -> None:
    """A command line has nobody to ask, and refusing would break every unattended flow.

    So it says it plainly on the stream that is not the answer, and goes. The run here has no
    exit at all, so it is killed rather than waited on -- which is the point being made.
    """
    with pytest.raises(subprocess.TimeoutExpired) as went_on:
        _ran(tmp_path, stand_in, "{}\n", timeout=10.0)

    said = (went_on.value.stderr or b"").decode(errors="replace")

    assert "nothing will stop this run" in said


@pytest.mark.timeout(120)
def test_a_budget_written_as_one_number_stops_the_line_before_anything_runs(
    tmp_path: Path, stand_in: dict[str, str]
) -> None:
    """Which is what every flowverse loop's settings file says today, meaning millions."""
    ran = _ran(tmp_path, stand_in, "budget: 25\n")

    assert ran.returncode != 0
    assert "rather than one number" in ran.stderr
    assert _how(stand_in) == []  # nothing ran at all
