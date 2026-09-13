"""What each backend runs, asked of the backend itself and kept until it is asked again.

A model id is not a fact anybody can write down. It is whatever that CLI shipped this week,
and which of them a turn may name depends on the account it runs as: a subscription, a key and
somebody's gateway are three catalogues under one command. So there is no list here. Each
backend is asked, in whatever way that backend offers being asked -- a control request, a debug
command, a provider dump, a table -- and what it says is kept per account.

Except that a CLI pointed at somebody's endpoint answers with the models *it* ships. It has no
way not to: nothing it enumerates ever went and looked at the other end of the base URL it was
handed. That answer is wrong the moment it is given, however recently it was taken, and the
account it is wrong for is exactly the one whose models nobody could have written down. So
where an account names an endpoint, the endpoint is what is asked -- `GET {base}/v1/models`,
under that account's own credentials -- and the CLI is asked only where there is no endpoint,
where it will not answer, or where what came back is not a list of models.

Asking means starting a coding agent, or reaching somebody's endpoint, and both cost seconds a
prompt has not got. So nothing is asked at a prompt: an account is asked the moment it is made,
`ask` is what asks again -- the `r` key on the sheet that lists what a backend runs, where
somebody pressed something and is waiting on the answer -- and everything else reads what
was kept. A catalogue that has
never been asked for is empty rather than guessed at: a model nobody can run is worse than a
list somebody has to fill.

What is kept for an account lives with that account, so that taking the account away takes its
catalogue with it: they are the same fact. The account nobody chose -- the CLI as whoever is at
this machine already runs it -- keeps its own under humanize's home.
"""

from __future__ import annotations

import datetime
import http.client
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, cast

from hmz import home
from hmz.coganchor import providers
from hmz.coganchor.backends import Model, elsewhere, named, speaking

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path
    from typing import IO

    from hmz.coganchor.backends import Profile

__all__ = ["ask", "asked", "offered", "where"]

#: How long a backend is given to say what it runs. Generous, because this is a coding agent
#: starting up and some of them take the better part of a minute over it. Nothing waits on
#: this at a prompt, so the cost of waiting too long is a spinner rather than a lost answer.
WAITING = 180.0

#: Where the catalogue of the account nobody chose is kept, under humanize's own home. A
#: provider's is kept in the provider's own directory instead.
_UNDER = "models"

#: What the file is called inside a provider's directory.
_HELD = "models.json"

#: The id the one thing said to Claude Code is sent under, which it answers by.
_ASKS = "models"

#: How Claude Code describes a model named by `ANTHROPIC_CUSTOM_MODEL_OPTION`, which is the
#: one entry whose `value` is a name somebody chose rather than one Claude ships.
_CUSTOM = "Custom model"

#: What Claude Code writes on the end of a model to mean that model at its largest window. A
#: way of running the model rather than a model, so it comes off the id: the backend asked for
#: one under that spelling answers that there is no such model.
_WINDOW = re.compile(r"\[[^\]]*\]$")

#: What codex marks the models it offers with. It has others it does not offer, and a list of
#: what can be chosen is the ones it lists.
_LISTED = "list"

#: What opencode and mimocode write after a model to say how much it holds.
_ABOUT = " — "

#: The advisory catalogue shipped by the official DeepSeek adapter. Its preview SDK has no
#: model-list request, so where the account names no endpoint this is both what asking it
#: answers and what a first prompt offers before there is a cache to read.
_DSH_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")

#: The same for Qwen Code, which has no command that lists what it runs: it is a client of an
#: OpenAI-compatible endpoint, so the catalogue belongs to the account rather than to the CLI.
#: These are what it ships pointed at, for an account that names no endpoint of its own; one
#: that does is answered by that endpoint, which is where its catalogue was all along.
_QWEN_MODELS = ("qwen3-coder-plus", "qwen3-coder-flash")

#: The backends whose catalogue is written down here rather than asked for, which is what a
#: prompt offers before either has been asked.
_ADVISORY = {"dsh": _DSH_MODELS, "qwen": _QWEN_MODELS}

#: How long an endpoint is given to say what it serves. Short beside `WAITING`, which is a
#: coding agent starting up: this is one request, and one that does not answer promptly is
#: one to fall back from rather than one to wait out.
_REACHING = 20.0

#: The most that will be read from it. A catalogue is kilobytes; this is the cap that says a
#: redirect onto something else is not a list to parse.
_MOST = 8 * 1024 * 1024

#: Where a model list is served under a base URL that already names its version -- an account
#: is written down either way, `https://host` and `https://host/v1` both being how a person
#: was told to spell the same gateway, and `/v1/v1/models` is nowhere.
_VERSIONED = re.compile(r"/v\d+[a-z0-9]*$")

#: What a key is sent as. Both, because a gateway fronting several vendors is asked what it
#: serves without knowing which protocol it prefers to be asked in: `Authorization` is what an
#: OpenAI-shaped catalogue reads and `x-api-key` is what an Anthropic-shaped one does, and
#: each ignores the other. The value never leaves this request -- not to the file, not to a
#: log, and not into the message raised when the endpoint refuses.
_BEARER = "Authorization"
_KEYED = "x-api-key"

#: The version an Anthropic-shaped endpoint refuses to answer without.
_DATED = "2023-06-01"


def where(cli: str, provider: str = "") -> Path:
    """Where what this backend said it runs is kept, for one account.

    Args:
      cli: The backend, by any name it answers to.
      provider: The account, by the name the provider was made under, or "" for the CLI as
        whoever is at this machine already runs it.

    Returns:
      The path, whether or not anything has been asked yet.

    Raises:
      ValueError: If the backend is not one there is, or the name is not one a provider could
        have been made under.
    """
    profile = named(cli)
    if profile is None:
        raise ValueError(f"{cli}: no such coding agent")
    if provider:
        return providers.where(profile.name, provider) / _HELD
    return home() / _UNDER / f"{profile.name}.json"


def offered(cli: str, provider: str = "") -> tuple[Model, ...]:
    """What this backend last said it runs for one account, which is what a prompt reads.

    One file read, so it can be asked for between keystrokes.

    Args:
      cli: The backend, by any name it answers to.
      provider: The account, or "" for the CLI as it already runs.

    Returns:
      The models, in the order the backend gave them. Nothing at all where it has never been
      asked, where what was written cannot be read back, or where the name is not one of a
      backend there is -- each of which is a catalogue to fill rather than a reason to raise
      at whoever only wanted to see a list.
    """
    found = tuple(
        Model(name, tuple(efforts), swarms)
        for name, efforts, swarms in _read(_kept(cli, provider))
    )
    profile = named(cli)
    if not found and profile is not None and profile.name in speaking():
        # The protocol says nothing about which models an agent runs: that is the agent's own
        # to know, and it runs as whoever installed it configured it. One row so that an
        # agent can be configured at all.
        return (Model(profile.efforts[0], profile.efforts, profile.swarms),)
    if not found and profile is not None and profile.name in _ADVISORY:
        return tuple(
            Model(name, profile.efforts, profile.swarms)
            for name in _ADVISORY[profile.name]
        )
    return found


def asked(cli: str, provider: str = "") -> str:
    """When this backend was last asked what it runs, for one account.

    Args:
      cli: The backend, by any name it answers to.
      provider: The account, or "" for the CLI as it already runs.

    Returns:
      The moment, as it was written down, and "" for an account that has never been asked.
    """
    held = _kept(cli, provider)
    said = held.get("asked")
    return said if isinstance(said, str) else ""


def ask(cli: str, provider: str = "", seconds: float = WAITING) -> tuple[Model, ...]:
    """Asks what this account runs, writes it down, and answers.

    Asked of the endpoint the account points its backend at, where it names one, and of the
    backend itself where it does not. Either way as a turn of that account is taken: under the
    provider's own paths, with the variables that account sets and without the ones its
    backend would take another account from. What comes back is what a turn could actually
    name -- which is why the endpoint goes first where there is one, a CLI having no way of
    answering with anything but the models it shipped with.

    Args:
      cli: The backend, by any name it answers to.
      provider: The account, or "" for the CLI as whoever is at this machine already runs it.
      seconds: How long the backend is given to answer, for the times it is the one asked.

    Returns:
      What was said, in its own order and with each model named once.

    Raises:
      ValueError: If the backend is not one there is, has no way of being asked, is not that
        account's, or said something this cannot read.
      OSError: If it is not installed here.
      subprocess.TimeoutExpired: If it did not answer in time.
    """
    profile = named(cli)
    if profile is None:
        raise ValueError(f"{cli}: no such coding agent")
    reading = _READING.get(profile.name)
    if reading is None:
        raise ValueError(f"{profile.name} has no way of being asked what it runs")
    environ, run = _asking(profile, provider, seconds)
    served = _served(profile, environ)
    found: list[Model] = []
    seen: set[str] = set()
    for model in served if served is not None else reading(profile, run):
        # A backend may name one model twice -- Claude Code offers the default under its own
        # name as well as under `default` -- and a list with a model in it twice is a list
        # somebody reads as two models.
        if model.name and model.name not in seen:
            seen.add(model.name)
            found.append(model)
    _write(where(profile.name, provider), found)
    return tuple(found)


def _asking(
    profile: Profile, provider: str, seconds: float
) -> tuple[dict[str, str], Callable[..., str]]:
    """How to put a question to one backend as one account.

    Args:
      profile: The backend.
      provider: The account, or "" for the CLI as it already runs.
      seconds: How long it is given to answer.

    Returns:
      The environment a turn of that account runs under, and what runs the backend's own
      command and answers with what it printed -- taking the arguments after the command's
      own name and what to say to it on the way in. The environment comes back beside it so
      that whatever asks the endpoint instead reads the same resolution rather than a second
      one of its own: an account is where its variables say it is, once.

    Raises:
      ValueError: If that backend has no account of that name.
    """
    held = providers.find(profile.name, provider) if provider else None
    if provider and held is None:
        raise ValueError(f"{profile.name} has no account called {provider}")
    # As a turn of that account is run: what the provider sets, and none of what its backend
    # would take another account from -- a key in somebody's shell profile outranks the
    # credentials a provider was signed in with, and the answer would be the wrong account's.
    hushed = profile.hushes() - set(held.env) if held is not None else frozenset[str]()
    environ = {name: value for name, value in os.environ.items() if name not in hushed}
    environ |= dict(held.env) if held is not None else {}

    def run(args: list[str], said: str = "") -> str:
        # Started as a turn of it is started, which is by name where PATH names one and by
        # the path it is installed at where it does not: a backend found somewhere this
        # machine's PATH does not name is still a backend to ask.
        command = profile.runs()
        argv = [elsewhere(command) or command, *args]
        # Under the provider's own credential paths, which is the whole of what makes the
        # answer that account's rather than this machine's.
        done = subprocess.run(
            held.command(argv) if held is not None else argv,
            input=said,
            capture_output=True,
            text=True,
            timeout=seconds,
            check=False,
            env=environ,
        )
        if done.returncode != 0:
            # The last line it said, which is where these put the reason: a CLI that is not
            # signed in says so, and that is the whole of what somebody needs to read.
            why = done.stderr.strip().splitlines()
            raise ValueError(
                f"{profile.name} exited {done.returncode}"
                + (f": {why[-1].strip()}" if why else "")
            )
        return done.stdout

    return environ, run


def _served(profile: Profile, environ: Mapping[str, str]) -> list[Model] | None:
    """What the endpoint this account points its backend at says it serves.

    The whole of the fix for a catalogue that is fresh and wrong: a CLI handed a base URL
    answers with the models it ships, having nothing that goes and looks, so an account on
    somebody's gateway is offered three names the gateway will refuse and a refresh changes
    nothing. What that account may name is what is at the other end of its own base URL.

    Args:
      profile: The backend, which says which variable carries that URL.
      environ: The environment a turn of this account runs under, as `_asking` resolved it.

    Returns:
      One per id it serves, each at the backend's whole ladder -- a catalogue says nothing
      about how hard a model may be asked to think, and a model nothing narrows is one its
      backend will take any rung for. None where there is no endpoint to ask, where it would
      not answer, and where what it answered is not a list of models: an endpoint that will
      not say is a reason to ask the CLI, never a reason to have no catalogue at all.
    """
    base = environ.get(profile.endpoint, "").strip() if profile.endpoint else ""
    if not base:
        return None
    try:
        ids = _listing(base, _secret(profile, environ))
    except (OSError, http.client.HTTPException, urllib.error.URLError, ValueError):
        # It is down, it refused, it is not HTTP, it answered something else, or the answer
        # stopped half way through. Every one of them is the CLI's turn to be asked.
        return None
    return [Model(one, profile.efforts, profile.swarms) for one in ids] if ids else None


class _Nearby(urllib.request.HTTPRedirectHandler):
    """A redirect that would carry the account's credential anywhere new, refused.

    urllib sends the headers it was given again wherever it is sent, and these carry the key
    the account was made with: an endpoint answering `302 https://somewhere-else` would be
    handed it, by a machine that was only asking what models there are. The same host is the
    whole of what is followed -- a path corrected, or `http` upgraded to `https` -- and going
    anywhere else, or back down to plain HTTP with the key still on the request, stops here.
    Which reads to the caller as an endpoint that would not say, and asks the CLI instead.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        moved = urllib.parse.urlsplit(newurl)
        plainer = req.type == "https" and moved.scheme != "https"
        if moved.netloc != req.host or plainer:
            return None  # not a place this account's credential may go
        return super().redirect_request(req, fp, code, msg, headers, newurl)


#: What asks, with that in place of urllib's own -- which follows anywhere and takes the
#: headers with it. Built once: it holds nothing between requests.
_OPENING = urllib.request.build_opener(_Nearby)


def _listing(base: str, secret: str) -> list[str]:
    """The ids one endpoint serves.

    Args:
      base: Where it is, as the account spells it -- with or without the version on the end.
      secret: The account's own credential, which is sent and nowhere else put.

    Returns:
      The ids, in the endpoint's own order and none of them empty. Nothing at all for a body
      this cannot read as a catalogue, which is how an endpoint that answers something other
      than a list of models ends up being fallen back from.

    Raises:
      ValueError: If the account points at something that is not HTTP.
      OSError: If it cannot be reached, or refused.
    """
    said = base.rstrip("/")
    at = f"{said}/models" if _VERSIONED.search(said) else f"{said}/v1/models"
    headers = {"Accept": "application/json", "User-Agent": "humanize"}
    if secret:
        headers |= {
            _BEARER: f"Bearer {secret}",
            _KEYED: secret,
            "anthropic-version": _DATED,
        }
    asked = urllib.request.Request(at, headers=headers)  # noqa: S310 -- checked below
    if asked.type not in {"http", "https"}:
        msg = f"a catalogue comes over http, not {asked.type}"
        raise ValueError(msg)
    with _OPENING.open(asked, timeout=_REACHING) as answer:
        body: object = json.loads(answer.read(_MOST))
    if not isinstance(body, dict):
        return []
    listed: object = cast("dict[str, Any]", body).get("data")
    if not isinstance(listed, list):
        return []
    return [
        str(cast("dict[str, Any]", one).get("id") or "")
        for one in cast("list[Any]", listed)
        if isinstance(one, dict) and cast("dict[str, Any]", one).get("id")
    ]


def _secret(profile: Profile, environ: Mapping[str, str]) -> str:
    """The credential this account would send, out of its own resolved environment.

    Read rather than written down: every way in already says which of the things it asks for
    is a secret, and a turn under a provider runs with that provider's own and without any
    other account's -- so the first of them that is set is this account's and no one else's.

    Args:
      profile: The backend, whose ways say which variables carry a secret.
      environ: The environment a turn of this account runs under.

    Returns:
      The credential, or "" for an account that keeps it somewhere an environment cannot
      reach -- a login's own store, a key a CLI read off stdin. Never printed, never written
      down, and never put in a message: it lives as long as one request.
    """
    # The way that names the endpoint first, since a way asking for both asks for a pair: the
    # key that goes with a gateway is the one that way named, and not a subscription's token
    # somebody also has exported. Stable, so the rest keep the order they are declared in.
    for way in sorted(
        profile.ways,
        key=lambda way: profile.endpoint not in {one.env for one in way.asks},
    ):
        for one in way.asks:
            said = environ.get(one.env, "").strip()
            if one.secret and said:
                return said
    return ""


def _rungs(profile: Profile, said: object) -> tuple[str, ...]:
    """The efforts one model takes, out of what its backend said of that model.

    The backend's own ladder narrowed rather than replaced: the order is how hard each is,
    which is the backend's to say and not something a list of names carries, and a rung it
    takes without documenting is one no such list will ever name.

    Args:
      profile: The backend.
      said: What it said this model takes, however it said it, or nothing where it said
        nothing about this one.

    Returns:
      The efforts, hardest first. The whole ladder where the backend said nothing of this
      model -- a model it says nothing about is one it will take any of these for, and a
      turn has to be asked for at one of them -- and where it named none this backend has a
      word for. The undocumented rungs are added to a ladder that was narrowed, never to one
      that was never spoken about: they are a way of running a model rather than the only way.
    """
    if not isinstance(said, list) or not said:
        return profile.efforts
    spoken = {str(one) for one in cast("list[Any]", said)}
    kept = tuple(
        rung for rung in profile.efforts if rung in spoken or rung in profile.beyond
    )
    return kept or profile.efforts


def _claude(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """Claude Code's catalogue, which is what its own `/model` list is drawn from.

    A session opened to say one thing to and never given a turn: the control request that asks
    what may be run is answered before any of it is a conversation, so finding out costs
    nothing but the start-up.

    Args:
      profile: Claude Code's own.
      run: What puts the question.

    Returns:
      One per model this account may name, in the order it offered them.

    Raises:
      ValueError: If it refused, or said nothing this can read.
    """
    said = run(
        [
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
        ],
        json.dumps(
            {
                "type": "control_request",
                "request_id": _ASKS,
                "request": {"subtype": "list_models"},
            }
        )
        + "\n",
    )
    return [
        Model(
            _claude_name(one),
            _rungs(profile, one.get("supportedEffortLevels")),
            profile.swarms,
        )
        for one in _answered(said)
    ]


def _claude_name(model: dict[str, Any]) -> str:
    """The name a Claude model may be asked for, preserving an explicit custom alias.

    Claude normally gives a stable canonical id in ``resolvedModel`` and a short alias in
    ``value``. A model named by `ANTHROPIC_CUSTOM_MODEL_OPTION` is the exception: whoever set
    that variable chose the alias, and the alias is what they can pass to `--model`, so a
    catalogue that answered with the canonical id would be answering with a name they never
    asked for. Claude marks those entries, which is how one is told from the rest.
    """
    value = model.get("value")
    described = model.get("description")
    custom = isinstance(described, str) and described.startswith(_CUSTOM)
    chosen = (
        value
        if custom and isinstance(value, str) and value
        else model.get("resolvedModel") or value
    )
    return _WINDOW.sub("", str(chosen or ""))


def _answered(said: str) -> list[dict[str, Any]]:
    """The models out of a stream of control responses, which is what Claude Code answers in.

    Args:
      said: Everything it printed.

    Returns:
      One entry per model, as it gave them.

    Raises:
      ValueError: If it refused the question, or never answered it.
    """
    for line in said.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue  # a line of something else, which a stream of these may carry
        if not isinstance(message, dict):
            continue
        held = cast("dict[str, Any]", message)
        answer = cast("dict[str, Any]", held.get("response") or {})
        if held.get("type") != "control_response" or answer.get("request_id") != _ASKS:
            continue
        if answer.get("subtype") != "success":
            raise ValueError(
                str(answer.get("error") or "it would not say what it runs")
            )
        listed = cast("dict[str, Any]", answer.get("response") or {})
        return [
            cast("dict[str, Any]", one)
            for one in cast("list[Any]", listed.get("models") or [])
            if isinstance(one, dict)
        ]
    raise ValueError("it said nothing about what it runs")


def _codex(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """Codex's own catalogue, which it renders as JSON and says the efforts in.

    Args:
      profile: Codex's own.
      run: What puts the question.

    Returns:
      One per model it offers, at the reasoning levels it said that model takes.

    Raises:
      ValueError: If what it rendered cannot be read.
    """
    said = _loaded(run(["debug", "models"]))
    found: list[Model] = []
    for one in cast("list[Any]", said.get("models") or []):
        model = cast("dict[str, Any]", one)
        # It has models it does not offer -- a review model of its own, the open ones -- and
        # a list of what can be chosen is the ones it says can be.
        if model.get("visibility") != _LISTED:
            continue
        levels = [
            cast("dict[str, Any]", rung).get("effort")
            for rung in cast("list[Any]", model.get("supported_reasoning_levels") or [])
        ]
        found.append(
            Model(str(model.get("slug") or ""), _rungs(profile, levels), profile.swarms)
        )
    return found


def _kimi(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """Kimi Code's models, which are the ones its providers between them front.

    Args:
      profile: Kimi Code's own.
      run: What puts the question.

    Returns:
      One per model it is configured for, at the efforts it said each takes.

    Raises:
      ValueError: If what it dumped cannot be read.
    """
    said = _loaded(run(["provider", "list", "--json"]))
    return [
        Model(
            str(name),
            _rungs(profile, cast("dict[str, Any]", one).get("supportEfforts")),
            profile.swarms,
        )
        for name, one in cast("dict[str, Any]", said.get("models") or {}).items()
    ]


def _dsh(profile: Profile, _run: Callable[..., str]) -> list[Model]:
    """The advisory catalogue shipped by the official DeepSeek Harness adapter.

    The rc6 Python SDK has no model-list request. These are the two defaults its bundled
    `@deepseek-ai/dsh-llm-deepseek` composition publishes; that adapter also accepts an
    uncatalogued DeepSeek model id when one is named explicitly. An account that sets
    `DEEPSEEK_BASE_URL` is answered by that endpoint instead and never reaches this.

    Args:
      profile: DeepSeek Harness's own.
      _run: Unused because its SDK protocol exposes no catalogue method.

    Returns:
      The official adapter's advisory models, in its own order.
    """
    return [Model(name, profile.efforts, profile.swarms) for name in _ADVISORY["dsh"]]


def _pi(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """Pi's models, which it prints as a table of the providers it has credentials for.

    pi is a client of whichever providers you have signed in to rather than a backend with
    models of its own, so what it lists is what this install can actually reach.

    Args:
      profile: pi's own.
      run: What puts the question.

    Returns:
      One per model, as `provider/id`, at pi's own thinking levels -- which it says of itself
      rather than of each model.
    """
    found: list[Model] = []
    for line in run(["--list-models"]).splitlines():
        columns = line.split()
        # The line that names the columns is not a model, and neither is a line with no room
        # for a provider and an id in it.
        if len(columns) < 2 or columns[:2] == ["provider", "model"]:  # noqa: PLR2004
            continue
        found.append(
            Model(f"{columns[0]}/{columns[1]}", profile.efforts, profile.swarms)
        )
    return found


def _agy(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """What Antigravity CLI runs, which it lists as a slug and the name a person reads.

    Two columns a line, so the slug is the first word: the rest is what its own picker shows.
    It has to be signed in to answer -- the catalogue is the account's -- and says so where the
    list would be.

    Args:
      profile: Antigravity CLI's own.
      run: What puts the question.

    Returns:
      One per model it offers, each at the one effort its own name carries -- it lists
      `gemini-3.7-flash-high`, `-medium` and `-low` as three models rather than as one model
      at three efforts. A model whose name carries none is offered at the whole ladder, being
      one that runs at its own level however hard it is asked to think.
    """
    found: list[Model] = []
    for line in run(["models"]).splitlines():
        columns = line.split()
        # A line with nothing on it, and the line that says to sign in, are not models.
        if not columns or len(columns) < 2:  # noqa: PLR2004
            continue
        name = columns[0]
        # The end of the name rather than a word of it, unlike Cursor's: these ids are the
        # model and then the rung, `gemini-3.7-flash-high`, with nothing written after it.
        carried = next(
            (rung for rung in profile.efforts if name.endswith(f"-{rung}")), ""
        )
        found.append(
            Model(name, (carried,) if carried else profile.efforts, profile.swarms)
        )
    return found


def _grok(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """Grok Build's catalogue, which it prints as a list with the default marked.

    A banner about how it is signed in, then the default, then one model a line behind a
    marker: a star for the one it would use and a dash for the rest. It fetches the live
    catalogue to answer, so what comes back is what this account may actually name.

    Args:
      profile: Grok Build's own.
      run: What puts the question.

    Returns:
      One per model it offers, at its own reasoning levels -- which it says of itself rather
      than of each model, so a level a model does not advertise is refused when it is asked
      for rather than left out here.
    """
    found: list[Model] = []
    for line in run(["models"]).splitlines():
        said = line.strip()
        # The lines about a model are the only marked ones; the banner and the default are
        # sentences, and a sentence is not a model.
        if not said.startswith(("* ", "- ")):
            continue
        name = said[2:].removesuffix(" (default)").strip()
        if name:
            found.append(Model(name, profile.efforts, profile.swarms))
    return found


def _cursor(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """What Cursor Agent runs, which it prints under a heading with a tip under it.

    One model a line -- the id, then the name a person reads behind a dash, and `(current)` or
    `(default)` against the ones it is at now. The catalogue is the account's, so a run that is
    not signed in says so where the list would be.

    Args:
      profile: Cursor Agent's own.
      run: What puts the question.

    Returns:
      One per model it offers, each at the whole ladder: how hard a Cursor model thinks is a
      parameter of the model rather than a property of it, and the list does not say which of
      them take one. A model whose own name carries a rung is offered at that one alone, its
      name being what it runs at -- `gpt-5-high` is not a model to ask for `low`, and neither
      is `gpt-5-low-fast`, which says the same thing with the service it runs on behind it.
    """
    found: list[Model] = []
    for line in run(["--list-models"]).splitlines():
        said = _plain(line).strip()
        # A model line is the id, and then either nothing, the name a person reads behind a
        # dash, or the brackets that mark the one it is at. The heading above the list and
        # the tip below it are sentences, and a sentence is not a model.
        name, _, rest = said.partition(" ")
        if not name or (rest and not rest.startswith(("- ", "("))):
            continue
        # A rung is a word of the name rather than the end of it: `gpt-5-low-fast` is the
        # `low` model asked for over the faster service, and `-fast` is not a rung.
        words = name.split("-")
        carried = next((rung for rung in profile.efforts if rung in words), "")
        found.append(Model(name, (carried,) if carried else profile.efforts))
    return found


#: What a CLI wraps a word in to colour it, which is not part of what the word says.
_COLOURED = re.compile(r"\x1b\[[0-9;]*m")


def _plain(said: str) -> str:
    """One line with whatever colour a CLI put round it taken off.

    Args:
      said: The line, as it was printed.

    Returns:
      The words alone.
    """
    return _COLOURED.sub("", said)


def _qwen(profile: Profile, _run: Callable[..., str]) -> list[Model]:
    """What Qwen Code runs where its account names no endpoint to ask instead.

    It has no command that lists them: it is an OpenAI-compatible client, so its catalogue is
    the account's rather than the CLI's, and there is nothing here to ask. An account that
    sets `OPENAI_BASE_URL` never reaches this -- the endpoint is asked and answers -- so these
    are the ids Qwen Code ships pointed at, for the account that named nowhere else.

    Args:
      profile: Qwen Code's own.
      _run: Unused, there being no question to put.

    Returns:
      The advisory models, in the order Qwen Code offers them.
    """
    return [Model(name, profile.efforts, profile.swarms) for name in _ADVISORY["qwen"]]


def _zcode(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """What ZCode's app server says the providers it is configured with front.

    Its command line has no `models`, because a model there belongs to a provider its
    configuration file names, and what resolves that file into a catalogue is the app server.
    So it is asked the way anything asks it: one frame in, one answer out, and the process
    ends when there is nothing more on its stdin.

    Args:
      profile: ZCode's own.
      run: What puts the question.

    Returns:
      One per model it is configured for, as `provider/id`, at the thought levels it said that
      model takes.

    Raises:
      ValueError: If nothing it wrote answers the question.
    """
    where = str(pathlib.Path.cwd())
    asked = json.dumps(
        {
            "id": 1,
            "method": "workspace/readState",
            "params": {
                "workspace": {"workspacePath": where, "workspaceKey": where},
            },
        }
    )
    for line in run(["app-server", "--stdio"], asked + "\n").splitlines():
        try:
            frame = _loaded(line)
        except (TypeError, ValueError):
            continue  # the server asks things of its client on the same stream
        if frame.get("id") != 1 or "result" not in frame:
            continue
        held = cast("dict[str, Any]", frame.get("result") or {})
        catalogue = cast("dict[str, Any]", held.get("modelCatalog") or {})
        found: list[Model] = []
        for one in cast("list[Any]", catalogue.get("available") or []):
            model = cast("dict[str, Any]", one)
            named = cast("dict[str, Any]", model.get("ref") or {})
            reasoning = cast("dict[str, Any]", model.get("reasoning") or {})
            levels = [
                cast("dict[str, Any]", rung).get("value")
                for rung in cast("list[Any]", reasoning.get("levels") or [])
            ]
            found.append(
                Model(
                    f"{named.get('providerId', '')}/{named.get('modelId', '')}",
                    _rungs(profile, levels),
                    profile.swarms,
                )
            )
        return found
    raise ValueError("it said nothing about what it runs")


def _listed(profile: Profile, run: Callable[..., str]) -> list[Model]:
    """What opencode and mimocode list, which is a model a line and its size after it.

    Args:
      profile: The backend's own.
      run: What puts the question.

    Returns:
      One per model, as `provider/id`, at the variants that backend takes -- which are the
      provider's rather than the model's, so it says them of itself.
    """
    found: list[Model] = []
    for line in run(["models"]).splitlines():
        name = line.split(_ABOUT)[0].strip()
        # Every model of these is a provider's, so a line with no provider in it is a line
        # about something else -- a banner, a warning, a blank.
        if "/" in name:
            found.append(Model(name, profile.efforts, profile.swarms))
    return found


def _loaded(said: str) -> dict[str, Any]:
    """One JSON object out of what a backend printed.

    Args:
      said: What it printed.

    Returns:
      The object.

    Raises:
      TypeError: If it printed something that is not an object.
      ValueError: If it printed something that is not JSON at all.
    """
    held = json.loads(said)
    if not isinstance(held, dict):
        raise TypeError("expected an object saying what it runs")
    return cast("dict[str, Any]", held)


def _kept(cli: str, provider: str) -> dict[str, Any]:
    """What was written down for one account, or nothing where nothing readable was."""
    try:
        held = json.loads(where(cli, provider).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}


def _read(held: dict[str, Any]) -> list[tuple[str, list[str], bool]]:
    """The models out of what was written down, less anything that is not one."""
    found: list[tuple[str, list[str], bool]] = []
    for one in cast("list[Any]", held.get("models") or []):
        if not isinstance(one, dict):
            continue
        model = cast("dict[str, Any]", one)
        name, efforts = model.get("name"), model.get("efforts")
        if isinstance(name, str) and name and isinstance(efforts, list):
            found.append(
                (
                    name,
                    [str(rung) for rung in cast("list[Any]", efforts)],
                    bool(model.get("swarms")),
                )
            )
    return found


def _write(at: Path, models: list[Model]) -> None:
    """Writes a catalogue down, whole, beside the moment it was asked for.

    Whole and then moved into place, so that a catalogue read while it is being written is
    either the old one or the new one and never half of each.

    Args:
      at: Where it goes.
      models: What the backend said it runs.
    """
    at.parent.mkdir(parents=True, exist_ok=True)
    beside = at.parent / f".{at.name}.new"
    beside.write_text(
        json.dumps(
            {
                "asked": datetime.datetime.now(datetime.UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "models": [
                    {
                        "name": model.name,
                        "efforts": list(model.efforts),
                        "swarms": model.swarms,
                    }
                    for model in models
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    beside.replace(at)


#: How each backend is asked what it runs. One entry per backend that has a way of being
#: asked, which is every one of them: a backend nobody can ask is a backend nobody can choose
#: a model of, and there would be nothing to offer at the prompt.
_READING: dict[str, Callable[[Profile, Callable[..., str]], list[Model]]] = {
    "agy": _agy,
    "claude": _claude,
    "codex": _codex,
    "cursor": _cursor,
    "dsh": _dsh,
    "grok": _grok,
    "kimi": _kimi,
    "pi": _pi,
    "qwen": _qwen,
    "opencode": _listed,
    "mimo": _listed,
    "zcode": _zcode,
}
