"""What an agent nobody named is called.

An agent needs a name nothing else answers to, and the one it gets is a designation out of
Amphoreus -- one the story spells, copied exactly as it spells it, or a Greek word and three
digits built by the rule the Chrysos Heirs are spelled by. The tests here are about both
shapes and about keeping them apart, about the canon coming up far oftener than a pool this
size would give it by chance, and about the one thing the joke must not cost: two agents left
unnamed are still two agents.
"""

from __future__ import annotations

import itertools
import random
import re
import threading

import pytest

from hmz.coganchor.agents import AgentConfig, codenames
from hmz.coganchor.agents.codenames import (
    HEIRS,
    JOINS,
    LOCKED,
    SAID,
    SIGNALS,
    STEMS,
    VISITORS,
    WORDS,
    codename,
)
from tests.stubs import ShellAgent

CONFIG = AgentConfig(model="m", effort="high")

#: How a generated code is spelled: a capital at the front, one more wherever the word breaks,
#: and three digits. Everything this hands out that the story did not already spell is one of
#: these, built or counted -- and never a hex tail, which is the name codenames were written to
#: be rid of.
SHAPE = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z]+)+[0-9]{3}")

#: What the story says out loud, which is drawn whole and never corrected on the way out.
CANON = frozenset(SAID)

#: Spellings the census turned down, and which no run may ever hand out: a casing variant
#: nobody could quote, the one Error Log line the wiki itself flags as a source-side typo,
#: three codes off derived wiki pages rather than the readable, and the Scepter, which names
#: the program the experiment runs on rather than anybody it ran. A codename is a joke only
#: while it is the story's, and a misspelled one is nobody.
REJECTED = (
    "Kalos618",
    "Neikos496",
    "PSotSTM1",
    "RustedBlood1",
    "RustedBlood2",
    "\N{GREEK SMALL LETTER DELTA}-me13",
)


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


def test_the_wider_canon_is_what_the_story_spells_and_nothing_else() -> None:
    """The census this was written off, kept where a rewrite of the generator trips on it."""
    assert LOCKED == ("Leoreia300", "Minphia14")  # Gnaeus and Calypso, of earlier runs
    assert SIGNALS == (
        "Doril701",  # the module that left the crowd
        "Doril704",
        "Golem99",  # the first spark of selfhood
        "Doril816",  # the birth of society
        "Chaoz666",  # the killing that made a Lord Ravager
        "Ortho102",  # the first tool
        "Eumyia03",  # the songbird that invented art
        "Dystop666",  # the primate that invented altruism
        "Utop13",  # the first killing done out of love
        "Imora8",  # the only prophet
        "Fovos032",
        "Nammou320",
    )
    assert VISITORS == (
        "HertA",
        "ScreW",
        "LykoS",
    )  # Herta, Screwllum, the Administrator
    assert set(SAID) == {f"{word}{number}" for word, number in HEIRS} | {
        *LOCKED,
        *SIGNALS,
        *VISITORS,
    }
    assert len(SAID) == len(set(SAID)) == 29  # twenty-nine, and no thirtieth invented


def test_a_spelling_the_story_does_not_have_is_in_no_pool_a_code_comes_out_of() -> None:
    """A code is the canon copied or the rule applied, and none of these is either."""
    words = {*(one for one, _ in HEIRS), *WORDS, *(j + s for j in JOINS for s in STEMS)}

    for one in REJECTED:
        assert one not in SAID  # nothing draws it whole
        assert not (one[-3:].isdigit() and one[:-3] in words), one  # nor builds it


def test_every_designation_the_story_spells_is_handed_out_exactly_as_it_is_spelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A code nobody can draw is a code nobody recognises, which is the whole of the point.

    And `Golem99` carries two digits where `Imora8` carries one and `ScreW` carries none, so
    the rule the rest are built by cannot spell them: padding one out to fit would hand over a
    designation the story never issued.
    """
    random.seed(216)
    monkeypatch.setattr(codenames, "_CALLED", set[str]())

    drawn = {codename() for _ in range(20 * len(SAID))}

    assert drawn >= CANON  # every one of the twenty-nine, verbatim
    for one in drawn - CANON:
        assert SHAPE.fullmatch(one), one  # while everything built keeps the rule


def test_the_wider_canon_never_leaks_into_a_word_the_rule_builds() -> None:
    """`Doril` is Greek for nothing, so `Doril204` would read as a bug and not as a joke."""
    random.seed(504)
    built = {join + stem for join in JOINS for stem in STEMS}

    words = {codenames._word() for _ in range(4000)}

    assert {*(one for one, _ in HEIRS), *WORDS, *built} >= words
    assert not words & {  # and no stem of a designation the story issued whole
        one.rstrip("0123456789") for one in (*LOCKED, *SIGNALS, *VISITORS)
    }
    for one in words:
        assert SHAPE.fullmatch(f"{one}000"), one


def test_what_is_generated_is_a_greek_word_and_three_digits_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing left to copy there is only the rule, and the rule has no exceptions."""
    random.seed(945)
    monkeypatch.setattr(codenames, "SAID", ())  # a process that has drawn the canon out
    monkeypatch.setattr(codenames, "_CALLED", set[str]())

    for _ in range(2000):
        assert SHAPE.fullmatch(codenames._drawn())


def test_every_word_a_code_is_drawn_from_breaks_where_the_heirs_words_do() -> None:
    """A word that read `Kykl0s` or `KYKLOS` would read as a mistake rather than a code."""
    for word in (*(one for one, _ in HEIRS), *WORDS):
        assert SHAPE.fullmatch(f"{word}000"), word

    assert len(set(WORDS)) == len(WORDS)  # no word twice, or one comes up double
    assert not set(WORDS) & {one for one, _ in HEIRS}  # and no heir's word among them


def test_a_morpheme_joins_into_a_word_spelled_the_way_the_heirs_words_are() -> None:
    """`Apo` and `Ria` are `ApoRia`, so `Meta` and `Kratos` are a word by the same rule."""
    for one in (*JOINS, *STEMS):
        assert re.fullmatch(r"[A-Z][a-z]+", one), one

    for join in JOINS:
        for stem in STEMS:
            assert SHAPE.fullmatch(f"{join}{stem}000"), f"{join}{stem}"


def test_a_code_is_one_the_story_spells_or_a_word_and_three_digits() -> None:
    for _ in range(500):
        drawn = codename()
        assert drawn in CANON or SHAPE.fullmatch(drawn), drawn


def test_the_canon_comes_up_far_oftener_than_chance_would_give_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is the whole point: a name is only a joke to somebody who recognises it."""
    random.seed(496)
    monkeypatch.setattr(
        codenames, "_CALLED", set[str]()
    )  # a process that has drawn none

    drawn = [codenames._drawn() for _ in range(4000)]

    # The rule can spell twelve of the twenty-nine at all, and uniform over the pool it would
    # land on one about once in eleven thousand. The other seventeen it cannot spell ever.
    by_chance = len(HEIRS) / ((len(HEIRS) + len(WORDS)) * 1000)
    seen = sum(one in CANON for one in drawn) / len(drawn)
    assert seen == pytest.approx(codenames.CANON, abs=0.05)
    assert seen > 1000 * by_chance

    # And of what is built, half is an heir's own word under some other number -- the same
    # role out of an era this one has not been told about. The canon half adds the heirs it
    # draws whole, which are twelve of the twenty-nine it draws from.
    words = {one for one, _ in HEIRS}
    heirs = sum(one[:-3] in words for one in drawn) / len(drawn)
    theirs = (
        codenames.CANON * len(HEIRS) / len(SAID)
        + (1 - codenames.CANON) * codenames.AGAIN
    )
    assert heirs == pytest.approx(theirs, abs=0.05)


def test_the_first_agent_a_run_leaves_unnamed_is_half_the_time_one_the_story_spells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case that matters: most runs drive a handful of agents, not eleven thousand."""
    random.seed(945)

    first: list[str] = []
    for _ in range(400):  # four hundred processes, each drawing its first code
        monkeypatch.setattr(codenames, "_CALLED", set[str]())
        first.append(codename())

    seen = sum(one in CANON for one in first) / len(first)
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


def test_a_crowded_process_is_answered_by_the_rule_and_never_with_a_hex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of the whole file: there is no last code, so there is nothing to fall back to."""
    monkeypatch.setattr(codenames, "HEIRS", (("NeiKos", "496"),))
    monkeypatch.setattr(codenames, "SAID", ("NeiKos496",))
    monkeypatch.setattr(codenames, "WORDS", ("KykLos",))
    monkeypatch.setattr(codenames, "JOINS", ("Meta", "Poly"))
    monkeypatch.setattr(codenames, "STEMS", ("Kratos",))
    monkeypatch.setattr(codenames, "_CALLED", set[str]())
    monkeypatch.setattr(codenames, "_COUNTING", itertools.count(1))
    monkeypatch.setattr(codenames, "_TRIES", 4)  # crowded sooner, so the test is a test

    # Four words and a thousand numbers each is the whole of what luck can reach here.
    whole = [codename() for _ in range(6000)]

    assert len(set(whole)) == len(whole)  # every one of them somebody else's
    for one in whole:
        assert SHAPE.fullmatch(one), one
        assert "#" not in one

    # And past those four the word grew a morpheme rather than a tail.
    assert any(one.count("Meta") + one.count("Poly") > 1 for one in whole)


def test_counting_spells_a_different_word_every_thousand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Place notation over the morphemes, so a count is a word and no count is another's."""
    monkeypatch.setattr(codenames, "_CALLED", set[str]())
    monkeypatch.setattr(codenames, "_COUNTING", itertools.count(1))

    counted = [codenames._counted() for _ in range(4000)]

    assert len(set(counted)) == len(counted)
    assert len({one[:-3] for one in counted}) >= 4  # a word per thousand, at the least
    assert all(SHAPE.fullmatch(one) for one in counted)
