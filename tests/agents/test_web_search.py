"""Whether an agent may search the web, and how each backend is told it.

One switch, and it has to mean one thing wherever it is read: an agent that may search the
web searches the web, on a CLI whose own web search is on until it is taken away and on one
whose own is off until it is asked for. So it is sent in both directions where a backend can
be told both, and a backend that cannot be told refuses it off rather than going on searching
under a setting that says it is not.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from hmz import backends
from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    DshAgent,
    DshAgentConfig,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
    QwenCodeAgent,
    QwenCodeAgentConfig,
)

#: The backends that can be told, and the ones that cannot. Read off `hmz.backends` here as
#: everything else reads it, so a backend that gains a way of being told is a backend this
#: notices rather than a list to remember.
TELLABLE = ("claude", "codex", "grok", "qwen", "opencode", "mimo", "zcode")


def test_an_agent_nobody_has_been_asked_about_may_search_the_web() -> None:
    """Which is what a coding agent has always been able to do."""
    assert ClaudeCodeAgentConfig(model="m", effort="high").web_search is True


def test_which_backends_can_be_told_is_read_off_the_one_place_a_cli_is_written_down() -> (
    None
):
    """One list of what a CLI is, so a switch and a driver cannot come to disagree."""
    told = {one.name for one in backends.profiles() if one.searches}

    assert told == set(TELLABLE)


def test_claude_is_refused_the_two_tools_that_reach_the_web() -> None:
    """A tool call is a tool call, and `--disallowedTools` is that call written as a rule."""
    config = ClaudeCodeAgentConfig(model="m", effort="high")
    searching = ClaudeCodeAgent(config).new()._command()

    assert "--disallowedTools" not in searching

    argv = ClaudeCodeAgent(replace(config, web_search=False)).new()._command()

    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch"


def test_claude_says_both_things_it_says_with_that_flag_in_the_one_list() -> None:
    """The flag takes one list, so goals switched off and no web search are one list."""
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", web_search=False, goals=False)
    )
    argv = agent.new()._command()

    assert argv.count("--disallowedTools") == 1
    assert argv[argv.index("--disallowedTools") + 1] == (
        "Agent,ScheduleWakeup,CronCreate,CronDelete,CronList,WebSearch,WebFetch"
    )


@pytest.mark.parametrize(
    ("kind", "config", "flag"),
    [
        (GrokBuildAgent, GrokBuildAgentConfig, "--disallowed-tools"),
        (QwenCodeAgent, QwenCodeAgentConfig, "--exclude-tools"),
    ],
)
def test_a_backend_that_withholds_tools_withholds_the_two_that_reach_the_web(
    kind: type, config: type, flag: str
) -> None:
    """At every rung rather than only at the one whose own ladder already refuses them."""
    session = kind(config(model="m", effort="high", web_search=False)).new()
    argv = session._turn("hi")[0]

    assert set(argv[argv.index(flag) + 1].split(",")) >= {"web_search", "web_fetch"}


def test_a_rung_that_already_withholds_them_does_not_withhold_them_twice() -> None:
    """The two say the same thing here, and either of them saying it is enough."""
    argv = (
        GrokBuildAgent(
            GrokBuildAgentConfig(
                model="m", effort="high", permission="workspace-write", web_search=False
            )
        )
        .new()
        ._turn("hi")[0]
    )
    withheld = argv[argv.index("--disallowed-tools") + 1].split(",")

    assert sorted(withheld) == sorted(set(withheld))


def test_opencode_denies_the_one_reaching_out_tool_it_names() -> None:
    """Its permission table is where each tool is allowed or denied, so it is said there."""
    config = OpencodeAgentConfig(model="p/m", effort="high")
    session = OpencodeAgent(config).new()
    permits = type(session).permits

    assert json.loads(session._environment()[permits])["webfetch"] == "allow"

    session = OpencodeAgent(replace(config, web_search=False)).new()

    assert json.loads(session._environment()[permits])["webfetch"] == "deny"


@pytest.mark.parametrize(
    ("kind", "config"),
    [
        (DshAgent, DshAgentConfig),
        (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
        (PiAgent, PiAgentConfig),
    ],
)
def test_a_backend_with_no_way_of_being_told_refuses_it_off(
    kind: type, config: type
) -> None:
    """An agent that quietly went on searching would be a setting that lies."""
    with pytest.raises(ValueError, match="no way of being told"):
        kind(config(model="m", effort="high", web_search=False))


def test_it_is_refused_wherever_the_config_arrives() -> None:
    """Where the agent is made, and where a running one is set up as something else."""
    agent = PiAgent(PiAgentConfig(model="m", effort="high"))

    with pytest.raises(ValueError, match="no way of being told"):
        agent.reconfigure(replace(agent.config, web_search=False))

    assert agent.config.web_search is True  # and the agent is left as it was


def test_an_agent_that_may_not_search_is_another_agent_at_the_same_model() -> None:
    """The config is frozen: this is a second agent rather than the first one changed."""
    config = ClaudeCodeAgentConfig(model="m", effort="high")

    assert replace(config, web_search=False) != config
    assert config.web_search is True


def test_a_line_says_it_the_way_a_line_says_every_other_setting() -> None:
    """Written out, beside the permission rung and the account it runs as."""
    assert backends.read("cli=claude,model=m,effort=high,web_search=off")[6] is False
    assert backends.read("cli=claude,model=m,effort=high,web_search=on")[6] is True
    # Nobody said, which is not the same as saying on: it is the agent as it comes.
    assert backends.read("claude/m:high")[6] is None
    with pytest.raises(ValueError, match="web_search must be on or off"):
        backends.read("cli=claude,model=m,effort=high,web_search=maybe")
