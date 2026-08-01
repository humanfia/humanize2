"""Running a program whose credentials are somewhere other than where it looks for them.

Two halves, as the module has two. The table -- which path is answered by which -- is read
here directly. The rest is the real thing: `hmz cred` spawned exactly as a turn spawns it,
with a program underneath that reads, writes, renames, lists a directory, forks, and dies of
a signal, on files that are all under `tmp_path`. Nothing here stands in for the supervisor,
because the supervisor is what there is to be wrong.

The end-to-end half needs a machine that can trace: an x86-64 Linux whose kernel will let
this process ptrace a child of its own. Whether it can is answered by running one rather than
by asking what the kernel is -- a container without `CAP_SYS_PTRACE` has every module and can
supervise nothing -- and where it cannot, those tests say so and skip.

`traced` and `cred` are imported by the login and command-line suites, which spawn the same
supervisor: this is the file the redirect is tested in, so it is the file they come from.
"""

from __future__ import annotations

import errno
import platform
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from hmz import cli
from hmz.providers import redirect

#: What the machine itself is signed in as, which a turn under a provider must never see.
MACHINE = '{"token": "the one at this machine"}'

#: What the provider is signed in as, which is what every read below has to come back with.
PROVIDER = '{"token": "the provider"}'

#: How long a supervised program is given before the run is taken to have hung.
PATIENCE = 45


def cred(
    argv: list[str], *, stdin: str = "", timeout: int = PATIENCE
) -> subprocess.CompletedProcess[str]:
    """Runs `hmz cred` as a turn under a provider runs it: its own process, on its own.

    Args:
      argv: What follows the command name -- the swaps, `--`, and the program.
      stdin: What to write to the program's standard input.
      timeout: How long to wait before taking the run to have hung.

    Returns:
      What the run came to, with its output read back.
    """
    return subprocess.run(
        [sys.executable, "-m", "hmz", "cred", *argv],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _cannot_trace() -> str:
    """Why a redirected run cannot be watched on this machine, or "" where one can.

    Answered by running one: the modules import on any Linux, and whether the kernel will
    hand over a tracee is a question only the attempt asks.
    """
    if sys.platform != "linux":
        return "a redirected run is a Linux seccomp filter and a ptrace supervisor"
    if platform.machine() != "x86_64":
        return f"the register map is x86-64 only, and this host is {platform.machine()}"
    with tempfile.TemporaryDirectory() as folder:
        named, instead = Path(folder) / "named", Path(folder) / "instead"
        named.write_text(MACHINE)
        instead.write_text(PROVIDER)
        try:
            done = cred([f"--map={named}={instead}", "--", "cat", str(named)])
        except (OSError, subprocess.SubprocessError) as why:
            return f"a supervisor could not be started here: {why}"
    if done.stdout != PROVIDER:
        return f"nothing is traced here: {done.stderr.strip() or done.returncode}"
    return ""


#: Why the end-to-end tests cannot run here, and the mark that leaves them out when so.
WITHOUT = _cannot_trace()
traced = pytest.mark.skipif(bool(WITHOUT), reason=WITHOUT or "this machine can trace")


@dataclass(frozen=True)
class Account:
    """One path a program names, and the provider's file it is answered with instead."""

    named: Path
    instead: Path

    def run(self, *argv: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        """Runs a program with this one path answered by the other."""
        return cred([f"--map={self.named}={self.instead}", "--", *argv], stdin=stdin)


@pytest.fixture
def account(tmp_path: Path) -> Account:
    """A machine signed into one account and a provider signed into another."""
    machine = tmp_path / "machine" / ".claude"
    provider = tmp_path / "provider" / "home"
    machine.mkdir(parents=True)
    provider.mkdir(parents=True)
    (machine / ".credentials.json").write_text(MACHINE)
    (provider / ".credentials.json").write_text(PROVIDER)
    return Account(machine / ".credentials.json", provider / ".credentials.json")


# ------------------------------------------------------------------ the table


def test_the_path_that_was_named_is_answered_exactly() -> None:
    swaps = redirect.Swaps.of(
        [("/house/.claude/.credentials.json", "/store/mine/creds")]
    )

    assert swaps.swap("/house/.claude/.credentials.json") == "/store/mine/creds"


def test_everything_inside_a_redirected_directory_moves_with_it() -> None:
    """Kimi keeps one file per endpoint it has signed into, so a credential is a directory."""
    swaps = redirect.Swaps.of([("/house/.kimi-code/oauth", "/store/mine/home/oauth")])

    assert swaps.swap("/house/.kimi-code/oauth/api.json") == (
        "/store/mine/home/oauth/api.json"
    )
    assert swaps.swap("/house/.kimi-code/oauth/deeper/still.lock") == (
        "/store/mine/home/oauth/deeper/still.lock"
    )


def test_the_longest_of_the_paths_that_name_one_file_is_the_one_that_answers() -> None:
    swaps = redirect.Swaps.of(
        [
            ("/house/.claude", "/store/all"),
            ("/house/.claude/.credentials.json", "/store/one/creds"),
        ]
    )

    assert swaps.swap("/house/.claude/.credentials.json") == "/store/one/creds"
    assert swaps.swap("/house/.claude/settings.json") == "/store/all/settings.json"


@pytest.mark.parametrize(
    "path",
    [
        "/house/.claudely",  # the same text, a different directory
        "/house/.claude-code/.credentials.json",
        "/etc/hosts",
        "",
        ".claude/.credentials.json",
        "relative/path",
    ],
)
def test_a_path_that_is_the_programs_own_is_left_alone(path: str) -> None:
    swaps = redirect.Swaps.of([("/house/.claude", "/store/all")])

    assert swaps.swap(path) is None


def test_a_table_that_points_nothing_anywhere_is_nothing() -> None:
    assert not redirect.Swaps.of([])
    assert not redirect.Swaps.of([("", "/store/one"), ("/house/.claude", "")])
    assert redirect.Swaps.of([("/house/.claude", "/store/one")])


def test_a_path_is_kept_the_way_the_kernel_would_read_it() -> None:
    """A trailing slash and a dot name the same file, so they must name the same swap."""
    swaps = redirect.Swaps.of([("/house/.claude/", "/store/mine/./home")])

    assert swaps.pairs == (("/house/.claude", "/store/mine/home"),)


def test_the_swaps_are_read_off_the_command_line_that_named_them() -> None:
    swaps = redirect.read(["/house/.claude=/store/mine/home", "/house/x=/store/mine/y"])

    assert swaps.swap("/house/.claude/.credentials.json") == (
        "/store/mine/home/.credentials.json"
    )
    assert swaps.swap("/house/x") == "/store/mine/y"


@pytest.mark.parametrize(
    "said", ["nonsense", "relative=/store/one", "/house/x=relative", "=/store/one"]
)
def test_a_swap_that_is_not_two_absolute_paths_is_a_line_to_correct(said: str) -> None:
    with pytest.raises(ValueError, match="is not FROM=TO"):
        redirect.read([said])


def test_the_command_names_every_swap_and_then_the_program() -> None:
    rendered = redirect.command(
        [("/house/x", "/store/y"), ("/house/.claude", "/store/mine/home")],
        ["claude", "--print"],
    )

    assert rendered == [
        sys.executable,
        "-m",
        "hmz",
        "cred",
        "--map=/house/.claude=/store/mine/home",  # longest first, as the table is
        "--map=/house/x=/store/y",
        "--",
        "claude",
        "--print",
    ]


def test_a_program_with_nothing_to_answer_is_spawned_as_itself() -> None:
    """A provider that is only variables costs no supervisor and no ptrace at all."""
    assert redirect.command([], ["claude", "--print"]) == ["claude", "--print"]
    assert redirect.command([("", "")], ("claude",)) == ["claude"]


@pytest.mark.parametrize(
    ("status", "exits"),
    [(0, 0), (7 << 8, 7), (int(signal.SIGKILL), 128 + int(signal.SIGKILL))],
)
def test_what_a_program_came_to_is_what_the_run_comes_to(
    status: int, exits: int
) -> None:
    assert redirect.failed(status) == exits


def test_a_call_that_could_not_be_answered_is_failed_rather_than_let_through() -> None:
    """A turn that read the credentials of whoever is at this machine is the wrong account."""
    assert redirect.UNSWAPPABLE == errno.EIO


# --------------------------------------------------------- the line that runs one


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["--map=/house/x=/store/y"], "no program given"),
        (["--map=relative=/store/y", "--", "true"], "is not FROM=TO"),
        (["--", "true"], "nothing to answer with anything"),
    ],
)
def test_a_line_that_could_not_be_run_is_a_line_to_correct(
    argv: list[str], says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["cred", *argv])

    assert stopped.value.code == 2
    assert says in capsys.readouterr().err


def test_a_run_that_cannot_be_supervised_does_not_run_unsupervised(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The program would read the credentials of whoever is at this machine, so it does not."""

    def refuse(*_: object) -> int:
        raise OSError("no supervisor here")

    monkeypatch.setattr("hmz.providers.redirect.run", refuse)

    assert cli.main(["cred", "--map=/house/x=/store/y", "--", "true"]) == 1
    assert "no supervisor here" in capsys.readouterr().err


@traced
def test_a_run_with_no_program_is_a_run_that_never_starts() -> None:
    with pytest.raises(ValueError, match="no program to run"):
        redirect.run(redirect.Swaps.of([("/house/x", "/store/y")]), [])


# ------------------------------------------------------------- the real thing


@traced
@pytest.mark.timeout(60)
def test_a_program_that_reads_the_path_is_given_the_providers_file(
    account: Account,
) -> None:
    done = account.run("cat", str(account.named))

    assert done.stdout == PROVIDER
    assert done.returncode == 0


@traced
@pytest.mark.timeout(60)
def test_a_shell_that_opens_the_path_itself_is_answered(account: Account) -> None:
    """No exec between the redirect and the read: the shell's own redirection is a syscall."""
    done = account.run("sh", "-c", f'read line < "{account.named}"; printf %s "$line"')

    assert done.stdout == PROVIDER


@traced
@pytest.mark.timeout(60)
def test_a_process_started_below_the_program_is_answered_too(account: Account) -> None:
    """A CLI is a program that runs programs, and the filter is inherited by every one."""
    done = account.run(
        "sh",
        "-c",
        f"{sys.executable} -c \"print(open({str(account.named)!r}).read(), end='')\"",
    )

    assert done.stdout == PROVIDER, done.stderr


@traced
@pytest.mark.timeout(60)
def test_what_a_program_writes_lands_in_the_provider(account: Account) -> None:
    """A token refreshed mid-turn is written back where it was read from."""
    done = account.run("sh", "-c", f'printf refreshed > "{account.named}"')

    assert done.returncode == 0
    assert account.instead.read_text() == "refreshed"
    assert account.named.read_text() == MACHINE


@traced
@pytest.mark.timeout(60)
def test_a_token_written_beside_the_file_and_renamed_onto_it_lands_there(
    account: Account,
) -> None:
    """Which is how these CLIs rotate one: a whole file, moved into place."""
    done = account.run(
        sys.executable,
        "-c",
        (
            "import os, sys\n"
            "beside = sys.argv[1] + '.tmp'\n"
            "open(beside, 'w').write('rotated')\n"
            "os.rename(beside, sys.argv[1])\n"
        ),
        str(account.named),
    )

    assert done.returncode == 0, done.stderr
    assert account.instead.read_text() == "rotated"
    assert account.named.read_text() == MACHINE
    # And the half-written one never touched the real store either: a name beside a credential
    # is answered as the credential is, or the new token would be written into this machine's
    # own directory on its way to the provider's.
    assert not (account.named.parent / f"{account.named.name}.tmp").exists()
    assert (account.instead.parent / f"{account.instead.name}.tmp").exists() is False


@traced
@pytest.mark.timeout(60)
def test_both_paths_of_a_rename_are_answered(tmp_path: Path) -> None:
    """Two credentials, and a call that names them both: neither may be left pointing home."""
    machine, provider = tmp_path / "machine", tmp_path / "provider"
    machine.mkdir()
    provider.mkdir()
    for name in ("one", "two"):
        (machine / name).write_text(f"{MACHINE} {name}")
        (provider / name).write_text(f"{PROVIDER} {name}")

    done = cred(
        [
            f"--map={machine / 'one'}={provider / 'one'}",
            f"--map={machine / 'two'}={provider / 'two'}",
            "--",
            sys.executable,
            "-c",
            f"import os; os.rename({str(machine / 'one')!r}, {str(machine / 'two')!r})",
        ]
    )

    assert done.returncode == 0, done.stderr
    assert (provider / "two").read_text() == f"{PROVIDER} one"
    assert not (provider / "one").exists()
    assert (machine / "one").read_text() == f"{MACHINE} one"
    assert (machine / "two").read_text() == f"{MACHINE} two"


@traced
@pytest.mark.timeout(60)
def test_a_whole_directory_moves_with_everything_inside_it(tmp_path: Path) -> None:
    """Made, written into, listed and taken away again, all at paths inside the provider."""
    machine = tmp_path / "machine" / ".kimi-code" / "oauth"
    provider = tmp_path / "provider" / "home" / "oauth"
    machine.mkdir(parents=True)
    provider.mkdir(parents=True)
    (machine / "api.json").write_text(MACHINE)
    (provider / "api.json").write_text(PROVIDER)
    swap = f"--map={machine}={provider}"

    made = cred(
        [
            swap,
            "--",
            "sh",
            "-c",
            (
                f'set -e; cat "{machine}/api.json"; mkdir "{machine}/kept"; '
                f'printf refreshed > "{machine}/kept/second.json"; ls "{machine}"'
            ),
        ]
    )

    assert made.returncode == 0, made.stderr
    assert made.stdout.startswith(PROVIDER)
    assert made.stdout[len(PROVIDER) :].split() == ["api.json", "kept"]
    assert (provider / "kept" / "second.json").read_text() == "refreshed"
    assert sorted(one.name for one in machine.iterdir()) == ["api.json"]

    gone = cred(
        [
            swap,
            "--",
            "sh",
            "-c",
            f'set -e; rm "{machine}/kept/second.json"; rmdir "{machine}/kept"',
        ]
    )

    assert gone.returncode == 0, gone.stderr
    assert not (provider / "kept").exists()
    assert provider.is_dir()


@traced
@pytest.mark.timeout(60)
def test_asking_about_the_path_answers_about_the_providers_file(tmp_path: Path) -> None:
    """Not only what is read out of it: what is asked of the name is asked of that file."""
    machine, provider = tmp_path / "machine", tmp_path / "provider"
    machine.mkdir()
    provider.mkdir()
    (machine / "creds").write_text("the machine's, which is longer")
    (provider / "creds").write_text("the provider's")
    (machine / "link").symlink_to("/elsewhere/the-machines")
    (provider / "link").symlink_to("/elsewhere/the-providers")

    done = cred(
        [
            f"--map={machine / 'creds'}={provider / 'creds'}",
            f"--map={machine / 'link'}={provider / 'link'}",
            "--",
            sys.executable,
            "-c",
            (
                "import os, sys\n"
                "print(os.stat(sys.argv[1]).st_size)\n"
                "print(os.access(sys.argv[1], os.R_OK), os.access(sys.argv[2], os.R_OK))\n"
                "print(os.readlink(sys.argv[2]))\n"
            ),
            str(machine / "creds"),
            str(machine / "link"),
        ]
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        str(len("the provider's")),
        "True False",  # the provider's link points nowhere, and is answered for as it is
        "/elsewhere/the-providers",
    ]


@traced
@pytest.mark.timeout(60)
def test_a_relative_path_opened_after_a_chdir_is_still_answered(tmp_path: Path) -> None:
    """The kernel resolves a relative path against the process's directory, and so does this."""
    machine = tmp_path / "machine" / "oauth"
    provider = tmp_path / "provider" / "oauth"
    machine.mkdir(parents=True)
    provider.mkdir(parents=True)
    (machine / "api.json").write_text(MACHINE)
    (provider / "api.json").write_text(PROVIDER)

    done = cred(
        [
            f"--map={machine}={provider}",
            "--",
            "sh",
            "-c",
            f'cd "{machine}" && cat api.json',
        ]
    )

    assert done.stdout == PROVIDER, done.stderr


@traced
@pytest.mark.timeout(60)
def test_everything_the_program_names_that_is_not_a_credential_is_its_own(
    account: Account, tmp_path: Path
) -> None:
    """Only the credentials move: the sessions, the settings and the skills stay where they are."""
    beside = account.named.parent / "settings.json"
    beside.write_text('{"theme": "the one at this machine"}')

    done = account.run("cat", str(beside), str(tmp_path / "machine" / ".claude" / "x"))

    assert '{"theme": "the one at this machine"}' in done.stdout


@traced
@pytest.mark.timeout(60)
def test_a_provider_that_was_never_signed_in_is_not_this_machines_account(
    account: Account,
) -> None:
    """The safety property: nothing there is nothing, never a quiet fall back to the real one."""
    account.instead.unlink()

    done = account.run("cat", str(account.named))

    assert done.returncode != 0
    assert MACHINE not in done.stdout
    assert "No such file" in done.stderr


@traced
@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("program", "exits"),
    [
        (["sh", "-c", "exit 7"], 7),
        (["sh", "-c", "exit 0"], 0),
        (
            [
                sys.executable,
                "-c",
                "import os, signal; os.kill(os.getpid(), signal.SIGKILL)",
            ],
            128 + int(signal.SIGKILL),
        ),
        (["/nonexistent/program"], 127),
    ],
)
def test_the_status_the_program_came_to_is_the_status_of_the_run(
    account: Account, program: list[str], exits: int
) -> None:
    assert account.run(*program).returncode == exits


@traced
@pytest.mark.timeout(60)
def test_the_program_is_given_this_lines_own_stdin_and_answers_on_its_own_streams(
    account: Account,
) -> None:
    """A login prints a code and waits to be told something, so the terminal is the program's."""
    done = account.run(
        "sh",
        "-c",
        (
            f'read said; printf "%s reading %s" "$said" "$(cat "{account.named}")"; '
            "printf trouble >&2"
        ),
        stdin="what was typed\n",
    )

    assert done.stdout == f"what was typed reading {PROVIDER}"
    assert done.stderr == "trouble"


@traced
@pytest.mark.timeout(60)
def test_two_runs_at_once_do_not_see_each_others_accounts(tmp_path: Path) -> None:
    """The whole point of the thing: one flow, one CLI, two accounts, at the same time."""
    machine = tmp_path / "machine" / ".credentials.json"
    machine.parent.mkdir(parents=True)
    machine.write_text(MACHINE)
    running: list[subprocess.Popen[str]] = []
    for name in ("first", "second"):
        instead = tmp_path / name / ".credentials.json"
        instead.parent.mkdir(parents=True)
        instead.write_text(f'{{"token": "{name}"}}')
        running.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "hmz",
                    "cred",
                    f"--map={machine}={instead}",
                    "--",
                    "sh",
                    "-c",
                    f'sleep 0.5; cat "{machine}"',
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )

    said = [one.communicate(timeout=PATIENCE) for one in running]

    assert [out for out, _ in said] == ['{"token": "first"}', '{"token": "second"}']
    assert [one.returncode for one in running] == [0, 0]
