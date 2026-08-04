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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import backends, home

from . import retry

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ENV",
    "Provider",
    "add",
    "chain",
    "find",
    "points",
    "providers",
    "retrying",
    "ways",
    "where",
]

#: What a provider may be called: a name that is one path component, holds nothing a shell or
#: a filesystem reads as something else, and cannot climb out of the directory it names.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: What the file a provider is written down in is called.
_HELD = "provider.json"

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
        having one place to go however many accounts there are.
      retries: How many times a failed turn is tried again under this account before the
        chain moves on, beyond the first try. Zero is the account as it comes: a turn is
        taken once, and a failure is a failure.
      policy: How long to wait between those tries, as :data:`hmz.providers.retry.POLICIES`
        names them.
      timeout: The longest the retrying under this account may go on for, in seconds, or 0.0
        for as long as the tries take. It is checked before each wait, so a turn is never
        started knowing it is already past.
    """

    cli: str
    name: str
    way: str = ENV.name
    env: Mapping[str, str] = field(default_factory=dict[str, str])
    args: tuple[str, ...] = ()
    made: str = ""
    fallback: str = ""
    retries: int = 0
    policy: str = retry.DEFAULT
    timeout: float = 0.0

    @property
    def at(self) -> Path:
        """The directory this provider's credentials are kept in."""
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
        if profile is None:
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
            "retries": self.retries,
            "policy": self.policy,
            "timeout": self.timeout,
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


def find(cli: str, name: str) -> Provider | None:
    """The provider of one backend that is called this.

    Args:
      cli: The backend, by any name it answers to.
      name: What the provider is called.

    Returns:
      It, or None where there is no such provider -- including for a name no provider could
      have, since nothing can be kept under one.
    """
    profile = backends.named(cli)
    if profile is None or not _NAMED.match(name):
        return None
    return _read(profile.name, under() / profile.name / name)


def chain(provider: Provider) -> list[Provider]:
    """The accounts a turn under this one walks, in the order it walks them.

    Each account names the one to carry on under when it has failed, so what a turn has is a
    chain rather than a second place: a subscription that runs out falls to a key, and a key
    that is refused falls to a gateway. A run walks it to the end and stops there.

    Args:
      provider: Where the turn starts, which is the account its agent was configured with.

    Returns:
      That account first, then whatever it falls back to, and so on. An account naming one
      that is not there ends the chain, as does one naming an account already in it: a loop
      is a chain that would be walked forever, and stopping at the second sight of an account
      is what makes a run that ends.
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
      name: Which account.
      at: What the account to fall back to is called, or "" for the end of the line.

    Returns:
      Whether there was an account of that name to say it of.

    Raises:
      ValueError: If it would point at itself, or at an account of that backend that is not
        there -- either is a chain that goes nowhere, said where it was written rather than
        found on the turn that needed it.
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


def retrying(cli: str, name: str, retries: int, policy: str, timeout: float) -> bool:
    """Says how a turn under one account is tried again when it fails.

    Args:
      cli: The backend it is for.
      name: Which account.
      retries: How many tries beyond the first.
      policy: How long to wait between them, as `hmz.providers.retry.POLICIES` names them.
      timeout: The longest the retrying may go on for, in seconds, or 0.0 for no limit.

    Returns:
      Whether there was an account of that name to say it of.

    Raises:
      ValueError: If the policy is not one there is, or either number is negative.
    """
    found = find(cli, name)
    if found is None:
        return False
    if retry.named(policy) is None:
        raise ValueError(
            f"{policy!r} is not a retry policy: "
            f"{', '.join(one.name for one in retry.POLICIES)}"
        )
    if retries < 0 or timeout < 0:
        raise ValueError("a number of tries and a timeout are both counts, not debts")
    _write(replace(found, retries=retries, policy=policy, timeout=timeout))
    return True


def _write(provider: Provider) -> None:
    """Writes one provider down again, whole, where it already lives."""
    at = provider.at
    _kept(at)
    beside = at / f".{_HELD}.new"
    beside.write_text(json.dumps(provider.held(), indent=2) + "\n", encoding="utf-8")
    beside.replace(at / _HELD)


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
    provider = Provider(
        cli=profile.name,
        name=name,
        way=way,
        env=dict(env or {}),
        args=tuple(args),
        made=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    # The directory before the file: a login run under this provider writes into it, and
    # 0700 is what every one of these CLIs keeps its own credential directory at. A level at
    # a time, because `mkdir` gives the mode to the last of them and leaves the rest at
    # whatever the umask says -- and what is being made here is a directory of credentials.
    _kept(at)
    held = at / _HELD
    # Written whole and then moved into place, so that a provider read while it is being
    # written is either the old one or the new one and never half of each.
    beside = at / f".{_HELD}.new"
    beside.write_text(json.dumps(provider.held(), indent=2) + "\n", encoding="utf-8")
    beside.chmod(0o600)  # it holds keys, and keys are not for the rest of the machine
    beside.replace(held)
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
        retries=int(_counted(held.get("retries"))),
        policy=str(held.get("policy") or retry.DEFAULT),
        timeout=_counted(held.get("timeout")),
    )


def _counted(said: Any) -> float:
    """One number a provider was written down with, read as the count it is.

    Args:
      said: What the file holds, which is whatever somebody put there.

    Returns:
      It, never negative, and zero for anything that is not a number at all -- a file written
      by hand is a file to read past rather than a reason to lose the account in it.
    """
    if not isinstance(said, (int, float)) or isinstance(said, bool):
        return 0.0
    return max(float(said), 0.0)


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
