"""A process holding a run is not one an agent's ``pkill -f`` can reach by the prompt."""

from __future__ import annotations

import subprocess
import sys

import pytest

from hmz import proctitle

#: Text that would sit on ``hmz``'s command line -- a prompt naming a test file -- and that
#: an agent is likely to feed ``pkill -f`` when it cleans up after running that file.
PROMPT = "run pytest tests/test_sentinel_for_proctitle.py and keep it green"

_SHOW = (
    "import sys\n"
    "from hmz.proctitle import named\n"
    "named(sys.argv[1])\n"
    "print(open('/proc/self/cmdline', 'rb').read().replace(b'\\0', b' ').decode())\n"
    "print(open('/proc/self/comm').read().strip())\n"
    "print(' '.join(sys.argv))\n"
)

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="reads /proc")


@linux_only
def test_other_processes_see_the_command_and_not_the_prompt() -> None:
    # The child starts with the prompt on its command line, as ``hmz exec`` does, and renames
    # itself the way ``hmz.cli.main`` does. What ``pkill -f`` would then match against is
    # what the operating system shows, read back from /proc by the process itself.
    said = subprocess.run(
        [sys.executable, "-c", _SHOW, "exec", PROMPT],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    cmdline, comm, argv = said.stdout.splitlines()
    assert "pytest tests/test_sentinel_for_proctitle.py" not in cmdline
    assert cmdline.strip() == "hmz exec"
    # The short name ``pkill NAME`` goes by is the program too, not the interpreter.
    assert comm == "hmz exec"
    # And the process's own view of its arguments is what it was started with: argparse
    # reads sys.argv, and sys.argv is not what was renamed.
    assert PROMPT in argv


@linux_only
def test_the_interface_is_named_by_the_program_alone() -> None:
    said = subprocess.run(
        [sys.executable, "-c", _SHOW, "", PROMPT],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert said.stdout.splitlines()[0].strip() == "hmz"


def test_a_machine_without_the_library_keeps_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A name is a courtesy; a run must not be spent on one.
    monkeypatch.setitem(sys.modules, "setproctitle", None)
    proctitle.named("exec")  # raises nothing


class _Hmz:
    """An `Hmz` whose run is the moment it is asked for: what is checked is the order."""

    def __init__(self, seen: list[str]) -> None:
        self.seen = seen

    def reports(self) -> None:
        pass

    def read(self, argv: list[str]) -> tuple[str, list[str], str, None, None]:
        self.seen.append("read")
        return "flow", [], argv[-1], None, None

    def run(self, *_args: object, **_kwargs: object) -> _Running:
        return _Running(self.seen)


class _Running:
    def __init__(self, seen: list[str]) -> None:
        self.seen = seen

    def run(self) -> None:
        self.seen.append("run")


def test_exec_renames_once_it_has_read_its_line_and_before_it_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hmz.sdk
    from hmz import cli

    seen: list[str] = []
    monkeypatch.setattr(hmz.sdk, "Hmz", lambda: _Hmz(seen))

    def named(command: str = "") -> None:
        seen.append(f"named {command}")

    monkeypatch.setattr(proctitle, "named", named)
    assert cli.main(["exec", "-f", "rlar", PROMPT]) == 0
    # After the line is read -- a line that is wrong is refused with the task still showing,
    # which is fine, nothing runs -- and before the first agent could start.
    assert seen == ["read", "named exec", "run"]
