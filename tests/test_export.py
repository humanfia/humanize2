"""One whole run, packaged up to send to somebody who was not there.

A run points at its sessions rather than holding them, which is right on the machine that ran
it and worth nothing anywhere else: a directory of symlinks into somebody's home is an archive
with nothing in it. So a bundle is the run with every link followed -- and with every
credential taken out, since the one thing a person sending their own run must not also send is
the key it ran on.
"""

from __future__ import annotations

import json
import tarfile
from typing import TYPE_CHECKING, Any

import pytest

from hmz import providers
from hmz.agents import AgentConfig
from hmz.epic import epics, sessions
from hmz.exporting import MANIFEST, REDACTED, TRANSCRIPT, bundle, logged, plain, sized
from hmz.runner import Runner
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that opens one session per agent, each naming itself as it lands.
FLOW = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    for at, agent in enumerate(agents):
        agent.new()(f"echo session-{at}")
"""

#: One that drives one agent, and says its session is called what the log is named after.
ONE = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0].new()("echo the-session")
"""

#: A flow that calls another, so that a bundle has a record beside the run's own to carry.
CALLS = """
from hmz.agents import AgentBase
from hmz.flows import flow, load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("under")(agents, task)
"""

#: The one it calls, which opens a session of its own -- one run, two records.
UNDER = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0].new()("echo the-session")
"""

#: One that calls the same flow twice, so that two calls of one flow are two records and the
#: manifest has to say which of them a session belongs to.
TWICE = """
from hmz.agents import AgentBase
from hmz.flows import flow, load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("each")(agents, "once")
    load("each")(agents, "again")
"""

#: The one it calls twice, whose session is named after the call so the two are two.
EACH = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0].new()(f"echo {task}")
"""

#: A flow that leaves something behind, so that `state.json` is there to be carried.
KEEPS = """
from typing import Any

from hmz.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    state["rounds"] = 3
    agents[0].new()("echo the-session")
"""


class ClaudeAgent(ShellAgent):
    """A stand-in for a backend humanize knows where the logs of are."""


class OpencodeAgent(ShellAgent):
    """A stand-in for one that keeps its sessions to itself and logs nothing."""


def _claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, said: str = "{}") -> Path:
    """Points Claude Code's home somewhere temporary, with one session already logged."""
    where = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(where))
    log = where / "projects" / "-tmp-project" / "the-session.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(f"{said}\n", encoding="utf-8")
    return log


def _held(at: Path) -> dict[str, str]:
    """Everything one bundle holds, by the name it is under with the epic's own stripped off."""
    held: dict[str, str] = {}
    with tarfile.open(at) as opened:
        for one in opened.getmembers():
            handle = opened.extractfile(one)
            said = handle.read().decode("utf-8") if handle is not None else ""
            held[one.name.partition("/")[2]] = said
    return held


def _manifest(at: Path) -> dict[str, Any]:
    """What one bundle says about itself."""
    return json.loads(_held(at)[MANIFEST])


def test_a_bundle_holds_every_record_the_run_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow that called another is two records, and one run is both of them."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path / ".humanize" / "flows", "under", UNDER)
    written(tmp_path, "flow", CALLS)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    held = _held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert "epic.jsonl" in held
    assert [one for one in held if one.startswith("epic.under_")], held
    # And the manifest lists what went in, the run's own record first.
    said = json.loads(held[MANIFEST])
    assert said["held"][0] == "epic.jsonl"
    assert said["held"][-1] == MANIFEST
    # And the run's own record reads back as the run: every line it wrote, not a summary.
    assert (
        '"event": "began"' in held["epic.jsonl"]
        or '"event":"began"' in (held["epic.jsonl"])
    )


def test_the_manifest_says_the_call_tree_and_whose_each_session_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow called twice is two records and two conversations, and the flow name says one."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path / ".humanize" / "flows", "each", EACH)
    written(tmp_path, "flow", TWICE)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    said = _manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    # Two calls of one flow, each in a record of its own, each saying which called it.
    assert [one["task"] for one in said["called"]] == ["once", "again"] or [
        one["task"] for one in said["called"]
    ] == ["again", "once"]
    assert {one["under"] for one in said["called"]} == {"epic.jsonl"}
    assert len({one["record"] for one in said["called"]}) == 2
    # And each session says which of the two it was opened in, not only which flow.
    assert {one["record"] for one in said["sessions"]} == {
        one["record"] for one in said["called"]
    }


def test_a_session_log_comes_as_its_contents_and_not_as_a_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: a link into somebody's home is worth nothing on another machine."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch, '{"type":"user","text":"hello"}')

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()
    (one,) = sessions(epic)

    at = bundle(epic, tmp_path / "out.tar.gz")[0]
    with tarfile.open(at) as opened:
        member = opened.getmember(f"{epic.name}/sessions/{one.name}/the-session.jsonl")
        assert not member.issym()
        assert not member.islnk()
        assert member.isfile()
    assert '"text":"hello"' in _held(at)[f"sessions/{one.name}/the-session.jsonl"]


def test_a_backend_that_logs_nothing_says_so_rather_than_carrying_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI that keeps its sessions in a database logs none, and an absence reads as loss."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)

    Runner(tmp_path / "flow", [OpencodeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    said = _manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    (one,) = said["sessions"]
    assert one["backend"] == "opencode"
    assert one["logs"] == []
    assert "keeps its sessions to itself" in one["because"]
    assert said["backends"]["opencode"]["logs"] is False


def test_no_account_variable_rides_along(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An export is the user's to send. The key it ran on is nobody's."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    providers.add(
        "claude",
        "work",
        "key",
        {"ANTHROPIC_AUTH_TOKEN": "hunter2-hunter2-hunter2"},
    )
    _claude(
        tmp_path,
        monkeypatch,
        '{"headers":{"x-api-key":"hunter2-hunter2-hunter2"}}',
    )
    agent = ClaudeAgent(
        AgentConfig(model="m", effort="high", provider="work"), name="builder"
    )

    Runner(tmp_path / "flow", [agent]).run("go")
    (epic,) = epics()

    held = _held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert not any("hunter2" in said for said in held.values()), held
    (log,) = [one for one in held if one.startswith("sessions/")]
    assert REDACTED in held[log]
    # The account is still named, which is what the run was: an agent ran as `work`.
    assert _manifest(tmp_path / "out.tar.gz")["agents"][0]["provider"] == "work"


def test_what_the_run_says_it_ran_is_not_struck_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An account may say which model to ask for, and Kimi Code's fixture one does.

    A bundle with the model taken out of it because some other account had that name in a
    variable is a bundle saying nothing about what actually ran.
    """
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    providers.add("kimi", "elsewhere", "env", {"KIMI_MODEL_NAME": "fixture-model"})
    _claude(tmp_path, monkeypatch)
    agent = ClaudeAgent(
        AgentConfig(model="fixture-model", effort="high"), name="builder"
    )

    Runner(tmp_path / "flow", [agent]).run("go")
    (epic,) = epics()

    said = _manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert said["agents"][0]["model"] == "fixture-model"
    assert said["agents"][0]["runs"] == "claude/fixture-model:high"


def test_the_manifest_is_scrubbed_like_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It holds the task, which is a line somebody typed and may hold anything."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    providers.add("claude", "work", "key", {"ANTHROPIC_AUTH_TOKEN": "hunter2-hunter2"})
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run(
        "push to https://bob:ghp_abcdefghijklmnopqrst@example.com with hunter2-hunter2"
    )
    (epic,) = epics()

    at, manifest = bundle(epic, tmp_path / "out.tar.gz")
    said = _held(at)[MANIFEST]
    assert "hunter2" not in said
    assert "ghp_abcdefghijklmnopqrst" not in said
    assert "bob" not in said
    # And what comes back is what was written, not what was about to be.
    assert "hunter2" not in json.dumps(manifest)


def test_where_a_bundle_lands_beside_two_of_them_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two exports of one run must not be two gzip streams into one file."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)
    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    at = bundle(epic)[0]
    assert bundle(epic)[0] == at
    assert MANIFEST in _held(at)
    # And nothing half-written is left beside it.
    assert [one.name for one in at.parent.iterdir()] == [at.name]


def test_a_directory_to_fill_that_is_not_there_yet_is_still_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-o out/` is somewhere to put it rather than a file called `out`.

    Answering it with the file would have the next run write over the last.
    """
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)
    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    at = bundle(epic, f"{tmp_path / 'bundles'}/")[0]

    assert at.parent == tmp_path / "bundles"
    assert at.name == f"{epic.name}.epic.tar.gz"


def test_the_manifest_says_which_run_on_what_and_by_whom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything a reader needs to know what they are looking at, and nothing secret."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", FLOW)
    _claude(tmp_path, monkeypatch)

    Runner(
        tmp_path / "flow",
        [ClaudeAgent(CONFIG, name="actor"), ClaudeAgent(CONFIG, name="reviewer")],
    ).run("fix the thing")
    (epic,) = epics()

    said = _manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert said["epic"] == epic.name
    assert said["run"]["task"] == "fix the thing"
    assert said["run"]["how"] == "done"
    assert said["workspace"]["at"] == str(tmp_path.resolve())
    assert [one["agent"] for one in said["agents"]] == ["actor", "reviewer"]
    assert said["agents"][0]["runs"] == "claude/m:high"
    assert "claude" in said["backends"]
    assert MANIFEST in said["held"]
    assert said["humanize"]
    assert said["redacted"]


def test_what_a_resumable_flow_left_behind_is_in_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run picked up again is picked up from that file, so a report of one needs it."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", KEEPS)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    held = _held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert json.loads(held["state.json"])[str(tmp_path / "flow")] == {"rounds": 3}


def test_a_trace_gathered_of_the_run_goes_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trace belongs with the run, and so belongs in the bundle of that run."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()
    (epic / "traces").mkdir()
    (epic / "traces" / "a.trace.json").write_text('{"traceEvents": []}', "utf-8")

    held = _held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert held["traces/a.trace.json"] == '{"traceEvents": []}'


def test_the_transcript_goes_in_as_it_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the interface hands over is the text, not the rows. There is none from a line."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    with_screen = _held(
        bundle(epic, tmp_path / "a.tar.gz", transcript="a long line\n")[0]
    )
    assert with_screen[TRANSCRIPT] == "a long line\n"
    assert TRANSCRIPT not in _held(bundle(epic, tmp_path / "b.tar.gz")[0])


def test_a_bundle_is_readable_by_whoever_made_it_and_nobody_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is in it is their prompts and their agents' output."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    assert bundle(epic)[0].stat().st_mode & 0o777 == 0o600


def test_a_bundle_carries_nothing_about_whoever_made_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tar records its writer by default, and a login name is not a thing to hand over."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    with tarfile.open(bundle(epic, tmp_path / "out.tar.gz")[0]) as opened:
        assert {one.uname for one in opened.getmembers()} == {""}
        assert {one.uid for one in opened.getmembers()} == {0}


def test_where_a_bundle_lands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file outright, a directory to fill, or `.humanize/` here -- it is a thing to send."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    # Where somebody is standing rather than in humanize's own home the way a trace of a
    # run goes, and named whole: it is a thing to attach to something.
    assert bundle(epic)[0] == tmp_path / ".humanize" / f"{epic.name}.epic.tar.gz"
    assert bundle(epic)[0].is_file()
    (tmp_path / "somewhere").mkdir()
    assert bundle(epic, tmp_path / "somewhere")[0].parent == tmp_path / "somewhere"
    assert bundle(epic, tmp_path / "named.tgz")[0].name == "named.tgz"


def test_a_directory_holding_no_run_is_nothing_to_export(tmp_path: Path) -> None:
    """Which is a thing to correct rather than an archive of nothing."""
    with pytest.raises(ValueError, match="is not a run"):
        bundle(tmp_path, tmp_path / "out.tar.gz")


def test_a_link_whose_log_has_gone_is_left_out_rather_than_carried_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log rolls over, a home is thrown away: a name with nothing behind it is not a log."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    log = _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()
    log.unlink()

    said = _manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert said["sessions"][0]["logs"] == []
    assert "has since gone" in said["sessions"][0]["because"]


def test_what_each_session_was_logged_to_is_read_through_the_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The files themselves, since what a bundle carries is what is behind each link."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    log = _claude(tmp_path, monkeypatch)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()
    (one,) = sessions(epic)

    assert logged(epic) == {one.name: {"the-session.jsonl": log.resolve()}}


@pytest.mark.parametrize(
    ("said", "wanted"),
    [
        (
            "https://x-access-token:ghs_abcdefgh@github.com/o/f",
            f"https://{REDACTED}@github.com/o/f",
        ),
        ("key sk-ant-api03-abcdefghijklmnop here", f"key {REDACTED} here"),
        ("ghp_abcdefghijklmnopqrst", REDACTED),
        ("AIzaSyAbcdefghijklmnopqrstuvwxyz01", REDACTED),
        (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NX0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
            REDACTED,
        ),
        (
            "Authorization: Bearer abcdefghijklmnopqrst",
            f"Authorization: Bearer {REDACTED}",
        ),
        ('{"api_key": "abcdefgh"}', f'{{"api_key": "{REDACTED}"}}'),
        ("ANTHROPIC_AUTH_TOKEN=abcdefgh", f"ANTHROPIC_AUTH_TOKEN={REDACTED}"),
        (
            "https://s3/x?X-Amz-Signature=deadbeef",
            f"https://s3/x?X-Amz-Signature={REDACTED}",
        ),
    ],
)
def test_what_is_struck_out_of_everything_a_bundle_carries(
    said: str, wanted: str
) -> None:
    assert plain(said) == wanted


@pytest.mark.parametrize(
    "said",
    [
        '{"input_tokens": 4211, "output_tokens": 12}',
        "/v1/messages?max_tokens=4096&model=x",
        "/search?monkey=hello",
        "https://github.com/humanfia/humanize2",
        "ask-the-reviewer-about-it",
        "the password is wrong",
    ],
)
def test_what_is_left_alone(said: str) -> None:
    """A bundle nobody can read is a bundle nobody develops against."""
    assert plain(said) == said


def test_a_value_is_struck_wherever_it_appears() -> None:
    """A gateway's key is whatever somebody pasted, and no pattern would know it."""
    assert (
        plain("ran with wobbly-elephant", ["wobbly-elephant"]) == f"ran with {REDACTED}"
    )


@pytest.mark.parametrize(
    ("count", "said"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (1000, "1.0 kB"),
        (91234, "91 kB"),
        (5_400_000, "5.4 MB"),
    ],
)
def test_how_big_it_came_out(count: int, said: str) -> None:
    assert sized(count) == said


def test_the_command_line_exports_the_last_run_of_this_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`hmz export` with nothing said is the run that has just happened."""
    from hmz import cli

    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)
    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    assert cli.main(["export"]) == 0

    at = tmp_path / ".humanize" / f"{epic.name}.epic.tar.gz"
    assert at.is_file()
    said = capsys.readouterr().out
    assert str(at) in said
    assert "1 session" in said
    assert "1 log" in said


def test_the_command_line_takes_a_run_by_name_and_a_file_to_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run to attach to an issue is a run named outright, written where it was asked for."""
    from hmz import cli

    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)
    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")
    (epic,) = epics()

    assert cli.main(["export", epic.name[:8], "-o", str(tmp_path / "sent.tgz")]) == 0

    assert (tmp_path / "sent.tgz").is_file()
    assert str(tmp_path / "sent.tgz") in capsys.readouterr().out


def test_a_name_no_run_answers_to_is_a_line_to_correct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rather than an archive of whichever run happened to sort last."""
    from hmz import cli

    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    _claude(tmp_path, monkeypatch)
    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")

    with pytest.raises(SystemExit) as stopped:
        cli.main(["export", "nothing-is-called-this"])

    assert stopped.value.code == 2


def test_a_directory_nothing_has_been_run_in_is_a_line_to_correct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There is no run here to package up, which is a thing to say rather than to guess at."""
    from hmz import cli

    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as stopped:
        cli.main(["export"])

    assert stopped.value.code == 2
