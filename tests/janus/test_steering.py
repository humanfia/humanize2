"""Talking to a turn that is already running, against the real thing.

The fakes elsewhere stand in for a protocol; this is the protocol. What it pins is the rule
the whole feature rests on -- Claude answers each thing it is told with a turn of its own --
which nothing but the real binary can confirm, and which was wrong here once already: a word
put in mid-turn had its answer left in the pipe, lost to this turn and read as the next one's.
"""

from __future__ import annotations

import threading
import time

import pytest

from humanize.janus import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)

#: Small and quick: what is being tested is the plumbing, not the model.
CONFIG = ClaudeCodeAgentConfig(model="claude-haiku-4-5-20251001", effort="low")


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_a_word_put_in_reaches_the_turn_and_leaves_the_stream_in_step() -> None:
    session = ClaudeCodeAgent(CONFIG).new()

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
    assert "SECOND" in session("Reply with exactly: SECOND")


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_codex_takes_a_word_put_into_the_turn_it_is_running() -> None:
    """Codex steers the turn itself, which is why its turns run on the app server: a
    `codex exec` per turn has ended by the time there is anything to say to it."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low")).new()

    said = []
    for event in session.stream(
        "Count from 1 to 60, one number per line. Do not use any tools."
    ):
        if not said:  # the turn is provably under way by the time it says anything
            session.interject("STOP. Ignore the counting. Reply with exactly: STEERED")
        said.append(event)

    assert "STEERED" in said[-1].text
    assert said[-1].kind == "result"


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_kimi_steers_a_word_into_the_turn_it_is_running() -> None:
    """A prompt sent to a working session is queued; `prompts:steer` moves it into this turn.

    Sending it alone would answer it as a turn of its own once this one ended, which is a turn
    queued behind rather than a word put into the one running.
    """
    session = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).new()

    def put_in() -> None:
        for _ in range(600):
            if session._running.session is not None:
                time.sleep(5)  # long enough that the turn is provably under way
                session.interject(
                    "STOP. Ignore the counting. Reply with exactly: STEERED"
                )
                return
            time.sleep(0.05)

    threading.Thread(target=put_in, daemon=True).start()
    answered = session(
        "Count slowly from 1 to 60, one number per line. Do not use any tools."
    )

    assert "STEERED" in answered
