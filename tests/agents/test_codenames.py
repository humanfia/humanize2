"""What an agent nobody named is called.

An agent needs a name nothing else answers to, and the one it gets is a Chrysos Heir's --
a Greek word for what the heir was made to be and three digits behind it. The tests here are
about the shape the story gives those codes, about the canon coming up far oftener than a pool
this size would give it by chance, and about the one thing the joke must not cost: two agents
left unnamed are still two agents.
"""

from __future__ import annotations

import random
import re
import threading

import pytest

from hmz.agents import AgentConfig, codenames
from hmz.agents.codenames import HEIRS, WORDS, codename
from tests.stubs import ShellAgent

CONFIG = AgentConfig(model="m", effort="high")

#: How the story spells a code: a capital at the front, one more where the word breaks, and
#: three digits. Every code drawn here is one of these, canon or not.
SHAPE = re.compile(r"[A-Z][a-z]+[A-Z][a-z]+[0-9]{3}")


def test_the_twelve_are_spelled_as_the_story_spells_them() -> None:
    """The corpus this was written off, kept where a rewrite of the generator trips on it."""
    assert dict(HEIRS) == {
        "NeiKos": "496",  # Phainon
        "PoleMos": "600",  # Mydei
        "SkeMma": "720",  # Anaxa
        "EpieiKeia": "216",  # Castorice
        "HapLotes": "405",  # Tribbie
        "KaLos": "618",  # Aglaea
        "EleOs": "252",  # Hyacine
        "HubRis": "504",  # Cerydra
        "PhiLia": "093",  # Cyrene
        "ApoRia": "432",  # Hysilens
        "OreXis": "945",  # Cipher
        "SkoPeo": "365",  # Terravox
    }


def test_every_word_a_code_is_drawn_from_breaks_where_the_heirs_words_do() -> None:
    """A word that read `Kykl0s` or `KYKLOS` would read as a mistake rather than a code."""
    for word in (*(one for one, _ in HEIRS), *WORDS):
        assert SHAPE.fullmatch(f"{word}000"), word

    assert len(set(WORDS)) == len(WORDS)  # no word twice, or one comes up double
    assert not set(WORDS) & {one for one, _ in HEIRS}  # and no heir's word among them


def test_a_code_is_a_word_and_three_digits() -> None:
    for _ in range(500):
        assert SHAPE.fullmatch(codename())


def test_the_heirs_come_up_far_oftener_than_chance_would_give_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is the whole point: a name is only a joke to somebody who recognises it."""
    random.seed(496)
    monkeypatch.setattr(codenames, "_CALLED", set[str]())  # a process that has drawn none
    canon = {f"{word}{number}" for word, number in HEIRS}

    drawn = [codenames._drawn() for _ in range(4000)]

    # Uniform over the pool, an exact canon code would come up about once in eleven thousand.
    by_chance = len(HEIRS) / ((len(HEIRS) + len(WORDS)) * 1000)
    seen = sum(one in canon for one in drawn) / len(drawn)
    assert seen == pytest.approx(codenames.CANON, abs=0.05)
    assert seen > 1000 * by_chance

    # And of what is left, half is an heir's own word under some other number -- the same
    # role out of a cycle this one has not been told about.
    words = {one for one, _ in HEIRS}
    heirs = sum(one[:-3] in words for one in drawn) / len(drawn)
    theirs = codenames.CANON + (1 - codenames.CANON) * codenames.AGAIN
    assert heirs == pytest.approx(theirs, abs=0.05)


def test_the_first_agent_a_run_leaves_unnamed_is_half_the_time_an_heir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case that matters: most runs drive a handful of agents, not eleven thousand."""
    random.seed(945)
    canon = {f"{word}{number}" for word, number in HEIRS}

    first: list[str] = []
    for _ in range(400):  # four hundred processes, each drawing its first code
        monkeypatch.setattr(codenames, "_CALLED", set[str]())
        first.append(codename())

    seen = sum(one in canon for one in first) / len(first)
    assert seen == pytest.approx(codenames.CANON, abs=0.05)


def test_no_two_agents_left_unnamed_are_one_agent() -> None:
    """The one thing the joke must not cost: a trace groups sessions under a name."""
    drawn = [ShellAgent(CONFIG).id for _ in range(500)]

    assert len(set(drawn)) == len(drawn)


def test_a_name_given_where_the_agent_was_made_is_still_the_name() -> None:
    assert ShellAgent(CONFIG, name="builder").id == "builder"


def test_two_threads_drawing_at_once_draw_two_codes() -> None:
    """A fleet opens its agents from every thread it has, and none of them may collide."""
    drawn: list[str] = []
    hold = threading.Lock()

    def draws() -> None:
        mine = [codename() for _ in range(100)]
        with hold:
            drawn.extend(mine)

    threads = [threading.Thread(target=draws) for _ in range(8)]
    for one in threads:
        one.start()
    for one in threads:
        one.join()

    assert len(set(drawn)) == len(drawn) == 800


def test_a_process_that_has_drawn_every_code_is_answered_with_the_misnumbered_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past every heir there is, an early cycle's fault -- unique the way a name was before."""
    monkeypatch.setattr(codenames, "HEIRS", (("NeiKos", "496"),))
    monkeypatch.setattr(codenames, "WORDS", ("KykLos",))
    monkeypatch.setattr(codenames, "_CALLED", set[str]())

    whole = {codename() for _ in range(2000)}

    assert len(whole) == 2000  # the whole of a space that small, each of it once
    assert all(SHAPE.fullmatch(one) for one in whole)
    assert codename().startswith("Chaoz666#")
