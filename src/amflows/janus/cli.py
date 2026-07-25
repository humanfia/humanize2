"""``amflows run`` -- run an agent flow in this directory.

    amflows run -f flow.py -a claude/claude-opus-4-8/high,codex/gpt-5.6-sol/max "$(cat TASK.md)"

A flow says how many agents it drives, and this is where they come from: one for each, in the
order the flow takes them, at the model and effort each is to run at.
"""

from __future__ import annotations

import argparse

from .agents import (
    AgentBase,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)
from .runner import NotAFlow, Runner

#: The backends an agent can be asked for by name, and the pair each one is built from.
_BACKENDS = {
    "claude": (ClaudeCodeAgent, ClaudeCodeAgentConfig),
    "codex": (CodexAgent, CodexAgentConfig),
    "kimi": (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
}


def main(argv: list[str] | None = None) -> None:
    """Runs the flow named on the command line, on the agents it names.

    Args:
      argv: The arguments to parse, defaulting to this process's own.
    """
    parser = argparse.ArgumentParser(
        prog="amflows run", description="Run an agent flow in this directory."
    )
    parser.add_argument(
        "-f",
        "--flow",
        required=True,
        metavar="PATH",
        help="the Python file the flow is written in, as a run(agents, task) function",
    )
    parser.add_argument(
        "-a",
        "--agents",
        action="append",
        required=True,
        metavar="BACKEND/MODEL/EFFORT[,...]",
        help="the agents to drive the flow with, comma separated and repeatable, as many "
        f"as it declares; BACKEND is one of {', '.join(_BACKENDS)}",
    )
    parser.add_argument(
        "task",
        help="what the flow is to have the agents do, after -- if it starts with a dash",
    )
    args = parser.parse_args(argv)

    agents: list[AgentBase] = []
    for spec in ",".join(args.agents).split(","):
        # Read from both ends, because a model name may hold slashes of its own -- Kimi's
        # are `kimi-code/k3` -- while a backend and an effort never do.
        backend, _, rest = spec.strip().partition("/")
        model, _, effort = rest.rpartition("/")
        if backend not in _BACKENDS or not model or not effort:
            parser.error(f"bad agent {spec!r}: expected BACKEND/MODEL/EFFORT")
        agent, config = _BACKENDS[backend]
        agents.append(agent(config(model=model, effort=effort)))

    try:
        runner = Runner(args.flow, agents)
    except NotAFlow as error:
        # A flow that is not there, or one that takes other agents than these, is a command
        # line that was wrong before anything ran, so it exits as argparse's own rejections
        # do. What the flow raises for itself is the flow's, and is left to say so itself.
        parser.error(str(error))
    runner.run(args.task)
