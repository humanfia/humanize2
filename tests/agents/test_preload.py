"""The preload layer: a coding agent's own runtime, patched from inside, saying what it did.

Four of the CLIs driven here are Node programs, and Node reads `NODE_OPTIONS` before it reads
the program -- so a file of ours is in the process before the CLI has run a line, and the calls
a turn makes are functions to patch. What is checked here is the whole road: the variables the
drivers set, the socket the reports arrive on, the moments they become, and -- against a real
`node`, which is the only thing that can confirm any of it -- that a program under the preload
says what it spawned, read, wrote and opened; that the layer follows a CLI that re-execs itself
and stops at any other program; that a patched call is the call it replaced in every other way;
and that a program whose preload has nowhere to report runs exactly as it would have.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig, Hooks, Moment, Occasion
from hmz.coganchor.agents import preload as layer
from hmz.coganchor.agents.preload import RUNTIME, Watch, preloaded, reported, runtime
from hmz.coganchor.backends import named
from tests.stubs import HereAnchor, ShellAgent

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase

#: What the stand-in agents here are configured with, which nothing in this file reads.
CONFIG = AgentConfig(model="m", effort="high")

#: How long the reports of one short program are waited for. They arrive on a thread of their
#: own, after the write that carried them: generous, because what is being waited on is a whole
#: Node process starting, doing four things and exiting.
PATIENCE = 30.0


def _agent(name: str = "worker") -> ShellAgent:
    """One agent with nothing hung on it, which is an agent nobody is listening to."""
    return ShellAgent(CONFIG, name=name)


def _seen(agent: AgentBase) -> list[Occasion]:
    """Has every `PreToolUse` of this agent written down, which is what turns the layer on."""
    said: list[Occasion] = []
    agent.hooks.on(Moment.PRE_TOOL_USE, said.append)
    return said


def _waits(said: list[Occasion], many: int) -> list[Occasion]:
    """Waits for that many reports to arrive, or for the patience to run out.

    Args:
      said: Where the hook is writing them down, which another thread is appending to.
      many: How many are expected.

    Returns:
      What arrived, which is what the test then reads -- short, where they did not.
    """
    ended = time.monotonic() + PATIENCE
    while len(said) < many and time.monotonic() < ended:
        time.sleep(0.05)
    return list(said)


def _ran(
    script: str, where: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Runs one Node program with the environment the layer composed.

    Args:
      script: The program, as source.
      where: A directory of the test's own to write it in.
      env: What to run it with, on top of nothing: the variables here are the whole of it.

    Returns:
      What it came to.
    """
    import os

    file = where / "program.js"
    file.write_text(script)
    return subprocess.run(
        ["node", str(file)],
        capture_output=True,
        text=True,
        check=False,
        timeout=PATIENCE,
        env={**os.environ, **env},
    )


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"did": "spawn", "what": "git status"}', ("spawn", "git status")),
        ('{"did": "read", "what": "/work/one.py"}', ("read", "/work/one.py")),
        ('{"did": "quiet"}', ("quiet", "")),
        ('{"did": "connect", "what": 8080}', ("connect", "")),
        ("not json at all", None),
        ("[1, 2, 3]", None),
        ('{"what": "/work/one.py"}', None),
        ('{"did": "", "what": "x"}', None),
        ('{"did": 3, "what": "x"}', None),
    ],
)
def test_what_one_line_a_runtime_wrote_says_its_process_did(
    line: str, expected: tuple[str, str] | None
) -> None:
    """A report is read rather than trusted: what another program wrote may be anything."""
    assert reported(line) == expected


def test_a_runtime_that_says_what_it_did_reaches_the_agents_own_moments() -> None:
    """The whole point: a report becomes a `PreToolUse`, named after what the runtime did."""
    hooks = Hooks(frozenset(Moment), "worker")
    said: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, said.append)
    watch = Watch(hooks)
    try:
        held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        held.connect(watch.address())
        with held:
            held.sendall(
                b'{"did": "spawn", "what": "git push"}\n{"did": "write", "what": "/x"}\n'
            )
            arrived = _waits(said, 2)
    finally:
        watch.close()

    assert [(one.tool, one.about) for one in arrived] == [
        ("spawn", "git push"),
        ("write", "/x"),
    ]
    assert {one.moment for one in arrived} == {Moment.PRE_TOOL_USE}
    assert {one.agent for one in arrived} == {"worker"}


def test_a_hook_that_only_watches_one_thing_is_not_told_about_the_others() -> None:
    """Which is what naming a report after what the runtime did is for."""
    hooks = Hooks(frozenset(Moment), "worker")
    said: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, said.append, tool="spawn")
    watch = Watch(hooks)
    try:
        watch.tells('{"did": "read", "what": "/one"}')
        watch.tells('{"did": "spawn", "what": "ls"}')
    finally:
        watch.close()

    assert [one.about for one in said] == ["ls"]


def test_a_hook_that_raises_is_a_hook_that_said_nothing() -> None:
    """A flow must not fail because something watching its agent did."""
    hooks = Hooks(frozenset(Moment), "worker")

    def angry(occasion: Occasion) -> None:
        raise RuntimeError(occasion.tool)

    hooks.on(Moment.PRE_TOOL_USE, angry)
    watch = Watch(hooks)
    try:
        watch.tells(
            '{"did": "spawn", "what": "ls"}'
        )  # which is to say: this does not raise
    finally:
        watch.close()


def test_nothing_at_all_is_set_for_an_agent_nobody_is_listening_to() -> None:
    """No socket, no thread and no patched runtime: the turns are the turns they always were."""
    agent = _agent()

    assert preloaded(agent, {"KEPT": "yes"}) == {"KEPT": "yes"}


def test_the_preload_and_where_to_report_are_set_for_an_agent_with_a_hook_hung() -> (
    None
):
    """One variable carries the file, the other says where to say what it saw."""
    agent = _agent()
    _seen(agent)
    added = preloaded(agent, {"KEPT": "yes"})
    try:
        assert added["KEPT"] == "yes"
        assert added["NODE_OPTIONS"] == f"--require {runtime()}"
        assert added["HMZ_PRELOAD_AT"].endswith(".sock")
    finally:
        layer._WATCHED[agent].close()


def test_an_option_somebody_else_set_is_kept_and_added_to() -> None:
    """A `--max-old-space-size` in somebody's shell profile is theirs; this goes after it."""
    agent = _agent()
    _seen(agent)
    added = preloaded(agent, {"NODE_OPTIONS": "--max-old-space-size=2048"})
    try:
        assert (
            added["NODE_OPTIONS"] == f"--max-old-space-size=2048 --require {runtime()}"
        )
    finally:
        layer._WATCHED[agent].close()


def test_nothing_is_set_for_a_turn_that_lands_on_another_machine() -> None:
    """A socket and a file on this machine name nothing at all on that one."""
    agent = _Anchored(CONFIG, HereAnchor(target="ssh://build-box", workspace="/srv"))
    _seen(agent)

    assert preloaded(agent, {"KEPT": "yes"}) == {"KEPT": "yes"}


def test_one_listener_serves_an_agent_however_many_turns_it_takes() -> None:
    """A backend holding every conversation in one server has one runtime for all of them."""
    agent = _agent()
    _seen(agent)
    try:
        first = preloaded(agent, {})["HMZ_PRELOAD_AT"]
        assert preloaded(agent, {})["HMZ_PRELOAD_AT"] == first
    finally:
        layer._WATCHED[agent].close()


def test_the_file_a_runtime_is_told_to_load_is_found_through_the_package() -> None:
    """Through the package rather than beside a module, so an install of any shape answers.

    That it is *in* the wheel is the build backend's to do and `uv build` to show; what is
    checked here is that what asks for it asks the way that finds it either way.
    """
    from pathlib import Path

    file = Path(runtime())

    assert file.name == RUNTIME
    assert file.parent.name == "preload"
    assert file.is_file()
    assert "NODE_OPTIONS" in file.read_text()


def test_the_backends_whose_runtime_takes_one_say_so_where_facts_are_written_down() -> (
    None
):
    """Which is what `anchor:preloaded` is read off, and the only place it is said."""
    for name in ("kimi", "qwen", "mimo", "pi"):
        profile = named(name)
        assert profile is not None
        assert profile.preloads == "NODE_OPTIONS"
        assert "anchor:preloaded" in profile.tags()
    # And the ones with a runtime compiled into them, which read none of this.
    for name in ("claude", "opencode", "codex", "grok"):
        profile = named(name)
        assert profile is not None
        assert profile.preloads == ""
        assert "anchor:preloaded" not in profile.tags()


def test_a_node_program_says_what_it_spawned_wrote_read_and_opened(
    tmp_path: Path,
) -> None:
    """Against the real runtime, which is the only thing that can confirm any of this."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    touched = tmp_path / "what-the-turn-wrote.txt"
    program = f"""
const child = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");

child.execFileSync("/bin/echo", ["hello", "from", "the", "turn"]);
fs.writeFileSync({json.dumps(str(touched))}, "what the turn wrote\\n");
fs.readFileSync({json.dumps(str(touched))}, "utf8");
const socket = net.connect({{ host: "127.0.0.1", port: 9 }});
socket.on("error", () => {{}});
socket.destroy();
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 4)
    finally:
        layer._WATCHED[agent].close()

    did = {(one.tool, one.about) for one in said}
    assert ("spawn", "/bin/echo hello from the turn") in did
    assert ("write", str(touched)) in did
    assert ("read", str(touched)) in did
    assert ("connect", "127.0.0.1:9") in did


def test_the_preload_does_not_follow_a_program_into_another_program(
    tmp_path: Path,
) -> None:
    """`NODE_OPTIONS` is inherited by every process the CLI starts, and this must not be.

    Every Node program under a turn -- a package manager, a language server, a script the
    agent wrote -- reporting its own reads as the agent's work is noise, and the agent running
    it was already reported by the spawn that ran it. What that program runs in turn finds
    nothing at all, which is what the variables it was handed being taken away means.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {"NODE_OPTIONS": "--max-old-space-size=2048"})
    install, elsewhere = tmp_path / "install", tmp_path / "elsewhere"
    install.mkdir()
    elsewhere.mkdir()
    inherited = tmp_path / "what-the-other-program-had.json"
    (elsewhere / "theirs.js").write_text(f"""
const child = require("node:child_process");
require("node:fs").writeFileSync({json.dumps(str(inherited))}, JSON.stringify({{
  options: process.env.NODE_OPTIONS || "",
  at: process.env.HMZ_PRELOAD_AT || "",
  in: process.env.HMZ_PRELOAD_IN || "",
}}));
child.execFileSync("/bin/echo", ["the", "other", "program's", "own", "work"]);
""")
    program = f"""
const child = require("node:child_process");
child.execFileSync(process.execPath, [{json.dumps(str(elsewhere / "theirs.js"))}]);
"""
    try:
        ran = _ran(program, install, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
    finally:
        layer._WATCHED[agent].close()

    other = json.loads(inherited.read_text())
    # What somebody else put in the variable is still there; only the `--require` is gone.
    assert other["options"] == "--max-old-space-size=2048"
    assert other["at"] == ""
    assert other["in"] == ""
    # The spawn that started it was reported, which is how its work is accounted for -- and
    # nothing it did itself was.
    did = [one.about for one in said if one.tool == "spawn"]
    assert any("theirs.js" in one for one in did)
    assert not any("other program" in one for one in did)


def test_the_preload_follows_a_cli_that_re_execs_itself(tmp_path: Path) -> None:
    """Which is the difference between watching a turn and watching a launcher.

    qwen's entry point starts a second `node` on the bundle beside it and takes the whole turn
    there. The rule is the program rather than the process: a process started from the same
    install is still the CLI, and goes on reporting.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    (tmp_path / "again.js").write_text("""
require("node:child_process").execFileSync("/bin/echo", ["the", "turn", "itself"]);
""")
    program = f"""
const child = require("node:child_process");
child.execFileSync(process.execPath, [{json.dumps(str(tmp_path / "again.js"))}]);
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 2)
    finally:
        layer._WATCHED[agent].close()

    did = [one.about for one in said if one.tool == "spawn"]
    assert any("again.js" in one for one in did)
    assert "/bin/echo the turn itself" in did


def test_one_thing_the_program_did_is_one_report(tmp_path: Path) -> None:
    """`exec` reaches for `execFile`, which reaches for `spawn`: one command, not three."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    program = """
const child = require("node:child_process");
child.execSync("/bin/echo once");
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
        time.sleep(
            0.5
        )  # long enough for a second report to have arrived, had there been one
    finally:
        layer._WATCHED[agent].close()

    assert [one.about for one in said if one.tool == "spawn"] == ["/bin/echo once"]


def test_a_patched_call_is_the_call_it_replaced_in_every_other_way(
    tmp_path: Path,
) -> None:
    """A patch is not allowed to change what the program it is inside of does.

    `util.promisify` reads a symbol off `exec` and `execFile` saying what their promised form
    answers with -- `{ stdout, stderr }` rather than the first thing the callback was given --
    and a patch that dropped it would leave `const { stdout } = await exec(...)` undefined,
    which is a CLI broken by something that was only supposed to be watching it.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    answered = tmp_path / "what-the-promise-answered.json"
    program = f"""
const child = require("node:child_process");
const fs = require("node:fs");
const promised = require("node:util").promisify(child.exec);
promised("/bin/echo promised").then((answer) => {{
  fs.writeFileSync({json.dumps(str(answered))}, JSON.stringify({{
    stdout: answer.stdout,
    named: child.exec.name,
  }}));
}});
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
    finally:
        layer._WATCHED[agent].close()

    answer = json.loads(answered.read_text())
    assert answer["stdout"] == "promised\n"
    assert answer["named"] == "exec"
    assert [one.about for one in said if one.tool == "spawn"] == ["/bin/echo promised"]


def test_a_program_whose_preload_has_nowhere_to_report_runs_as_it_would_have(
    tmp_path: Path,
) -> None:
    """Fail open. This file runs inside somebody else's program, and must never end one."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    ran = _ran(
        'console.log("the turn ran");',
        tmp_path,
        {
            "NODE_OPTIONS": f"--require {runtime()}",
            "HMZ_PRELOAD_AT": str(tmp_path / "nothing" / "is" / "listening.sock"),
        },
    )

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "the turn ran"


def test_a_program_that_was_never_meant_to_report_loads_it_and_says_nothing(
    tmp_path: Path,
) -> None:
    """Any Node program on the machine may find this file; one with nowhere named is silent.

    Which is what keeps a `node` somebody runs by hand, with this still in their environment
    from a flow that has ended, from connecting to anything.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    hooks = Hooks(frozenset(Moment), "worker")
    said: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, said.append)
    watch = Watch(hooks)
    try:
        at = watch.address()
        ran = _ran(
            'require("node:child_process").execFileSync("/bin/echo", ["unwatched"]);',
            tmp_path,
            {"NODE_OPTIONS": f"--require {runtime()}"},
        )
        assert ran.returncode == 0, ran.stderr
        assert at  # there was somewhere to report to, and nothing was told where it was
        time.sleep(0.5)  # long enough for a report to have arrived, had one been made
    finally:
        watch.close()

    assert said == []


def test_a_cli_that_re_execs_itself_out_of_another_install_is_still_the_cli(
    tmp_path: Path,
) -> None:
    """The rule is the package rather than the path, because the path is not stable.

    qwen's entry point runs whichever copy of itself its own updater has put under the user's
    home in preference to the one beside it -- a different directory entirely, and the same
    program. A rule written in paths would stop watching there, which is the half of the turn
    that does the work.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    install, updated = tmp_path / "install", tmp_path / "updated"
    install.mkdir()
    updated.mkdir()
    for where in (install, updated):
        (where / "package.json").write_text(json.dumps({"name": "@some/cli"}))
    (updated / "newer.js").write_text("""
require("node:child_process").execFileSync("/bin/echo", ["the", "newer", "copy"]);
""")
    program = f"""
const child = require("node:child_process");
child.execFileSync(process.execPath, [{json.dumps(str(updated / "newer.js"))}]);
"""
    try:
        ran = _ran(program, install, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 2)
    finally:
        layer._WATCHED[agent].close()

    assert "/bin/echo the newer copy" in [
        one.about for one in said if one.tool == "spawn"
    ]


def test_what_a_cli_reads_and_writes_of_its_own_install_is_not_the_turns_work(
    tmp_path: Path,
) -> None:
    """What the CLI is is not what the CLI did.

    A bundle loading itself is thousands of reads and not one of them is the agent doing
    anything; a file beside the work is the turn.
    """
    if shutil.which("node") is None:
        pytest.skip("node is not installed here")
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    install, work = tmp_path / "install", tmp_path / "work"
    install.mkdir()
    work.mkdir()
    (install / "package.json").write_text(json.dumps({"name": "@some/cli"}))
    (install / "its-own.txt").write_text("part of the program\n")
    (work / "the-turns.txt").write_text("part of the work\n")
    program = f"""
const fs = require("node:fs");
fs.readFileSync({json.dumps(str(install / "its-own.txt"))}, "utf8");
fs.readFileSync({json.dumps(str(work / "the-turns.txt"))}, "utf8");
"""
    try:
        ran = _ran(program, install, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
        time.sleep(
            0.5
        )  # long enough for the other read to have arrived, had it been said
    finally:
        layer._WATCHED[agent].close()

    read = [one.about for one in said if one.tool == "read"]
    assert str(work / "the-turns.txt") in read
    assert str(install / "its-own.txt") not in read


class _Anchored(ShellAgent):
    """An agent whose turns land on a machine that is not this one."""

    def __init__(self, config: AgentConfig, anchor: HereAnchor) -> None:
        super().__init__(config)
        self._held = anchor

    @property
    def anchor(self) -> HereAnchor:
        return self._held
