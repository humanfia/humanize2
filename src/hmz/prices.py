"""What a token costs in money, from a list somebody else keeps up to date.

A token count says how much work was done and nothing about what it came to. The unit prices
are somebody else's to keep -- they change on the vendors' own schedule, and a list written
down in here would be wrong the week after it was written -- so they are fetched from
OpenLLMPrices, which is one JSON file of them, and kept under humanize's own home.

Two rules hold this whole module up. **Nothing here may cost a prompt its responsiveness**:
`price` and `cost` read what was already kept and never reach for the network, and fetching
is asked for by whoever has time for it and runs on a thread of its own. And **a model
nobody lists reads as tokens alone**: the list covers a few dozen models and humanize drives
whatever CLI you have, so answering nothing is the ordinary case rather than the broken one.
A `$0.00` against a model nobody priced would be a lie about a bill.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from hmz import home

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["SOURCE", "Price", "cost", "money", "price", "refresh", "where"]

#: The one JSON file OpenLLMPrices is over. There is no API beside it: the site itself reads
#: this and nothing else, so this is the whole of the source rather than a scrape of a page.
SOURCE = "https://openllmprices.com/data/prices.json"

#: What names another file or another URL to read instead, and what turns the fetching off
#: altogether -- which is what an air-gapped install wants, and what this suite is run under
#: so that no test ever reaches the network.
WHENCE = "HUMANIZE_PRICES"

#: How old what is kept may get before a refresh is worth making. A vendor's price moves a
#: few times a year, so a day is far oftener than it needs to be and cheap besides: the fetch
#: is conditional, and an unchanged file comes back as three hundred and four bytes of nothing.
STALE = 24 * 60 * 60.0

#: How long the fetch is given before it is left for another day. Nobody is waiting on it.
_WAITING = 20.0

#: The most that will be read from the source. It is two and a half megabytes today; this is
#: the cap that says a redirect onto something else is not a file to parse.
_MOST = 64 * 1024 * 1024

#: A price is per this many tokens, which is what the file's own `unit` says.
_MILLION = 1_000_000

#: What each priced category is called here. The file's vocabulary is not humanize's, and a
#: kind is named the same thing wherever it is counted. `cache_storage` is deliberately
#: absent: it is charged by the hour rather than by the token, and there is no token count
#: here to multiply it by.
_CATEGORIES = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cache_read_tokens": "cache_read",
    "cache_write_tokens": "cache_write",
}

#: What a kind is billed as where it is not billed as itself. A backend that counts its
#: reasoning beside the output rather than inside it is still buying output tokens.
_BILLED = {"reasoning": "output"}

#: And what to fall back on for a kind the list does not price separately. Only where the
#: fallback cannot overstate: a cache write is an input token and a surcharge on it, so the
#: input price is a floor on it. A cache *read* is the other way about -- a tenth of the input
#: price is usual -- and an agent's turns are mostly cached reads, so pricing one as an input
#: token would put the bill several times over the truth. It is left out instead, and the
#: figure is a floor.
_INSTEAD = {"cache_write": "input"}

#: A trailing scrap that names a release rather than a model. Tried one at a time and then
#: together, so that a model listed with its date intact still matches itself first.
_DATED = re.compile(r"[-@_](?:19|20)\d{2}-?\d{2}-?\d{2}$")
_VERSIONED = re.compile(r"[-@]v\d+$")
_LATEST = re.compile(r"[-@](?:latest|stable)$")

#: Where a hosted deployment name ends and the model begins: `us.anthropic.claude-sonnet-5`
#: is Bedrock's spelling of a model this file lists as `claude-sonnet-5`.
_QUALIFIED = re.compile(r"^[a-z]+\.")

#: And where the route a gateway offers a model by ends. A gateway in front of several clouds
#: writes which cloud into the id -- `aws/anthropic/bedrock-claude-opus-5` is one machine's
#: way of saying `claude-opus-5` -- and where it goes is neither the model nor its price.
#: Tried only after the id as written, so a model listed under one of these words still wins.
_ROUTED = re.compile(r"^(?:bedrock|vertex|azure|aws|gcp)-")

_lock = threading.Lock()
#: What was last read off the disk, and the modification time it was read at -- so that a
#: refresh landing is picked up without the file being parsed again on every draw.
_listing: dict[str, Price] | None = None
_read_from: tuple[str, float] | None = None
#: Whether a fetch is already running, and when one was last attempted: a source that is down
#: must not be asked again on every redraw of a screen.
_fetching = False
_tried = 0.0


@dataclass(frozen=True, slots=True)
class Price:
    """What one model costs, per million tokens, as the list spells it.

    Attributes:
      model: The id the list gives it, which is not necessarily the id the backend runs it
        under -- see :func:`price` for what the matching does and does not promise.
      provider: Who sells it.
      per_million: US dollars per million tokens, by the kind of token. A kind that is not
        here is one this model is not priced for, which is not the same as a free one.
    """

    model: str
    provider: str
    per_million: Mapping[str, float]


def where() -> pathlib.Path:
    """Where what was fetched is kept.

    Returns:
      The file, under humanize's own home. It holds the newest version of the list and
      nothing else: the source carries three years of dated snapshots, and what a run costs
      is what it costs today.
    """
    return home() / "prices.json"


def price(model: str) -> Price | None:
    """What one model costs, if anybody lists it.

    The match is exact once both names are stripped to what they have in common: the account
    or provider a backend writes in front of a model, the release date it writes behind one,
    and the punctuation two spellings of one model disagree about. `anthropic/claude-sonnet-5`,
    `claude-sonnet-5` and `us.anthropic.claude-sonnet-5-v1:0` are all `claude-sonnet-5`, and
    `claude-haiku-4-5-20251001` is `claude-haiku-4.5`.

    Nothing here guesses. A near miss is a miss: `gpt-5` is not `gpt-5.6-sol`, and a model
    the list has never heard of answers nothing rather than the price of its neighbour. Nor
    does it read a tier: a model priced differently above some context length is taken at the
    first tier the list gives, which is the standard price, so a very long turn cost more than
    this says.

    Args:
      model: The model as whatever counted the tokens spelled it.

    Returns:
      Its price, or None where the list does not have it -- which is the ordinary answer,
      the list being a few dozen models and humanize driving whatever CLI you have.
    """
    listed = _index()
    for key in _keys(model):
        found = listed.get(key)
        if found is not None:
            return found
    return None


def cost(usage: Mapping[str, float], model: str) -> float | None:
    """What some tokens came to, in US dollars.

    Args:
      usage: Tokens by kind, as `hmz.agents.Usage` counts them.
      model: What they were spent on.

    Returns:
      The money, or None both for a model nobody lists and for a reckoning none of whose
      kinds this model is priced for -- a caller MUST show either as tokens alone rather than
      as nothing spent. A kind that is not priced adds nothing, so what comes back is what the
      priced kinds came to: a floor, and never more than the truth.
    """
    listed = price(model)
    if listed is None:
        return None
    per = listed.per_million
    total = 0.0
    priced = False
    for kind, tokens in usage.items():
        named = _BILLED.get(kind, kind)
        rate = per.get(named)
        if rate is None:
            rate = per.get(_INSTEAD.get(named, ""))
        if rate is None:
            continue  # a kind nobody prices, including the one that has no name at all
        if tokens > 0:
            # Priced only where something was actually priced. A reckoning whose priced kinds
            # are all empty has nothing to say about a bill, and `$0.00` of it would say the
            # run was free.
            priced = True
            total += tokens * rate / _MILLION
    return total if priced else None


def money(dollars: float) -> str:
    """Renders a bill short enough to sit beside a token count.

    Args:
      dollars: What it came to.

    Returns:
      The money, cut to what can be read at a glance -- and to four places while it is under
      a cent, since a run that has cost a tenth of one has still cost something and `$0.00`
      would say it had not.
    """
    if dollars >= 100:  # noqa: PLR2004 -- cents nobody reads on a bill this size
        return f"${dollars:,.0f}"
    if dollars >= 0.01:  # noqa: PLR2004 -- a cent, under which two places say nothing
        return f"${dollars:.2f}"
    if dollars > 0:
        return f"${dollars:.4f}"
    return "$0.00"


def refresh(*, wait: bool = False) -> bool:
    """Fetches the list again, if what is kept has got old.

    Asked for by whoever has the time for it -- the interface, as it opens -- and never by
    the drawing of a figure. It runs on a thread of its own, it is conditional on the etag of
    what is already here, and every way it can go wrong ends with what was kept still being
    served: a price list that could stop a run would be worth less than no price list.

    Args:
      wait: Whether to fetch on this thread instead of on one of its own. For a caller that
        has somewhere to report the answer, and for a test.

    Returns:
      Whether the list was fetched and kept, which is only ever answered for a caller that
      waited: one left running answers False because it has not happened yet.
    """
    global _fetching, _tried  # noqa: PLW0603 -- one list per process, held beside it
    whence = _whence()
    if not whence:
        return False  # somebody has said not to reach for it at all
    now = time.monotonic()
    with _lock:
        if _fetching or (_tried and now - _tried < STALE / 24):
            return False
        if not wait and _fresh():
            return False  # what is kept is new enough to go on serving
        _fetching = True
        _tried = now
    if wait:
        try:
            return _fetch(whence)
        finally:
            _release()
    threading.Thread(target=_fetching_now, args=(whence,), daemon=True).start()
    return False


def _fetching_now(whence: str) -> None:
    """Fetches on the thread this was started on, and lets go however it goes."""
    try:
        _fetch(whence)
    finally:
        _release()


def _release() -> None:
    """Marks the fetch as over, so that the next stale read may make another."""
    global _fetching  # noqa: PLW0603 -- one list per process, held beside it
    with _lock:
        _fetching = False


def _whence() -> str:
    """The source, which an environment variable may point elsewhere or turn off entirely."""
    said = os.environ.get(WHENCE)
    if said is None:
        return SOURCE
    return (
        "" if said.strip().lower() in {"", "off", "0", "no", "none"} else said.strip()
    )


def _fresh() -> bool:
    """Whether what is kept is new enough that fetching it again would buy nothing."""
    try:
        return time.time() - where().stat().st_mtime < STALE
    except OSError:
        return False


def _fetch(whence: str) -> bool:
    """Reads the source and keeps what it says, or leaves what is kept exactly as it was.

    Args:
      whence: The URL, or a path for a caller pointing this at a file.

    Returns:
      Whether what is kept is now the source's.
    """
    kept = where()
    held = _held(kept)
    # The etag only where it belongs to the source being asked. Replayed at another, a 304
    # would date the first source's prices forward and go on serving them as this one's.
    was = str(held.get("etag") or "") if held.get("source") == whence else ""
    try:
        if "://" not in whence:
            body, etag = _from_file(whence)
        else:
            body, etag = _over_http(whence, was)
    except _Unchanged:
        # The etag matched, so what is here is the source's: dated forward rather than
        # written again, which is what stops the next read fetching it all over.
        with contextlib.suppress(OSError):
            os.utime(kept)
        return True
    except (OSError, http.client.HTTPException, urllib.error.URLError, ValueError):
        # The network is gone, the file is, or the answer stopped half way through. Every
        # one of them leaves what was kept still serving: nothing here may fail a run.
        return False
    try:
        loaded: object = json.loads(body)
    except ValueError:
        return False
    trimmed = _trim(loaded, whence, etag)
    if trimmed is None:
        return False  # not the shape this reads, or not priced in dollars a token
    return _keep(kept, trimmed)


class _Unchanged(Exception):  # noqa: N818 -- an answer rather than a failure
    """The source says what is already kept here is what it has."""


def _over_http(whence: str, etag: str) -> tuple[bytes, str]:
    """Fetches the list, asking for it only if it has changed.

    Args:
      whence: The URL.
      etag: What the copy already here came back with, or nothing.

    Returns:
      The body and the etag to keep beside it.

    Raises:
      _Unchanged: If the source says what is kept is current.
    """
    asked = urllib.request.Request(  # noqa: S310 -- the scheme is checked below
        whence, headers={"Accept": "application/json", "User-Agent": "humanize"}
    )
    if asked.type not in {"http", "https"}:
        msg = f"prices come over http, not {asked.type}"
        raise ValueError(msg)
    if etag:
        asked.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(asked, timeout=_WAITING) as answer:  # noqa: S310
            return answer.read(_MOST), str(answer.headers.get("ETag") or "")
    except urllib.error.HTTPError as why:
        if why.code == 304:  # noqa: PLR2004 -- not modified, which is the good answer
            raise _Unchanged from why
        raise


def _from_file(whence: str) -> tuple[bytes, str]:
    """Reads the list off the disk, for whoever pointed this at a copy of it."""
    return pathlib.Path(whence).read_bytes(), ""


def _trim(loaded: object, whence: str, etag: str) -> dict[str, Any] | None:
    """Cuts the source down to the prices, and refuses anything it cannot read as money.

    The file is three years of dated snapshots and every modality each model takes, of which
    what is wanted is the newest version's per-token prices. Keeping the rest would be two
    and a half megabytes parsed at every start for nothing.

    Args:
      loaded: The whole document.
      whence: Where it came from, kept so that a cache filled from a copy says so.
      etag: What to send back next time.

    Returns:
      What to keep, or None for a document this cannot read -- which includes one priced in
      another currency or by another unit. Showing the wrong money is worse than none.
    """
    if not isinstance(loaded, dict):
        return None
    said = cast("dict[str, Any]", loaded)
    if str(said.get("currency") or "") != "USD":
        return None
    if "1M" not in str(said.get("unit") or ""):
        return None
    versions: object = said.get("versions")
    if not isinstance(versions, list) or not versions:
        return None
    # By its date rather than by its place in the list. The source writes them newest first
    # today; a source that one day appended instead would otherwise have humanize quietly
    # serving three-year-old prices, with nothing anywhere to notice it by.
    listed: dict[str, Any] | None = None
    latest = ""
    for one in cast("list[Any]", versions):
        if not isinstance(one, dict):
            continue
        version = cast("dict[str, Any]", one)
        when = str(version.get("date") or "")
        if listed is None or when > latest:
            listed, latest = version, when
    if listed is None:
        return None
    every: object = listed.get("models")
    models: dict[str, Any] = {}
    for one in cast("list[Any]", every) if isinstance(every, list) else []:
        if not isinstance(one, dict):
            continue
        model = cast("dict[str, Any]", one)
        named = str(model.get("id") or "")
        per = _per_million(model.get("pricingItems") or [])
        if named and per:
            models[named] = {
                "provider": str(model.get("provider") or ""),
                "name": str(model.get("name") or ""),
                "per_million": per,
            }
    if not models:
        return None
    return {
        "source": whence,
        "etag": etag,
        "fetched": time.time(),
        "date": str(listed.get("date") or ""),
        "models": models,
    }


def _per_million(items: object) -> dict[str, float]:
    """What one model costs per million tokens, by kind.

    The first entry for a kind wins. One model carries several, one per context tier and one
    per cache duration, written cheapest-tier-first -- and nothing here knows how long the
    prompt was or how long the cache was held for, so the standard price is the honest one to
    take and the one to say has been taken.

    Args:
      items: The model's `pricingItems`.

    Returns:
      Dollars per million tokens, by the kind humanize counts them under.
    """
    per: dict[str, float] = {}
    if not isinstance(items, list):
        return per
    for one in cast("list[Any]", items):
        if not isinstance(one, dict):
            continue
        item = cast("dict[str, Any]", one)
        kind = _CATEGORIES.get(str(item.get("category") or ""))
        asked: object = item.get("price")
        if kind is None or kind in per or not isinstance(asked, (int, float)):
            continue
        if isinstance(asked, bool) or asked < 0:
            continue
        per[kind] = float(asked)
    return per


def _keep(kept: pathlib.Path, trimmed: dict[str, Any]) -> bool:
    """Writes what was fetched, whole or not at all.

    Args:
      kept: Where it goes.
      trimmed: What to write.

    Returns:
      Whether it landed.
    """
    beside = kept.with_name(f"{kept.name}.{os.getpid()}")
    try:
        kept.parent.mkdir(parents=True, exist_ok=True)
        beside.write_text(json.dumps(trimmed), encoding="utf-8")
        # Replaced rather than written over: two humanize processes refresh this on their
        # own clocks, and a reader must never see half a file.
        beside.replace(kept)
    except OSError:
        with contextlib.suppress(OSError):
            beside.unlink()
        return False
    with _lock:
        global _read_from  # noqa: PLW0603 -- one list per process, held beside it
        _read_from = None  # so the next read picks this up rather than what it holds
    return True


def _held(kept: pathlib.Path) -> dict[str, Any]:
    """What is on the disk now, as it was written -- or nothing, for every way that fails."""
    try:
        loaded: object = json.loads(kept.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else {}


def _index() -> dict[str, Price]:
    """The prices as they were last kept, read once and then held.

    Re-read when the file under it has moved, which is how a refresh landing on a thread of
    its own reaches a screen that is already drawing figures.

    Returns:
      One entry per way of spelling a model that is listed, which is what `price` looks in.
    """
    global _listing, _read_from  # noqa: PLW0603 -- one list per process, held beside it
    kept = where()
    try:
        stamp = kept.stat().st_mtime
    except OSError:
        stamp = 0.0
    # The path as well as the time it was written: a home moved out from under this -- which
    # is what a suite does to every test -- is another list, however old either of them is.
    at = (str(kept), stamp)
    with _lock:
        if _listing is not None and at == _read_from:
            return _listing
        _read_from = at
        _listing = _read(kept)
        return _listing


def _read(kept: pathlib.Path) -> dict[str, Price]:
    """Builds the lookup out of what was kept.

    Args:
      kept: The file.

    Returns:
      Every listed model under every spelling of it this can recognise. An id wins over a
      name, two models never being one because their display names squash the same.
    """
    held = _held(kept)
    models: object = held.get("models")
    if not isinstance(models, dict):
        return {}
    found: dict[str, Price] = {}
    for named, one in cast("dict[str, Any]", models).items():
        if not isinstance(one, dict):
            continue
        model = cast("dict[str, Any]", one)
        per: object = model.get("per_million")
        if not isinstance(per, dict):
            continue
        rates: dict[str, float] = {
            str(kind): float(rate)
            for kind, rate in cast("dict[str, Any]", per).items()
            if isinstance(rate, (int, float)) and not isinstance(rate, bool)
        }
        if not rates:
            continue
        priced = Price(
            model=str(named),
            provider=str(model.get("provider") or ""),
            per_million=rates,
        )
        found[_squash(named)] = priced
        found.setdefault(_squash(str(model.get("name") or "")), priced)
    found.pop("", None)
    return found


def _keys(model: str) -> list[str]:
    """Every way this model might be written in the list, likeliest first.

    Args:
      model: The model as whatever counted the tokens spelled it.

    Returns:
      Squashed keys to look up, in the order to try them: the whole of it before the part
      after the provider, and each of those before the same with a release date or a version
      cut off it. Order matters, so that a model the list gives with its date intact -- and
      there are such -- matches itself rather than a shorter neighbour.
    """
    said = re.sub(r":\d+$", "", model.strip().lower())
    tries: list[str] = []
    for whole in (said, said.rpartition("/")[2]):
        bare = _QUALIFIED.sub("", _QUALIFIED.sub("", whole))
        for one in (whole, bare, _ROUTED.sub("", bare)):
            for cut in (
                one,
                _LATEST.sub("", one),
                _VERSIONED.sub("", one),
                _DATED.sub("", one),
                _DATED.sub("", _VERSIONED.sub("", _LATEST.sub("", one))),
            ):
                key = _squash(cut)
                if key and key not in tries:
                    tries.append(key)
    return tries


def _squash(named: str) -> str:
    """One spelling of a model, cut to the letters and digits two spellings would share.

    `claude-haiku-4-5` and `Claude Haiku 4.5` are one model written by two people who
    disagreed about punctuation, and nothing but punctuation.
    """
    return re.sub(r"[^a-z0-9]", "", named.lower())
