"""The agents written down under a name, as one object over the file they are kept in.

What an agent is -- a CLI, an account, a model at an effort, what it may do and where its work
lands -- is worth saying once and reaching for from every flow that needs one like it. The
file is :mod:`hmz.kept`; this is what a command line, an interface and a daemon all ask, so
that a name already taken is refused the same way whichever of them asked, and one written
over keeps its place in the list rather than moving to the end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.backends import Profile
    from hmz.kept import Kept, Runs

__all__ = ["Agents", "Taken"]


class Taken(ValueError):  # noqa: N818  -- what the name is, not what went wrong
    """A name already written down, raised rather than quietly written over.

    Its own class because what to say about it is whoever asked's: a command line says which
    flag writes over one, and a menu that has already asked which name to save over says
    nothing at all.
    """


class Agents:
    """The agents kept under a name: what there is, and the two things that happen to one."""

    def reads(
        self, spec: str
    ) -> tuple[
        Profile,
        str,
        str,
        str,
        str,
        str | None,
        bool | None,
        tuple[tuple[str, str], ...],
    ]:
        """Reads one agent the way a command line names one.

        Args:
          spec: The short or written-out form `-a` takes.

        Returns:
          The backend, model, effort, service tier, account, the permission rung where one
          was named, whether it may search the web where anybody said, and the pairs said in
          the backend's own vocabulary.

        Raises:
          ValueError: If it is not an agent, or names no permission rung there is.
        """
        from hmz.runner import read_agent

        return read_agent(spec)

    def all(self) -> list[Kept]:
        """Every agent written down, in the order they were written down in."""
        from hmz.kept import Templates

        return Templates().all()

    def find(self, name: str) -> Kept | None:
        """The one written down under this name, or None for a name none answers to."""
        from hmz.kept import Templates

        return Templates().find(name)

    def keep(self, agents: list[Kept]) -> None:
        """Writes down exactly these and nothing else, which is what a menu saves.

        Args:
          agents: What is written down from now on, in the order it is to be listed in.
        """
        from hmz.kept import Templates

        Templates().keep(agents)

    def write(self, name: str, runs: Runs, *, force: bool = True) -> Kept:
        """Writes one agent down under a name.

        Args:
          name: What to call it.
          runs: What it runs, and whatever else it says about itself.
          force: Whether a name already taken may be written over. False refuses instead: an
            agent somebody else set up is not a thing to lose to a typo on a command line,
            while a menu that asked which name to save over has already asked.

        Returns:
          It, as it is now written down.

        Raises:
          ValueError: If the name is empty.
          Taken: If the name is one already written down and `force` is False.
        """
        from hmz.kept import Kept, Templates

        if not name.strip():
            raise ValueError("an agent is written down under a name")
        templates = Templates()
        held = templates.all()
        already = any(one.name == name for one in held)
        if already and not force:
            raise Taken(f"there is already an agent called {name}")
        # Whole, as the menu writes them: one written over keeps its place in the list, and
        # one that is new goes on the end, which is the order they were written down in.
        one = Kept(name, runs)
        templates.keep(
            [one if each.name == name else each for each in held]
            if already
            else [*held, one]
        )
        return one

    def add(
        self,
        name: str,
        spec: str,
        *,
        anchor: str = "",
        goals: bool = True,
        web_search: bool | None = None,
        force: bool = False,
    ) -> Kept:
        """Writes one agent down out of the way a command line names one.

        Args:
          name: What to call it.
          spec: What it runs, exactly as `-a` takes it.
          anchor: The machine its work lands on, or "" for this one.
          goals: Whether its backend's own goals are available to it.
          web_search: Whether it may search the web, or None for whatever the spec said --
            and on where it said nothing, which is what an agent nobody has been asked about
            does.
          force: Whether a name already taken may be written over.

        Returns:
          It, as it is now written down.

        Raises:
          ValueError: If the spec is not one an agent may be written down as.
          Taken: If the name is one already written down and `force` is False.
        """
        from hmz.agents import PERMISSIONS
        from hmz.backends import read
        from hmz.kept import Runs

        if not name.strip():
            raise ValueError("an agent is written down under a name")
        try:
            (
                profile,
                model,
                effort,
                service_tier,
                provider,
                permission,
                searches,
                overrides,
            ) = read(spec)
        except ValueError as why:
            # Said against the spelling that was refused: a line with four agents on it is
            # one where the message has to say which of them was the one to correct.
            raise ValueError(f"{spec}: {why}") from why
        if service_tier != "default":
            raise ValueError(
                "service_tier is a per-run setting on the agent line, "
                "not a saved-agent setting"
            )
        if overrides:
            raise ValueError(
                "config.KEY is a setting of the agent on the line that runs it, "
                "not of one written down under a name"
            )
        if permission is not None and permission not in PERMISSIONS:
            raise ValueError(
                f"permission must be one of {', '.join(PERMISSIONS)}, not {permission!r}"
            )
        return self.write(
            name,
            Runs(
                f"{profile.name}/{model}:{effort}",
                anchor.strip(),
                permission or "",
                provider,
                goals,
                web_search if web_search is not None else searches is not False,
            ),
            force=force,
        )

    def remove(self, name: str) -> bool:
        """Takes one agent away.

        Args:
          name: What it is written down under.

        Returns:
          Whether there was one of that name to take away.
        """
        from hmz.kept import Templates

        templates = Templates()
        held = templates.all()
        if not any(one.name == name for one in held):
            return False
        templates.keep([one for one in held if one.name != name])
        return True
