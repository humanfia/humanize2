"""Talking to a turn that is already running, against the real thing.

The fakes elsewhere stand in for a protocol; this is the protocol. What it pins is the rule
the whole feature rests on -- Claude answers each thing it is told with a turn of its own --
which nothing but the real binary can confirm, and which was wrong here once already: a word
put in mid-turn had its answer left in the pipe, lost to this turn and read as the next one's.
"""

from __future__ import annotations

import pytest

from amflows.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig

#: Small and quick: what is being tested is the plumbing, not the model.
CONFIG = ClaudeCodeAgentConfig(model="claude-haiku-4-5-20251001", effort="low")


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_word_put_in_reaches_the_turn_and_leaves_the_stream_in_step() -> None:
    session = ClaudeCodeAgent(CONFIG).launch()

    # Put in at the first thing the agent says rather than after a wait: the turn is provably
    # under way by then, however fast the model happens to be today.
    said = []
    for event in session.stream("Count from 1 to 40, one number per line. No tools."):
        if not said:
            session.interject("STOP. Ignore the counting. Reply with exactly: STEERED")
        said.append(event)

    # The turn is over when everything said in it has been answered, so the answer is the
    # answer to the last thing said -- which is the word put in, not the prompt it replaced.
    assert "STEERED" in said[-1].text
    assert said[-1].kind == "result"
    assert (
        sum(event.kind == "result" for event in said) == 1
    )  # one turn, two things said
    # And nothing of it was left behind for the next turn to pick up as its own.
    assert "SECOND" in session.run("Reply with exactly: SECOND")
