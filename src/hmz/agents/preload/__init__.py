"""What a turn did, read from inside the runtime the CLI is running on.

Four of the CLIs driven here are Node programs -- kimi, qwen, mimo and pi -- and Node reads
`NODE_OPTIONS` before it reads the program. So a file of ours can be in the process before the
CLI has run a line, and from in there the calls a turn actually makes are ordinary functions to
patch: the processes it spawns, the files it reads and writes, the connections it opens. That
file is `runtime.cjs` beside this module, and this is the other end of it -- the socket it
reports on, and what those reports become here.

Which is near-syscall fidelity without a supervisor, and only where a runtime will have it: a
CLI shipped as a compiled binary -- claude and opencode are Bun executables, codex and grok are
native, agy is a compiled Deno -- has no Node to load anything into.
:attr:`hmz.backends.Profile.preloads` is where it is written down which CLIs take a preload and
through which variable, and `anchor:preloaded` is the name a flow asks for it under. Four
backends of twelve is the honest ceiling, which is why this supplements the hooks a CLI offers
rather than replacing them.

What is watched is the CLI rather than the process it started in, and rather than everything
under the turn. `NODE_OPTIONS` is inherited by every process a CLI spawns, and neither end of
that is what is wanted: every Node program under a turn reporting its own reads as the agent's
work is noise, and a layer that stopped at the first process would watch a launcher -- qwen's
entry point starts a second `node` on its own bundle and takes the whole turn there. So the
preload passes down the name of the package the program it was loaded for belongs to, and a
process belonging to some other package strips the variables, reports nothing and hands nothing
on. The package rather than the directory because a CLI re-execs itself to wherever its own
updater put its newest copy, which is a different path and the same program. One consequence is
measured and worth knowing: mimocode's entry point starts a native binary, so what is watched
there is the launcher and the spawn of the binary, and nothing inside it.

Two more things worth knowing before hanging a hook. The question is asked where a CLI's process
is started, so a hook hung later is picked up on the next turn -- except on kimi, whose one
daemon is started once and holds every session of the agent, so a hook hung after that gets
nothing from it. And a report reaches a hook on the thread reading the socket rather than on the
thread taking the turn, as a watcher's events do: a hook that touches what the flow is touching
answers for that itself.

What the reports become is the agent's own moments: one :class:`~hmz.agents.hooks.Occasion` at
`PreToolUse` per thing observed, named `spawn`, `read`, `write` or `connect` after what the
runtime did rather than after any tool the CLI has -- so a flow that wants only these hangs its
hook with `tool="spawn"`, and one hung on a tool of the CLI's own never sees them. They are
told rather than asked: this layer is behind the call it is reporting, so a hook that refuses
one would be refusing something that has already happened, and nothing here acts on a verdict.
A flow that means to *stop* an agent doing something hangs its hook where the CLI asks first.

Nothing is started unless somebody is listening, for the reason a toolbox with no callbacks in
it has no socket: an agent with nothing hung on `PreToolUse` is an agent whose turns are the
turns they always were, with no socket, no thread and no patched runtime.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import tempfile
import threading
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.agents.base import AgentBase
    from hmz.agents.hooks import Hooks

__all__ = ["RUNTIME", "Watch", "preloaded", "reported", "runtime"]

#: The file the runtime is told to load, beside this module and shipped with it.
RUNTIME = "runtime.cjs"

#: What the runtime is told through: the variable Node takes a preload in, and the one saying
#: where to report. The first is written down as a fact about each backend in
#: :mod:`hmz.backends`; this is where the layer that uses it spells its own.
_OPTIONS = "NODE_OPTIONS"
_AT = "HMZ_PRELOAD_AT"

#: How long a socket nothing has connected to is waited on before the thread serving it looks
#: again at whether it has been closed, so that closing one needs no poke to wake it.
_LOOKING = 0.2

#: How many runtimes may be connecting at once before one of them is refused. A fleet of
#: sessions is a process apiece and every one of them connects as it starts, and a runtime
#: refused here is a turn nothing was observed of -- which is cheaper to avoid than to notice.
_WAITING = 64

#: The longest line a runtime's report may be before it is read as two. The preload writes
#: nothing near this, so an ordinary report is never split; what this is for is the runtime
#: that writes something enormous with no newline in it, which would otherwise be held whole
#: in this process's memory. Split, neither half reads as a report and both are dropped.
_LONGEST = 1 << 16


def runtime() -> str:
    """Where the file a CLI's runtime is told to load is, as this installation ships it.

    Read out of the package rather than built from `__file__`, which is what makes it the same
    answer wherever hmz was installed from.

    Returns:
      The path, resolved: Node names a module it required by that module's real path, and the
      preload takes itself back out of `NODE_OPTIONS` by the name it was given under.
    """
    import importlib.resources

    found = importlib.resources.files("hmz.agents.preload").joinpath(RUNTIME)
    return str(Path(str(found)).resolve())


def preloaded(agent: AgentBase, added: Mapping[str, str]) -> dict[str, str]:
    """What a turn of this agent runs with, plus the preload wherever one is wanted.

    Called by the drivers of the backends whose runtime takes one, on top of whatever else each
    of them is setting: the variables are composed here rather than in four places, and
    `NODE_OPTIONS` is added to rather than replaced -- a `--max-old-space-size` the person who
    started the flow exported is theirs, and this goes on the end of it. Nothing takes it away
    again: what a turn under a provider is run without is that backend's account variables, and
    this is not one of them.

    Nothing at all is added where nothing is listening, where the turn lands on another machine
    -- the socket and the file are paths on this one, which name nothing over there -- or where
    the socket could not be made, which is a machine with none to spare rather than a turn that
    must not run.

    Args:
      agent: Whose turn it is, which is what the reports are told about and what says whether
        anybody is listening for them.
      added: What the driver is already setting, which is passed through whatever happens here.

    Returns:
      Those variables, plus the preload and the socket to report on where one was started.
    """
    from hmz.agents.hooks import Moment

    held = dict(added)
    if agent.anchor is not None or not agent.hooks.hooked(Moment.PRE_TOOL_USE):
        return held
    at = _watching(agent).address()
    if not at:
        return held
    held[_OPTIONS] = _requiring(held.get(_OPTIONS) or os.environ.get(_OPTIONS) or "")
    held[_AT] = at
    return held


def _requiring(options: str) -> str:
    """One `NODE_OPTIONS` with the preload on the end of whatever was already in it.

    Args:
      options: What was there, which is the provider's own where it set one and this process's
        otherwise.

    Returns:
      The variable to run the turn with. The path is quoted where it has whitespace in it,
      which is the one thing Node's own reading of this variable needs told.
    """
    file = runtime()
    said = (
        f'--require "{file}"' if any(c.isspace() for c in file) else f"--require {file}"
    )
    return f"{options} {said}".strip()


def reported(line: str) -> tuple[str, str] | None:
    """What one line a runtime wrote says its process did.

    Written as a function of the line so that what the runtime says is one thing to read and
    one thing to test, whatever carried it.

    Args:
      line: The report, as JSON: what the runtime did, and what it did it to.

    Returns:
      What it did -- `spawn`, `read`, `write`, `connect`, or `quiet` for a process that has
      said all it is going to -- and what it did it to. None for a line that is not a report at
      all, which is a runtime writing something nothing here can read rather than a failure.
    """
    try:
        held: object = json.loads(line)
    except ValueError:
        return None
    if not isinstance(held, dict):
        return None
    said = cast("dict[str, Any]", held)
    did, what = said.get("did"), said.get("what")
    if not isinstance(did, str) or not did:
        return None
    return did, what if isinstance(what, str) else ""


#: The listener each agent has, for as long as it has one. Weak, and one apiece: a report comes
#: off a process, and some of these backends run one process for every conversation an agent
#: holds, so the agent is what a report can be said to have happened to.
_WATCHED: weakref.WeakKeyDictionary[AgentBase, Watch] = weakref.WeakKeyDictionary()
_WATCHING = threading.Lock()


def _watching(agent: AgentBase) -> Watch:
    """The listener this agent's turns report to, made the first time one is asked for.

    Args:
      agent: Whose turns they are.

    Returns:
      It. Whether it is serving anything is :meth:`Watch.address`'s to say.
    """
    with _WATCHING:
        watch = _WATCHED.get(agent)
        if watch is None:
            watch = Watch(agent.hooks)
            # Held by the finalizer alone, which is what takes the socket and its thread away:
            # when the agent is collected, and at exit for one held to the end.
            weakref.finalize(agent, watch.close)
            _WATCHED[agent] = watch
        return watch


class Watch:
    """The socket one agent's preloaded runtimes report on, and what their reports become.

    One per agent rather than one per session, for the reason an agent's hooks are its own: a
    hook is hung on an agent, and what is reported here is a process rather than a conversation
    -- a backend that holds every session of an agent open in one server has one runtime for
    all of them, and nothing in it says which conversation a `spawn` belonged to.
    """

    def __init__(self, hooks: Hooks) -> None:
        """Initializes a listener that is not serving anything yet.

        Args:
          hooks: What is hung on the agent's moments, which is where a report goes and what
            says which agent it happened to.
        """
        self._hooks = hooks
        self._lock = threading.Lock()
        self._at = ""
        self._sock: socket.socket | None = None
        self._where: tempfile.TemporaryDirectory[str] | None = None
        self._closed = threading.Event()

    def address(self) -> str:
        """Where a runtime reports to, starting the listener if nothing has yet.

        Returns:
          The path of the socket, which is under a directory of its own so that nothing else on
          the machine can name it -- or "" where one could not be made at all, a machine with
          no socket to spare being a turn run unwatched rather than a turn that does not run.
        """
        with self._lock:
            if self._sock is not None:
                return self._at
            # A listener started again after it was closed is an agent that went on taking
            # turns: the thread that is looking would otherwise see the old answer and stop
            # before it had read anything.
            self._closed.clear()
            try:
                self._where = tempfile.TemporaryDirectory(
                    prefix="humanize-preload-", ignore_cleanup_errors=True
                )
                # Inside a directory this user alone may enter: what is said on this socket is
                # every file the agent touched, and one anybody could connect to is a way for
                # anybody to watch somebody else's work.
                where = Path(self._where.name)
                where.chmod(0o700)
                self._at = str(where / "said.sock")
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._sock.bind(self._at)
                self._sock.listen(_WAITING)
                self._sock.settimeout(_LOOKING)
            except OSError:
                self._closed.set()
                self._shut()
                return ""
            threading.Thread(
                target=self._accepts, name="humanize-preload", daemon=True
            ).start()
            return self._at

    def close(self) -> None:
        """Stops listening, and takes the socket away. Doing it twice does it once."""
        self._closed.set()
        with self._lock:
            self._shut()

    def _shut(self) -> None:
        """Drops the socket and the directory holding it, with this listener's lock held."""
        sock, self._sock = self._sock, None
        where, self._where = self._where, None
        self._at = ""
        if sock is not None:
            sock.close()
        if where is not None:
            where.cleanup()

    def _accepts(self) -> None:
        """Reads each runtime that connects, on a thread of its own, until this is closed.

        A thread apiece because a runtime stays connected for as long as its process lives, and
        an agent may have several of those at once -- a fleet of sessions, each one a turn.
        """
        while not self._closed.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                held, _from = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return  # closed under us, which is what closing does
            threading.Thread(
                target=self._reads, args=(held,), name="humanize-preloaded", daemon=True
            ).start()

    def _reads(self, held: socket.socket) -> None:
        """Reads what one runtime says, a line at a time, until its process is gone.

        A line at a time and no more than :data:`_LONGEST` of one: what is at the other end is
        another program's output, and a program that writes without ever writing a newline must
        not be a program that fills this one's memory.

        Args:
          held: The connection.
        """
        with held, held.makefile("rb") as stream:
            while (line := stream.readline(_LONGEST)) != b"":
                self.tells(line.decode("utf-8", "replace"))

    def tells(self, line: str) -> None:
        """Tells the agent's hooks what one line a runtime wrote says its process did.

        Args:
          line: The report, as the runtime wrote it. One that says nothing readable is
            dropped: a runtime is another program's, and what comes off it is read rather
            than trusted.
        """
        from hmz.agents.hooks import Moment, Occasion

        said = reported(line)
        if said is None:
            return
        did, what = said
        # A hook is the flow's own code, and one that raises has said nothing -- including the
        # stop `fire` lets through, which has nowhere to go on a thread of this one's: there is
        # no turn here to end, the turn being in another process entirely.
        with contextlib.suppress(Exception):
            self._hooks.fire(
                Occasion(
                    moment=Moment.PRE_TOOL_USE,
                    agent=self._hooks.agent,
                    tool=did,
                    about=what,
                )
            )
