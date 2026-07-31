"""The Python call and the command line, which are one thing said twice.

Everything the parser reads is a field of :class:`AnchorConfig`, and everything a config renders
is read back by that parser -- a flow spawns what an operator types. The rest of this suite runs
through both, so what is left to check here is that the two spellings still mean the same, and
that :func:`connect` is reachable without a command line at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

import pytest

from humanize import cli
from humanize.coganchor import AnchorConfig, check, connect
from humanize.coganchor.argv import parser
from tests.coganchor.conftest import DEFAULT_TIMEOUT, REPO_ROOT, Anchorage

#: Every setting at once, none of them left at its default. The token is spelled the way one
#: in eighty of `secrets.token_urlsafe`'s are, and the paths hold a space, because a setting
#: that reads as an option of ours is the way this crossing breaks.
FULL = AnchorConfig(
    target="ssh://build-box",
    workspace="/srv/a project",
    remote_path="/mnt/data/a project",
    shadow="/tmp/mirror",
    local_paths=("/home/me/.secrets", "/home/me/.cache"),
    local_execs=("/usr/local/bin/here",),
    redirects=(("/home/me/.claude/.credentials.json", "/srv/a provider/creds.json"),),
    net="remote",
    net_allow=("api.anthropic.com:443",),
    token="-Vx9nQs3cret",
    force=True,
)


def test_a_rendered_command_is_parsed_back_as_the_settings_it_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A setting that did not survive the round trip would be dropped in silence."""
    seen: dict[str, Any] = {}

    def record(command: list[str], config: AnchorConfig) -> int:
        seen.update(command=command, config=config)
        return 0

    monkeypatch.setattr("humanize.coganchor.anchor.connect", record)
    rendered = FULL.command(["claude", "--print"])
    # The interpreter running the flow, so the child is the one humanize is installed in.
    assert rendered[:4] == [sys.executable, "-m", "humanize", "anchor"]

    assert cli.main(rendered[3:]) == 0

    assert seen["config"] == FULL
    assert seen["command"] == ["claude", "--print"]


def test_an_agent_argument_is_never_read_as_one_of_ours() -> None:
    """A kimi turn carries its prompt in argv, and a prompt can be worded like anything."""
    argv = ["kimi", "--prompt", "--force the issue, and mind the gap", "--model", "k3"]

    rendered = AnchorConfig(target="ssh://build-box", force=True).command(argv)

    assert parser().parse_args(rendered[4:]).command == argv


def test_a_default_anchor_says_only_where_the_work_lands() -> None:
    assert AnchorConfig().command(["claude"])[4:] == [
        "--target=local",
        "--net=local",
        "claude",
    ]


def test_connect_runs_the_agent_without_a_command_line(anchorage: Anchorage) -> None:
    """The API the flows use, in a process of its own because the supervisor takes over signals."""
    anchorage.seed({"greeting.txt": "hello from the target\n"})
    config = AnchorConfig(
        target=f"local:{anchorage.target}",
        workspace=anchorage.workspace,
        shadow=str(anchorage.mirror),
    )
    program = (
        "from humanize.coganchor import AnchorConfig, connect\n"
        "raise SystemExit(connect(['bash', '-c', 'cat greeting.txt; echo back > answer.txt'],"
        f" {config!r}))\n"  # a config reads back as itself, which is how it crosses
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "hello from the target" in result.stdout
    assert anchorage.target_text("answer.txt") == "back\n"


def test_checking_reports_the_target_without_running_anything(
    anchorage: Anchorage, capsys: pytest.CaptureFixture[str]
) -> None:
    """What `--check` prints is what the call returns, and neither starts an agent."""
    anchorage.seed({"one.txt": "1", "two.txt": "2"})
    config = AnchorConfig(
        target=f"local:{anchorage.target}", workspace=anchorage.workspace
    )

    found = check(config)

    assert found["target"] == f"local:{anchorage.target}"
    assert found["workspace"] == anchorage.workspace
    assert found["entries"] == 2
    assert found["exports"] == [
        {"virtual": anchorage.workspace, "real": str(anchorage.target)}
    ]

    assert cli.main([*config.command(())[3:], "--check"]) == 0
    printed = capsys.readouterr().out
    assert found["target"] in printed
    assert f"{anchorage.workspace} (2 entries)" in printed


def test_a_target_nobody_can_read_is_refused_the_way_argparse_refuses_an_argument() -> (
    None
):
    with pytest.raises(SystemExit) as refused:
        cli.main(["anchor", "--target", "rsync://build-box", "claude"])
    assert refused.value.code == 2


@pytest.mark.parametrize(
    ("settings", "complaint"),
    [
        ({"target": "rsync://build-box"}, "unsupported target"),
        ({"net": "Remote"}, "unsupported net"),
    ],
    ids=["a target nobody can read", "a net that is neither"],
)
def test_settings_no_session_could_run_under_are_refused_as_they_are_written(
    settings: dict[str, Any], complaint: str
) -> None:
    """Both spellings refuse the same thing: the command line by parsing, this by construction."""
    with pytest.raises(ValueError, match=complaint):
        AnchorConfig(**settings)


def test_connect_refuses_to_run_nothing() -> None:
    """Refused before a mirror is prepared or a target dialled, so nothing is left half done."""
    with pytest.raises(ValueError, match="no agent"):
        connect([])
