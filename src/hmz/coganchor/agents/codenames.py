"""What an agent nobody named is called, which is a codename out of Amphoreus.

An agent given no name still needs one nothing else answers to, and `ClaudeCodeAgent#3f2a1b9c`
is a name only a debugger loves. So one is drawn from the Chrysos Heirs instead -- the golden
blooded of Amphoreus, whose codes *Honkai: Star Rail* spells as a Greek word for what the heir
was made to be and three digits with something behind them. `NeiKos496` is strife, and 496 is
the third perfect number; `SkeMma720` is inquiry, and 720 is 6!; `KaLos618` is beauty, and 618
is the golden ratio. The era the story is told in is the 33,550,336th, which is the fifth
perfect number, so the numbers are the joke and not decoration.

The twelve are not all the story numbers, though: Amphoreus is an experiment, and every
electrical signal it ever ran was issued a designation. Two heirs of earlier recurrences carry
one; so do twelve signals out of the cycles before there were heirs at all -- `Golem99` is the
first spark of selfhood, `Eumyia03` a songbird that invented art, `Utop13` the first killing
done out of love, `Chaoz666` the killing that made the Scepter a Lord Ravager -- and so do the
three who walked into the calculation rather than being run by it. Twenty-nine in all, and all
twenty-nine are the canon here, because all twenty-nine are somebody a reader might recognise,
and the canon comes up far oftener than its share would give it: a name is only a joke to
somebody who recognises it. The thirteenth factor is the one the experiment never issued a code
to -- "an unrecorded electrical signal" -- and this invents none for it.

Which makes two rules and not one. What is drawn from the canon is copied verbatim, in whatever
shape the story spells it: `Ortho102` has no capital inside it, `Imora8` has a single digit,
`ScreW` has no digits at all, and tidying any of them would hand out a name the story never
gave. What is generated has nothing to copy, so it keeps the rule the heirs are spelled by, and
builds words rather than only listing them. A Greek word is morphemes joined at a capital --
`Apo` and `Ria` are `ApoRia`, which is an heir's -- so `MetaKratos`, `PolyMorphe` and `NeoTelos`
are words the same rule makes and the story merely never needed. That is what makes the space
endless: when the short words are used up the next one grows a morpheme, so there is always
another code and never a tail of hex to fall back to.
"""

from __future__ import annotations

import itertools
import random
import threading

__all__ = ["codename"]

#: The twelve codes the story spells out: what the heir was made to be, and the number they
#: carry. Ordered as the heirs are introduced rather than alphabetically, since this is a
#: cast list before it is a table.
HEIRS: tuple[tuple[str, str], ...] = (
    ("NeiKos", "496"),  # Phainon -- strife, and the third perfect number
    ("PoleMos", "600"),  # Mydei -- war
    ("SkeMma", "720"),  # Anaxa -- inquiry, and 6!
    ("EpieiKeia", "216"),  # Castorice -- clemency, and 6**3
    ("HapLotes", "405"),  # Tribbie -- singleness, of the three who are one
    ("KaLos", "618"),  # Aglaea -- beauty, and the golden ratio
    ("EleOs", "252"),  # Hyacine -- mercy, and the middle of Pascal's tenth row
    ("HubRis", "504"),  # Cerydra -- pride, and 7 * 8 * 9
    ("PhiLia", "093"),  # Cyrene -- love
    ("ApoRia", "432"),  # Hysilens -- impasse
    ("OreXis", "945"),  # Cipher -- appetite, and the smallest odd abundant number
    ("SkoPeo", "365"),  # Terravox -- watching, and a year of it
)

#: The two the story numbers out of earlier recurrences of the same twelve roles. Amphoreus
#: reruns its heirs, and these are the runs it kept a designation from. Held whole rather than
#: as word and number, as everything below is: `Minphia14` carries two digits, and rounding it
#: up to three would be issuing a designation the story never did.
LOCKED: tuple[str, ...] = (
    "Leoreia300",  # Gnaeus, who split himself into five and is remembered as Nikador
    "Minphia14",  # Calypso, whose rebuilt Grove of Epiphany came down as Cerces
)

#: The twelve signals logged before there were heirs to inherit anything, in the order the
#: cycles ran. These carry the better jokes: the experiment is counting its way up to a person,
#: and what it writes down along the way is the first module to leave the crowd, the first thing
#: to pick up a tool, the first creature to make something for no reason, and the first murder.
#: Numbered by the story rather than by the rule, which is why they are held whole.
SIGNALS: tuple[str, ...] = (
    "Doril701",  # 12,649th -- the module that broke away from the unified consciousness
    "Doril704",  # named only by what left it, which is a kind of parenthood
    "Golem99",  # 22,449th -- detached from Doril704: the first spark of selfhood
    "Doril816",  # 39,665th -- a cluster protocol, which is the birth of society
    "Chaoz666",  # 50,121st -- killed the aggressor taking its compute, and made a Lord Ravager
    "Ortho102",  # 90,123rd -- an orthopteran, the first to use a tool
    "Eumyia03",  # 100,907th -- a passerine, logged as a deviant, that developed "art"
    "Dystop666",  # 132,905th -- a primate that developed altruism
    "Utop13",  # 176,100th -- killed a fellow being out of "love"
    "Imora8",  # the only prophet, who founded an empire of absolute beauty
    "Fovos032",  # stripped the other signals for data to keep the old cycle, and failed
    "Nammou320",  # 19,522,113th -- cleared the other factors out of the extrapolation
)

#: The three that entered the calculation rather than being run by it. Two are Genius Society
#: members the log puts under "External variables", and the third is the Administrator who
#: reached in to keep the experiment running. None of them is Greek and none carries a number,
#: which is what says they came from outside: a designation with no cycle behind it is somebody
#: the experiment did not raise.
VISITORS: tuple[str, ...] = (
    "HertA",  # The Herta, an external variable
    "ScreW",  # Screwllum, the same
    "LykoS",  # Lygus the Administrator, whom Cerydra logged as a malicious visitor
)

#: Every designation the story says out loud, which is what the canon half draws from, and the
#: only place the wider canon is allowed to reach: a code out of here is finished, drawn whole
#: or not at all, where a word out of `HEIRS` is a stem three digits still have to be hung off.
#: Twenty-nine and no thirtieth -- the Scepter's own serial names the program the experiment
#: runs on rather than anybody it ran. Joined once here rather than rebuilt on every draw.
SAID: tuple[str, ...] = (
    *(f"{word}{number}" for word, number in HEIRS),
    *LOCKED,
    *SIGNALS,
    *VISITORS,
)

#: Everything else a generated code may be hung off: Greek for a thing a person can be made
#: to be, spelled as the heirs' own are -- a capital at the front and one more inside, falling
#: where the word breaks. No heir was ever issued one of these, which is the point: an agent
#: called `KykLos204` reads as somebody out of an era this one has not been told about.
WORDS: tuple[str, ...] = (
    "AgaPe",
    "AiDos",
    "AiOn",
    "AiTher",
    "AisThesis",
    "AletheIa",
    "AnamNesis",
    "AnanKe",
    "AndreIa",
    "AneMos",
    "ApeiRon",
    "ArChe",
    "AreTe",
    "ArithMos",
    "AsTer",
    "AtaraXia",
    "AthaNasia",
    "AutarKeia",
    "BiOs",
    "ChaRis",
    "ChroNos",
    "DaiMon",
    "DeiMos",
    "DemiOurgos",
    "DiKe",
    "DoLos",
    "DoXa",
    "DynaMis",
    "EidOs",
    "ElPis",
    "EnerGeia",
    "EpisTeme",
    "ErIs",
    "EtHos",
    "EudaiMonia",
    "GaIa",
    "GeneSis",
    "GnoSis",
    "HarmoNia",
    "HedoNe",
    "HeimarMene",
    "HeLios",
    "HemeRa",
    "HenoSis",
    "HoLos",
    "HorKos",
    "HyDor",
    "HyLe",
    "HypNos",
    "KaiRos",
    "KanOn",
    "KatharSis",
    "KenoMa",
    "KineSis",
    "KleOs",
    "KleRos",
    "KosMos",
    "KriSis",
    "KykLos",
    "LeThe",
    "LoGos",
    "LyPe",
    "MeLos",
    "MeTis",
    "MetRon",
    "MiasMa",
    "MimeSis",
    "MneMe",
    "MoiRa",
    "MonAs",
    "MorPhe",
    "NemeSis",
    "NoMos",
    "NosTos",
    "NoUs",
    "NykTos",
    "OiKos",
    "OrGe",
    "OuraNos",
    "OuSia",
    "ParrheSia",
    "PaThos",
    "PenThos",
    "PhaOs",
    "PhanTasia",
    "PhoBos",
    "PhosPhoros",
    "PhroNesis",
    "PhthoRa",
    "PisTis",
    "PleRoma",
    "PneuMa",
    "PoieSis",
    "PoiNe",
    "PoLis",
    "PoNos",
    "PraXis",
    "ProNoia",
    "PseuDos",
    "PsyChe",
    "RhythMos",
    "SeLene",
    "SoPhia",
    "SophroSyne",
    "SoTer",
    "StaSis",
    "StorGe",
    "SymBolon",
    "TechNe",
    "TeLos",
    "ThalasSa",
    "ThanaTos",
    "TheMis",
    "TheoRia",
    "ThyMos",
    "TiMai",
    "TriAs",
    "TyChe",
    "XeNia",
    "XeNos",
)

#: The morphemes a word may lead with, and the ones it may end on. A word is one of each
#: joined at the capital -- `MetaKratos`, `PolyMorphe` -- which is how `ApoRia` is spelled and
#: so how anything the story never needed is spelled too. Split in two rather than drawn from
#: one bag because `KratosMeta` reads backwards and `MetaKratos` does not. Two of these at
#: the least: a count is spelled in them, and one alone is a place notation that never carries.
JOINS: tuple[str, ...] = (
    "Amphi",
    "Ana",
    "Anti",
    "Apo",
    "Archi",
    "Auto",
    "Dia",
    "Dys",
    "Ek",
    "En",
    "Endo",
    "Epi",
    "Eu",
    "Exo",
    "Hemi",
    "Hetero",
    "Homo",
    "Hyper",
    "Hypo",
    "Iso",
    "Kata",
    "Makro",
    "Meso",
    "Meta",
    "Mikro",
    "Mono",
    "Neo",
    "Ortho",
    "Oxy",
    "Palin",
    "Pan",
    "Para",
    "Peri",
    "Poly",
    "Pro",
    "Proto",
    "Pseudo",
    "Syn",
    "Tele",
    "Tetra",
    "Tri",
)

#: What one of those leads to.
STEMS: tuple[str, ...] = (
    "Aion",
    "Arche",
    "Bios",
    "Chronos",
    "Doxa",
    "Genesis",
    "Gnosis",
    "Grapha",
    "Kosmos",
    "Kratos",
    "Krisis",
    "Latreia",
    "Lexis",
    "Logos",
    "Machia",
    "Mania",
    "Metron",
    "Moira",
    "Morphe",
    "Nomos",
    "Nous",
    "Odos",
    "Pathos",
    "Phonia",
    "Phora",
    "Pistis",
    "Pneuma",
    "Poiesis",
    "Praxis",
    "Psyche",
    "Rhythmos",
    "Skopos",
    "Soma",
    "Sophia",
    "Sphaira",
    "Stasis",
    "Taxis",
    "Techne",
    "Telos",
    "Thesis",
    "Thymos",
    "Tonos",
    "Topos",
    "Tropos",
    "Tyche",
)

#: The fewest morphemes a word is made of. One alone has no capital inside it and would not
#: read as a code at all, so a word is two and grows from there.
JOINED = 2

#: How often a code is one the story says out loud, while any of the twenty-nine is still
#: free. Half, which is nothing like what chance would give them: the rule can spell twelve of
#: the twenty-nine at all, and would land on one about once in eleven thousand with the words
#: written down here, let alone the ones built. The canon is what somebody would recognise, so
#: it is what somebody mostly gets.
CANON = 0.5

#: And how often the rest of the time is an heir's own word under a different number -- the
#: same role out of another era -- rather than some other word.
AGAIN = 0.5

#: How often that other word is one Greek already had rather than one built out of morphemes.
#: Both are the same rule; a word with a meaning behind it is just the better joke.
KNOWN = 0.5

#: The codes handed out in this process, which no second agent may be given: two agents left
#: unnamed are two agents, and a trace that read them as one would read a flow reviewing its
#: own work as a flow arguing with itself.
_CALLED: set[str] = set()
_CALLING = threading.Lock()

#: How far the counted codes have got. Only a process that has drawn most of what luck can
#: find reaches them, and it goes on from where it left off rather than counting again.
_COUNTING = itertools.count(1)

#: How many draws before the space is treated as crowded and codes are counted out instead.
#: Well past what luck needs when most of it is free.
_TRIES = 64


def codename() -> str:
    """Draws a codename no agent in this process has been given.

    Returns:
      The code: one the story spells, exactly as it spells it -- `NeiKos496`, `Golem99`,
      `ScreW` -- or one the rule builds, which is a Greek word and three digits --
      `KykLos204`, `MetaKratos881`.
    """
    with _CALLING:
        for _ in range(_TRIES):
            drawn = _drawn()
            if drawn not in _CALLED:
                _CALLED.add(drawn)
                return drawn
        return _counted()


def _drawn() -> str:
    """One draw, canon-heavy, which may be a code already given out.

    The canon half draws from the designations nobody holds yet rather than from all
    twenty-nine, so the first agents a process leaves unnamed get whole ones instead of losing
    half their draws to a code already out. Once those are gone that half falls through to the
    rule, which is what Amphoreus does with them anyway: the role runs again under another
    number.

    Returns:
      A code, canon or otherwise.
    """
    if random.random() < CANON and (  # noqa: S311 -- a joke, not a key
        free := [one for one in SAID if one not in _CALLED]
    ):
        return random.choice(free)  # noqa: S311
    return f"{_word()}{random.randrange(1000):03d}"  # noqa: S311


def _word() -> str:
    """A word to hang three digits off: an heir's, one Greek keeps, or one built to order.

    Only the heirs' words come back here, and none of the rest of the canon's. `Doril` is not
    Greek for anything a person can be made to be, so `Doril204` would read as a bug rather
    than as a joke, and `HertA` has no number to put one under at all. What the story spells
    outside the twelve is a finished designation, and `SAID` is the only place it is drawn from.

    Returns:
      The word, capitalised at the front and where it breaks.
    """
    if random.random() < AGAIN:  # noqa: S311
        return random.choice(HEIRS)[0]  # noqa: S311
    if random.random() < KNOWN:  # noqa: S311
        return random.choice(WORDS)  # noqa: S311
    return random.choice(JOINS) + random.choice(STEMS)  # noqa: S311


def _counted() -> str:
    """A code built to order, for a process that has drawn most of what luck can find.

    Counted rather than drawn, so it always answers and always by the rule. The count is read
    off as morphemes -- the stem lowest, the joins above it -- which is a place notation over
    the two lists, so every count spells a different word and the word grows one morpheme each
    time the shorter ones run out. There is no last code, and so nothing to fall back to: an
    agent nobody named has a Greek word and three digits however many have been handed out.

    Returns:
      The first counted code nobody holds.
    """
    while True:
        count, number = divmod(next(_COUNTING), 1000)
        count, index = divmod(count, len(STEMS))
        parts = [STEMS[index]]
        while count or len(parts) < JOINED:
            count, index = divmod(count, len(JOINS))
            parts.append(JOINS[index])
        drawn = f"{''.join(reversed(parts))}{number:03d}"
        if drawn not in _CALLED:
            _CALLED.add(drawn)
            return drawn
