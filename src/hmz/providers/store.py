"""What a provider is, and where the credentials of one are kept.

One directory per provider, under `~/.humanize/providers/<cli>/<name>/`: what it was made by
and what a turn under it is run with, in `provider.json`, and beside that the files the CLI
itself writes when it signs in -- kept at the same names it uses, under `home/` for the ones
inside its own directory and `user/` for the ones outside it.

Nothing here reaches a CLI. Making a provider is :mod:`hmz.providers.login`, running a
turn under one is :mod:`hmz.providers.redirect`, and this is only the answer to "which
ones are there, and what is in each".
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import backends, home

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ENV",
    "LOCAL",
    "Provider",
    "add",
    "alone",
    "chain",
    "copies",
    "find",
    "points",
    "providers",
    "serves",
    "ways",
    "where",
]

#: What a provider may be called: a name that is one path component, holds nothing a shell or
#: a filesystem reads as something else, and cannot climb out of the directory it names.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: What the file a provider is written down in is called.
_HELD = "provider.json"

#: What the account this machine is already signed into is called, which is no name at all.
#: It is the CLI as whoever is at this machine runs it -- humanize did not make it, keeps no
#: credentials for it and cannot take it away -- and it is already the spelling an agent
#: configured with no account uses, in `AgentConfig.provider` and in `Runs.provider`. So it is
#: an account here too, and the one thing every backend has whether or not anybody made one.
LOCAL = ""

#: Where what is written down about it is kept: one file per backend under humanize's own
#: home, beside the catalogue that machine's own sign-in answers with. Not under `providers/`,
#: which is the tree of accounts humanize made -- taking every one of those away must not
#: leave a stray file behind, and the account nobody made is not one of them.
_ALONE = "local"

#: The way in that every backend has, whatever else it offers: variables of your own. Every
#: one of these CLIs reads a key out of the environment under some name of its own -- pi has
#: one per provider it knows, opencode has one for each of a hundred and eighty -- and a list
#: of all of them would be a list to keep in step with six vendors. So the names are typed.
ENV = backends.Way(
    name="env",
    about="variables of your own: whatever this CLI reads a key or an endpoint under",
)


def ways(cli: str) -> tuple[backends.Way, ...]:
    """Every way there is of getting credentials into one backend.

    Args:
      cli: The backend, by any name it answers to.

    Returns:
      What that backend offers, in the order it offers them, and variables of your own last
      where that backend accepts arbitrary credentials. DeepSeek Harness takes only its
      named API-key way. Nothing at all for a name no backend answers to.
    """
    profile = backends.named(cli)
    if profile is None:
        return ()
    if profile.name == "dsh":
        return profile.ways
    return (*profile.ways, ENV)


@dataclass(frozen=True, slots=True)
class Provider:
    """One named set of credentials for one backend.

    What a flow chooses between when two agents drive the same CLI as two different accounts:
    an agent is configured with a name, and a turn of it runs with this provider's variables
    and reads its credentials out of this provider's own directory rather than the CLI's.

    Attributes:
      cli: The backend this is for, under the name that backend is called here.
      name: What this provider is called, which is what an agent is configured with.
      way: The way it was made by, as :class:`hmz.backends.Way` names them.
      env: What a turn run under it is given on top of the environment it inherits.
      args: What to add to the backend's own command line for such a turn.
      made: When it was made, as the moment written down.
      fallback: The account a turn carries on under when this one has failed, by name, or ""
        for one that is the end of the line. A property of the account rather than of the
        agent: it is the account that goes down, and whichever agent was running under one
        when it did is the agent that needs somewhere else to run. Each account naming its
        own means a run walks a chain -- subscription, then key, then gateway -- rather than
        having one place to go however many accounts there are. How many times over a turn
        under one is tried before the chain moves on is not written here: that is a thing
        about the place a turn runs at rather than about the credentials it runs with, and
        `hmz.fallbacks` is where it is said.
    """

    cli: str
    name: str
    way: str = ENV.name
    env: Mapping[str, str] = field(default_factory=dict[str, str])
    args: tuple[str, ...] = ()
    made: str = ""
    fallback: str = ""

    @property
    def at(self) -> Path:
        """The directory this account's credentials are kept in.

        Which for one humanize made is its own directory, and for the account this machine is
        already signed into is the CLI's own home: those credentials are the CLI's, which is
        what makes that account the one nobody has to make.
        """
        if not self.name:
            profile = backends.named(self.cli)
            return profile.directory() if profile is not None else Path()
        return where(self.cli, self.name)

    def swaps(self) -> tuple[tuple[str, str], ...]:
        """Every path a turn under this provider reads and writes somewhere else instead.

        The backend's own credential paths, mapped onto this provider's copies of them. Only
        those: a turn under a provider keeps the sessions, the settings and the skills the CLI
        already has, and takes nothing but the account from here.

        Returns:
          One `(the path the CLI names, the path it gets instead)` pair per credential, and
          nothing at all for a backend that has none written down.
        """
        profile = backends.named(self.cli)
        # Nothing at all for the account this machine is already signed into: what it reads is
        # what the CLI reads, and answering those paths with themselves is a supervisor for
        # nothing.
        if profile is None or not self.name:
            return ()
        held: list[tuple[str, str]] = []
        for real, under in profile.credentials():
            instead = str(self.at / under)
            held.append((real, instead))
            # And the same path with the links in it followed, where that is a different
            # spelling: a home reached through one -- `/home` pointing at `/homes` -- is the
            # same file under two names, and a CLI that settles a path before opening it
            # would otherwise name one this table had never heard of.
            settled = os.path.realpath(real)
            if settled != real:
                held.append((settled, instead))
        return tuple(held)

    def command(self, argv: list[str] | tuple[str, ...]) -> list[str]:
        """Renders the invocation that runs `argv` under this provider's own paths.

        Args:
          argv: The backend to run and its own arguments.

        Returns:
          The command to spawn, which exits with the backend's own status. The command itself
          when there is nothing to point anywhere else, so that a provider which is only
          variables costs no supervisor at all.
        """
        from .redirect import command

        return command(self.swaps(), argv)

    def held(self) -> dict[str, Any]:
        """This provider as it is written down."""
        return {
            "cli": self.cli,
            "name": self.name,
            "way": self.way,
            "env": dict(self.env),
            "args": list(self.args),
            "made": self.made,
            "fallback": self.fallback,
        }


def under() -> Path:
    """Where every provider is kept, which is one directory under humanize's own home."""
    return home() / "providers"


def where(cli: str, name: str) -> Path:
    """The directory one provider's credentials are kept in.

    Args:
      cli: The backend it is for, by any name it answers to.
      name: What the provider is called.

    Returns:
      The path, whether or not anything is there yet.

    Raises:
      ValueError: If the backend is not one there is, or the name is not one a provider may
        have -- a name is a directory, and one that climbs out of this one is not a name.
    """
    profile = backends.named(cli)
    if profile is None:
        raise ValueError(f"{cli}: no such coding agent")
    if not _NAMED.match(name):
        raise ValueError(
            f"{name!r} is not a provider name: letters, digits, dot, dash and underscore, "
            "starting with a letter or a digit"
        )
    return under() / profile.name / name


def providers(cli: str = "") -> list[Provider]:
    """Every provider there is, or every one for a backend.

    Args:
      cli: The backend to list, by any name it answers to, or "" for all of them.

    Returns:
      One per provider, by backend and then by name. A directory holding nothing readable is
      not a provider and is left out rather than raised about: the list is what can be run.
      So is one under a name no provider could be made under, or under a directory no backend
      answers to -- a provider whose CLI is not one of these has no credentials written down
      and so no paths to answer, which is a turn that would run as whoever is at this machine.
    """
    profile = backends.named(cli) if cli else None
    wanted = profile.name if profile is not None else cli
    held: list[Provider] = []
    for folder in sorted(_directories(under())):
        whose = backends.named(folder.name)
        if whose is None or (wanted and whose.name != wanted):
            continue
        held.extend(
            provider
            for named in sorted(_directories(folder))
            if _NAMED.match(named.name)
            and (provider := _read(whose.name, named)) is not None
        )
    return held


def serves(one: Provider) -> tuple[str, ...]:
    """Which other backends this account could be run as.

    A vendor's credential is the vendor's rather than the CLI's: an Anthropic key is an
    Anthropic key whether Claude Code, pi, opencode or mimocode is holding it, and a
    subscription token is one under whatever name each of them reads it under. So an account
    made for one backend is often an account several others could be run as -- which is worth
    saying at the moment it is made, since making the same key four times by hand is four
    places to correct it when it is rotated.

    Args:
      one: The account.

    Returns:
      The other backends, in the order humanize lists them. Nothing at all for an account
      that cannot travel: a subscription signed into writes the CLI's own credential store,
      in that CLI's own format, and nothing else reads it.
    """
    return tuple(
        profile.name
        for profile in backends.profiles()
        if profile.name != backends.named(one.cli).name  # pyright: ignore[reportOptionalMemberAccess]
        and backends.serves(one.env, profile.name) is not None
    )


def copies(one: Provider, cli: str, name: str = "") -> Provider:
    """Writes one account down for another backend, under the same name.

    Written over where there is already one of that name for that backend, which is what
    makes this a way of correcting several at once: a key rotated is a key rotated everywhere
    it was copied to, said once.

    Args:
      one: The account to copy.
      cli: The backend to copy it to, by any name it answers to.
      name: What to call it there, defaulting to what it is called here.

    Returns:
      The account as it is now written down for that backend.

    Raises:
      ValueError: If that backend could not be run as this account at all, or the name is not
        one an account may be kept under.
      OSError: If it cannot be written.
    """
    held = backends.serves(one.env, cli)
    if held is None:
        raise ValueError(
            f"{one.cli}/{one.name} is not an account {cli} could be run as"
        )
    return add(cli, name or one.name, _as_made(cli, held), held)


def _as_made(cli: str, env: Mapping[str, str]) -> str:
    """What to say a copied account was made by, on the backend it was copied to.

    Args:
      cli: The backend it is being written down for.
      env: What a turn under it is run with, under that backend's own names.

    Returns:
      The name of that backend's own way that asks for exactly these, so that a copied
      Anthropic key reads as the key way rather than as something nobody recognises -- and
      variables of your own where it has no such way, which is what these are then.
    """
    wanted = set(env)
    for way in ways(cli):
        if way.argv:
            continue  # a way with a command of its own is a login, and this is not one
        asked = {one.env for one in way.asks if one.keep} | {
            name for name, _ in way.sets
        }
        if asked == wanted:
            return way.name
    return ENV.name


def find(cli: str, name: str) -> Provider | None:
    """The account of one backend that is called this.

    Args:
      cli: The backend, by any name it answers to.
      name: What the account is called, or :data:`LOCAL` for the one this machine is already
        signed into.

    Returns:
      It, or None where there is no such account -- including for a name no account could
      have, since nothing can be kept under one. Never None for :data:`LOCAL`, which is an
      account of every backend there is: it is the CLI as whoever is at this machine runs it,
      and what is written down about it is only what it does when it fails.
    """
    profile = backends.named(cli)
    if profile is None:
        # Not a backend, so not an account of one. Said of the account this machine is signed
        # into as well as of any other: a name nothing answers to must not be written down as
        # though it were, or a line with a typo in it reports success and leaves a file
        # nothing will ever read back.
        return None
    if name == LOCAL:
        return _alone(profile.name)
    if not _NAMED.match(name):
        return None
    return _read(profile.name, under() / profile.name / name)


def alone(cli: str) -> Path:
    """Where what is written down about the account this machine is signed into is kept.

    Args:
      cli: The backend, by the name it is called here.

    Returns:
      The file, whether or not anything has been written to it.
    """
    return home() / _ALONE / f"{cli}.json"


def _alone(cli: str) -> Provider:
    """The account this machine is already signed into, as one.

    Args:
      cli: The backend, by the name it is called here.

    Returns:
      It, with nothing but what it does when it fails: no way in, since nobody signed it in
      here; no variables, since it is the CLI as it is already run; and no credentials of its
      own, since the ones it reads are the CLI's. Zeros where nothing has been written down,
      which is an account that is tried once and is the end of its own chain.
    """
    try:
        said = json.loads(alone(cli).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        said = {}
    held = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    return Provider(
        cli=cli,
        name=LOCAL,
        way="",
        fallback=str(held.get("fallback") or ""),
    )


def chain(provider: Provider) -> list[Provider]:
    """The accounts a turn under this one walks, in the order it walks them.

    Each account names the one to carry on under when it has failed, so what a turn has is a
    chain rather than a second place: a subscription that runs out falls to a key, and a key
    that is refused falls to a gateway. A run walks it to the end and stops there.

    Args:
      provider: Where the turn starts, which is the account its agent was configured with --
        or the one this machine is already signed into, for an agent configured with none.

    Returns:
      That account first, then whatever it falls back to, and so on. An account naming one
      that is not there ends the chain, as does one naming an account already in it: a loop
      is a chain that would be walked forever, and stopping at the second sight of an account
      is what makes a run that ends. Never empty: there is always the account it starts at.
    """
    walked = [provider]
    seen = {provider.name}
    while walked[-1].fallback:
        instead = find(walked[-1].cli, walked[-1].fallback)
        if instead is None or instead.name in seen:
            break
        seen.add(instead.name)
        walked.append(instead)
    return walked


def points(cli: str, name: str, at: str) -> bool:
    """Says which account a turn under this one carries on under when it fails.

    Args:
      cli: The backend it is for.
      name: Which account, or :data:`LOCAL` for the one this machine is already signed into
        -- which is where the chain of an agent nobody gave an account begins.
      at: What the account to fall back to is called, or "" for the end of the line.

    Returns:
      Whether there was an account of that name to say it of.

    Raises:
      ValueError: If it would point at itself, or at an account of that backend that is not
        there -- either is a chain that goes nowhere, said where it was written rather than
        found on the turn that needed it.

    Note:
      A chain may begin at the account this machine is signed into and MUST NOT end there: ""
      in this position is the end of the line, and an agent that is to try that account is an
      agent given no account, which is where its chain starts anyway.
    """
    found = find(cli, name)
    if found is None:
        return False
    if at:
        if at == name:
            raise ValueError(f"{name} cannot fall back to itself")
        if find(cli, at) is None:
            raise ValueError(f"there is no {found.cli} account called {at!r}")
    _write(replace(found, fallback=at))
    return True


def _write(provider: Provider) -> None:
    """Writes one account down again, whole, where it is kept.

    Args:
      provider: The account. The one this machine is signed into is written to its own file
        under humanize's home rather than into the tree of accounts humanize made: it has no
        directory, having no credentials of its own to keep in one.
    """
    if not provider.name:
        at = alone(provider.cli)
        _kept(at.parent)
        _writes(
            at,
            json.dumps(
                {"fallback": provider.fallback},
                indent=2,
            )
            + "\n",
        )
        return
    at = provider.at
    _kept(at)
    _writes(at / _HELD, json.dumps(provider.held(), indent=2) + "\n")


def _writes(at: Path, said: str) -> None:
    """Writes one of these files whole, kept to its owner alone from the moment it exists.

    Args:
      at: The file to end up with.
      said: What to put in it.

    Note:
      Written beside and then moved into place, so that a file read while it is being written
      is the old one or the new one and never half of each -- and beside it under a name
      nothing else will pick, because two `hmz` at once (a menu saving while a script points
      a chain) writing one fixed `.new` is one of them finding its own file already moved
      away. `mkstemp` is `0600` from the moment the file exists, which is what these hold: a
      key, a token, or an endpoint somebody pays for. A file that was readable for the moment
      between being written and being chmodded was readable.
    """
    handle, beside = tempfile.mkstemp(
        dir=at.parent, prefix=f".{at.name}.", suffix=".new"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(said)
        Path(beside).replace(at)
    except OSError:
        Path(beside).unlink(missing_ok=True)
        raise


def add(
    cli: str,
    name: str,
    way: str = ENV.name,
    env: Mapping[str, str] | None = None,
    args: tuple[str, ...] = (),
) -> Provider:
    """Writes a provider down, and makes the directory its credentials will be kept in.

    What it holds is replaced rather than merged: a provider made again is the answers given
    the second time, and the credentials a login left in its directory are left alone -- a
    key corrected is not a reason to sign in again.

    Args:
      cli: The backend it is for, by any name it answers to.
      name: What to call it.
      way: The way it was made by.
      env: What a turn under it is run with.
      args: What to add to the backend's own command line.

    Returns:
      The provider, as it is now written down.

    Raises:
      ValueError: If the backend or the name is not one that may be used.
      OSError: If the directory cannot be made or the file cannot be written.
    """
    at = where(cli, name)
    profile = backends.named(cli)
    assert profile is not None  # noqa: S101 -- `where` has already refused anything else
    # What it does when it fails is not part of what it was made with: an account corrected --
    # a key retyped, a gateway moved -- is the same account, and the chain and the tries
    # somebody wrote against it are theirs rather than this line's to forget.
    already = find(profile.name, name)
    provider = Provider(
        cli=profile.name,
        name=name,
        way=way,
        env=dict(env or {}),
        args=tuple(args),
        made=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        fallback=already.fallback if already is not None else "",
    )
    # The directory before the file: a login run under this provider writes into it, and
    # 0700 is what every one of these CLIs keeps its own credential directory at. A level at
    # a time, because `mkdir` gives the mode to the last of them and leaves the rest at
    # whatever the umask says -- and what is being made here is a directory of credentials.
    _kept(at)
    # Whole and then moved into place, and kept to its owner: it holds keys, and keys are not
    # for the rest of the machine.
    _writes(at / _HELD, json.dumps(provider.held(), indent=2) + "\n")
    ready(provider)
    return provider


def ready(provider: Provider) -> None:
    """Makes the places this provider's credentials will land, before anything writes one.

    A CLI writing its credentials file expects the directory it keeps its own in to be there;
    its own always is. The provider's is made here instead, at the mode these CLIs keep theirs
    at, so that a turn which refreshes a token has somewhere to write it back to.

    Args:
      provider: The provider.
    """
    for _, instead in provider.swaps():
        _kept(Path(instead).parent)


def _kept(at: Path) -> None:
    """Makes a directory and every one above it, each kept to its owner alone.

    `Path.mkdir(parents=True, mode=...)` gives the mode to the last directory only and makes
    the rest at whatever the umask allows, which for a tree of credentials is the wrong way
    round: what is being made is `~/.humanize/providers/<cli>/<name>/...`, and every level of
    it is this user's business and nobody else's.

    Args:
      at: The directory to make.
    """
    made: list[Path] = []
    for one in (at, *at.parents):
        if one.exists():
            break
        made.append(one)
    for one in reversed(made):
        one.mkdir(exist_ok=True)
        # Set rather than passed: `mkdir` takes the umask off the mode it is given, and a
        # group-writable directory of credentials is not what 0700 was asked for.
        one.chmod(0o700)


def remove(cli: str, name: str) -> bool:
    """Takes a provider away, credentials and all.

    Args:
      cli: The backend it is for, by any name it answers to.
      name: What it is called.

    Returns:
      Whether there was one to take away. Everything under it goes with it, which is the
      point: what is being removed is an account this machine can run turns as.

    Raises:
      ValueError: If the backend or the name is not one that may be used.
    """
    at = where(cli, name)
    if not at.is_dir():
        return False
    shutil.rmtree(at)
    return True


def _read(cli: str, at: Path) -> Provider | None:
    """Reads one provider back off its directory.

    Args:
      cli: The backend whose directory it was found under, which is what it is for whatever
        the file says -- the place it is kept is the answer, and the file only describes it.
      at: The provider's directory.

    Returns:
      It, or None where there is nothing readable there.
    """
    try:
        said = json.loads((at / _HELD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(said, dict):
        return None
    held = cast("dict[str, Any]", said)
    env = held.get("env")
    args = held.get("args")
    return Provider(
        cli=cli,
        name=at.name,
        way=str(held.get("way") or ENV.name),
        env={
            str(key): str(value)
            for key, value in (
                cast("dict[Any, Any]", env).items() if isinstance(env, dict) else ()
            )
        },
        args=tuple(str(one) for one in cast("list[Any]", args))
        if isinstance(args, list)
        else (),
        made=str(held.get("made") or ""),
        # A name, and never a mark: an account written down when a fallback was a yes or a no
        # names nobody, so it is the end of its own chain until somebody says otherwise.
        fallback=str(held.get("fallback") or "")
        if isinstance(held.get("fallback"), str)
        else "",
    )


def _directories(at: Path) -> list[Path]:
    """Every directory directly inside one, and nothing at all where there is no such place."""
    try:
        return [path for path in at.iterdir() if path.is_dir()]
    except OSError:
        return []


def env_of(said: str) -> dict[str, str]:
    """Reads variables of your own out of the lines they were typed as.

    Args:
      said: `NAME=VALUE` a line at a time, as somebody typed them. Blank lines and lines
        starting with `#` are nothing; a line with no `=` in it is a line to correct.

    Returns:
      The variables, in the order they were given.

    Raises:
      ValueError: If a line is not a variable.
    """
    held: dict[str, str] = {}
    for line in said.splitlines():
        said_line = line.strip()
        if not said_line or said_line.startswith("#"):
            continue
        name, sep, value = said_line.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"{line!r} is not NAME=VALUE")
        held[name.strip()] = value.strip()
    return held


def filled(said: str, answers: Mapping[str, str]) -> str:
    """Fills the answers into something written with `{VARIABLE}` in it.

    Args:
      said: The text, as a way wrote it.
      answers: What was answered, by variable.

    Returns:
      The text with each `{VARIABLE}` replaced by its answer, and anything else left as it is
      -- a brace that names nothing is a brace the backend itself is being given.
    """
    for name, value in answers.items():
        said = said.replace("{" + name + "}", value)
    return said


def environ(provider: Provider | None) -> dict[str, str]:
    """What a turn under a provider is run with, on top of what it inherits.

    Args:
      provider: The provider, or None for an agent running as the CLI already runs.

    Returns:
      The variables to add, which is nothing at all where there is no provider.
    """
    return dict(provider.env) if provider is not None else {}
