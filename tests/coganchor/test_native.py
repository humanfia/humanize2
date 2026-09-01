"""The other arrangement: the CLI already on the target, driven there with nothing below it.

Nothing here traces anything, which is the point of the whole file -- so unlike the
end-to-end suites beside it, every one of these runs on any machine whether or not it can
supervise a process. What is being checked is that a turn taken this way is the turn it would
have been: it runs in the target's copy of the workspace, both its streams come back
untouched, its status is its own, and the three things that do not follow a CLI across a
machine boundary on their own are each carried over deliberately and each taken away again.

A `local:` target stands in for a remote one throughout, exactly as it does elsewhere here:
the two sides speak the same protocol over a pipe, and the workspace path the agent is given
exists on neither of them, so a command that reads it proves the read went through the target.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: The workspace path both sides name, which exists on neither machine.
WORKSPACE = "/coganchor-native"

#: Long enough for a pipe, a handshake and a shell, and short enough that a hung one is a
#: failure rather than a suite that never finishes.
PATIENCE = 90


@dataclass(frozen=True)
class Driven:
    """A target directory, and the means to run something on it the way a turn is run."""

    target: Path

    def anchor(self, **settings: object) -> AnchorConfig:
        """The settings a native turn on this target runs under."""
        return AnchorConfig(
            target=f"local:{self.target}",
            workspace=WORKSPACE,
            native=True,
            **settings,  # pyright: ignore[reportArgumentType]
        )

    def run(
        self, *command: str, stdin: bytes = b"", **settings: object
    ) -> subprocess.CompletedProcess[str]:
        """Runs one command on the target, spawned the way an anchored turn is spawned.

        Through `AnchorConfig.command`, so what this suite drives is the line a backend
        renders rather than a call arranged for the test.
        """
        completed = subprocess.run(
            self.anchor(**settings).command(command),
            input=stdin,
            capture_output=True,
            timeout=PATIENCE,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            check=False,
        )
        return subprocess.CompletedProcess(
            completed.args,
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )


@pytest.fixture
def driven(tmp_path: Path) -> Driven:
    """A target with a project directory on it, and nothing mirrored anywhere."""
    target = tmp_path / "target"
    target.mkdir()
    return Driven(target=target)


def test_an_anchor_told_to_drive_the_targets_own_cli_says_so_by_name() -> None:
    assert AnchorConfig(native=True).capabilities == frozenset({"anchor:native-cli"})
    assert AnchorConfig().capabilities == frozenset({"anchor:supervised"})


def test_every_setting_a_native_turn_takes_survives_being_written_back_out() -> None:
    from hmz.coganchor import argv as line

    settings = AnchorConfig(
        target="docker://box",
        native=True,
        hushes=("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"),
        projects=(("CLAUDE_CONFIG_DIR", "/here/creds"),),
        carries=(("/here/skill", ".claude/skills/review"),),
        installs="npm i -g @anthropic-ai/claude-code",
    )
    rendered = settings.command(["claude", "--print"])
    assert rendered[-2:] == ["claude", "--print"]
    # Read back by the same parser the spawned process reads it with, which is the whole of
    # what makes this a bijection rather than two lists that happen to look alike.
    written = line.settings(line.parser().parse_args(rendered[4:]))
    assert written == settings


def test_a_turn_driven_on_the_target_runs_in_the_targets_copy_of_the_workspace(
    driven: Driven,
) -> None:
    (driven.target / "note.txt").write_text("the target's own file\n")

    said = driven.run("/bin/sh", "-c", "pwd; cat note.txt")

    assert said.returncode == 0
    # The directory it reports is the workspace as the *agent* names it, and the file it read
    # exists only on the target: both halves of one claim.
    assert said.stdout.splitlines() == [str(driven.target), "the target's own file"]


def test_a_driven_turn_answers_with_its_own_status_and_its_own_two_streams(
    driven: Driven,
) -> None:
    said = driven.run("/bin/sh", "-c", "echo out; echo err >&2; exit 7")

    assert said.returncode == 7
    assert said.stdout == "out\n"
    assert "err" in said.stderr


def test_what_a_driven_turn_is_given_on_stdin_reaches_it_on_the_target(
    driven: Driven,
) -> None:
    said = driven.run("/bin/cat", stdin=b"one line\nand another\n")

    assert said.returncode == 0
    assert said.stdout == "one line\nand another\n"


def test_a_cli_the_target_has_not_got_is_refused_with_the_line_that_installs_it(
    driven: Driven,
) -> None:
    said = driven.run("nonesuch-cli", "--print", installs="npm i -g nonesuch")

    # The status every shell uses for a command it could not find, which is the one each
    # backend here already reads as a CLI that is not installed.
    assert said.returncode == 127
    assert "nonesuch-cli is not installed" in said.stderr
    assert "npm i -g nonesuch" in said.stderr


def test_a_projected_credential_is_readable_by_nobody_else_and_gone_afterwards(
    driven: Driven, tmp_path: Path
) -> None:
    creds = tmp_path / "creds"
    (creds / "nested").mkdir(parents=True)
    (creds / "auth.json").write_text("a token\n")
    (creds / "nested" / "more.json").write_text("another\n")

    said = driven.run(
        "/bin/sh",
        "-c",
        'printf "%s\\n" "$CLAUDE_CONFIG_DIR"; cat "$CLAUDE_CONFIG_DIR/auth.json"; '
        'cat "$CLAUDE_CONFIG_DIR/nested/more.json"; '
        'stat -c %a "$CLAUDE_CONFIG_DIR" "$CLAUDE_CONFIG_DIR/auth.json"',
        projects=(("CLAUDE_CONFIG_DIR", str(creds)),),
    )

    assert said.returncode == 0
    landed, token, more, on_directory, on_file = said.stdout.splitlines()
    assert (token, more) == ("a token", "another")
    assert (on_directory, on_file) == ("700", "600")
    # And it is not there once the turn is over, which is the half a leak would be made of.
    assert not Path(landed).exists()


def test_a_projected_credential_is_taken_away_even_when_the_turn_failed(
    driven: Driven, tmp_path: Path
) -> None:
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "auth.json").write_text("a token\n")

    said = driven.run(
        "/bin/sh",
        "-c",
        'printf "%s\\n" "$CLAUDE_CONFIG_DIR"; exit 3',
        projects=(("CLAUDE_CONFIG_DIR", str(creds)),),
    )

    assert said.returncode == 3
    # Whatever became of the turn, the account is not left on that machine.
    assert not Path(said.stdout.strip()).exists()


def test_a_credential_is_never_written_into_the_command_line_that_carries_it(
    tmp_path: Path,
) -> None:
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "auth.json").write_text("sk-the-actual-secret\n")

    rendered = AnchorConfig(
        native=True, projects=(("CLAUDE_CONFIG_DIR", str(creds)),)
    ).command(["claude"])

    # The path is in the line, because a path is not a secret; what is in the file is not,
    # because every other user on this machine can read a command line.
    assert any(str(creds) in word for word in rendered)
    assert not any("sk-the-actual-secret" in word for word in rendered)


def test_a_variable_the_account_hushes_is_unset_on_the_target_not_merely_unsent(
    driven: Driven, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exported here, which is what a target's own shell profile would look like from this
    # side: a `local:` target inherits this process's environment the way a real one inherits
    # its own, so a variable merely left out of what is sent would still be there.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses-key")

    said = driven.run(
        "/bin/sh",
        "-c",
        'printf "[%s]\\n" "${ANTHROPIC_API_KEY-unset}"',
        hushes=("ANTHROPIC_API_KEY",),
    )

    assert said.returncode == 0
    assert said.stdout == "[unset]\n"


def test_what_the_flow_carries_is_in_the_workspace_for_the_turn_and_out_of_it_after(
    driven: Driven, tmp_path: Path
) -> None:
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: review\n---\n")

    said = driven.run(
        "/bin/sh",
        "-c",
        "cat .claude/skills/review/SKILL.md",
        carries=((str(skill), ".claude/skills/review"),),
    )

    assert said.returncode == 0
    assert "name: review" in said.stdout
    # And the directories that had to be made to hold it go with it: a turn does not leave a
    # `.claude/` behind in somebody's project.
    assert not (driven.target / ".claude").exists()


def test_what_the_flow_carries_never_writes_over_what_the_project_already_had(
    driven: Driven, tmp_path: Path
) -> None:
    theirs = driven.target / ".claude" / "skills" / "review"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("the project's own\n")
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text("the flow's\n")

    said = driven.run(
        "/bin/sh",
        "-c",
        "cat .claude/skills/review/SKILL.md",
        carries=((str(skill), ".claude/skills/review"),),
    )

    assert said.returncode == 0
    assert said.stdout == "the project's own\n"
    # Still theirs afterwards, and still where they left it: what a turn did not make, a turn
    # does not take away.
    assert (theirs / "SKILL.md").read_text() == "the project's own\n"


def test_a_turn_does_not_take_a_carried_skill_out_from_under_another_turn(
    driven: Driven, tmp_path: Path
) -> None:
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text("the flow's\n")
    carries = ((str(skill), ".claude/skills/review"),)
    at = driven.target / ".claude" / "skills" / "review"

    # One turn still running, said by leaving its claim where a second turn will find it: the
    # two are processes of their own, so the only place either can read the other is there.
    held = subprocess.Popen(
        driven.anchor(carries=carries).command(
            ["/bin/sh", "-c", "cat .claude/skills/review/SKILL.md; sleep 20"]
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    try:
        assert held.stdout is not None
        assert held.stdout.readline() == b"the flow's\n"

        # A second turn shares what the first planted, and ends first.
        said = driven.run(
            "/bin/sh", "-c", "cat .claude/skills/review/SKILL.md", carries=carries
        )

        assert said.returncode == 0
        assert said.stdout == "the flow's\n"
        # And the first turn still has it: a claim given up is not a mount taken away.
        assert (at / "SKILL.md").read_text() == "the flow's\n"
    finally:
        held.terminate()
        held.wait(timeout=PATIENCE)
    # Once the last of them is done with it, it goes -- and so does what was made to hold it.
    assert not (driven.target / ".claude").exists()


def test_what_the_flow_carries_does_not_remove_a_file_of_the_projects_in_its_way(
    driven: Driven, tmp_path: Path
) -> None:
    theirs = driven.target / ".claude" / "skills"
    theirs.mkdir(parents=True)
    # Not a directory at all, which a listing would have read as nothing being there.
    (theirs / "review").write_text("somebody's note\n")
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text("the flow's\n")

    said = driven.run(
        "/bin/sh",
        "-c",
        "cat .claude/skills/review",
        carries=((str(skill), ".claude/skills/review"),),
    )

    assert said.returncode == 0
    assert said.stdout == "somebody's note\n"
    assert (theirs / "review").read_text() == "somebody's note\n"


#: A whole native session, run in a process of its own, which then says what it had to load.
#: The tracing half is not merely unused here -- it is unreachable, and a machine whose kernel
#: or whose architecture could not have it must still be able to take a turn this way.
_WITHOUT_A_TRACER = """
import sys
from hmz.cli import main

sys.argv = ["hmz", *{argv!r}]
status = main()
loaded = sorted(
    name
    for name in sys.modules
    if name.startswith(("hmz.coganchor.linux", "hmz.coganchor.supervisor"))
    or name in ("hmz.coganchor.policy", "hmz.coganchor.shadow", "hmz.coganchor.statepaths")
)
print(status, loaded, file=sys.stderr)
"""


def test_a_turn_driven_on_the_target_reaches_nothing_that_needs_to_trace_one(
    driven: Driven,
) -> None:
    line = driven.anchor().command(["/bin/sh", "-c", "exit 0"])
    said = subprocess.run(
        [line[0], "-c", _WITHOUT_A_TRACER.format(argv=line[3:])],
        capture_output=True,
        timeout=PATIENCE,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )

    assert said.returncode == 0
    assert said.stderr.decode().strip().splitlines()[-1] == "0 []"


def test_a_driven_turn_is_marked_the_way_a_supervised_one_is(driven: Driven) -> None:
    said = driven.run(
        "/bin/sh", "-c", 'printf "%s %s\\n" "$HUMANIZE_TARGET" "$HUMANIZE_WORKSPACE"'
    )

    assert said.returncode == 0
    # Set on the target's own command line rather than sent: the target strikes out every
    # `HUMANIZE_` variable on the way in as describing the machine that sent it. And the
    # workspace arrives as the *target's* path rather than the virtual one, because that is
    # the directory the CLI is actually working in -- there being no mirror to work in.
    assert said.stdout == f"local:{driven.target} {driven.target}\n"


def _agent(anchor: AnchorConfig) -> object:
    """One claude agent whose turns land through that anchor, configured and never run.

    The real backend rather than a stand-in for it: what is being checked is the one line
    every backend funnels through, so a fake agent would be checking the fake.
    """
    from hmz.agents.claude import ClaudeCodeAgent
    from hmz.agents.config import AgentConfig
    from hmz.machines import AnchoredConfig

    return ClaudeCodeAgent(
        AgentConfig(
            model="claude-haiku-4-5",
            effort="high",
            machine=AnchoredConfig(anchor=anchor),
        )
    )


def test_a_native_turn_is_spawned_as_the_anchor_line_and_looks_for_no_local_cli() -> (
    None
):
    from hmz.agents.base import AgentBase

    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)

    rendered = agent.spawned(["claude", "--print"], "/work/sub")

    assert rendered[1:4] == ["-m", "hmz", "anchor"]
    assert "--native" in rendered
    assert "--chdir=/work/sub" in rendered
    # The CLI is named as it was written. Where claude is installed is a fact about the
    # target, and this machine's answer to it would be a path that machine never had.
    assert rendered[-2:] == ["claude", "--print"]
    assert "--installs=npm i -g @anthropic-ai/claude-code" in rendered


def test_a_supervised_turn_is_told_none_of_what_only_a_native_one_needs() -> None:
    from hmz.agents.base import AgentBase

    agent = _agent(AnchorConfig(target="docker://box"))
    assert isinstance(agent, AgentBase)

    rendered = agent.spawned(["claude", "--print"])

    assert "--native" not in rendered
    assert not [word for word in rendered if word.startswith(("--installs", "--carry"))]


def test_the_skills_a_flow_carries_are_named_to_a_native_turn_by_where_they_go() -> (
    None
):
    from hmz.agents.base import AgentBase
    from hmz.agents.skills import Loaded

    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)
    agent.loads([Loaded(name="review", at=Path("/here/flows/review"))])

    rendered = agent.spawned(["claude"])

    assert "--carry=/here/flows/review=.claude/skills/review" in rendered


def test_a_turn_offering_the_flows_callbacks_to_a_cli_on_another_machine_is_refused() -> (
    None
):
    from hmz.agents.base import AgentBase
    from hmz.agents.tools import Tool

    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)
    agent.toolbox.offers(
        1, [Tool(name="ask", about="ask the flow", call=lambda: "yes")]
    )

    with pytest.raises(ValueError, match="cannot be offered"):
        agent.spawned(["claude"])


def test_the_flows_callbacks_still_reach_a_native_turn_that_is_running_here() -> None:
    from hmz.agents.base import AgentBase
    from hmz.agents.tools import Tool

    agent = _agent(AnchorConfig(target="local", native=True))
    assert isinstance(agent, AgentBase)
    agent.toolbox.offers(
        1, [Tool(name="ask", about="ask the flow", call=lambda: "yes")]
    )

    # Nothing is refused: a `local` target is this machine, so the bridge, the socket and
    # humanize are exactly where they have always been.
    assert "--native" in agent.spawned(["claude"])


def _account(
    monkeypatch: pytest.MonkeyPatch, cli: str, at: Path, *, variables: bool = True
) -> None:
    """Puts one account in front of any agent of that CLI, keeping its files under `at`.

    Args:
      monkeypatch: What puts it there.
      cli: The backend it is an account of.
      at: Where its copies of that backend's credential files are.
      variables: Whether it also carries the account in the environment, which is what a
        gateway and a key do and what a subscription does not.
    """
    from hmz import providers
    from hmz.providers import store

    held = providers.Provider(
        cli=cli,
        name="somebody",
        way="gateway" if variables else "subscription",
        env={"ANTHROPIC_AUTH_TOKEN": "sk-x"} if variables else {},
    )

    def found(*_named: str) -> providers.Provider:
        return held

    def kept(*_named: str) -> Path:
        return at

    monkeypatch.setattr(providers, "find", found)
    monkeypatch.setattr(store, "where", kept)


def test_the_files_an_account_keeps_are_named_to_a_native_turn_by_what_points_at_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hmz.agents.base import AgentBase

    # Where the CLI keeps its own state, which its own variable moves; the shared
    # configuration directory, which one other variable moves; and the user's own home, which
    # nothing moves but `HOME`.
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / ".credentials.json").write_text("a session\n")
    (tmp_path / "config" / "anthropic").mkdir(parents=True)
    (tmp_path / "config" / "anthropic" / "key").write_text("a key\n")
    (tmp_path / "user").mkdir()
    (tmp_path / "user" / ".claude.json").write_text("{}\n")
    _account(monkeypatch, "claude", tmp_path)
    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)

    rendered = agent.spawned(["claude"])

    assert f"--project=CLAUDE_CONFIG_DIR={tmp_path / 'home'}" in rendered
    assert f"--project=XDG_CONFIG_HOME={tmp_path / 'config'}" in rendered
    # And the home is not replaced, however much of the account is kept under it. A replaced
    # home is not a projected account -- it is a different machine: the target's git identity,
    # its ssh keys and the CLI's own transcripts all live under that name, and the next turn
    # of this conversation would have nothing to resume.
    assert not [word for word in rendered if word.startswith("--project=HOME=")]


def test_what_a_native_turn_is_run_without_is_what_its_account_would_be_outranked_by(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hmz.agents.base import AgentBase

    _account(monkeypatch, "claude", tmp_path)
    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)

    rendered = agent.spawned(["claude"])

    assert "--hush=ANTHROPIC_API_KEY" in rendered
    # Except what this account set itself, which is the account the turn is meant to be on.
    assert "--hush=ANTHROPIC_AUTH_TOKEN" not in rendered
    # And it is not kept off the target either, the way a supervised turn keeps it: the CLI
    # that needs it is the one over there.
    assert "--private=ANTHROPIC_AUTH_TOKEN" not in rendered


def test_an_account_kept_only_where_nothing_can_point_a_remote_cli_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hmz.agents.base import AgentBase

    # The whole of this account is one file under the user's own home, which nothing but
    # `HOME` moves. A turn driven on the target would read the target's own copy instead,
    # which is a turn taken as whoever that machine is signed into.
    (tmp_path / "user").mkdir()
    (tmp_path / "user" / ".claude.json").write_text('{"key": "somebody else\'s"}\n')
    _account(monkeypatch, "claude", tmp_path, variables=False)
    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)

    with pytest.raises(ValueError, match="without replacing its home"):
        agent.spawned(["claude"])


def test_an_account_its_variables_carry_is_not_refused_for_what_stays_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hmz.agents.base import AgentBase

    (tmp_path / "user").mkdir()
    (tmp_path / "user" / ".claude.json").write_text("{}\n")
    _account(monkeypatch, "claude", tmp_path)
    agent = _agent(AnchorConfig(target="docker://box", native=True))
    assert isinstance(agent, AgentBase)

    # The account reaches the turn as variables, so what it also keeps at `~/.claude.json`
    # staying here is a file the turn does without rather than a turn that will not run.
    rendered = agent.spawned(["claude"])

    assert not [word for word in rendered if word.startswith("--project=")]


def test_an_account_under_a_directory_a_variable_only_half_names_is_not_projected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hmz.agents.config import AgentConfig
    from hmz.agents.opencode import OpencodeAgent
    from hmz.machines import AnchoredConfig

    # opencode keeps its state under a directory its variable names the *parent* of, so a
    # projection of it would land a level out of place and the CLI would read nothing.
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "auth.json").write_text("a token\n")
    _account(monkeypatch, "opencode", tmp_path, variables=False)
    agent = OpencodeAgent(
        AgentConfig(
            model="claude-haiku-4-5",
            effort="high",
            machine=AnchoredConfig(
                anchor=AnchorConfig(target="docker://box", native=True)
            ),
        )
    )

    with pytest.raises(ValueError, match="without replacing its home"):
        agent.spawned(["opencode"])


def test_a_backend_that_reads_no_project_skills_carries_none_of_a_flows() -> None:
    from hmz.agents.skills import Loaded, carried

    brought = [Loaded(name="review", at=Path("/here/review"))]

    assert carried("claude", brought) == (("/here/review", ".claude/skills/review"),)
    assert carried("dsh", brought) == ()
    assert carried("nothing-of-that-name", brought) == ()


@pytest.mark.parametrize(
    ("settings", "complaint"),
    [
        ({"projects": (("", "/creds"),)}, "unsupported projection"),
        ({"projects": (("HOME", "creds"),)}, "unsupported projection"),
        ({"projects": (("HO=ME", "/creds"),)}, "unsupported projection"),
        ({"carries": (("skill", "skills/one"),)}, "unsupported carry"),
        ({"carries": (("/skill", "/skills/one"),)}, "unsupported carry"),
        ({"carries": (("/skill", "../outside"),)}, "unsupported carry"),
        ({"carries": (("/skill", ""),)}, "unsupported carry"),
    ],
)
def test_a_credential_or_a_skill_bound_for_nowhere_is_refused_where_it_is_written(
    settings: dict[str, Sequence[tuple[str, str]]], complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint):
        AnchorConfig(native=True, **settings)  # pyright: ignore[reportArgumentType]
