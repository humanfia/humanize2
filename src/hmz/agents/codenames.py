"""What an agent nobody named is called, which is a codename out of Amphoreus.

An agent given no name still needs one nothing else answers to, and `ClaudeCodeAgent#3f2a1b9c`
is a name only a debugger loves. So one is drawn from the Chrysos Heirs instead -- the golden
blooded of Amphoreus, whose codes *Honkai: Star Rail* spells as a Greek word for what the heir
was made to be and three digits with something behind them. `NeiKos496` is strife, and 496 is
the third perfect number; `SkeMma720` is inquiry, and 720 is 6!; `KaLos618` is beauty, and 618
is the golden ratio. The cycle the story is told in is the 33,550,336th, which is the fifth
perfect number, so the numbers are the joke and not decoration.

Twelve of the thirteen carry a code the story says out loud. The thirteenth is the outsider
who walked into the simulation and was never issued one, which is the shape of this file: the
twelve are the canon, and everything else drawn here is another cycle of the same roles under
another number -- Amphoreus reruns its heirs, and two of them have already shared `EpieiKeia216`
across cycles. The canon comes up far more often than its share of the pool would give it, a
name being only a joke to somebody who recognises it.
"""

from __future__ import annotations

import random
import threading
import uuid

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

#: Everything else a code may be drawn from: Greek for a thing a person can be made to be,
#: spelled as the heirs' own are -- a capital at the front and one more inside, falling where
#: the word breaks. No heir was ever issued one of these, which is the point: an agent called
#: `KykLos204` reads as somebody out of a cycle this one has not been told about.
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

#: How often a code is one of the twelve exactly as the story spells it, while any of the
#: twelve is still free. Half, which is nothing like the one in eleven thousand a pool this
#: size would give them by chance: the heirs are what somebody would recognise, so they are
#: what somebody mostly gets.
CANON = 0.5

#: And how often the rest of the time is an heir's own word under a different number -- the
#: same role out of another cycle -- rather than a word no heir ever carried.
AGAIN = 0.5

#: The codes handed out in this process, which no second agent may be given: two agents left
#: unnamed are two agents, and a trace that read them as one would read a flow reviewing its
#: own work as a flow arguing with itself.
_CALLED: set[str] = set()
_CALLING = threading.Lock()

#: How many draws before the space is treated as crowded and walked in order instead. Well
#: past what luck needs when most of it is free, and reached only by a process that has
#: opened tens of thousands of agents nobody named.
_TRIES = 64


def codename() -> str:
    """Draws a codename no agent in this process has been given.

    Returns:
      The code, as an heir's word and three digits -- `NeiKos496`, `KykLos204`.
    """
    with _CALLING:
        for _ in range(_TRIES):
            drawn = _drawn()
            if drawn not in _CALLED:
                _CALLED.add(drawn)
                return drawn
        return _walked()


def _drawn() -> str:
    """One draw, canon-heavy, which may be a code already given out.

    The canon half draws from the heirs nobody holds yet rather than from all twelve, so the
    first agents a process leaves unnamed get whole heirs instead of losing half their draws
    to a code already out. Once the twelve are gone that half falls through to the rest, which
    is what Amphoreus does with them anyway: the role runs again under another number.

    Returns:
      A code, canon or otherwise.
    """
    if random.random() < CANON:  # noqa: S311 -- a joke, not a key
        canon = (f"{word}{number}" for word, number in HEIRS)
        if free := [one for one in canon if one not in _CALLED]:
            return random.choice(free)  # noqa: S311
    again = random.random() < AGAIN  # noqa: S311
    word = random.choice(HEIRS)[0] if again else random.choice(WORDS)  # noqa: S311
    return f"{word}{random.randrange(1000):03d}"  # noqa: S311


def _walked() -> str:
    """The whole space in order, for a process that has drawn most of it already.

    Returns:
      The first code nobody holds, or -- past every code there is -- the misnumbered one out
      of the early cycle, which is not a code so much as a fault, and is made unique the way
      an agent's name was before any of this.
    """
    for word in (*(one for one, _ in HEIRS), *WORDS):
        for number in range(1000):
            drawn = f"{word}{number:03d}"
            if drawn not in _CALLED:
                _CALLED.add(drawn)
                return drawn
    drawn = f"Chaoz666#{uuid.uuid4().hex[:8]}"
    _CALLED.add(drawn)
    return drawn
