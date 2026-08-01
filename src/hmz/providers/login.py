"""Making a provider: what is asked, what is written down, and what signs in.

A CLI's own login is the only thing that can perform that CLI's login -- it is a browser
opened, a code read out, a token exchanged and refreshed on a schedule nobody else knows. So
it is not reimplemented here: the CLI's own command is run, on this terminal, with its
credential paths pointed into the provider's directory. What it writes when it succeeds is
the provider, and it is the CLI that wrote it.

The ways in that are answers rather than a command -- a key, an endpoint, an account on
somebody's console -- are written down instead, as the variables that backend reads them
under. Both kinds end up as one provider, and a turn run under it cannot tell which it was.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from . import redirect
from .store import ENV, add, filled, find, ready, ways

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.backends import Way

    from .store import Provider

__all__ = ["asked", "make", "sign_in", "way_of"]


def way_of(cli: str, name: str) -> Way | None:
    """The way in one backend offers under a name.

    Args:
      cli: The backend, by any name it answers to.
      name: What the way is called.

    Returns:
      It, or None for a name that backend does not offer.
    """
    return next((way for way in ways(cli) if way.name == name), None)


def asked(way: Way, given: Mapping[str, str]) -> list[str]:
    """What a way still has to be told before it can be used.

    Args:
      way: The way in.
      given: What has been answered so far.

    Returns:
      The variables that are neither answered nor answerable from a fixed value, in the order
      the way asks them.
    """
    return [one.env for one in way.asks if not given.get(one.env) and not one.fixed]


def make(
    cli: str, name: str, way: Way, answers: Mapping[str, str] | None = None
) -> Provider:
    """Writes a provider down out of what its way was answered with.

    Args:
      cli: The backend it is for, by any name it answers to.
      name: What to call it.
      way: The way in it was made by.
      answers: What was answered, by variable. A question with a fixed answer that nobody was
        asked takes that.

    Returns:
      The provider, with its directory made and every place a credential of it will land
      ready to be written to.

    Raises:
      ValueError: If the backend or the name is not one that may be used.
      OSError: If the directory cannot be made.
    """
    said = {one.env: one.fixed for one in way.asks if one.fixed} | dict(answers or {})
    # Only what is kept: a key read off stdin by the CLI's own login ends up inside that
    # CLI's store, and a second copy of it in an environment would be a second place to leak.
    keeping = {one.env for one in way.asks if one.keep}
    env = {
        name_: value
        for name_, value in said.items()
        if value and (way is ENV or name_ in keeping)
    }
    env |= dict(way.sets)
    return add(
        cli,
        name,
        way=way.name,
        env=env,
        args=tuple(filled(one, said) for one in way.args),
    )


def sign_in(
    provider: Provider, way: Way, answers: Mapping[str, str] | None = None
) -> int:
    """Runs a backend's own way in, under this provider's paths.

    The terminal is the backend's: a login opens a browser, prints a code, waits to be told
    something. What it writes lands in the provider's directory, because every path it would
    have written to is answered by one there.

    Args:
      provider: The provider being signed in, which must already have been made.
      way: The way in, whose own command is what runs.
      answers: What was answered, for a command that takes one of them on its standard input
        or inside its arguments.

    Returns:
      The command's exit status, or zero for a way that has no command -- one that is only
      answers is already done, having been written down. A CLI that is not installed is a
      status like any other: what is spawned is the supervisor, which says which program it
      could not run and exits 127, the way a shell does.
    """
    if not way.argv:
        return 0
    said = {one.env: one.fixed for one in way.asks if one.fixed} | dict(answers or {})
    # Again, in case the provider was made before whatever it is signing into was: a login
    # writes where it reads, and it reads a path that has to be there to be written to.
    ready(provider)
    argv = [filled(one, said) for one in way.argv]
    spawned = redirect.command(provider.swaps(), argv)
    fed = said.get(way.stdin, "") if way.stdin else ""
    landed = subprocess.run(
        spawned,
        input=f"{fed}\n" if way.stdin else None,
        text=True,
        env={**os.environ, **provider.env},
        check=False,
    )
    return landed.returncode


def again(cli: str, name: str) -> Provider | None:
    """The provider of that name, read back as it is now written down.

    Args:
      cli: The backend, by any name it answers to.
      name: What the provider is called.

    Returns:
      It, or None if it is not there.
    """
    return find(cli, name)
