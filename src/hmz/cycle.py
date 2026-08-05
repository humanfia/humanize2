"""What one run of one flow was, written down as it runs.

A flow drives several agents through many sessions, and every one of those sessions is written
down by the backend that ran it -- under an id of its own, in a directory of its own, saying
nothing about whose it was or what it was part of. The run itself is written nowhere. This is
that: which flow was run, on what, by which agents, and which sessions each of them opened as
it went -- each under the account it ran as. Enough to gather a trace of the run afterwards
out of the ids alone, and enough to find the sessions a run left behind.

Not what the sessions said. A backend's own log is the turn-by-turn record and this is not a
second copy of it: what is kept here is the shape of the run, one line per thing that happened
to it, and beside the lines a link per session pointing at the log the backend is writing. A
link rather than a copy, and read by whoever is looking rather than by humanize: a run is
written and read through the paths the backends themselves keep, so that nothing here can be
the reason a log is written twice or read from the wrong place.

One cycle is one run, and one directory::

    ~/.humanize/cycles/<workspace>/<when>-<which>/
        cycle.jsonl                     what happened, a line at a time
        sessions/<session>/…            a link per file the backend logged it to

It opens when the flow starts and closes when the flow stops, however it stops -- finished,
failed, or interrupted. A closed cycle is never reopened: running the flow again is another
run, with sessions of its own, and so another cycle.
"""

from __future__ import annotations

import datetime
import json
import re
import threading
import uuid
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Self, cast

from hmz import backends, home

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .agents import AgentBase

__all__ = [
    "JOURNAL",
    "LOCAL",
    "SESSIONS",
    "Cycle",
    "Drove",
    "Ran",
    "Session",
    "called",
    "cycles",
    "linked",
    "opened",
    "read",
    "sessions",
    "where",
]

#: What a directory may be called after: everything else in a path is flattened, the way the
#: agents themselves flatten a workspace into the folder they log it under.
_PLAIN = re.compile(r"[^A-Za-z0-9]")

#: What a session may be named with. Wider than the above, because this name is read as well
#: as written -- the backend, the account and the id are meant to be legible in it -- and
#: narrower than a path, because it is one directory name on somebody's filesystem.
_LEGIBLE = re.compile(r"[^A-Za-z0-9._@-]+")

#: The file a cycle's own record is written to, inside the cycle's directory.
JOURNAL = "cycle.jsonl"

#: Where the links to the sessions' own logs go, a directory per session.
SESSIONS = "sessions"

#: What a session opened as the account this machine is already signed into is written under.
#: A word rather than the empty string it is configured as: this goes in a directory name and
#: in a listing, and both of those read better saying which account than saying nothing.
LOCAL = "local"


def _now() -> str:
    """This moment, as every file humanize writes spells one."""
    return (
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )


class Session(NamedTuple):
    """One session a run opened, as the run wrote it down.

    Attributes:
      agent: Whose it was, by the name the flow calls that agent.
      backend: The coding agent CLI that took its turns, which is what logged it.
      provider: The account those turns ran as, or `local` for the one this machine is
        already signed into.
      ident: The id the backend gave it, which is what a trace of the run is gathered by.
      name: What the run calls it -- which agent, which CLI, which account and which session,
        in one name -- and the directory its links are under.
      at: When it was opened.
    """

    agent: str
    backend: str
    provider: str
    ident: str
    name: str
    at: str = ""


class Drove(NamedTuple):
    """One agent a run was driven by, as the run wrote it down.

    Attributes:
      agent: What the flow calls it.
      backend: The CLI it drives.
      model: What that CLI was asked to run.
      effort: How hard it was asked to think.
      permission: What it was allowed to do without being asked.
      provider: The account it was configured to run as, or "" for this machine's own.
    """

    agent: str
    backend: str
    model: str
    effort: str
    permission: str = ""
    provider: str = ""

    @property
    def spec(self) -> str:
        """What it runs, spelled the way `-a` spells one."""
        cli = f"{self.backend}@{self.provider}" if self.provider else self.backend
        return f"{cli}/{self.model}:{self.effort}"


class Ran(NamedTuple):
    """What one cycle was, read back off its own record.

    Attributes:
      at: The cycle's directory, which is what everything about it is under.
      flow: The flow that was run, as it was named.
      task: What its agents were asked to do.
      workspace: Where it ran.
      began: When it started.
      ended: When it stopped, or "" for one still running or abandoned where it stood.
      how: How it stopped -- done, failed or stopped -- and "" while it has not.
      agents: What drove it, in the order the flow takes them.
      sessions: Every session it opened, oldest first.
      resumable: Whether the flow it ran says it can be picked up again, which is what makes
        the state it left behind something to run the flow on rather than something to read.
    """

    at: Path
    flow: str = ""
    task: str = ""
    workspace: str = ""
    began: str = ""
    ended: str = ""
    how: str = ""
    agents: tuple[Drove, ...] = ()
    sessions: tuple[Session, ...] = ()
    resumable: bool = False

    @property
    def name(self) -> str:
        """What this cycle is called, which is the directory it is written in."""
        return self.at.name


def called(agent: str, backend: str, provider: str, ident: str) -> str:
    """What a run calls one session, which is a name rather than an id.

    A backend names a session with a UUID and nothing else, which says nothing about whose it
    was, what took its turns or which account they were taken as -- and a directory of forty
    of those is a directory nobody can read. So a session is named here for the four things
    somebody looking at a run wants to tell one from another by, the id among them: the id
    alone is what a trace is gathered by, and a name without it would name two.

    Args:
      agent: Whose session it is, by the name the flow calls that agent.
      backend: The CLI that took its turns.
      provider: The account they ran as, or "" for this machine's own.
      ident: The backend's own id for it.

    Returns:
      The name, as one directory name: `<agent>-<cli>@<account>-<id>`.
    """
    parts = (
        agent or "agent",
        backend or "cli",
        provider or LOCAL,
        ident or uuid.uuid4().hex[:8],
    )
    agent_at, cli, account, said = (
        _LEGIBLE.sub("-", part).strip("-") for part in parts
    )
    return f"{agent_at}-{cli}@{account}-{said}"


def _provider(agent: AgentBase) -> str:
    """Which account an agent's turns are running as, as a name to write down.

    Asked of the agent rather than read off its config, so that a turn that fell over onto
    the account the first one falls back to is written down under the account it actually ran
    as. An agent configured with an account that is not there says so the first time a turn
    needs one, and this is not that moment: what it was configured with is what is written.

    Args:
      agent: The agent.

    Returns:
      The account's name, or "" for the one this machine is already signed into.
    """
    try:
        at = agent.provider
    except ValueError:
        return agent.config.provider
    return at.name if at is not None else ""


def _logs(backend: str, ident: str) -> list[Path]:
    """Every file one session was logged to by the backend that ran it.

    Args:
      backend: The CLI, by the name `hmz.backends` knows it under.
      ident: The id it gave the session.

    Returns:
      The files, oldest path first, and nothing at all for a backend humanize has no logs
      written down for or one that has never run on this machine.
    """
    profile = backends.named(backend)
    if profile is None or not profile.logs:
        return []
    where = profile.directory()
    if not where.is_dir():
        return []
    found: list[Path] = []
    for pattern in profile.logs:
        try:
            found += sorted(where.glob(pattern.format(ident=ident)))
        except (OSError, ValueError):
            continue  # a home that cannot be read is a session with no links, not a failure
    return [one for one in found if one.is_file()]


def _link(at: Path, backend: str, ident: str) -> list[str]:
    """Points a directory of the cycle's own at the logs one session is being written to.

    Made for whoever is reading the run afterwards, and for nothing else: humanize reads and
    writes a log where the backend keeps it, so a link that is broken, refused by the
    filesystem or pointing at a file that has since been rolled over costs the run nothing.

    Args:
      at: The directory to make them in, which is the session's own under `sessions/`.
      backend: The CLI that logged it.
      ident: The id it logged it under.

    Returns:
      What each link is called, which is the log's own name where that is unambiguous and the
      path under the backend's home flattened where two of them share one.
    """
    found = _logs(backend, ident)
    if not found:
        return []
    profile = backends.named(backend)
    where = profile.directory() if profile is not None else Path()
    shared = Counter(one.name for one in found)
    made: list[str] = []
    try:
        at.mkdir(parents=True, exist_ok=True)
        # The links this made last time go first: a session gains files as it runs -- a
        # sub-agent's transcript, a second day's log -- and a name that was unambiguous when
        # there was one file is a name two files want once there are two.
        for old in at.iterdir():
            if old.is_symlink():
                old.unlink()
        for one in found:
            name = one.name
            if shared[name] > 1:
                with_root = one.relative_to(where) if one.is_relative_to(where) else one
                name = _LEGIBLE.sub("-", str(with_root)).strip("-")
            (at / name).symlink_to(one)
            made.append(name)
    except OSError:
        # A filesystem that will not make one -- Windows without the privilege, a mount that
        # has gone -- is a run without links rather than a run that stops.
        return made
    return made


class Cycle:
    """One run of one flow: the directory it is written to, and what has happened to it."""

    def __init__(
        self,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        workspace: Path | None = None,
    ) -> None:
        """Opens a cycle, and writes down what it is a run of.

        Args:
          flow: The flow being run, as it was named.
          agents: The agents it is being run with, in the order it takes them.
          task: What they were asked to do.
          workspace: Where the run happens, defaulting to this directory. Cycles are kept
            under the workspace they ran in, since that is what anyone looking for one has.
        """
        self._at = (
            home()
            / "cycles"
            / _PLAIN.sub("-", str((workspace or Path.cwd()).resolve()))
            # The moment names it and six hex say which, since two flows may be started in
            # one second and neither is the other's run.
            / f"{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
        )
        self._writing = (
            threading.Lock()
        )  # sessions open on whichever thread a turn runs on
        self._agents = list(agents)
        #: Every session this run has opened, by the name it was written down under, so that
        #: the links can be made again as the backends go on writing to them.
        self._sessions: dict[str, tuple[str, str]] = {}
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str((workspace or Path.cwd()).resolve()),
            agents=[
                {
                    "agent": agent.id,
                    "backend": agent.backend,
                    "model": agent.config.model,
                    "effort": agent.config.effort,
                    "permission": agent.config.permission,
                    # What it was configured with rather than what a turn of it ends up
                    # running as: the account a turn fell back onto is written down against
                    # the session that ran there, which is where it happened.
                    "provider": agent.config.provider,
                }
                for agent in agents
            ],
        )

    @property
    def path(self) -> Path:
        """The directory this cycle is written in."""
        return self._at

    @property
    def journal(self) -> Path:
        """The file the run's own record is written to, a line per thing that happened."""
        return self._at / JOURNAL

    def __enter__(self) -> Self:
        """Hands the cycle to whatever is running the flow inside it."""
        return self

    def __exit__(
        self, kind: type[BaseException] | None, why: object, traceback: object
    ) -> None:
        """Closes the cycle, saying how the run ended: a cycle closes once and for all.

        Args:
          kind: What was raised out of the run, if anything.
          why: The exception itself, unread.
          traceback: Where it was raised, unread.
        """
        from .agents import Stopped

        # The links again, now that the run is over: a backend writes a session's log while
        # the session runs and finishes writing it after the last turn, and a sub-agent's
        # transcript appears whenever that sub-agent was started.
        self.links()
        # An agent that was told to stop is a run that was stopped, whatever the turn under
        # way made of it: the process goes out from under that turn, and from inside one that
        # reads as a turn that could not finish.
        stopped = kind is not None and (
            issubclass(kind, Stopped) or any(agent.stopped for agent in self._agents)
        )
        self.write(
            "ended",
            how="stopped" if stopped else "failed" if kind is not None else "done",
        )
        for agent in self._agents:
            agent.cycle = None

    def opened(self, agent: AgentBase, session: str) -> None:
        """Writes down a session one of the agents has just opened.

        Which agent it was, which CLI took its turns and which account they were taken as:
        the backend's own log says none of those, and two agents at one configuration are one
        agent to anything reading the logs alone.

        Args:
          agent: Whose session it is.
          session: The backend's id for it, which is what a trace of the run is gathered by.
        """
        provider = _provider(agent)
        name = called(agent.id, agent.backend, provider, session)
        with self._writing:
            self._sessions[name] = (agent.backend, session)
        self.write(
            "opened",
            agent=agent.id,
            backend=agent.backend,
            provider=provider or LOCAL,
            session=session,
            name=name,
            # Where to look for it inside this cycle, which is a link and not the log itself.
            where=f"{SESSIONS}/{name}",
        )
        self.links(name)

    def links(self, only: str = "") -> None:
        """Points this cycle's `sessions/` at the logs its sessions are being written to.

        Args:
          only: One session, by the name it was written down under, or "" for every session
            this run has opened.
        """
        with self._writing:
            held = dict(self._sessions)
        for name, (backend, ident) in held.items():
            if only and name != only:
                continue
            _link(self._at / SESSIONS / name, backend, ident)

    def write(self, event: str, **said: Any) -> None:
        """Appends one line to the cycle.

        Appended and flushed apiece rather than held: a flow runs for hours and is watched
        while it does, and a run that died is a run whose cycle has to say what it got to.

        Args:
          event: What happened.
          said: What is worth saying about it.
        """
        with self._writing:
            self._at.mkdir(parents=True, exist_ok=True)
            with (self._at / JOURNAL).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "at": _now(), **said}) + "\n")


def cycles(workspace: Path | str | None = None) -> list[Path]:
    """The cycles run in one workspace, oldest first.

    Args:
      workspace: Where they ran, defaulting to this directory.

    Returns:
      One directory per cycle, which is empty where nothing has been run.
    """
    under = (
        home()
        / "cycles"
        / _PLAIN.sub("-", str(Path(workspace or Path.cwd()).resolve()))
    )
    try:
        return sorted(one for one in under.iterdir() if (one / JOURNAL).is_file())
    except OSError:
        return []


def _events(cycle: Path) -> list[dict[str, Any]]:
    """Every line one cycle holds, in the order they were written.

    Args:
      cycle: The cycle's directory, or the record inside it.

    Returns:
      One record apiece, less whatever could not be read as one: a run that died mid-line
      left a line rather than a cycle, and the rest of it is still what happened.
    """
    at = cycle / JOURNAL if cycle.is_dir() else cycle
    try:
        lines = at.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    held: list[dict[str, Any]] = []
    for line in lines:
        try:
            said = json.loads(line)
        except ValueError:
            continue
        if isinstance(said, dict):
            held.append(cast("dict[str, Any]", said))
    return held


def opened(cycle: Path) -> dict[str, list[str]]:
    """What each agent of one cycle opened, as the ids the backends gave those sessions.

    Which is what a trace is gathered by: the backends log a session under an id and never
    say whose it was, so the run has to say it instead.

    Args:
      cycle: The cycle to read.

    Returns:
      One entry per agent that opened anything, oldest session first.
    """
    held: dict[str, list[str]] = {}
    for said in _events(cycle):
        if said.get("event") == "opened" and said.get("session"):
            held.setdefault(str(said.get("agent")), []).append(str(said["session"]))
    return held


def sessions(cycle: Path) -> list[Session]:
    """Every session one cycle opened, oldest first.

    Args:
      cycle: The cycle to read.

    Returns:
      One apiece, saying whose it was, what took its turns, which account they ran as and
      what the run calls it.
    """
    held: list[Session] = []
    for said in _events(cycle):
        if said.get("event") != "opened" or not said.get("session"):
            continue
        agent, backend = str(said.get("agent") or ""), str(said.get("backend") or "")
        ident = str(said["session"])
        provider = str(said.get("provider") or LOCAL)
        held.append(
            Session(
                agent=agent,
                backend=backend,
                provider=provider,
                ident=ident,
                # Worked out where an older cycle did not write one down: a name is what this
                # session is called, and a cycle written before it had one still has sessions.
                name=str(said.get("name") or called(agent, backend, provider, ident)),
                at=str(said.get("at") or ""),
            )
        )
    return held


def read(cycle: Path) -> Ran | None:
    """What one cycle was, read back off its own record.

    Args:
      cycle: The cycle's directory.

    Returns:
      The run, or None for a directory holding nothing this wrote -- which is a directory
      somebody put there rather than a run to report.
    """
    events = _events(cycle)
    began = next((one for one in events if one.get("event") == "began"), None)
    if began is None:
        return None
    ended = next((one for one in reversed(events) if one.get("event") == "ended"), None)
    agents: list[Drove] = []
    for one in began.get("agents") or ():
        if not isinstance(one, dict):
            continue
        said = cast("dict[str, Any]", one)
        agents.append(
            Drove(
                agent=str(said.get("agent") or ""),
                backend=str(said.get("backend") or ""),
                model=str(said.get("model") or ""),
                effort=str(said.get("effort") or ""),
                permission=str(said.get("permission") or ""),
                provider=str(said.get("provider") or ""),
            )
        )
    return Ran(
        at=cycle,
        flow=str(began.get("flow") or ""),
        task=str(began.get("task") or ""),
        workspace=str(began.get("workspace") or ""),
        began=str(began.get("at") or ""),
        ended=str(ended.get("at") or "") if ended else "",
        how=str(ended.get("how") or "") if ended else "",
        agents=tuple(agents),
        sessions=tuple(sessions(cycle)),
        resumable=bool(began.get("resumable")),
    )


def where(cycle: Path, session: Session) -> Path:
    """Where one session's links are, inside the cycle that opened it.

    Args:
      cycle: The cycle's directory.
      session: The session.

    Returns:
      The directory, which is there once that session has been logged to anything.
    """
    return cycle / SESSIONS / session.name


def linked(cycle: Path) -> dict[str, list[str]]:
    """What each session of one cycle is linked to, as the paths the links point at.

    Args:
      cycle: The cycle's directory.

    Returns:
      One entry per session that has links, by the name the run gave it.
    """
    held: dict[str, list[str]] = {}
    for one in sessions(cycle):
        at = where(cycle, one)
        try:
            found = sorted(at.iterdir())
        except OSError:
            continue
        held[one.name] = [str(link.readlink()) for link in found if link.is_symlink()]
    return held
