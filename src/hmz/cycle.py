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
        state.json                      what a flow that can be picked up again left behind
        profile.jsonl                   the programs it ran, for a run that was profiled
        sessions/<session>/…            a link per file the backend logged it to
        traces/<when>.trace.json        what was gathered of it afterwards, to be read

It opens when the flow starts and closes when the flow stops, however it stops -- finished,
failed, or interrupted. A closed cycle is never reopened: running the flow again is another
run, with sessions of its own, and so another cycle -- which is what a flow that says it can
be picked up again is picked up as. What it left behind is read out of the cycle it left it
in and handed to the next run of it, which writes into a cycle of its own.
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
    from collections.abc import Mapping, Sequence

    from .agents import AgentBase
    from .tracing.profile import Profiler

__all__ = [
    "JOURNAL",
    "LOCAL",
    "SESSIONS",
    "STATE",
    "TRACES",
    "Cycle",
    "Drove",
    "Ran",
    "Session",
    "State",
    "called",
    "cycles",
    "linked",
    "opened",
    "read",
    "resumed",
    "sessions",
    "state",
    "under",
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

#: What a resumable flow left behind, kept beside the run it left it in.
STATE = "state.json"

#: Where the traces gathered of one run go, inside that run's own directory. A trace of a run
#: belongs with the run: the sessions it points at and the state it left are already there.
TRACES = "traces"

#: What a session opened as the account this machine is already signed into is written under.
#: A word rather than the empty string it is configured as: this goes in a directory name and
#: in a listing, and both of those read better saying which account than saying nothing.
LOCAL = "local"


def _now() -> str:
    """This moment, as every file humanize writes spells one."""
    return (
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )


def _stamp() -> str:
    """This moment, as a name that sorts the way the moments do: to the millisecond."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S.%f")[:-3] + "Z"


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
      goals: Whether it was allowed to run under its backend's own goal feature.
      person: Whether it was the person at the prompt, who is handed to a flow rather than
        chosen -- so a run picked up again is picked up on the agents somebody chose, and
        the person is handed over afresh by whatever is doing the picking up.
    """

    agent: str
    backend: str
    model: str
    effort: str
    permission: str = ""
    provider: str = ""
    goals: bool = True
    person: bool = False

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


class State(dict[str, Any]):
    """What a resumable flow left behind, and what it is writing now.

    A dict as far as the flow is concerned -- it is handed one, it writes into it, and the
    next run of that flow is handed what it wrote. What it also is is a file in the cycle,
    written as the flow writes: a flow worth picking up again is one that was stopped or
    killed rather than one that ended tidily, and state saved only at the end is state a
    stopped run does not have. Something written inside a value it holds -- a list appended
    to, a dict of its own written into -- is a change no mapping can see, and is saved when
    the run ends or when the flow says :meth:`save`.
    """

    def __init__(
        self, at: Path, flow: str, held: Mapping[str, Any] | None = None
    ) -> None:
        """Holds what one flow left behind, against the cycle it is being written into.

        Args:
          at: The cycle's directory.
          flow: Whose state this is, since a flow that called another is two flows and each
            has its own to keep.
          held: What was read back, or nothing for a run that is picking nothing up.
        """
        super().__init__(held or {})
        self._at = at
        self._flow = flow
        self._writing = threading.Lock()

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self.save()

    def update(self, *said: Any, **and_so: Any) -> None:
        super().update(*said, **and_so)
        self.save()

    def setdefault(self, key: str, default: Any = None) -> Any:
        held = super().setdefault(key, default)
        self.save()
        return held

    def pop(self, *said: Any) -> Any:
        held = super().pop(*said)
        self.save()
        return held

    def popitem(self) -> tuple[str, Any]:
        held = super().popitem()
        self.save()
        return held

    def clear(self) -> None:
        super().clear()
        self.save()

    def save(self) -> None:
        """Writes what this flow is holding into the cycle, beside what the others hold.

        Read again and merged rather than dumped over, for the reason the settings are: a
        flow that called another is two flows writing one file, and a plain dump would put
        back a file missing whatever the other had written. Whole and then moved into place,
        so that one read while it is being written is the old one or the new one.

        Anything that cannot be written -- a value no JSON has a shape for, a directory that
        has gone -- leaves the run as it was: state is what a flow may pick up, and a run
        that stopped because it could not save it would be worse than one that cannot.
        """
        with self._writing:
            held = _kept(self._at)
            held[self._flow] = dict(self)
            try:
                self._at.mkdir(parents=True, exist_ok=True)
                said = json.dumps(held, ensure_ascii=False, default=str)
                beside = self._at / f".{STATE}.new"
                beside.write_text(said, encoding="utf-8")
                beside.replace(self._at / STATE)
            except (OSError, TypeError, ValueError):
                return


def _kept(cycle: Path) -> dict[str, Any]:
    """What every flow of one cycle left behind, by the name each was run as.

    Args:
      cycle: The cycle's directory.

    Returns:
      One entry per flow that wrote anything, and nothing at all for a cycle that holds no
      state, holds one nothing can read, or holds one written by hand as something else.
    """
    try:
        said = json.loads((cycle / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(said, dict):
        return {}
    return {
        str(flow): cast("dict[str, Any]", one)
        for flow, one in cast("dict[str, Any]", said).items()
        if isinstance(one, dict)
    }


def state(cycle: Path, flow: str = "") -> dict[str, Any]:
    """What a resumable flow left behind in one cycle.

    Args:
      cycle: The cycle's directory.
      flow: Which flow's, as it was named when it ran, or "" for the one the cycle is a run
        of -- which is the flow somebody picking the cycle up is picking up.

    Returns:
      What it wrote, and nothing at all where that flow wrote nothing.
    """
    held = _kept(cycle)
    if flow:
        return held.get(flow, {})
    ran = read(cycle)
    return held.get(ran.flow, {}) if ran is not None else {}


def resumed(flow: str, workspace: Path | str | None = None) -> Path | None:
    """The cycle one flow's next run picks up from, which is the last run of it here.

    Args:
      flow: The flow, as it is named when it is run.
      workspace: Where it runs, defaulting to this directory.

    Returns:
      The cycle, or None where the flow has not run here or left nothing behind. A run that
      wrote nothing is nothing to pick up: what it would be picked up as is the state a run
      before it left, which is the run that has something to say. Found by what the state
      holds rather than by what the run was of, so that a flow which was called by another
      is picked up too -- it wrote under its own name, which is where it is looked for.
    """
    for cycle in reversed(cycles(workspace)):
        if _kept(cycle).get(flow):
            return cycle
    return None


class Cycle:
    """One run of one flow: the directory it is written to, and what has happened to it."""

    def __init__(
        self,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        workspace: Path | None = None,
        *,
        resumable: bool = False,
        picked_up: str = "",
        profile: bool = False,
    ) -> None:
        """Opens a cycle, and writes down what it is a run of.

        Args:
          flow: The flow being run, as it was named.
          agents: The agents it is being run with, in the order it takes them.
          task: What they were asked to do.
          workspace: Where the run happens, defaulting to this directory. Cycles are kept
            under the workspace they ran in, since that is what anyone looking for one has.
          resumable: Whether the flow says it can be picked up again, which is what makes
            the state it leaves behind something to run it on rather than something to read.
          picked_up: The cycle this run was picked up from, by name, or "" for one starting
            from nothing.
          profile: Whether to sample the programs the agents start while the run goes, so
            that what a turn spent its minutes on is in the run's trace beside the turn. A
            setting of the workspace, asked of it by whoever opens the cycle.
        """
        from .agents import HumanAgent

        self._at = (
            home()
            / "cycles"
            / _PLAIN.sub("-", str((workspace or Path.cwd()).resolve()))
            # The moment names it and six hex say which, since two flows may be started in
            # one millisecond and neither is the other's run. To the millisecond rather than
            # to the second because these are read back in the order they sort in: which run
            # a flow is picked up from is the last of them, and two started inside one second
            # would otherwise be ordered by the hex, which is to say at random.
            / f"{_stamp()}-{uuid.uuid4().hex[:6]}"
        )
        self._writing = (
            threading.Lock()
        )  # sessions open on whichever thread a turn runs on
        self._agents = list(agents)
        #: Every session this run has opened, by the name it was written down under, so that
        #: the links can be made again as the backends go on writing to them.
        self._sessions: dict[str, tuple[str, str]] = {}
        #: What each resumable flow of this run is holding, so that a value written inside
        #: one -- which no mapping can see -- is still saved when the run ends.
        self._state: list[State] = []
        self._flow = flow
        self._where = (workspace or Path.cwd()).resolve()
        #: The programs this run starts, sampled while it runs, or None for a run nobody
        #: asked to profile -- which is every run until somebody says otherwise.
        self._profiler = self._profiling() if profile else None
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str((workspace or Path.cwd()).resolve()),
            resumable=resumable,
            **({"picked_up": picked_up} if picked_up else {}),
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
                    "goals": agent.config.goals,
                    # Asked as the run is written down rather than read back off a name:
                    # what the person's backend is called is the agents' own business, and
                    # what a run picked up again needs is which of its agents nobody chose.
                    "person": isinstance(agent, HumanAgent),
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

    @property
    def workspace(self) -> Path:
        """Where this run is happening, which is what its cycles are kept under."""
        return self._where

    def _profiling(self) -> Profiler | None:
        """The sampler this run is profiled by, started, or None where there is none.

        Nothing here MUST be able to stop a run: a machine whose processes cannot be read is
        a run with no profile rather than a run that will not start.

        Returns:
          The profiler, already running.
        """
        try:
            from .tracing.profile import PROFILE, Profiler
        except (
            ImportError
        ):  # pragma: no cover -- an install missing what it was built with
            return None
        one = Profiler(self._at / PROFILE)
        try:
            one.start()
        except (OSError, RuntimeError):
            return None
        return one

    def state(self, flow: str = "", held: Mapping[str, Any] | None = None) -> State:
        """The dict a resumable flow of this run writes what it wants back into.

        Args:
          flow: Whose it is, as that flow was named, or "" for the flow this is a run of.
            A flow that called another is two flows, and each keeps its own.
          held: What it is picking up, or nothing for a run starting from nothing.

        Returns:
          The state, saved into this cycle as the flow writes it.
        """
        one = State(self._at, flow or self._flow, held)
        with self._writing:
            self._state.append(one)
        return one

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

        # The sampler first, so that what it saw is written down before anything reads it,
        # and so that a run which is over stops costing anything.
        if self._profiler is not None:
            self._profiler.stop()
        # The links again, now that the run is over: a backend writes a session's log while
        # the session runs and finishes writing it after the last turn, and a sub-agent's
        # transcript appears whenever that sub-agent was started.
        self.links()
        # And what each flow of this run is holding, which is where a value written inside
        # something the state holds -- a list appended to -- is finally written down.
        for one in list(self._state):
            one.save()
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


def under(workspace: Path | str | None = None) -> Path:
    """Where the runs of one workspace are kept.

    Args:
      workspace: Which workspace, defaulting to this directory.

    Returns:
      The directory. It may not exist: a workspace nothing has been run in has none, and
      whatever writes there is what makes it.
    """
    return (
        home()
        / "cycles"
        / _PLAIN.sub("-", str(Path(workspace or Path.cwd()).resolve()))
    )


def cycles(workspace: Path | str | None = None) -> list[Path]:
    """The cycles run in one workspace, oldest first.

    Args:
      workspace: Where they ran, defaulting to this directory.

    Returns:
      One directory per cycle, which is empty where nothing has been run.
    """
    try:
        return sorted(
            one for one in under(workspace).iterdir() if (one / JOURNAL).is_file()
        )
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
                goals=bool(said.get("goals", True)),
                person=bool(said.get("person")),
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
