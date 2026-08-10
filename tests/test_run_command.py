"""The command line: a flow file, the agents it declares, and the task they are given.

Nothing here drives a real agent. A flow is handed agents and decides for itself whether to
launch anything, so a flow that only writes down what it was given exercises the whole path
from the command line to the entry point without a turn being run.
"""

from __future__ import annotations

import json
import re
import runpy
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest

from hmz.agents import PERMISSIONS, AgentConfig
from hmz.cli import main
from hmz.flows import ENTRY, NotAFlow
from hmz.runner import Runner
from tests.stubs import ShellAgent, written

#: A flow that drives nothing and writes down what it was handed, next to its own file. AGENTS
#: is filled in per test: what a flow declares there is how many agents it takes.
RECORD = """
import json
import os
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AGENTS], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [
                    [type(a).__name__, a.config.model, a.config.effort, a.id] for a in agents
                ],
                "held": type(agents).__name__,
                "task": task,
                "cwd": os.getcwd(),
            }
        )
    )
"""

#: A flow that writes down which account each of its agents was configured to run as, which
#: is what an `-a` naming a provider has to reach.
ACCOUNTS = """
import json
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps([agent.config.provider for agent in agents])
    )
"""

#: A flow that writes down the permission rung each agent was configured to run at.
ACCESS = """
import json
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps([agent.config.permission for agent in agents])
    )
"""

#: A flow proving that one backend-native command-line setting reaches the
#: concrete Claude config rather than being treated as a Codex override.
CLAUDE_NATIVE_CONFIG = """
import json
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(list(agents[0].config.allowed_tools))
    )
"""

#: One common provider-latency setting reaches both supported backend configs.
SERVICE_TIER_CONFIG = """
import json
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps([agent.config.service_tier for agent in agents])
    )
"""

#: The same flow, declaring its agents as a named tuple: as many as there are places, and what
#: each of them is for. It reaches them by name to prove it was handed the type it asked for.
NAMED = """
import json
import os
from pathlib import Path
from typing import NamedTuple

from hmz.agents import AgentBase
from hmz.flows import flow


class Agents(NamedTuple):
    builder: AgentBase
    reviewer: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [[agents.builder.id], [agents.reviewer.id]],
                "held": type(agents).__name__,
                "task": task,
                "cwd": os.getcwd(),
            }
        )
    )
"""

#: A flow that declares its agents where only a type checker looks, which is nowhere the count
#: it declares can be read back from.
UNREADABLE = """
from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.flows import flow

if TYPE_CHECKING:
    from hmz.agents import AgentBase


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""

#: The flows humanize ships, each of which shows the line that would start it. A flow is a
#: directory with an `__init__.py` in it or a file of its own, and these are looked for as
#: both: a glob for one shape is a list that quietly empties the day a flow takes the other.
PREBUILT = sorted(
    (
        path if path.is_file() else path / "__init__.py"
        for path in (
            Path(__file__).resolve().parents[1] / "src/hmz/flows/builtin"
        ).glob("*")
        if not path.name.startswith("_")
        and (path.suffix == ".py" or (path / "__init__.py").is_file())
    ),
    key=lambda path: path.parts,
)


def _named(flow: Path) -> str:
    """What a shipped flow is called, which is its directory where the file is an init."""
    return flow.parent.name if flow.name == "__init__.py" else flow.stem


def _flow(tmp_path: Path, source: str) -> str:
    """Writes a flow file and returns its path, as the command line would be given it."""
    path = tmp_path / "flow.py"
    path.write_text(source)
    return str(path)


def _seen(tmp_path: Path) -> dict[str, Any]:
    """Reads back what the flow written by :data:`RECORD` was handed."""
    return json.loads((tmp_path / "flow.json").read_text())


def test_it_drives_the_flow_with_the_agents_the_command_line_names(
    tmp_path: Path,
) -> None:
    """A model may hold slashes of its own, so only the backend and the effort are split off."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            "claude/claude-opus-4-8:high",
            "-a",
            "kimi/kimi-code/k3:swarmmax",
            "fix the build",
        ]
    )
    seen = _seen(tmp_path)
    assert [agent[:3] for agent in seen["agents"]] == [
        ["ClaudeCodeAgent", "claude-opus-4-8", "high"],
        ["KimiCodeCLIAgent", "kimi-code/k3", "swarmmax"],
    ]
    assert seen["task"] == "fix the build"
    assert seen["held"] == "tuple"  # a flow unpacks what it was promised


def test_one_option_is_one_agent_however_it_is_written(tmp_path: Path) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase, AgentBase"))
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            "cli=claude,model=m,effort=high",
            "-a",
            "codex/m:high",
            "-a",
            "kimi/m:high",
            "task",
        ]
    )
    assert [agent[0] for agent in _seen(tmp_path)["agents"]] == [
        "ClaudeCodeAgent",
        "CodexAgent",
        "KimiCodeCLIAgent",
    ]


def test_an_agent_may_be_told_which_account_to_run_as(tmp_path: Path) -> None:
    """One flow, one CLI, two accounts: which is the whole reason a provider has a name."""
    flow = _flow(tmp_path, ACCOUNTS)
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            "claude@subscription/claude-opus-5:high",
            "-a",
            "cli=claude,model=claude-opus-5,effort=high,provider=deepseek",
            "task",
        ]
    )
    assert json.loads((tmp_path / "flow.json").read_text()) == [
        "subscription",
        "deepseek",
    ]


def test_an_agent_that_names_no_account_runs_as_this_machine_does(
    tmp_path: Path,
) -> None:
    flow = _flow(tmp_path, ACCOUNTS)
    main(["exec", "-f", flow, "-a", "claude/m:high", "-a", "codex/m:high", "task"])
    assert json.loads((tmp_path / "flow.json").read_text()) == ["", ""]


@pytest.mark.parametrize("permission", PERMISSIONS)
def test_an_agent_may_be_given_a_permission_rung(
    tmp_path: Path, permission: str
) -> None:
    """Each `-a` carries its own rung, and omitting it keeps the existing default."""
    flow = _flow(tmp_path, ACCESS)
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            f"cli=codex,model=m,effort=high,permission={permission}",
            "-a",
            "claude/m:high",
            "task",
        ]
    )

    assert json.loads((tmp_path / "flow.json").read_text()) == [permission, "bypass"]


def test_a_claude_agent_receives_its_native_allowed_tools_rule(
    tmp_path: Path,
) -> None:
    flow = _flow(tmp_path, CLAUDE_NATIVE_CONFIG)
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            ("cli=claude,model=m,effort=high,config.allowed_tools=Bash(git diff *)"),
            "task",
        ]
    )
    assert json.loads((tmp_path / "flow.json").read_text()) == ["Bash(git diff *)"]


def test_one_service_tier_setting_reaches_claude_and_codex(tmp_path: Path) -> None:
    flow = _flow(tmp_path, SERVICE_TIER_CONFIG)
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            "cli=claude,model=m,effort=max,service_tier=fast",
            "-a",
            "cli=codex,model=m,effort=max,service_tier=fast",
            "task",
        ]
    )
    assert json.loads((tmp_path / "flow.json").read_text()) == ["fast", "fast"]


def test_a_named_tuple_says_what_each_agent_is_for_as_well_as_how_many(
    tmp_path: Path,
) -> None:
    """A flow that named its agents is handed the type it asked for, and they answer to it."""
    from hmz.flows import drives

    flow = _flow(tmp_path, NAMED)
    assert drives(flow) == ("builder", "reviewer")

    main(["exec", "-f", flow, "-a", "claude/m:high", "-a", "codex/m:high", "task"])

    seen = _seen(tmp_path)
    assert seen["held"] == "Agents"  # the named tuple, not a plain one
    # And the agents took those names, so a trace groups each one's sessions under a word
    # rather than under a hex tail.
    assert seen["agents"] == [["builder"], ["reviewer"]]


#: A flow that says one of the agents it drives is the person at the prompt.
PEOPLED = """
import json
import os
from pathlib import Path
from typing import NamedTuple

from hmz.agents import AgentBase, HumanAgent
from hmz.flows import flow


class Agents(NamedTuple):
    assistant: AgentBase
    human: HumanAgent


@flow
def run(agents: Agents, task: str) -> None:
    agents.human.prompting = ["", "and then this"].pop
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [[type(a).__name__, a.id] for a in agents],
                "held": type(agents).__name__,
                "said": [agents.human(task), agents.human(task)],
                "task": task,
                "cwd": os.getcwd(),
            }
        )
    )
"""


def test_the_person_at_the_prompt_is_an_agent_nobody_is_asked_to_configure(
    tmp_path: Path,
) -> None:
    """A flow says it talks to them; it is handed one, and what they answer with is typed."""
    from hmz.flows import drives

    flow = _flow(tmp_path, PEOPLED)
    # Two places, one of them the person -- so one agent is asked for and one is given.
    assert drives(flow) == ("assistant",)

    main(["exec", "-f", flow, "-a", "claude/m:high", "task"])

    seen = _seen(tmp_path)
    assert seen["agents"] == [["ClaudeCodeAgent", "assistant"], ["HumanAgent", "human"]]
    # Said to like any other agent, and its answer is what was typed -- then "" for a
    # conversation that is over, which is what ends a flow that is one.
    assert seen["said"] == ["and then this", ""]


#: A flow whose only side is the person at the prompt: it drives no coding agent at all, so
#: there is nothing on its line to name.
ALONE = """
import json
from pathlib import Path
from typing import NamedTuple

from hmz.agents import HumanAgent
from hmz.flows import flow


class Agents(NamedTuple):
    human: HumanAgent


@flow
def run(agents: Agents, task: str) -> None:
    agents.human.prompting = lambda: "answered"
    Path(__file__).with_suffix(".json").write_text(
        json.dumps({"agents": [a.id for a in agents], "said": agents.human(task)})
    )
"""


def test_a_flow_whose_only_side_is_the_person_names_no_agent_at_all(
    tmp_path: Path,
) -> None:
    """A line that named an agent would be naming what nobody picks.

    Nobody chooses what the person runs, so a flow whose only side is them has everything it
    needs the moment it is named -- and a line that named no agent is not short of anything.
    """
    from hmz.flows import drives

    flow = _flow(tmp_path, ALONE)
    assert drives(flow) == ()

    main(["exec", "-f", flow, "task"])

    seen = _seen(tmp_path)
    assert seen == {"agents": ["human"], "said": "answered"}


def test_a_flow_that_does_drive_agents_still_has_to_be_given_them(
    tmp_path: Path,
) -> None:
    """Which is caught against what the flow declares, as every other miscount is."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))

    with pytest.raises(SystemExit) as exit_code:
        main(["exec", "-f", flow, "task"])

    assert exit_code.value.code == 2


#: A flow that says one of its agents has to be one a hook can say no to, which is what
#: writing the moment beside the type in the annotation means.
DEMANDING = """
import json
from pathlib import Path
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Moment, Verdict
from hmz.flows import flow


class Agents(NamedTuple):
    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
    reviewer: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    agents.builder.hooks.on(Moment.PERMISSION_REQUEST, lambda _: Verdict(refused=True))
    Path(__file__).with_suffix(".json").write_text(
        json.dumps({"agents": [[a.id] for a in agents], "task": task})
    )
"""


def test_a_flow_says_what_each_agent_has_to_be_able_to_do(tmp_path: Path) -> None:
    """Beside the type, where the flow declares the place -- and read back before the run."""
    from hmz.agents import Moment
    from hmz.flows import drives, wanted

    flow = _flow(tmp_path, DEMANDING)

    assert drives(flow) == ("builder", "reviewer")
    assert [place.moments for place in wanted(flow)] == [
        frozenset({Moment.PERMISSION_REQUEST}),
        frozenset(),
    ]


def test_an_agent_that_cannot_do_what_its_place_asks_is_refused_before_the_run(
    tmp_path: Path,
) -> None:
    """Before the first turn, for the reason the count is: not hours into a loop."""
    flow = _flow(tmp_path, DEMANDING)

    with pytest.raises(SystemExit):
        main(["exec", "-f", flow, "-a", "kimi/m:high", "-a", "kimi/m:high", "task"])

    assert not (tmp_path / "flow.json").exists()  # nothing ran

    # And a backend that does ask before it uses a tool is taken.
    main(["exec", "-f", flow, "-a", "claude/m:high", "-a", "kimi/m:high", "task"])
    assert _seen(tmp_path)["agents"] == [["builder"], ["reviewer"]]


def test_what_a_place_asks_for_is_said_where_it_is_refused(tmp_path: Path) -> None:
    from hmz.agents import KimiCodeCLIAgent, KimiCodeCLIAgentConfig

    flow = _flow(tmp_path, DEMANDING)
    agents = [
        KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="m", effort="high")),
        KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="m", effort="high")),
    ]

    with pytest.raises(NotAFlow, match="builder has to run PermissionRequest"):
        Runner(flow, agents)


def test_a_plain_tuple_says_how_many_agents_and_nothing_more(tmp_path: Path) -> None:
    from hmz.flows import drives

    assert drives(
        _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    ) == (
        "",
        "",
    )


def test_two_agents_of_one_spelling_are_two_agents(tmp_path: Path) -> None:
    """An actor and the reviewer reading its work are one configuration and not one agent."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    main(["exec", "-f", flow, "-a", "claude/m:high", "-a", "claude/m:high", "task"])
    ids = {agent[3] for agent in _seen(tmp_path)["agents"]}
    assert len(ids) == 2


def test_the_flow_runs_where_the_command_was_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And not where the flow file happens to live: the work lands in this project."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    monkeypatch.chdir(workspace)
    main(["exec", "-f", flow, "-a", "claude/m:high", "task"])
    assert Path(_seen(tmp_path)["cwd"]).resolve() == workspace.resolve()


@pytest.mark.parametrize(
    ("source", "complaint"),
    [
        ("flow = None\n", "nothing in it is marked @flow()"),
        (
            "from hmz.flows import flow\n\n\n@flow\ndef run(agents, task):\n    pass\n",
            "tuple",
        ),
        (RECORD.replace("AGENTS", "AgentBase, ..."), "fixed length"),
        (RECORD.replace("AGENTS", "AgentBase, AgentBase"), "drives 2 agents, 1 given"),
        (UNREADABLE, "cannot be read here"),
    ],
)
def test_a_file_that_is_not_the_flow_asked_for_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str, complaint: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["exec", "-f", _flow(tmp_path, source), "-a", "claude/m:high", "task"])
    assert stopped.value.code == 2
    assert complaint in capsys.readouterr().err
    assert not (tmp_path / "flow.json").exists()  # refused before anything was driven


def test_a_flow_that_is_not_there_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(
            ["exec", "-f", str(tmp_path / "nowhere.py"), "-a", "claude/m:high", "task"]
        )
    assert stopped.value.code == 2
    assert "nowhere.py" in capsys.readouterr().err


@pytest.mark.parametrize(
    "spec",
    [
        "claude/claude-opus-4-8",
        "claude",
        "gemini/g:high",
        "/m:high",
        "claude/m:",
        "cli=claude,model=m,effort=high,mode=x",
    ],
)
def test_an_agent_that_is_not_cli_model_and_effort_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], spec: str
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    with pytest.raises(SystemExit) as stopped:
        main(["exec", "-f", flow, "-a", spec, "task"])
    assert stopped.value.code == 2
    assert f"bad agent {spec!r}" in capsys.readouterr().err


@pytest.mark.parametrize("permission", ["readonly", "read_only", ""])
def test_an_unknown_permission_is_a_usage_error_before_any_agent_runs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    permission: str,
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    spec = f"cli=codex,model=m,effort=high,permission={permission}"

    with pytest.raises(SystemExit) as stopped:
        main(["exec", "-f", flow, "-a", spec, "task"])

    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert f"bad agent {spec!r}" in error
    assert "permission must be one of read-only, workspace-write, auto, bypass" in error
    assert not (tmp_path / "flow.json").exists()


def test_a_flow_fails_as_it_would_anywhere_when_it_is_the_flow_that_failed(
    tmp_path: Path,
) -> None:
    """A flow whose own setup cannot find a file has not been mistyped on the command line."""
    flow = _flow(tmp_path, "open('nowhere/prompt.md')\n")
    with pytest.raises(FileNotFoundError):
        main(["exec", "-f", flow, "-a", "claude/m:high", "task"])


def test_a_flow_for_other_agents_than_these_is_refused_before_it_is_run(
    tmp_path: Path,
) -> None:
    """What the usage error is made of, for a flow driven from Python instead."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    with pytest.raises(NotAFlow):
        Runner(flow, [ShellAgent(AgentConfig(model="m", effort="high"))])


def test_python_m_hmz_is_the_hmz_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    monkeypatch.setattr(
        sys, "argv", ["hmz", "exec", "-f", flow, "-a", "claude/m:high", "task"]
    )
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("hmz", run_name="__main__")
    assert stopped.value.code == 0
    assert _seen(tmp_path)["task"] == "task"


@pytest.mark.parametrize("flow", PREBUILT, ids=_named)
def test_every_example_runs_as_the_command_line_it_shows(
    flow: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each one shows an `hmz exec` line, and it is one that would start that flow."""
    shown = re.search(r"^\s*hmz exec (?:.*\\\n)*.*", flow.read_text(), re.MULTILINE)
    assert shown is not None, "no `hmz exec` command line to be checked against"
    monkeypatch.chdir(Path(__file__).resolve().parents[1])

    def nothing(_self: Runner, _task: str) -> None:
        """Every line is checked as far as the entry point, and no further."""

    monkeypatch.setattr(Runner, "run", nothing)
    main(shlex.split(shown[0].replace("\\\n", " "))[1:])


def test_a_flow_of_your_own_is_found_where_flows_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest wins: this project, then yours, then the ones humanize came with.

    A flow written down beside the traces is one humanize knows about without being told
    where it is -- and one taking a built-in's name stands in for it, which is what makes
    a project able to mean its own `chat` by `chat`.

    What each of them is *called* is another question, and the answer is the one every place
    gets: `<where it came from>/<flow>`, which for these two places is `local` and `user`. So
    one of yours sharing a name with one of humanize's is listed beside it under a name of its
    own rather than instead of it.
    """
    from hmz.flows import find, found

    home, project = tmp_path / "home", tmp_path / "project"
    for where in (home / ".humanize/flows", project / ".humanize/flows"):
        where.mkdir(parents=True)
    mine = RECORD.replace("AGENTS", "AgentBase")
    written(home / ".humanize/flows", "yours", mine)
    written(project / ".humanize/flows", "theirs", mine)
    written(project / ".humanize/flows", "chat", mine)  # a name humanize uses
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    listed = found()

    named = [(one.whose, one.name) for one in listed]
    assert ("local", "local/theirs") in named
    assert ("user", "user/yours") in named
    # Both, under names of their own: one is not offered as if it were the other.
    assert ("local", "local/chat") in named
    assert ("builtin", "chat") in named
    # `-f` still takes a bare name, and the nearest flow answering to it is what runs.
    assert find("chat") == str((project / ".humanize/flows/chat" / ENTRY).resolve())
    assert find("yours") == str((home / ".humanize/flows/yours" / ENTRY).resolve())
    assert find("ralph_loop").endswith(f"src/hmz/flows/builtin/ralph_loop/{ENTRY}")
    # And it takes what the list calls one, which says which place it came from and so is the
    # spelling nothing can stand in for.
    assert find("user/yours") == str((home / ".humanize/flows/yours" / ENTRY).resolve())
    assert find("local/chat") == str(
        (project / ".humanize/flows/chat" / ENTRY).resolve()
    )
    # A path is still a path, `~` and all: a flow being written lives wherever it is.
    assert find("~/.humanize/flows/yours") == str(
        (home / ".humanize/flows/yours" / ENTRY).resolve()
    )
    assert find(".humanize/flows/theirs") == str(
        (project / ".humanize/flows/theirs" / ENTRY).resolve()
    )
    assert find("nowhere") == "nowhere"  # a path is taken as given


def test_a_flow_of_your_own_runs_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of finding it: `-f theirs` starts it, with no path said anywhere."""
    project = tmp_path / "project"
    (project / ".humanize/flows").mkdir(parents=True)
    written(
        project / ".humanize/flows", "theirs", RECORD.replace("AGENTS", "AgentBase")
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)
    driven: list[str] = []

    def record(_self: Runner, task: str) -> None:
        driven.append(task)

    monkeypatch.setattr(Runner, "run", record)

    assert main(["exec", "-f", "theirs", "-a", "claude/m:high", "do it"]) == 0
    assert driven == ["do it"]


def test_the_chat_flow_is_one_session_for_as_long_as_it_is_told_things(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Talking to a coding agent, with no loop around it: the turns are a conversation."""
    from hmz.agents import HumanAgent
    from hmz.flows.builtin.chat import Chat
    from hmz.flows.builtin.chat import run as chat

    agent = ShellAgent(AgentConfig(model="m", effort="high"))
    said = ["echo third", "echo second"]
    # The person is an agent like any other, and what they answer with is what they typed.
    person = HumanAgent()
    person.prompting = said.pop

    chat(Chat(agent, person), "echo first")

    # One session for all three, so the agent had the earlier turns in context: a second
    # would have opened a second id. And the run ended when there was nothing left to be
    # told, rather than looping on nothing.
    assert len(agent.opened) == 1
    assert said == []


def test_the_chat_flow_run_from_a_command_line_does_the_one_thing_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nobody is at a prompt there, so there is nothing to wait for and it returns."""
    from hmz.agents import HumanAgent
    from hmz.flows.builtin.chat import Chat
    from hmz.flows.builtin.chat import run as chat

    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    # Nothing is hooked up to the person, so they answer with nothing the first time.
    chat(Chat(agent, HumanAgent()), "echo once")

    assert len(agent.opened) == 1
