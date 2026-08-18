"""``hmz providers`` -- the accounts an agent may be run as, from a command line.

The same store the interface's `/providers` walks through, said as arguments instead: what
there is, what a backend offers, and the three things that can happen to one -- made, signed
in again, taken away. It is reached through :class:`hmz.sdk.Hmz`, which is what the interface
asks too: one place a thing is kept is one place it is kept, whichever way somebody reached it.

What is here and nowhere else is the asking. A way in that has not been told everything it
needs is answered at the terminal, and a secret is never echoed -- which is a thing about
somebody sitting at a command line rather than about an account.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from hmz.providers import Provider
    from hmz.sdk import Accounts

__all__ = ["providers"]

#: What one account is written down in, and the key that used to be in it. How often a failed
#: turn is taken again was once a thing about an account and is now a thing about a place --
#: the CLI, the account and the model -- so `hmz.providers` stopped reading this and nothing
#: reads it since. A file written before that move still holds it, and an account whose tries
#: quietly stopped happening is worse than one that never had any: it is a setting somebody
#: goes on believing in. So the file is read again as it stands, wherever an account is read.
#: Spelled here rather than asked of the store, which is the thing that stopped reading it, and
#: pinned to the store's own spelling by a test so a rename cannot quietly end the notice.
_HELD = "provider.json"
_TRIED = "retries"
_WAITED = "policy"
_LONGEST = "timeout"


def providers(argv: list[str]) -> int:
    """Carries out one `hmz providers` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct, or one for something that could not be done.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz providers",
        description="The accounts an agent may be run as: one named set of credentials per "
        "provider, kept apart from the CLI's own.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND")

    listing = doing.add_parser("list", help="what providers there are")
    listing.add_argument("cli", nargs="?", default="", help="only this backend's")

    offered = doing.add_parser("ways", help="how one backend can be signed into")
    offered.add_argument("cli", help="the backend")

    making = doing.add_parser("add", help="make one, and sign it in")
    making.add_argument("provider", metavar="CLI/NAME", help="what to call it")
    making.add_argument(
        "-w", "--way", default="", help="how to sign in; `ways` lists them"
    )
    making.add_argument(
        "-s",
        "--set",
        metavar="VAR=VALUE",
        action="append",
        default=[],
        dest="given",
        help="answer one of the way's questions without being asked; repeatable",
    )
    making.add_argument(
        "--no-login",
        action="store_true",
        help="write it down without running the backend's own way in",
    )
    making.add_argument(
        "--also",
        metavar="CLI[,CLI...]",
        default="",
        help="write the same account down for these backends too, under the same name, "
        "over one already there; `all` for every backend it could be run as",
    )

    again = doing.add_parser("login", help="sign an existing one in again")
    again.add_argument("provider", metavar="CLI/NAME")
    again.add_argument(
        "-s",
        "--set",
        metavar="VAR=VALUE",
        action="append",
        default=[],
        dest="given",
        help="answer one of the way's questions without being asked; repeatable",
    )

    showing = doing.add_parser("show", help="what one holds")
    showing.add_argument(
        "provider",
        metavar="CLI/NAME",
        help="the account, or `CLI/` for the one this machine is already signed into",
    )

    dropping = doing.add_parser("remove", help="take one away, credentials and all")
    dropping.add_argument("provider", metavar="CLI/NAME")

    falling = doing.add_parser(
        "falls-back",
        help="say which account a turn carries on under when this one fails",
    )
    falling.add_argument(
        "provider",
        metavar="CLI/NAME",
        help="the account, or `CLI/` for the one this machine is already signed into, which "
        "is where the chain of an agent given no account begins",
    )
    falling.add_argument(
        "at",
        nargs="?",
        default="",
        metavar="NAME",
        help="the account of that CLI to carry on under, or nothing for the end of the line",
    )

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(getattr(args, "cli", ""))
    if args.doing == "ways":
        return _ways(args.cli)
    try:
        # `claude/` is the account this machine is already signed into: a thing to show
        # and to point somewhere, and not one to make or take away.
        cli, name = _named(args.provider, made=args.doing not in ("show", "falls-back"))
    except ValueError as why:
        parser.error(str(why))
    if args.doing == "show":
        return _show(cli, name)
    if args.doing == "remove":
        return _remove(cli, name)
    if args.doing == "add":
        return _add(
            cli,
            name,
            args.way,
            args.given,
            login=not args.no_login,
            also=args.also,
        )
    if args.doing == "falls-back":
        return _falls_back(cli, name, args.at)
    return _again(cli, name, args.given)


def _falls_back(cli: str, name: str, at: str) -> int:
    """Says which account a turn under this one carries on under when it fails."""
    try:
        said = _accounts().points(cli, name, at.strip())
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not said:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    whose = f"{cli}/{name}" if name else f"{cli}, as this machine is signed in,"
    print(
        f"{whose} falls back to {at.strip()}"
        if at.strip()
        else f"{whose} falls back to nowhere"
    )
    return 0


def _named(said: str, *, made: bool = True) -> tuple[str, str]:
    """Reads `CLI/NAME` into the two it names.

    Args:
      said: What was typed.
      made: Whether it has to be an account somebody made. `claude/` -- a CLI and no name at
        all -- is the account this machine is already signed into, which is an account to say
        things about and not one to make, sign in or take away.

    Returns:
      The backend and the name, which is "" for the account this machine is signed into.

    Raises:
      ValueError: If it is not that shape.
    """
    cli, sep, name = said.partition("/")
    if not sep or not cli.strip() or (made and not name.strip()):
        wanted = "CLI/NAME, as in claude/deepseek"
        raise ValueError(f"{said!r} is not {wanted}")
    return cli.strip(), name.strip()


def _accounts() -> Accounts:
    """The accounts, as the one object every way in reaches them through."""
    from hmz.sdk import Hmz

    return Hmz().accounts


def _tries_moved(provider: Provider) -> str:
    """What to say about tries written on one account before they moved, or "" for none.

    Args:
      provider: The account. Its file is read as it stands rather than as the store parses
        it, since what is being looked for is exactly the key the store stopped reading.

    Returns:
      One line saying the setting is no longer read here and naming what says it now, with
      everything that was written down -- the number, the wait between them and the cap on
      how long they go on -- carried into that line so it can be typed as it stands. "" for
      an account that never had one, which is every account made since.
    """
    from hmz.providers import LOCAL, alone

    at = alone(provider.cli) if provider.name == LOCAL else provider.at / _HELD
    try:
        said = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(said, dict):
        return ""
    held = cast("dict[str, Any]", said)
    tries = held.get(_TRIED)
    if not isinstance(tries, int) or isinstance(tries, bool) or tries < 1:
        return ""
    # As `hmz fallback` names a place: the account after an `@`, and nothing at all for the
    # one this machine is signed into. The model is the part an account never had, which is
    # why nothing could carry these over by itself -- so it is left as the command's own
    # spelling of that argument rather than as anything a shell would try to read.
    place = f"{provider.cli}@{provider.name}" if provider.name else provider.cli
    line = f"hmz fallback retry {place}/MODEL {tries}"
    policy = held.get(_WAITED)
    if isinstance(policy, str) and policy:
        line += f" -p {policy}"
    longest = held.get(_LONGEST)
    if (
        isinstance(longest, (int, float))
        and not isinstance(longest, bool)
        and longest > 0
    ):
        line += f" -t {longest:g}"
    return f"the tries written down here are no longer read: `{line}` is where that is said now"


def _also(cli: str) -> list[Provider]:
    """The account this machine is signed into, where it says anything about itself.

    Args:
      cli: The backend to list, or "" for all of them.

    Returns:
      One per backend whose own sign-in has a chain written down, since that is a setting
      in force and a list that did not show it would be a list that hid one, and one per
      backend still holding the tries that moved, since a listing is where somebody finds
      out. Nothing for the ones left as they come, which is every backend on a machine
      nobody has said anything about them on.
    """
    from hmz import backends
    from hmz.providers import LOCAL

    accounts = _accounts()
    wanted = backends.named(cli) if cli else None
    return [
        one
        for profile in backends.profiles()
        if (wanted is None or profile.name == wanted.name)
        and (one := accounts.find(profile.name, LOCAL)) is not None
        and (one.fallback or _tries_moved(one))
    ]


def _list(cli: str) -> int:
    """Prints every provider there is, or one backend's."""
    from hmz import backends

    if cli and backends.named(cli) is None:
        # Said rather than answered with everybody's: a name no backend answers to reads as
        # "all of them" everywhere below, so a typo would report another backend's account
        # and its chain as though they were this one's.
        print(f"hmz: {cli}: no such coding agent", file=sys.stderr)
        return 1
    found = _accounts().all(cli)
    # And the account this machine is signed into, wherever it says something about itself:
    # a chain in force is a thing to see, and it is an account here too.
    mine = _also(cli)
    if not found and not mine:
        whose = f"no {cli} providers yet" if cli else "no providers yet"
        print(f"{whose}; try `hmz providers add {cli or 'claude'}/mine`")
        return 0
    for provider in [*found, *mine]:
        variables = ", ".join(sorted(provider.env)) or "-"
        way = provider.way or "as local"
        said = f"{provider.cli}/{provider.name}  {way:10} {variables}"
        if provider.fallback:
            said += f"  falls back to {provider.fallback}"
        print(said)
        # Under the row rather than after it: it is about the account above rather than
        # another account, and a row this ran onto the end of would be a row nobody reads.
        if moved := _tries_moved(provider):
            print(f"  {moved}")
    return 0


def _ways(cli: str) -> int:
    """Prints how one backend can be signed into."""
    offered = _accounts().ways(cli)
    if not offered:
        print(f"hmz: {cli}: no such coding agent", file=sys.stderr)
        return 1
    for way in offered:
        asks = ", ".join(one.env for one in way.asks) or "-"
        runs = " ".join(way.argv) if way.argv else "-"
        print(f"{way.name:10} {way.about}")
        print(f"{'':10} asks: {asks}")
        print(f"{'':10} runs: {runs}")
    return 0


def _show(cli: str, name: str) -> int:
    """Prints what one provider holds, saying nothing a secret is."""
    accounts = _accounts()
    provider = accounts.find(cli, name)
    if provider is None:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(f"provider    {provider.cli}/{provider.name}")
    print(f"way         {provider.way or 'as this machine is signed in'}")
    print(f"made        {provider.made or '-'}")
    print(f"kept in     {provider.at}")
    print(f"falls to    {provider.fallback or 'nowhere'}")
    for variable in sorted(provider.env):
        # The names, never the values: this prints where a person can read it, and a key
        # printed once is a key in a scrollback.
        print(f"sets        {variable}")
    for one in provider.args:
        print(f"adds        {one}")
    for named, instead in provider.swaps():
        print(f"answers     {named} -> {instead}")
    for backend in accounts.serves(provider):
        # What else this account is: a vendor's credential is the vendor's, and an account
        # that several backends could be run as is worth saying so about where it is read.
        print(f"also runs   {backend}")
    # Last, and not as a field: a setting nothing reads any more is not one of the things
    # this account holds, and reading it as one is how it went unnoticed in the first place.
    if moved := _tries_moved(provider):
        print(moved)
    return 0


def _copies(provider: Provider, also: str) -> int:
    """Writes one account down for the other backends it could be run as, where asked.

    A vendor's credential is the vendor's rather than the CLI's, so an account made for one
    backend is often an account several others could be run as -- and making the same key
    four times by hand is four places to correct when it is rotated.

    Args:
      provider: The account just made.
      also: What the line asked for: backends by name, comma separated, or `all` for every
        one it could be run as, or "" for none.

    Returns:
      Zero, or one for a backend named that this account could not be run as -- which is a
      line to correct rather than a copy to skip quietly.
    """
    accounts = _accounts()
    among = accounts.serves(provider)
    if not also:
        if among:
            # Said rather than done: a line that did not ask for it gets a line saying it
            # could have, which is how somebody finds out this is a thing at all.
            print(
                f"it could also run {', '.join(among)}; `--also` writes it down for them"
            )
        return 0
    wanted = among if also.strip() == "all" else _backends(also)
    for backend in wanted:
        try:
            copied = accounts.copies(provider, backend)
        except (ValueError, OSError) as why:
            print(f"hmz: {why}", file=sys.stderr)
            return 1
        print(f"{copied.cli}/{copied.name} is written down at {copied.at}")
    return 0


def _backends(said: str) -> tuple[str, ...]:
    """The backends one `--also` named, in the order they were named."""
    return tuple(one.strip() for one in said.split(",") if one.strip())


def _remove(cli: str, name: str) -> int:
    """Takes a provider away."""
    try:
        gone = _accounts().remove(cli, name)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not gone:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(f"{cli}/{name} is gone, credentials and all")
    return 0


def _add(
    cli: str,
    name: str,
    way: str,
    given: list[str],
    *,
    login: bool,
    also: str = "",
) -> int:
    """Makes a provider, asking for whatever its way still needs, and signs it in."""
    accounts = _accounts()
    offered = accounts.ways(cli)
    if not offered:
        print(f"hmz: {cli}: no such coding agent", file=sys.stderr)
        return 1
    chosen = accounts.way(cli, way) if way else offered[0]
    if chosen is None:
        print(
            f"hmz: {cli} has no way in called {way!r}; try `hmz providers ways {cli}`",
            file=sys.stderr,
        )
        return 1
    try:
        answers = accounts.env("\n".join(given))
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    try:
        answers = _asking(chosen, answers)
    except EOFError:
        print("hmz: nothing to read the answers from", file=sys.stderr)
        return 1
    except ValueError as why:
        # A line typed at the prompt that is not `NAME=VALUE`, which is a line to correct
        # and not a traceback: the same answer as the same mistake made on the command line.
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    try:
        provider = accounts.make(cli, name, chosen, answers)
    except (ValueError, OSError) as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{provider.cli}/{provider.name} is written down at {provider.at}")
    status = _copies(provider, also)
    if status:
        return status
    if not login:
        # A line that says not to run the backend's own way in is a line that says not to
        # start the backend: asking it what it runs would be starting it. What it runs is
        # found out by whatever next wants a list of it.
        return 0
    if not chosen.argv:
        return _asks(provider.cli, provider.name)
    return _sign(provider, chosen, answers) or _asks(provider.cli, provider.name)


def _asks(cli: str, name: str) -> int:
    """Asks a new account's CLI what it runs, so that there is a list before one is wanted.

    An account is made in order to run turns as, and which models those turns may name is
    that account's rather than the CLI's: this is where that is found out, once, and it is
    kept until somebody asks for it again.

    Args:
      cli: The backend the account is for.
      name: What the account is called.

    Returns:
      Zero either way. An account whose CLI would not say what it runs is still an account,
      and exiting badly over it would be reporting the thing that worked as the thing that
      did not.
    """
    try:
        found = _accounts().ask(cli, name)
    except Exception as why:  # noqa: BLE001 -- a CLI that will not say, however it will not
        print(f"hmz: {cli} did not say what it runs as {name}: {why}", file=sys.stderr)
        return 0
    print(f"{cli} says it runs {len(found)} models as {name}")
    return 0


def _again(cli: str, name: str, given: list[str]) -> int:
    """Signs an existing provider in again, by the way it was made with."""
    accounts = _accounts()
    provider = accounts.find(cli, name)
    if provider is None:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    chosen = accounts.way(cli, provider.way)
    if chosen is None or not chosen.argv:
        print(
            f"hmz: {cli}/{name} was made by {provider.way}, which has nothing to run; "
            "make it again to change what it holds",
            file=sys.stderr,
        )
        return 1
    try:
        answers = accounts.env("\n".join(given))
        answers = _asking(chosen, answers)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    except EOFError:
        print("hmz: nothing to read the answers from", file=sys.stderr)
        return 1
    # Signed in again is possibly a different account, and certainly a fresh answer to what
    # it runs: an account that has just changed hands is one to ask again.
    return _sign(provider, chosen, answers) or _asks(cli, name)


def _sign(provider: object, way: object, answers: dict[str, str]) -> int:
    """Runs the backend's own way in, and says what came of it."""
    from hmz.backends import Way
    from hmz.providers import Provider

    assert isinstance(provider, Provider)  # noqa: S101 -- built by the caller, two lines up
    assert isinstance(way, Way)  # noqa: S101
    status = _accounts().sign_in(provider, way, answers)
    if status:
        # Including a CLI that is not installed: what is spawned is the supervisor, and a
        # program it cannot start is a status of its own with the reason already on stderr.
        print(f"hmz: {way.argv[0]} exited {status}", file=sys.stderr)
    return status


def _asking(way: object, given: dict[str, str]) -> dict[str, str]:
    """Puts whatever a way still needs to whoever is at the terminal.

    Args:
      way: The way in.
      given: What the line already answered.

    Returns:
      Every answer, the ones typed here included.

    Raises:
      EOFError: If there is nobody to ask -- a line run from a script has to say everything it
        means on the line -- or if a question that has to be answered was answered with
        nothing. A provider written down without the key it is for is one that fails at the
        first turn instead of here.
    """
    import getpass

    from hmz.backends import Way
    from hmz.providers import ENV

    assert isinstance(way, Way)  # noqa: S101 -- taken from the table two lines up
    answers = dict(given)
    for one in way.asks:
        if answers.get(one.env):
            continue
        if not sys.stdin.isatty():
            if not one.fixed:
                raise EOFError(one.env)
            answers[one.env] = one.fixed
            continue
        asked = one.about + (f" [{one.fixed}]" if one.fixed else "")
        said = (
            getpass.getpass(f"{asked}: ") if one.secret else input(f"{asked}: ")
        ).strip()
        if not said and not one.fixed:
            raise EOFError(one.env)
        answers[one.env] = said or one.fixed
    if way.name == ENV.name and not answers:
        # The way that is only variables asks nothing in particular, so it is asked for all of
        # them at once -- and a provider of no variables at all is one that does nothing.
        if not sys.stdin.isatty():
            raise EOFError("--set NAME=VALUE")
        print(
            "the variables this CLI reads, one NAME=VALUE per line, then a blank line:"
        )
        lines: list[str] = []
        while said := input("  ").strip():
            lines.append(said)
        answers = _accounts().env("\n".join(lines))
        if not answers:
            raise EOFError("NAME=VALUE")
    return answers
