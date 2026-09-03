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
        cycle.<flow>_<which>.jsonl      the same, for one flow the run called
        state.json                      what a flow that can be picked up again left behind
        profile.jsonl                   the programs it ran, for a run that was profiled
        sessions/<session>/…            a link per file the backend logged it to
        traces/<when>.trace.json        what was gathered of it afterwards, to be read

A flow may call another, and a called flow opens sessions and keeps state exactly as the flow
that called it does. So each call gets a record of its own beside the run's own, and the
record of whatever called it says what it called and which file to read it in. Still one run
and still one directory: a called flow is part of the run that called it, not another run.

It opens when the flow starts and closes when the flow stops, however it stops -- finished,
failed, or interrupted. A closed cycle is never reopened: running the flow again is another
run, with sessions of its own, and so another cycle -- which is what a flow that says it can
be picked up again is picked up as. What it left behind is read out of the cycle it left it
in and handed to the next run of it, which writes into a cycle of its own.
"""

from __future__ import annotations

import contextlib
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
    from .agents.event import Usage
    from .tracing.profile import Profiler

__all__ = [
    "JOURNAL",
    "LOCAL",
    "RECORD",
    "RECORDS",
    "SESSIONS",
    "STATE",
    "TRACES",
    "Called",
    "Cycle",
    "Drove",
    "Ran",
    "Session",
    "State",
    "Sub",
    "called",
    "cycles",
    "forks",
    "linked",
    "opened",
    "read",
    "records",
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

#: What the record of a flow another flow called is called, beside the run's own: which
#: flow it is of, and an id of that call rather than of the flow -- a flow called twice is
#: two records, since it is two runs of it and each opened its own sessions.
RECORD = "cycle.{flow}_{ident}.jsonl"

#: Every such record of one cycle, as a glob over its directory. It does not match the
#: run's own, which is the record of the flow nothing called.
RECORDS = "cycle.*.jsonl"

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
      flow: The flow it was opened inside, as that flow was asked for: the run's own, or one
        the run called. "" for a session written down before a run said.
    """

    agent: str
    backend: str
    provider: str
    ident: str
    name: str
    at: str = ""
    flow: str = ""


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


class Called(NamedTuple):
    """One flow a run called, as the run that called it wrote it down.

    Attributes:
      flow: The flow, as it was asked for.
      task: What it was called with.
      record: The file inside the cycle it was written to, which is where its own sessions
        are and where whatever it called in turn is written down.
      began: When it was called.
      ended: When it returned, or "" for a call that never did -- a run killed under it.
    """

    flow: str
    task: str
    record: str
    began: str = ""
    ended: str = ""


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
      sessions: Every session it opened, oldest first, the ones opened inside a flow it
        called among them -- one run is one run, however many flows it took to run it.
      called: Every flow this run called, in the order it called them. What each of those
        called in turn is written in its own record rather than here.
      resumable: Whether the flow said it could be picked up again when this run happened.
        Whether it says so now is asked of the flow: this is what the run recorded, which is
        what it was rather than what can be done with it today.
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
    called: tuple[Called, ...] = ()
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


def _record(flow: str, ident: str) -> str:
    """What the record of one called flow is called, inside the cycle that called it.

    Args:
      flow: The flow, as it was asked for -- which may be a path, and is flattened the way
        everything else humanize writes a name into a filename is.
      ident: What tells this call of it from the next one.

    Returns:
      The filename, beside the run's own record.
    """
    return RECORD.format(flow=_LEGIBLE.sub("-", flow).strip("-") or "flow", ident=ident)


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
      The cycle, or None where the flow has not run here. A run that wrote nothing at all is
      nothing to pick up and the search goes past it; a run that wrote and then emptied what
      it had written is not the same thing, and is where the search stops -- a flow that
      cleared its state said the next run starts clean, and answering that by handing it the
      state of the run before would be answering the opposite. Found by what the state holds
      rather than by what the run was of, so that a flow which was called by another is
      picked up too -- it wrote under its own name, which is where it is looked for.
    """
    for cycle in reversed(cycles(workspace)):
        if flow in _kept(cycle):
            return cycle
    return None


def _drove(agents: Sequence[AgentBase]) -> list[dict[str, Any]]:
    """What each agent of a run is, for the line a record opens with.

    Args:
      agents: The agents, in the order the flow takes them.

    Returns:
      One entry apiece, saying what it drives and at what.
    """
    from .agents import HumanAgent

    return [
        {
            "agent": agent.id,
            "backend": agent.backend,
            "model": agent.config.model,
            "effort": agent.config.effort,
            "service_tier": agent.config.service_tier,
            "permission": agent.config.permission,
            # What it was configured with rather than what a turn of it ends up running as:
            # the account a turn fell back onto is written down against the session that ran
            # there, which is where it happened.
            "provider": agent.config.provider,
            "goals": agent.config.goals,
            "web_search": agent.config.web_search,
            # Asked as the run is written down rather than read back off a name: what the
            # person's backend is called is the agents' own business, and what a run picked
            # up again needs is which of its agents nobody chose.
            "person": isinstance(agent, HumanAgent),
        }
        for agent in agents
    ]


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
        self._begin(
            home()
            / "cycles"
            / _PLAIN.sub("-", str((workspace or Path.cwd()).resolve()))
            # The moment names it and six hex say which, since two flows may be started in
            # one millisecond and neither is the other's run. To the millisecond rather than
            # to the second because these are read back in the order they sort in: which run
            # a flow is picked up from is the last of them, and two started inside one second
            # would otherwise be ordered by the hex, which is to say at random.
            / f"{_stamp()}-{uuid.uuid4().hex[:6]}",
            JOURNAL,
            (workspace or Path.cwd()).resolve(),
            flow,
            agents,
        )
        #: The programs this run starts, sampled while it runs, or None for a run nobody
        #: asked to profile -- which is every run until somebody says otherwise.
        self._profiler = self._profiling() if profile else None
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str(self._where),
            resumable=resumable,
            **({"picked_up": picked_up} if picked_up else {}),
            agents=_drove(agents),
        )

    def _begin(
        self,
        at: Path,
        journal: str,
        workspace: Path,
        flow: str,
        agents: Sequence[AgentBase],
    ) -> None:
        """Settles what is written down, and where.

        Shared with the record of a flow this one called, which is the same thing written
        into a file of its own beside this one: a called flow opens sessions and keeps state
        exactly as the flow that called it does, and neither writes the other's.

        Args:
          at: The cycle's directory.
          journal: The file inside it these lines go to.
          workspace: Where the run is happening.
          flow: The flow this is a record of, as it was named.
          agents: The agents it is being run with, in the order it takes them.
        """
        self._at = at
        self._journal = journal
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
        self._where = workspace
        self._profiler: Profiler | None = None

    @property
    def path(self) -> Path:
        """The directory this cycle is written in."""
        return self._at

    @property
    def journal(self) -> Path:
        """The file this record is written to, a line per thing that happened to it."""
        return self._at / self._journal

    @property
    def record(self) -> str:
        """What that file is called inside the cycle, which is what a call refers to."""
        return self._journal

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
        self._close(kind)
        for agent in self._agents:
            agent.cycle = None

    def _close(self, kind: type[BaseException] | None) -> None:
        """Writes down that what this is a record of has ended, and how it ended.

        Shared with the record of a flow this one called, which ends when the call returns
        rather than when the run does: a record closes once and for all either way.

        Args:
          kind: What was raised out of it, if anything.
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

    def called(
        self,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        *,
        resumable: bool = False,
    ) -> Sub:
        """Opens the record of a flow this one called, beside this one's own.

        A flow that called another is two flows, and each of them opened sessions, kept its
        own state and may have called a third. So each gets a record of its own -- one file
        per call, in the directory of the run that started it -- and this one is left saying
        what it called, when, and which file to read it in. One run, written down as the
        shape it actually ran in rather than as one flat list nothing can be attributed to.

        Args:
          flow: The flow being called, as it was asked for.
          agents: The agents it was handed, in the order it takes them.
          task: What it was called with.
          resumable: Whether it says it can be picked up again.

        Returns:
          The record, to be written to while the call runs and ended when it returns.
        """
        # Named for the flow and for this call of it: a flow called twice in one run is two
        # runs of it, each with its own sessions, and one file for both would say neither.
        record = _record(flow, uuid.uuid4().hex[:6])
        self.write("called", flow=flow, task=task, cycle=record)
        return Sub(self, record, flow, agents, task, resumable=resumable)

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

    def forked(
        self,
        agent: AgentBase,
        parent: str,
        child: str,
        last_turn_id: str | None = None,
        *,
        provider: str | None = None,
        permission: str | None = None,
        cache_equivalent: bool = True,
    ) -> None:
        """Writes down that one session branched into another, at a completed boundary.

        A fork is not an open: the child did not start from nothing, so the run records the
        parent it came from and the boundary it came off. Both ids are written for
        diagnostics, and both relation keys -- the cycle's own names for the two sessions --
        for whoever links the trace afterwards.

        Args:
          agent: Whose conversation it is, which is the same agent for both.
          parent: The parent's backend id.
          child: The child's backend id, just given by the native fork.
          last_turn_id: The completed turn the child branched from, or None for a backend
            whose fork takes no intermediate boundary.
          provider: The effective provider snapshot at the fork boundary, if already known.
          permission: The child's effective permission.
          cache_equivalent: Whether the child retains the parent's cache-equivalent settings.
        """
        account = _provider(agent) if provider is None else provider
        parent_name = called(agent.id, agent.backend, account, parent)
        child_name = called(agent.id, agent.backend, account, child)
        with self._writing:
            self._sessions[child_name] = (agent.backend, child)
        self.write(
            "forked",
            agent=agent.id,
            backend=agent.backend,
            provider=account or LOCAL,
            parent_session_id=parent,
            session_id=child,
            parent_key=parent_name,
            session_key=child_name,
            permission=permission,
            cache_equivalent=cache_equivalent,
            **({"last_turn_id": last_turn_id} if last_turn_id else {}),
        )
        self.links(child_name)

    def fork_usage(self, agent: AgentBase, session: str, usage: Usage) -> None:
        """Writes numeric usage for one completed fork child turn."""
        if not usage.total:
            return
        self.write(
            "fork-usage",
            agent=agent.id,
            backend=agent.backend,
            session_id=session,
            **dict(usage),
            total=usage.total,
        )

    def fork_failed(self, agent: AgentBase, session: str, error: str) -> None:
        """Writes a bounded diagnostic for a fork child turn that failed."""
        self.write(
            "fork-failed",
            agent=agent.id,
            backend=agent.backend,
            session_id=session,
            error=" ".join(error.split())[:400],
        )

    def fork_lost(
        self,
        agent: AgentBase,
        parent: str,
        last_turn_id: str | None = None,
        *,
        provider: str | None = None,
    ) -> None:
        """Writes down a fork whose child id was lost with the response that made it.

        A native fork that fails after the backend may already have created the child is not
        retried -- a retry would create another branch -- so the orphan is written down for a
        person to reconcile rather than left to multiply in silence.

        Args:
          agent: Whose conversation it is.
          parent: The parent's backend id, which the branch was made from.
          last_turn_id: The boundary the branch was made at, or None where the backend takes
            none.
          provider: The effective provider snapshot, or None to resolve it from the agent.
        """
        provider = _provider(agent) if provider is None else provider
        self.write(
            "fork-lost",
            agent=agent.id,
            backend=agent.backend,
            provider=provider or LOCAL,
            parent_session_id=parent,
            **({"last_turn_id": last_turn_id} if last_turn_id else {}),
        )

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
            with (self._at / self._journal).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "at": _now(), **said}) + "\n")


class Sub(Cycle):
    """One flow another flow called, written down in a record of its own.

    Everything a run writes down, a flow the run called writes down too: the sessions it
    opened, what it kept, and whatever it called in turn. What it does not have is a
    directory: it is part of the run that called it, so its record sits beside that run's own
    in the same cycle, and its sessions link into the same `sessions/`.

    It ends when the call returns rather than when the run does, and says so at both ends --
    here, and in the record of whatever called it. Closed by :meth:`ended` rather than as a
    block, since what ends a call is the flow returning and the agents are the run's own
    afterwards.
    """

    def __init__(
        self,
        under: Cycle,
        record: str,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        *,
        resumable: bool = False,
    ) -> None:
        """Opens the record, and writes down what it is a record of.

        Args:
          under: What called it, which is where the call itself is written down.
          record: What this record is called, inside the cycle they share.
          flow: The flow being called, as it was asked for.
          agents: The agents it was handed, in the order it takes them.
          task: What it was called with.
          resumable: Whether it says it can be picked up again.
        """
        self._under = under
        self._begin(under.path, record, under.workspace, flow, agents)
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str(under.workspace),
            resumable=resumable,
            # Which record called this one, so that a flow that called a flow that called a
            # flow reads back as what it was rather than as three things one run did.
            under=under.record,
            agents=_drove(agents),
        )

    def ended(self, kind: type[BaseException] | None = None) -> None:
        """Closes this record, and writes the call's other end where the call was written.

        Args:
          kind: What was raised out of the called flow, if anything.
        """
        self._close(kind)
        self._under.write("returned", flow=self._flow, cycle=self._journal)


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


def records(cycle: Path) -> list[Path]:
    """Every record one cycle holds: the run's own, and one per flow the run called.

    Args:
      cycle: The cycle's directory.

    Returns:
      The files, the run's own first and the rest by name. Not the order they were opened
      in: a name says which flow before it says which call of it, and what happened in what
      order is what the lines themselves say.
    """
    at = cycle / JOURNAL
    held = [at] if at.is_file() else []
    # A directory that went while it was being read is the records that were read, the way
    # a record that cannot be read at all is a cycle with nothing in it.
    with contextlib.suppress(OSError):
        held += sorted(one for one in cycle.glob(RECORDS) if one.is_file())
    return held


def forks(cycle: Path) -> dict[str, str]:
    """What each session one cycle branched from, child id to parent id.

    A forked child did not start from nothing, so a trace of the run draws it as the child of
    the conversation it branched from. Read across every record of the cycle, as
    :func:`opened` is, and keyed by the backend ids -- which is what a trace is gathered by.

    Args:
      cycle: The cycle to read.

    Returns:
      One entry per fork, the child's id to the parent's id. Empty for a run that forked
      nothing.
    """
    held: dict[str, str] = {}
    for at in records(cycle):
        for said in _events(at):
            if said.get("event") != "forked" or not said.get("session_id"):
                continue
            parent = said.get("parent_session_id")
            if isinstance(parent, str):
                held[str(said["session_id"])] = parent
    return held


def opened(cycle: Path) -> dict[str, list[str]]:
    """What each agent of one cycle opened, as the ids the backends gave those sessions.

    Which is what a trace is gathered by: the backends log a session under an id and never
    say whose it was, so the run has to say it instead. Every record of the cycle, since a
    session opened inside a flow the run called is one of the run's own -- what a trace of it
    is is what the whole run did.

    Args:
      cycle: The cycle to read.

    Returns:
      One entry per agent that opened anything, oldest session first.
    """
    held: dict[str, list[str]] = {}
    for one in sessions(cycle):
        held.setdefault(one.agent, []).append(one.ident)
    return held


def sessions(cycle: Path) -> list[Session]:
    """Every session one cycle opened, oldest first.

    Read across every record it holds, and each session says which flow opened it: one run
    is one run, however many flows it took to run it, and which of them a session was opened
    inside is what a record of its own is for.

    Args:
      cycle: The cycle to read.

    Returns:
      One apiece, saying whose it was, what took its turns, which account they ran as, what
      the run calls it and which flow it was opened in.
    """
    held: list[Session] = []
    for at in records(cycle):
        events = _events(at)
        flow = next(
            (
                str(one.get("flow") or "")
                for one in events
                if one.get("event") == "began"
            ),
            "",
        )
        for said in events:
            if said.get("event") == "opened" and said.get("session"):
                ident = str(said["session"])
            elif said.get("event") == "forked" and said.get("session_id"):
                # A forked child is a session the run opened, even though it did not start
                # from nothing: it is read back the same way, keyed by the id the fork gave.
                ident = str(said["session_id"])
            else:
                continue
            agent, backend = (
                str(said.get("agent") or ""),
                str(said.get("backend") or ""),
            )
            provider = str(said.get("provider") or LOCAL)
            held.append(
                Session(
                    agent=agent,
                    backend=backend,
                    provider=provider,
                    ident=ident,
                    # Worked out where an older cycle did not write one down: a name is what
                    # this session is called, and a cycle written before it had one still
                    # has sessions. A fork writes its own name, as `session_key`.
                    name=str(
                        said.get("name")
                        or said.get("session_key")
                        or called(agent, backend, provider, ident)
                    ),
                    at=str(said.get("at") or ""),
                    flow=flow,
                )
            )
    # By when each was opened rather than by which record it is in: the records are one run,
    # and a run happened in one order.
    return sorted(held, key=lambda one: one.at)


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
        called=tuple(_calls(events)),
        resumable=bool(began.get("resumable")),
    )


def _calls(events: Sequence[dict[str, Any]]) -> list[Called]:
    """Every flow one record says it called, in the order it called them.

    Paired by the record each call was written to rather than by the order the lines are in:
    a flow written as a coroutine may have two calls going at once, and their two ends
    interleave. A run written before calls had records of their own says only which flow, and
    is paired by taking a return for the last call of that flow still open -- which is what
    nesting is, and the best a record that says no more can be read as.

    Args:
      events: The lines of one record.

    Returns:
      One apiece. A call with no end is a call that never returned -- a run killed under it
      -- and is one of them all the same.
    """
    held: list[Called] = []
    where: dict[str, int] = {}
    for said in events:
        record, flow = str(said.get("cycle") or ""), str(said.get("flow") or "")
        if said.get("event") == "called":
            # Kept by the record and not by the flow: one flow called twice is two calls,
            # and each wrote to a file of its own.
            where[record] = len(held)
            held.append(
                Called(
                    flow=flow,
                    task=str(said.get("task") or ""),
                    record=record,
                    began=str(said.get("at") or ""),
                )
            )
        elif said.get("event") == "returned":
            at = (
                where.get(record)
                if record
                else next(
                    (
                        which
                        for which, one in reversed(list(enumerate(held)))
                        if one.flow == flow and not one.ended
                    ),
                    None,
                )
            )
            if at is not None:
                held[at] = held[at]._replace(ended=str(said.get("at") or ""))
    return held


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
