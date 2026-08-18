"""Callbacks of a flow's own, put in front of a coding agent as tools it may reach for.

What is checked is the whole road: the protocol answered a message at a time, the socket a
toolbox serves it on, the bridge a CLI actually runs, and the one thing that makes any of it
worth having -- that the callback runs in *this* process, so a tool can reach whatever the
flow can reach.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, Field

from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    Tool,
    Toolbox,
)
from hmz.agents import codex as appservers
from hmz.agents.tools import PROTOCOL, serve
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.agents import AgentConfig


class Asked(BaseModel):
    """What the tool under test is called with."""

    task: str = Field(description="what to have it do")
    times: int = 1


def _tool(seen: list[Asked]) -> Tool:
    """A callback that writes down what it was called with and answers."""

    def called(said: Asked) -> str:
        seen.append(said)
        return f"did {said.task} {said.times}x"

    return Tool(
        name="delegate",
        about="hand a task to another flow and wait for what it comes to",
        takes=Asked,
        call=called,
    )


def _another(named: str) -> Tool:
    """A second callback, under a name of its own, built afresh each time it is asked for.

    Which is what an ordinary flow does: the tools it offers before a turn are the tools it
    just wrote down, so two turns offering the same thing are offering two objects.
    """
    return Tool(
        name=named,
        about="hand the work back to whoever asked for it",
        call=lambda: "handed back",
    )


def _sent(method: str, marked: int = 1, **given: object) -> str:
    """One message of the protocol, as a line."""
    return json.dumps(
        {"jsonrpc": "2.0", "id": marked, "method": method, "params": given}
    )


def test_the_protocol_says_who_it_is_and_what_it_has() -> None:
    """The four methods a CLI actually calls, and nothing else pretending to be there."""
    seen: list[Asked] = []
    offered = (_tool(seen),)

    said = serve(_sent("initialize"), lambda: offered)
    assert said is not None
    assert said["result"]["protocolVersion"] == PROTOCOL
    assert said["result"]["capabilities"]["tools"] == {"listChanged": False}

    listed = serve(_sent("tools/list"), lambda: offered)
    assert listed is not None
    (one,) = listed["result"]["tools"]
    assert one["name"] == "delegate"
    assert "hand a task" in one["description"]
    # The model is the whole of what the agent is told about the arguments.
    assert (
        one["inputSchema"]["properties"]["task"]["description"] == "what to have it do"
    )
    assert one["inputSchema"]["required"] == ["task"]


def test_a_notification_is_not_answered() -> None:
    """A message with no id has nowhere for an answer to go, and one is not made up."""
    assert (
        serve(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}), tuple
        )
        is None
    )
    assert serve("this is not json at all", tuple) is None


def test_calling_one_runs_the_callback_and_answers_with_what_it_said() -> None:
    """Which is the whole feature: the agent reached for it, and the flow's code ran."""
    seen: list[Asked] = []
    offered = (_tool(seen),)

    said = serve(
        _sent("tools/call", name="delegate", arguments={"task": "read", "times": 2}),
        lambda: offered,
    )

    assert said is not None
    assert said["result"]["isError"] is False
    assert said["result"]["content"] == [{"type": "text", "text": "did read 2x"}]
    assert [(one.task, one.times) for one in seen] == [("read", 2)]


def test_a_callback_that_raised_is_the_tool_failing_and_not_the_flow() -> None:
    """A flow must not end because a model called one of its tools wrongly."""

    def up(_said: Asked) -> str:
        raise KeyError("task")

    offered = (Tool(name="one", about="a tool", takes=Asked, call=up),)

    said = serve(
        _sent("tools/call", name="one", arguments={"task": "x"}), lambda: offered
    )

    assert said is not None
    assert said["result"]["isError"] is True
    # In words the model can act on: `KeyError('task')` alone says nothing.
    assert "KeyError" in said["result"]["content"][0]["text"]


def test_a_tool_nothing_answers_to_is_refused_rather_than_invented() -> None:
    """And so is a method: a server that answered everything would answer wrongly."""
    said = serve(_sent("tools/call", name="nonesuch", arguments={}), tuple)
    assert said is not None
    assert "no tool called" in said["error"]["message"]

    beyond = serve(_sent("resources/list"), tuple)
    assert beyond is not None
    assert "not something humanize serves" in beyond["error"]["message"]


def test_a_toolbox_starts_nothing_until_something_is_offered() -> None:
    """An agent whose flow hands it no callbacks pays for none of this."""
    box = Toolbox()
    try:
        assert box.empty()
        assert box.offered() == ()
        box.offers(1, [_tool([])])
        assert not box.empty()
        assert [one.name for one in box.offered()] == ["delegate"]
        # And taking it back is the conversation that offered it saying nothing.
        box.offers(1, [])
        assert box.empty()
    finally:
        box.close()


def test_two_conversations_offering_one_name_are_offering_one_tool() -> None:
    """A CLI has one list of tools, so the agent's list is what it is told about."""
    box = Toolbox()
    try:
        box.offers(1, [_tool([])])
        box.offers(
            2, [_tool([]), Tool(name="other", about="another", call=lambda: "x")]
        )
        assert [one.name for one in box.offered()] == ["delegate", "other"]
    finally:
        box.close()


def _says(said: str) -> Tool:
    """One round's callback, closing over what that round would answer with."""
    return Tool(name="review", about="read what this round wrote", call=lambda: said)


def test_a_conversation_let_go_of_takes_back_what_it_was_offering() -> None:
    """A loop that opens a session a round and drops it closes none of them.

    So the taking back cannot be a line in `close`: a callback still in front of the agent
    after the conversation that offered it is over is one the flow can no longer see the point
    of -- and an agent that goes on being offered something is an agent every later turn of
    which is started knowing about it.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))
    session = agent.new()
    session.offers([_tool([])])
    assert not agent.toolbox.empty()

    del session
    gc.collect()

    assert agent.toolbox.empty()
    assert agent.toolbox.offered() == ()


def test_a_round_that_is_over_stops_answering_for_the_one_that_replaced_it() -> None:
    """Two conversations offering one name are offering one tool, and it is the live one's.

    Which is what a loop offering a callback per round is: each round's closes over that
    round. A round that is over going on being offered would have the agent reach for the
    first one anybody wrote, an hour after the state it closed over stopped being true.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))
    first = agent.new()
    first.offers([_says("round 0")])
    second = agent.new()  # the next round, opened before the one before it is let go of
    second.offers([_says("round 1")])

    del first
    gc.collect()

    (one,) = agent.toolbox.offered()
    assert one.call() == "round 1"


def test_a_conversation_closed_takes_them_back_once_however_often_it_is_closed() -> (
    None
):
    """The close and the collection are one taking back, done by whichever gets there first."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))
    session = agent.new()
    session.offers([_tool([])])

    session.close()
    session.close()

    assert agent.toolbox.empty()
    assert session.tools == ()
    # And a conversation that is spoken to again is one that may offer again.
    session.offers([_tool([])])
    assert not agent.toolbox.empty()


#: A client that speaks the protocol down a pipe the way one of these CLIs does: it starts the
#: bridge, says hello, asks what there is, calls one, and prints what came back.
_CLIENT = """
import json, subprocess, sys

argv = json.loads(sys.argv[1])
with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      text=True, bufsize=1) as talking:
    def ask(marked, method, **given):
        talking.stdin.write(json.dumps({"jsonrpc": "2.0", "id": marked,
                                        "method": method, "params": given}) + "\\n")
        talking.stdin.flush()
        return json.loads(talking.stdout.readline())

    ask(1, "initialize")
    listed = ask(2, "tools/list")
    called = ask(3, "tools/call", name="delegate",
                 arguments={"task": "the thing", "times": 3})
    print(json.dumps({"listed": [one["name"] for one in listed["result"]["tools"]],
                      "said": called["result"]["content"][0]["text"]}))
    talking.stdin.close()
"""


@pytest.mark.timeout(60)
def test_a_cli_reaches_the_callback_through_the_bridge_it_is_told_to_run(
    tmp_path: Path,
) -> None:
    """The whole road, in two processes: the callback runs here and the agent reads it there.

    Which is the point of the bridge. A tool server started as a program of its own would be
    a subprocess with none of the flow's variables in it; this one is a relay, so the
    function that runs is the one the flow wrote, on this interpreter, in this process.
    """
    seen: list[Asked] = []
    box = Toolbox()
    here = threading.current_thread().ident
    ran: list[int] = []

    def called(said: Asked) -> str:
        seen.append(said)
        ran.append(os.getpid())
        return f"did {said.task} {said.times}x"

    box.offers(
        1,
        [Tool(name="delegate", about="hand a task on", takes=Asked, call=called)],
    )
    try:
        client = tmp_path / "client.py"
        client.write_text(_CLIENT)
        done = subprocess.run(
            [sys.executable, str(client), json.dumps(box.command())],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    finally:
        box.close()

    assert done.returncode == 0, done.stderr
    said = json.loads(done.stdout.strip().splitlines()[-1])
    assert said["listed"] == ["delegate"]
    assert said["said"] == "did the thing 3x"
    # And it ran here rather than in either of the two processes that carried the message.
    assert [(one.task, one.times) for one in seen] == [("the thing", 3)]
    assert ran == [os.getpid()]
    assert here is not None


#: A `claude --print` that writes down how it was started and answers whatever it is told.
_CLAUDE = """
import json, pathlib, sys

pathlib.Path(LOG).open("a").write(json.dumps(sys.argv[1:]) + "\\n")
flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}),
      flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": said}), flush=True)
"""


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in `claude` on PATH, writing down each command line it was started with."""
    log = tmp_path / "starts.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{_CLAUDE.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    return log


def _starts(log: Path) -> list[list[str]]:
    """Every command line the stand-in was started with."""
    return [json.loads(line) for line in log.read_text().splitlines()]


@pytest.mark.timeout(60)
def test_claude_is_told_about_the_callbacks_on_its_own_command_line(
    claude: Path,
) -> None:
    """A server on the flag rather than a line written into anybody's settings file."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high")
    ).new()
    session.offers([_tool([])])

    assert session("hello") == "hello"

    (argv,) = _starts(claude)
    held = json.loads(argv[argv.index("--mcp-config") + 1])
    assert list(held["mcpServers"]) == ["humanize"]
    assert held["mcpServers"]["humanize"]["args"][:2] == ["-m", "hmz"]
    # And what the person at this machine has configured is left alone: adding ours is not
    # the same as taking theirs away.
    assert "--strict-mcp-config" not in argv


@pytest.mark.timeout(60)
def test_offering_one_between_two_turns_starts_a_claude_that_knows_about_it(
    claude: Path,
) -> None:
    """A process that was started without it was never told the tool exists."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high")
    ).new()

    session("first")
    session.offers([_tool([])])
    session("second")

    first, second = _starts(claude)
    assert "--mcp-config" not in first
    assert "--mcp-config" in second
    # The same conversation, carried on: the process ended, not the session.
    assert second[second.index("--resume") + 1] == session.id


@pytest.mark.timeout(60)
def test_swapping_one_callback_for_another_starts_a_claude_told_about_the_new_one(
    claude: Path,
) -> None:
    """Claude reads what a tool server has once, so a list that moved is a list it never saw.

    The tool that arrived would be nowhere on its list, and the one that left would still be
    on it -- so reaching for that one comes back as there being no such tool. Silent both
    ways, which is why what is compared is the list the process was told and not whether it
    was told anything.
    """
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high")
    ).new()

    session.offers([_tool([])])
    session("first")
    session.offers([_another("escalate")])
    session("second")

    first, second = _starts(claude)
    assert "--mcp-config" in first
    assert "--mcp-config" in second
    # The same conversation, carried on: the process ended, not the session.
    assert second[second.index("--resume") + 1] == session.id
    # And what the new one enumerates is the offer as it stands: the one that arrived, and
    # not the one that was taken back. Asked of the server the command line points at, which
    # is where the process about to be started would ask it.
    listed = serve(_sent("tools/list"), session._agent.toolbox.offered)
    assert listed is not None
    assert [one["name"] for one in listed["result"]["tools"]] == ["escalate"]
    assert [one.name for one in session.tools] == ["escalate"]


@pytest.mark.timeout(60)
def test_offering_an_equal_list_again_leaves_the_claude_that_is_up_alone(
    claude: Path,
) -> None:
    """A flow that writes its tools out before every turn is offering one list, not many.

    Compared by what the tools are called rather than by which objects they are: a callback
    is a closure, so two equal lists share no object and are not even equal as values, and a
    process ended for that would be a process ended every turn of the flow.
    """
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high")
    ).new()

    session.offers([_tool([]), _another("escalate")])
    session("first")
    session.offers([_another("escalate"), _tool([])])
    session("second")

    (argv,) = _starts(claude)
    assert "--mcp-config" in argv


@pytest.mark.timeout(60)
def test_swapping_one_callback_for_another_starts_a_codex_server_told_about_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An app server enumerates its tool servers where it is started, exactly as Claude does.

    It is the agent's rather than the session's, so what a changed offer costs here is every
    live conversation of that agent going on in a server started afresh -- which is the price
    of the model being told the truth about what it may reach for.
    """
    started: list[list[str]] = []

    class _Recording:
        """A stand-in app server, which writes down how it would have been started."""

        def __init__(
            self, argv: list[str], env: Mapping[str, str] | None = None
        ) -> None:
            del env
            started.append(argv)
            self._held: list[Any] = []

        def stop(self) -> None:
            """Nothing was started, so there is nothing to take down."""

    monkeypatch.setattr(appservers, "_AppServer", _Recording)
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high"))
    session = agent.new()
    try:
        session.offers([_tool([])])
        assert agent.server is not None
        session.offers([_another("escalate")])
        assert agent.server is not None
        # And the same offer written out again is the same offer: nothing moved, so the
        # server holding this agent's conversations goes on holding them.
        session.offers([_another("escalate")])
        assert agent.server is not None
    finally:
        agent.toolbox.close()

    first, second = started
    assert any(one.startswith("mcp_servers.humanize.command=") for one in first)
    assert any(one.startswith("mcp_servers.humanize.command=") for one in second)


def test_a_backend_with_no_way_of_being_told_refuses_a_callback() -> None:
    """A tool the model never sees would be a flow that quietly does not do what it says."""
    from hmz.agents import AgentConfig as Config

    said: AgentConfig = Config(model="m", effort="high")
    session = ShellAgent(said).new()

    assert not type(session).takes_tools
    with pytest.raises(NotImplementedError, match="no way of being given a tool"):
        session.offers([_tool([])])
    # And saying it offers nothing is not something to refuse: it was already offering none.
    session.offers(None)


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_real_claude_connects_to_the_flow_and_lists_its_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole road against the real CLI: it connects, and our callback is on its list.

    No model is asked anything -- the key is deliberately wrong, and the turn fails at the
    door -- so this costs nothing. What it pins is the half a stand-in cannot: that the
    inline `--mcp-config` humanize writes is the shape Claude actually reads, and that what
    it starts talks to this process.
    """
    import shutil

    if shutil.which("claude") is None:
        pytest.skip("claude is not installed here")
    monkeypatch.chdir(tmp_path)
    box = Toolbox()
    box.offers(1, [_tool([])])
    try:
        done = subprocess.run(
            [
                "claude",
                "--print",
                "--output-format",
                "stream-json",
                "--verbose",
                "--mcp-config",
                json.dumps(box.config()),
                "--model",
                "claude-opus-5",
                "say ok",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            # A home of its own and a key that is not one: nothing of this machine's account
            # is read, and no turn of any model is taken.
            env=dict(os.environ)
            | {"ANTHROPIC_API_KEY": "not-a-key", "HOME": str(tmp_path)},
            check=False,
        )
    finally:
        box.close()

    said = json.loads((done.stdout or "{}").splitlines()[0])
    assert said.get("mcp_servers") == [{"name": "humanize", "status": "connected"}]
    assert "mcp__humanize__delegate" in said.get("tools", [])


def test_the_bridge_runs_here_for_an_agent_whose_turns_land_elsewhere() -> None:
    """Everything a CLI spawns under an anchor goes to the target unless it is named.

    The socket is in this process, so a bridge started on the target would find no socket and
    no humanize -- and the flow would lose its callbacks without anything looking wrong.
    """
    from hmz.machines import AnchoredConfig
    from tests.stubs import HereAnchor

    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(
            model="claude-opus-5",
            effort="high",
            machine=AnchoredConfig(anchor=HereAnchor(target="tcp://stub:0")),
        )
    )
    # Nothing offered, nothing named: an agent whose flow hands it no callbacks is anchored
    # exactly as it always was.
    assert agent.anchor is not None
    before = agent.anchor.local_execs
    assert agent._reaching(agent.anchor) is agent.anchor

    # Held for as long as the offer is asked about: what a conversation nobody holds any more
    # was offering is taken back with it.
    session = agent.new()
    session.offers([_tool([])])
    try:
        held = agent.toolbox.command()[0]
        assert held not in before
        # The anchor a turn is actually spawned under names it, and the one the agent holds
        # is left as it was: what a turn reaches is a turn's business.
        assert agent._reaching(agent.anchor).local_execs == (*before, held)
        assert agent.anchor.local_execs == before
    finally:
        agent.toolbox.close()
