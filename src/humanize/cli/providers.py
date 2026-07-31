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
    return _again(cli, name, args.given)


def _named(said: str) -> tuple[str, str]:
    """Reads `CLI/NAME` into the two it names."""
    cli, sep, name = said.partition("/")
    if not sep or not cli.strip() or not name.strip():
        raise ValueError(f"{said!r} is not CLI/NAME, as in claude/deepseek")
    return cli.strip(), name.strip()


def _list(cli: str) -> int:
    """Prints every provider there is, or one backend's."""
    from humanize import providers as held

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
    from humanize import providers as held

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
    from humanize import providers as held

    provider = held.find(cli, name)
    if provider is None:
        print(f"hmz: no provider {cli}/{name}", file=sys.stderr)
        return 1
    print(f"provider    {provider.cli}/{provider.name}")
    print(f"way         {provider.way}")
    print(f"made        {provider.made or '-'}")
    print(f"kept in     {provider.at}")
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
    from humanize import providers as held

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
    from humanize import providers as held
    from humanize.providers import login as signing

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
    if not login or not chosen.argv:
        return 0
    return _sign(provider, chosen, answers)


def _again(cli: str, name: str, given: list[str]) -> int:
    """Signs an existing provider in again, by the way it was made with."""
    from humanize import providers as held
    from humanize.providers import login as signing

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
    return _sign(provider, chosen, answers)


def _sign(provider: object, way: object, answers: dict[str, str]) -> int:
    """Runs the backend's own way in, and says what came of it."""
    from humanize.backends import Way
    from humanize.providers import Provider
    from humanize.providers import login as signing

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

    from humanize.backends import Way
    from humanize.providers import ENV, env_of

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
