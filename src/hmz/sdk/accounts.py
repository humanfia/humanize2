"""The accounts an agent may be run as, and what each backend runs as one of them.

One named set of credentials per account, kept apart from the CLI's own, and the catalogue of
models that account may name -- which is a thing about the account rather than about the CLI,
since which models a key is good for is the key's. The store is :mod:`hmz.providers` and the
catalogue is :mod:`hmz.models`; both are reached from here, so that an account made from a
command line is one the interface offers a moment later and one whose models have been asked
for once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.backends import Model, Way
    from hmz.providers import Provider

__all__ = ["Accounts"]


class Accounts:
    """Every account there is, how a backend is signed into, and what one of them runs."""

    def all(self, cli: str = "") -> list[Provider]:
        """Every account somebody made, or one backend's.

        Args:
          cli: The backend, by any name it answers to, or "" for all of them.

        Returns:
          One apiece, by backend and then by name.
        """
        from hmz import providers

        return providers.providers(cli)

    def ways(self, cli: str) -> tuple[Way, ...]:
        """How one backend can be signed into, in the order it offers them."""
        from hmz import providers

        return providers.ways(cli)

    def way(self, cli: str, name: str) -> Way | None:
        """The way in one backend offers under a name, or None for one it does not."""
        from hmz.providers import login

        return login.way_of(cli, name)

    def find(self, cli: str, name: str) -> Provider | None:
        """The account of that backend under that name.

        Args:
          cli: The backend, by any name it answers to.
          name: What the account is called, or "" for the one this machine is already signed
            into -- which is an account of every backend and one nobody made.

        Returns:
          It, or None for a name that backend has no account under.
        """
        from hmz import providers

        return providers.find(cli, name)

    def where(self, cli: str, name: str) -> Path:
        """Where one account keeps its credentials, whether or not it has been made.

        Args:
          cli: The backend it is for, by any name it answers to.
          name: What it is called.

        Returns:
          The directory.

        Raises:
          ValueError: If the backend is not one humanize drives, or the name is not one an
            account may be kept under -- which is what asks it of a name before it is made.
        """
        from hmz import providers

        return providers.where(cli, name)

    def local(self, cli: str) -> Path:
        """Where the account this machine is already signed into keeps what is written of it."""
        from hmz.providers import store

        return store.alone(cli)

    def write(
        self,
        cli: str,
        name: str,
        way: str = "",
        env: Mapping[str, str] | None = None,
        args: tuple[str, ...] = (),
    ) -> Provider:
        """Writes an account down as it now stands, without running anything.

        What it holds is replaced rather than merged, and the credentials a login left in its
        directory are left alone: a key corrected is not a reason to sign in again. What it
        does when it fails is not part of what it was made with, so the chain and the tries
        somebody wrote against it are left as they were.

        Args:
          cli: The backend it is for, by any name it answers to.
          name: What it is called.
          way: The way it was made by, or "" for the one that is only variables.
          env: What a turn under it is run with.
          args: What to add to the backend's own command line.

        Returns:
          The account, as it is now written down.

        Raises:
          ValueError: If the backend or the name is not one that may be used.
          OSError: If the directory cannot be made or the file cannot be written.
        """
        from hmz import providers

        if way:
            return providers.add(cli, name, way, env, args)
        return providers.add(cli, name, env=env, args=args)

    def make(
        self,
        cli: str,
        name: str,
        way: Way,
        answers: Mapping[str, str] | None = None,
    ) -> Provider:
        """Writes an account down out of what its way in was answered with.

        Args:
          cli: The backend it is for, by any name it answers to.
          name: What to call it.
          way: The way in it is made by.
          answers: What was answered, by variable.

        Returns:
          The account, with its directory made and every place a credential of it will land
          ready to be written to.

        Raises:
          ValueError: If the backend or the name is not one that may be used.
          OSError: If the directory cannot be made or the file cannot be written.
        """
        from hmz.providers import login

        return login.make(cli, name, way, answers)

    def sign_in(
        self, provider: Provider, way: Way, answers: Mapping[str, str] | None = None
    ) -> int:
        """Runs a backend's own way in, under this account's paths.

        Args:
          provider: The account, which must already have been made.
          way: The way in, whose own command is what runs.
          answers: What was answered, for a command that takes one on its standard input.

        Returns:
          What the backend's own command exited with, which is zero for a sign-in that worked.
        """
        from hmz.providers import login

        return login.sign_in(provider, way, answers)

    def asks(self, way: Way, given: Mapping[str, str]) -> list[str]:
        """What a way in still has to be told before it can be used."""
        from hmz.providers import login

        return login.asked(way, given)

    def serves(self, one: Provider) -> tuple[str, ...]:
        """The other backends this account's credentials could run, in the order they are listed."""
        from hmz import providers

        return providers.serves(one)

    def copies(self, one: Provider, cli: str, name: str = "") -> Provider:
        """Writes the same account down for another backend it could be run as.

        Args:
          one: The account to copy.
          cli: The backend to write it down for.
          name: What to call the copy, defaulting to the name it already has.

        Returns:
          The copy, as it is now written down.

        Raises:
          ValueError: If that backend could not be run as this account.
          OSError: If it cannot be written.
        """
        from hmz import providers

        return providers.copies(one, cli, name)

    def chain(self, one: Provider) -> list[Provider]:
        """Every account a turn under this one would carry on under, this one first."""
        from hmz import providers

        return providers.chain(one)

    def points(self, cli: str, name: str, at: str) -> bool:
        """Says which account a turn under one carries on under when it fails.

        Args:
          cli: The backend they are both of.
          name: The account it is written on, or "" for the one this machine is signed into.
          at: The account to carry on under, or "" for the end of the line.

        Returns:
          Whether there was an account to write it on.

        Raises:
          ValueError: If the account named is not one of that backend's, or is the account
            itself, or would make a chain that comes round on itself.
        """
        from hmz import providers

        return providers.points(cli, name, at)

    def remove(self, cli: str, name: str) -> bool:
        """Takes an account away, credentials and all.

        Args:
          cli: The backend it is for.
          name: What it is called.

        Returns:
          Whether there was one to take away.

        Raises:
          ValueError: If it is the account this machine is already signed into, which
            humanize did not make and keeps no credentials for.
        """
        from hmz import providers

        return providers.remove(cli, name)

    def env(self, said: str) -> dict[str, str]:
        """Reads `NAME=VALUE` lines into what a turn under an account is run with."""
        from hmz import providers

        return providers.env_of(said)

    def environ(self, provider: Provider | None) -> dict[str, str]:
        """What a turn under this account is run with, and nothing for no account at all."""
        from hmz import providers

        return providers.environ(provider)

    def models(self, cli: str, provider: str = "") -> tuple[Model, ...]:
        """What one backend last said it runs as one account, read off what was kept.

        Args:
          cli: The backend, by any name it answers to.
          provider: The account, or "" for the one this machine is already signed into.

        Returns:
          One model apiece, each with the efforts it takes, and nothing at all for a backend
          nobody has asked yet.
        """
        from hmz import models

        return models.offered(cli, provider)

    def asked(self, cli: str, provider: str = "") -> str:
        """When one backend was last asked what it runs as one account, and "" for never."""
        from hmz import models

        return models.asked(cli, provider)

    def ask(
        self, cli: str, provider: str = "", seconds: float | None = None
    ) -> tuple[Model, ...]:
        """Starts a backend to find out what it runs as one account, and keeps what it said.

        Args:
          cli: The backend, by any name it answers to.
          provider: The account, or "" for the one this machine is already signed into.
          seconds: How long it is given to answer, or None for however long that backend is
            ordinarily given.

        Returns:
          What it said it runs, which is nothing at all for one that would not answer.
        """
        from hmz import models

        if seconds is None:
            return models.ask(cli, provider)
        return models.ask(cli, provider, seconds)
