"""The person at the prompt, driven as an agent -- which is what they are to a flow.

A flow that is a conversation has two sides, and only one of them was a thing a flow could
name. What the other side said arrived through a hook hung off whichever agent happened to be
talking, which is a way of asking the person something without ever saying that is what is
happening. Here they are an agent: it is said to, and it answers, and the answer is what was
typed. `agents.human(said)` reads as what it does.

Not a coding agent. It runs no model, spends nothing, and takes no turn that anyone is
watching -- the transcript already has what was typed, behind the `❯` it was typed at. Which
is why it is not among the agents a flow is configured with: nobody chooses what the person
runs, so a flow that names one is handed one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AgentBase, Event, SessionBase
from .config import AgentConfig

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["HumanAgent", "HumanSession"]


class HumanSession(SessionBase):
    """One conversation with the person: said to, and answered when they answer."""

    def stream(self, prompt: str) -> Iterator[Event]:  # noqa: ARG002
        """Says something to the person and waits for what they say back.

        Overridden rather than implemented through `_stream`, so that this is not bracketed
        by the `begins` and `ends` that say whose turn it is: the person's turn is not one
        being watched. Counting it would put them in the graph of who handed to whom and spin
        a clock at them while they thought, which is a run of a flow saying that the flow is
        working when the flow is waiting.

        Args:
          prompt: What to say to them, which they have already read -- it is what the agent
            just said, and the transcript is where they read it.

        Yields:
          One `result`: what they said back, or "" once there will be nothing more, which is
          how a flow that is a conversation learns the conversation is over.
        """
        yield Event(kind="result", text=self._agent.prompted() or "")

    def _stream(self, prompt: str) -> Iterator[Event]:
        """Never called: `stream` is what a turn of this goes through.

        Args:
          prompt: What to say to them.

        Yields:
          Nothing.
        """
        yield from self.stream(prompt)


class HumanAgent(AgentBase):
    """Whoever is at the prompt, said to as an agent and answering as one.

    Made by whatever is driving the flow rather than by the flow: the person is reached
    through the interface they are sitting at, and a flow only says that it is talking to
    them. Run from a command line, where nobody is at a prompt, they answer "" the first time
    they are asked -- so a flow that is a conversation does the one thing it was given and
    returns, rather than waiting on somebody who is not there.
    """

    def __init__(self, *, name: str = "human") -> None:
        """Initializes the person as an agent.

        Args:
          name: What to call them, which a flow that names its agents overrides as it does
            for any other.
        """
        super().__init__(AgentConfig(model="human", effort=""), name=name)

    def new(self) -> HumanSession:
        """Opens a conversation with them.

        Returns:
          The session. There is nothing to open: the person is already there, or is not.
        """
        return HumanSession(self)
