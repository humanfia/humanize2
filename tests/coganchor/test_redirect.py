"""Paths an anchored session answers with others, which is how a turn runs as an account.

A process has one tracer, so a turn that is both anchored and run under a provider cannot be
wrapped in the provider's own supervisor: coganchor is told which paths to answer instead.
What is checked here is that both halves of that hold -- the swaps a turn is given survive the
command line it is spawned as, and the syscalls that name one of those paths really do reach
the other file, including the write-then-rename most of these CLIs save a credential with.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from humanize import cli
from humanize.coganchor import AnchorConfig
from humanize.coganchor.argv import parser, settings
from humanize.coganchor.handlers import _plant
from humanize.coganchor.linux import ptrace
from humanize.coganchor.linux.syscalls import ARCH
from humanize.coganchor.policy import Layout, Router

if TYPE_CHECKING:
    from tests.coganchor.conftest import Anchorage

#: A provider's copy of a credential and the path the CLI insists on looking at, as
#: `hmz providers` lays them out.
NAMED = "/home/me/.claude/.credentials.json"
INSTEAD = "/home/me/.humanize/providers/claude/work/home/.credentials.json"


def test_a_swap_a_turn_is_given_is_a_redirect_the_session_is_spawned_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider is read where the flow runs; the session that answers for it is elsewhere."""
    # The parser fills the token from the environment, and this round trip is about neither.
    monkeypatch.delenv("HUMANIZE_TOKEN", raising=False)
    rendered = AnchorConfig(target="ssh://build-box").command(
        ["claude"], swaps=[(NAMED, INSTEAD)]
    )

    assert f"--redirect={NAMED}={INSTEAD}" in rendered
    assert settings(parser().parse_args(rendered[4:])) == AnchorConfig(
        target="ssh://build-box", redirects=((NAMED, INSTEAD),)
    )


def test_a_turn_answers_what_the_settings_answer_as_well_as_its_own() -> None:
    """A session's own redirects are not a turn's to drop, and neither is the reverse."""
    config = AnchorConfig(redirects=(("/etc/machine-id", "/srv/borrowed-id"),))

    rendered = config.command(["claude"], swaps=[(NAMED, INSTEAD)])

    assert settings(parser().parse_args(rendered[4:])).redirects == (
        ("/etc/machine-id", "/srv/borrowed-id"),
        (NAMED, INSTEAD),
    )


@pytest.mark.parametrize(
    "said",
    ["/one-path-only", "~/.claude=/srv/creds", "/home/me/.claude=creds"],
    ids=["no second path", "a home nobody expanded", "a relative answer"],
)
def test_a_redirect_that_is_not_two_absolute_paths_is_refused(said: str) -> None:
    """Resolved against the turn's own directory, a relative answer is a different file."""
    with pytest.raises(SystemExit) as refused:
        cli.main(["anchor", "--redirect", said, "claude"])
    assert refused.value.code == 2


def test_the_python_spelling_refuses_the_redirect_the_command_line_refuses() -> None:
    """Both spellings mean the same thing, so a flow hears about it where it wrote it."""
    with pytest.raises(ValueError, match="unsupported redirect"):
        AnchorConfig(redirects=(("~/.claude", "/srv/creds"),))


def test_a_redirected_file_is_answered_and_nothing_beside_it_is() -> None:
    router = Router(
        layouts=(Layout.create("/mirror", "/project"),), redirects=((NAMED, INSTEAD),)
    )

    assert router.swap(NAMED) == INSTEAD
    assert router.swap("/home/me/.claude/settings.json") is None
    assert router.swap("/etc/passwd") is None


def test_a_redirected_directory_names_everything_inside_it() -> None:
    """The kimi CLI keeps one credential file per endpoint it has signed into, together."""
    router = Router(layouts=(), redirects=(("/home/me/.kimi", "/srv/prov/kimi"),))

    assert router.swap("/home/me/.kimi/auth/api.json") == "/srv/prov/kimi/auth/api.json"
    assert router.swap("/home/me/.kimi") == "/srv/prov/kimi"
    # A prefix that is not a directory boundary names a different file entirely.
    assert router.swap("/home/me/.kimi-code/auth.json") is None


def test_the_redirect_that_says_most_about_a_path_is_the_one_it_takes() -> None:
    router = Router(
        layouts=(),
        redirects=(("/home/me/.claude", "/srv/prov/home"), (NAMED, INSTEAD)),
    )

    assert router.swap(NAMED) == INSTEAD
    assert router.swap("/home/me/.claude/skills") == "/srv/prov/home/skills"


def test_a_path_that_cannot_be_planted_fails_rather_than_going_unanswered() -> None:
    """Left as it was, the syscall would read the credentials of whoever is at this machine."""
    buffer = (ctypes.c_ulonglong * ARCH.register_count)()
    buffer[ARCH.stack_index] = 0x7FFF_F000_0000
    registers = ptrace.Registers(buffer)
    # One past the largest pid there can be, so there is certainly nobody to write to.
    gone = int(Path("/proc/sys/kernel/pid_max").read_text())

    assert not _plant(gone, registers, 0, 1, INSTEAD)
    assert not registers.dirty


@pytest.mark.timeout(60)
def test_an_anchored_agent_reads_and_writes_the_file_it_was_answered_with(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """The whole point: the account a turn is taken as is the redirected file's, not this one's."""
    named = tmp_path / "home" / ".claude" / ".credentials.json"
    named.parent.mkdir(parents=True)
    named.write_text("whoever is at this machine\n")
    instead = tmp_path / "provider" / "home" / ".credentials.json"
    instead.parent.mkdir(parents=True)
    instead.write_text("the account this turn runs as\n")

    result = anchorage.run(
        "python3",
        "-c",
        f"path = {str(named)!r}\n"
        "print(open(path).read().strip())\n"
        "open(path, 'w').write('refreshed\\n')\n",
        redirects=((str(named), str(instead)),),
    )

    assert result.returncode == 0, result.stderr
    assert "the account this turn runs as" in result.stdout
    assert instead.read_text() == "refreshed\n"
    assert named.read_text() == "whoever is at this machine\n"


@pytest.mark.timeout(60)
def test_a_credential_written_and_renamed_into_place_lands_where_it_was_answered(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """Most of these CLIs save a token by writing a temporary file and moving it over."""
    named = tmp_path / "home" / ".claude"
    instead = tmp_path / "provider" / "home"
    instead.mkdir(parents=True)

    result = anchorage.run(
        "python3",
        "-c",
        f"import os\nheld = {str(named)!r}\n"
        "open(held + '/.credentials.json.tmp', 'w').write('fresh token\\n')\n"
        "os.rename(held + '/.credentials.json.tmp', held + '/.credentials.json')\n"
        "print(open(held + '/.credentials.json').read().strip())\n",
        redirects=((str(named), str(instead)),),
    )

    assert result.returncode == 0, result.stderr
    assert "fresh token" in result.stdout
    assert (instead / ".credentials.json").read_text() == "fresh token\n"
    # It never existed on this machine, and a rename that answered one path but not the
    # other would have had to make it.
    assert not named.exists()
