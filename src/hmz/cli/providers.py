"""``hmz providers`` -- the accounts an agent may be run as, from a command line.

The same store the interface's `/providers` walks through, said as arguments instead: what
there is, what a backend offers, and the three things that can happen to one -- made, signed
in again, taken away.
"""

from __future__ import annotations

import sys

__all__ = ["providers"]


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
    showing.add_argument("provider", metavar="CLI/NAME")

    dropping = doing.add_parser("remove", help="take one away, credentials and all")
    dropping.add_argument("provider", metavar="CLI/NAME")

    falling = doing.add_parser(
        "falls-back",
        help="say which account a turn carries on under when this one fails",
    )
    falling.add_argument("provider", metavar="CLI/NAME")
    falling.add_argument(
        "at",
        nargs="?",
        default="",
        metavar="NAME",
        help="the account of that CLI to carry on under, or nothing for the end of the line",
    )

    trying = doing.add_parser(
        "retry", help="say how a failed turn under one is tried again"
    )
    trying.add_argument("provider", metavar="CLI/NAME")
    trying.add_argument(
        "-n",
        "--tries",
        type=int,
        default=0,
        help="how many times over a failed turn is tried again, beyond the first",
    )
    trying.add_argument(
        "-p",
        "--policy",
        default=_waits()[1],
        help="how long to wait between tries: " + ", ".join(_waits()[0]),
    )
    trying.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="the longest the trying again may go on for, or 0 for as long as it takes",
    )

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(getattr(args, "cli", ""))
    if args.doing == "ways":
        return _ways(args.cli)
    try:
        cli, name = _named(args.provider)
    except ValueError as why:
        parser.error(str(why))
    if args.doing == "show":
        return _show(cli, name)
    if args.doing == "remove":
        return _remove(cli, name)
    if args.doing == "add":
        return _add(cli, name, args.way, args.given, login=not args.no_login)
    if args.doing == "falls-back":
        return _falls_back(cli, name, args.at)
    if args.doing == "retry":
        return _retry(cli, name, args.tries, args.policy, args.timeout)
    return _again(cli, name, args.given)


def _falls_back(cli: str, name: str, at: str) -> int:
    """Says which account a turn under this one carries on under when it fails."""
    from hmz import providers as held

    try:
        said = held.points(cli, name, at.strip())
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not said:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(
        f"{cli}/{name} falls back to {at.strip()}"
        if at.strip()
        else f"{cli}/{name} falls back to nowhere"
    )
    return 0


def _retry(cli: str, name: str, tries: int, policy: str, timeout: float) -> int:
    """Says how a failed turn under one account is tried again."""
    from hmz import providers as held

    try:
        said = held.retrying(cli, name, tries, policy, timeout)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not said:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(
        f"{cli}/{name} is tried {tries} more times, {policy}"
        if tries
        else f"{cli}/{name} is tried once"
    )
    return 0


def _waits() -> tuple[tuple[str, ...], str]:
    """What a turn may be waited over between tries, and the one an account starts on."""
    from hmz.providers import retry

    return tuple(one.name for one in retry.POLICIES), retry.DEFAULT


def _named(said: str) -> tuple[str, str]:
    """Reads `CLI/NAME` into the two it names."""
    cli, sep, name = said.partition("/")
    if not sep or not cli.strip() or not name.strip():
        raise ValueError(f"{said!r} is not CLI/NAME, as in claude/deepseek")
    return cli.strip(), name.strip()


def _list(cli: str) -> int:
    """Prints every provider there is, or one backend's."""
    from hmz import providers as held

    found = held.providers(cli)
    if not found:
        whose = f"no {cli} providers yet" if cli else "no providers yet"
        print(f"{whose}; try `hmz providers add {cli or 'claude'}/mine`")
        return 0
    for provider in found:
        variables = ", ".join(sorted(provider.env)) or "-"
        print(f"{provider.cli}/{provider.name}  {provider.way:10} {variables}")
    return 0


def _ways(cli: str) -> int:
    """Prints how one backend can be signed into."""
    from hmz import providers as held

    offered = held.ways(cli)
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
    from hmz import providers as held

    provider = held.find(cli, name)
    if provider is None:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(f"provider    {provider.cli}/{provider.name}")
    print(f"way         {provider.way}")
    print(f"made        {provider.made or '-'}")
    print(f"kept in     {provider.at}")
    print(f"falls to    {provider.fallback or 'nowhere'}")
    print(
        "tried       "
        + (
            f"{provider.retries} more times, {provider.policy}"
            + (f", for up to {provider.timeout:.0f}s" if provider.timeout else "")
            if provider.retries
            else "once"
        )
    )
    for variable in sorted(provider.env):
        # The names, never the values: this prints where a person can read it, and a key
        # printed once is a key in a scrollback.
        print(f"sets        {variable}")
    for one in provider.args:
        print(f"adds        {one}")
    for named, instead in provider.swaps():
        print(f"answers     {named} -> {instead}")
    return 0


def _remove(cli: str, name: str) -> int:
    """Takes a provider away."""
    from hmz import providers as held

    try:
        gone = held.remove(cli, name)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not gone:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(f"{cli}/{name} is gone, credentials and all")
    return 0


def _add(cli: str, name: str, way: str, given: list[str], *, login: bool) -> int:
    """Makes a provider, asking for whatever its way still needs, and signs it in."""
    from hmz import providers as held
    from hmz.providers import login as signing

    offered = held.ways(cli)
    if not offered:
        print(f"hmz: {cli}: no such coding agent", file=sys.stderr)
        return 1
    chosen = signing.way_of(cli, way) if way else offered[0]
    if chosen is None:
        print(
            f"hmz: {cli} has no way in called {way!r}; try `hmz providers ways {cli}`",
            file=sys.stderr,
        )
        return 1
    try:
        answers = held.env_of("\n".join(given))
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    try:
        answers = _asking(chosen, answers)
    except EOFError:
        print("hmz: nothing to read the answers from", file=sys.stderr)
        return 1
    try:
        provider = signing.make(cli, name, chosen, answers)
    except (ValueError, OSError) as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{provider.cli}/{provider.name} is written down at {provider.at}")
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
    from hmz import models

    try:
        found = models.ask(cli, name)
    except Exception as why:  # noqa: BLE001 -- a CLI that will not say, however it will not
        print(f"hmz: {cli} did not say what it runs as {name}: {why}", file=sys.stderr)
        return 0
    print(f"{cli} says it runs {len(found)} models as {name}")
    return 0


def _again(cli: str, name: str, given: list[str]) -> int:
    """Signs an existing provider in again, by the way it was made with."""
    from hmz import providers as held
    from hmz.providers import login as signing

    provider = held.find(cli, name)
    if provider is None:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    chosen = signing.way_of(cli, provider.way)
    if chosen is None or not chosen.argv:
        print(
            f"hmz: {cli}/{name} was made by {provider.way}, which has nothing to run; "
            "make it again to change what it holds",
            file=sys.stderr,
        )
        return 1
    try:
        answers = held.env_of("\n".join(given))
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
    from hmz.providers import login as signing

    assert isinstance(provider, Provider)  # noqa: S101 -- built by the caller, two lines up
    assert isinstance(way, Way)  # noqa: S101
    status = signing.sign_in(provider, way, answers)
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
    from hmz.providers import ENV, env_of

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
        answers = env_of("\n".join(lines))
        if not answers:
            raise EOFError("NAME=VALUE")
    return answers
