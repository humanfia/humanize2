"""The ptrace event loop that keeps the agent honest about where it is running.

The supervisor forks the agent under a seccomp filter, then services the stops
that filter produces.  Its one hard rule is that the loop must never block:
filesystem calls to the target are fast and the tracee is stopped anyway, but a
remote *command* may run for minutes, so it is handed to
:class:`~humanize.coganchor.execproxy.ExecProxy` and the tracee is left waiting as a
stand-in (see :mod:`humanize.coganchor.standin`) until the completion arrives.

The loop therefore waits on two things at once -- child state changes and
finished remote work -- using ``signal.set_wakeup_fd`` to make ``SIGCHLD``
selectable alongside a completion pipe.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import queue
import select
import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from humanize.coganchor import standin
from humanize.coganchor.execproxy import ExecProxy, ExecResult
from humanize.coganchor.handlers import STALL, Action, SyscallDispatcher
from humanize.coganchor.linux import procfs, ptrace, seccomp
from humanize.coganchor.linux.syscalls import NR, TRAPPED_SYSCALLS, syscall_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from humanize.coganchor.linux.ptrace import Registers
    from humanize.coganchor.netproxy import NetProxy
    from humanize.coganchor.policy import Router
    from humanize.coganchor.remote import RemoteClient
    from humanize.coganchor.shadow import ShadowTree

__all__ = ["Launch", "Supervisor", "Tracee"]

log = logging.getLogger(__name__)

#: How long the loop sleeps before re-checking stalled tracees for signals.
_IDLE_SECONDS = 0.2

#: Signals an agent uses to cancel a command; relayed to the remote process.
_CANCEL_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGHUP)

#: Signals whose default action terminates, so they can be replayed onto the
#: stand-in process instead of being flattened into an exit code.
_FATAL_SIGNALS = frozenset(
    {
        signal.SIGHUP,
        signal.SIGINT,
        signal.SIGQUIT,
        signal.SIGILL,
        signal.SIGABRT,
        signal.SIGFPE,
        signal.SIGKILL,
        signal.SIGSEGV,
        signal.SIGPIPE,
        signal.SIGALRM,
        signal.SIGTERM,
        signal.SIGBUS,
        signal.SIGXCPU,
        signal.SIGXFSZ,
    }
)


@dataclass(slots=True)
class Launch:
    """The agent invocation coganchor is wrapping."""

    program: str
    argv: list[str]
    env: dict[str, str]
    cwd: str


@dataclass(slots=True)
class Tracee:
    """Per-process state for one traced task."""

    pid: int
    attached: bool = False
    exec_count: int = 0
    #: Set while this process stands in for a command running on the target.
    proxy: ExecProxy | None = None
    #: Errno to plant at the next syscall-exit stop, for a cancelled syscall.
    pending_errno: int | None = None


class Supervisor:
    """Runs the agent under interception and returns its exit status."""

    def __init__(
        self,
        client: RemoteClient,
        router: Router,
        shadow: ShadowTree,
        launch: Launch,
        *,
        netproxy: NetProxy | None = None,
        token: str | None = None,
        private: Iterable[str] = (),
    ) -> None:
        self.client = client
        self.router = router
        self.shadow = shadow
        self.netproxy = netproxy
        #: What the agent was given that the target is not to be given: the credentials it
        #: reaches its own model provider with. Everything else it exports is inherited by
        #: every command it runs there, which is what makes these worth naming.
        self.private = frozenset(private)
        self._launch = launch
        self._token = token
        self._dispatcher = SyscallDispatcher(self)
        self._tracees: dict[int, Tracee] = {}
        self._completions: queue.SimpleQueue[tuple[int, ExecResult]] = (
            queue.SimpleQueue()
        )
        self._wake_read = -1
        self._wake_write = -1
        self._signal_read = -1
        self._signal_write = -1
        self._root_pid = 0
        self._exit_status = 1

    # --------------------------------------------------------------- lifecycle

    def run(self) -> int:
        """Launch the agent, service its syscalls, and return its exit code."""
        self._open_wakeup_pipes()
        try:
            self._root_pid = self._fork_tracee()
            self._await_initial_stop()
            # The tracee is parked at SIGSTOP, so it is safe to start threads
            # now; forking a multi-threaded process is not.
            try:
                self.client.start(self._token)
            except BaseException:
                # The agent exists but is not yet traced, so letting it run
                # would leave it seccomp-filtered with nobody servicing the
                # traps -- every execve would fail ENOSYS and report a second,
                # baffling error on top of the real one.
                os.kill(self._root_pid, signal.SIGKILL)
                raise
            log.info(
                "connected to the target %s", self.client.info.get("hostname", "?")
            )
            ptrace.setoptions(self._root_pid)
            self._tracees[self._root_pid] = Tracee(self._root_pid, attached=True)
            ptrace.cont(self._root_pid)
            self._loop()
        finally:
            self._flush_final()
            self._teardown()
        return self._exit_status

    def _flush_final(self) -> None:
        """Push anything written after the last remote command.

        Flushing normally happens just before a command runs on the target.
        A session that ends with an edit -- the common case for a one-shot
        agent run -- would otherwise leave those bytes only on this machine.
        """
        try:
            pushed = self.shadow.flush()
        except OSError:
            log.exception("could not push final changes to the target")
        else:
            if pushed:
                log.info("pushed %d file(s) to the target at exit", pushed)

    def _open_wakeup_pipes(self) -> None:
        self._wake_read, self._wake_write = os.pipe()
        self._signal_read, self._signal_write = os.pipe()
        for fd in (
            self._wake_read,
            self._wake_write,
            self._signal_read,
            self._signal_write,
        ):
            os.set_blocking(fd, False)
        # A Python-level handler (rather than SIG_IGN) is required for
        # set_wakeup_fd to fire, and handlers reset to default across execve so
        # the agent keeps its own signal behaviour.
        signal.signal(signal.SIGCHLD, _ignore)
        signal.signal(signal.SIGINT, _ignore)
        signal.set_wakeup_fd(self._signal_write, warn_on_full_buffer=False)

    def _teardown(self) -> None:
        signal.set_wakeup_fd(-1)
        for tracee in self._tracees.values():
            if tracee.proxy is not None:
                tracee.proxy.abandon()
        for fd in (
            self._wake_read,
            self._wake_write,
            self._signal_read,
            self._signal_write,
        ):
            if fd >= 0:
                with contextlib.suppress(OSError):
                    os.close(fd)

    # ------------------------------------------------------------------- start

    def _fork_tracee(self) -> int:
        """Fork the agent under ``PTRACE_TRACEME`` and a seccomp filter.

        Must run while this process is single-threaded: everything between
        ``fork`` and ``execve`` shares the parent's memory, and a lock held by
        another thread at fork time would never be released here.
        """
        launch = self._launch
        pid = os.fork()
        if pid:
            return pid
        try:
            os.chdir(launch.cwd)
            ptrace.traceme()
            seccomp.install(TRAPPED_SYSCALLS)
            os.kill(os.getpid(), signal.SIGSTOP)
            # Becoming the traced program is the whole errand of this fork, and it is an
            # argv rather than a command line, so there is no shell for one to go through.
            os.execve(launch.program, launch.argv, launch.env)  # noqa: S606
        # Everything, deliberately: this is the forked child, and anything that escapes here
        # would run the parent's code a second time rather than report a failed launch.
        except BaseException as exc:  # noqa: BLE001
            os.write(2, f"hmz: cannot launch {launch.program}: {exc}\n".encode())
        os._exit(127)

    def _await_initial_stop(self) -> None:
        _, status = os.waitpid(self._root_pid, 0)
        if not os.WIFSTOPPED(status):
            raise RuntimeError(
                f"agent exited before it could be traced (status {status})"
            )

    # -------------------------------------------------------------- event loop

    def _loop(self) -> None:
        while self._root_pid in self._tracees:
            self._drain_completions()
            if self._reap_one():
                continue
            self._wait_for_events()

    def _wait_for_events(self) -> None:
        """Sleep until a child changes state or remote work finishes."""
        try:
            readable, _, _ = select.select(
                [self._signal_read, self._wake_read], [], [], _IDLE_SECONDS
            )
        except InterruptedError:  # pragma: no cover - retried by the loop
            return
        for fd in readable:
            _drain(fd)
        if not readable:
            self._relay_pending_signals()

    def _reap_one(self) -> bool:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG | ptrace.WALL)
        except ChildProcessError:
            self._tracees.clear()
            return False
        if pid == 0:
            return False
        self._on_status(pid, status)
        return True

    def _on_status(self, pid: int, status: int) -> None:
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            self._on_death(pid, status)
            return
        tracee = self._tracees.get(pid)
        if tracee is None:
            # A new child reported before its parent's fork event; adopt it.
            tracee = self._tracees.setdefault(pid, Tracee(pid))
        if not tracee.attached:
            tracee.attached = True
            _try(ptrace.setoptions, pid)
            _try(ptrace.cont, pid)
            return
        self._on_stop(tracee, status)

    def _on_death(self, pid: int, status: int) -> None:
        tracee = self._tracees.pop(pid, None)
        if tracee is not None and tracee.proxy is not None:
            tracee.proxy.abandon()
        if pid == self._root_pid:
            self._exit_status = (
                os.WEXITSTATUS(status)
                if os.WIFEXITED(status)
                else 128 + os.WTERMSIG(status)
            )
            log.debug("agent exited with status %d", self._exit_status)

    def _on_stop(self, tracee: Tracee, status: int) -> None:
        stop_signal = os.WSTOPSIG(status)
        event = status >> 16
        if event == ptrace.EVENT_SECCOMP:
            self._on_seccomp(tracee)
        elif event in (ptrace.EVENT_FORK, ptrace.EVENT_VFORK, ptrace.EVENT_CLONE):
            self._adopt_child(tracee)
            _try(ptrace.cont, tracee.pid)
        elif event != 0:
            _try(ptrace.cont, tracee.pid)
        elif stop_signal == (signal.SIGTRAP | ptrace.SYSCALL_STOP_SIG):
            self._finish_cancelled_syscall(tracee)
        elif stop_signal == signal.SIGTRAP:
            _try(ptrace.cont, tracee.pid)
        else:
            self._on_signal(tracee, stop_signal)

    def _adopt_child(self, parent: Tracee) -> None:
        try:
            child = ptrace.get_event_message(parent.pid)
        except OSError:
            return
        self._tracees.setdefault(int(child), Tracee(int(child)))

    def _on_signal(self, tracee: Tracee, stop_signal: int) -> None:
        """Pass a signal through to the tracee that was meant to receive it.

        A process standing in for a remote command is parked in a seccomp stop
        and never reports signals here; those are picked up from its pending
        mask instead, by :meth:`_relay_pending_signals`.
        """
        _try(ptrace.cont, tracee.pid, stop_signal)

    # ------------------------------------------------------------ syscall stops

    def _on_seccomp(self, tracee: Tracee) -> None:
        try:
            registers = ptrace.getregs(tracee.pid)
        except OSError:
            return
        number = registers.syscall_number
        action = self._dispatcher.dispatch(tracee, registers)
        if action is STALL:
            return
        if action.kind == "errno":
            log.debug(
                "pid %d: %s -> %s",
                tracee.pid,
                syscall_name(number),
                errno.errorcode.get(action.errno, action.errno),
            )
            self._cancel_syscall(tracee, registers, action)
            return
        if registers.dirty:
            _try(ptrace.setregs, tracee.pid, registers)
        _try(ptrace.cont, tracee.pid)

    def _cancel_syscall(self, tracee: Tracee, registers: Any, action: Action) -> None:
        """Skip the syscall, then substitute the target's errno on the way out.

        The kernel overwrites the return register when a syscall is skipped, so
        the value can only be planted at the syscall-exit stop.
        """
        registers.syscall_number = -1
        tracee.pending_errno = action.errno
        try:
            ptrace.setregs(tracee.pid, registers)
            ptrace.syscall(tracee.pid)
        except OSError:
            tracee.pending_errno = None

    def _finish_cancelled_syscall(self, tracee: Tracee) -> None:
        code = tracee.pending_errno
        tracee.pending_errno = None
        if code is None:
            _try(ptrace.cont, tracee.pid)
            return
        try:
            registers = ptrace.getregs(tracee.pid)
            registers.result = -code
            ptrace.setregs(tracee.pid, registers)
            ptrace.cont(tracee.pid)
        except OSError:
            pass

    # -------------------------------------------------------------- exec bridge

    def is_agent_launch(self, tracee: Tracee, program: str) -> bool:
        """True when a program belongs to this machine rather than the target."""
        if tracee.pid == self._root_pid and tracee.exec_count == 1:
            return True
        return self.router.runs_locally(program)

    def begin_remote_exec(
        self,
        tracee: Tracee,
        registers: Registers,
        program: str,
        argv: list[str],
        env: dict[str, str],
    ) -> Action:
        """Run a command on the target in place of this ``execve``."""
        try:
            self.shadow.flush()
        except OSError as exc:
            log.warning("could not push local changes before exec: %s", exc)
        stdio = (_steal(tracee.pid, 0), _steal(tracee.pid, 1), _steal(tracee.pid, 2))
        try:
            cwd = self.router.virtual_cwd(procfs.working_directory(tracee.pid))
        except OSError:
            cwd = self.router.virtual_cwd(self._launch.cwd)
        remote_program = (
            self.router.to_virtual(program)
            if self.router.is_remote_path(program)
            else program
        )
        argv = [self.router.rewrite(item) for item in argv]
        env = {
            name: self.router.rewrite(value)
            for name, value in env.items()
            if name not in self.private
        }
        remote_program = self.router.rewrite(remote_program)
        log.debug(
            "pid %d: running %s on the target (cwd %s)", tracee.pid, argv[:1], cwd
        )
        proxy = ExecProxy(
            self.client,
            tracee.pid,
            argv,
            cwd,
            env,
            stdio,
            self._on_exec_finished,
            program=remote_program,
            tty=stdio[0] >= 0 and os.isatty(stdio[0]),
        )
        tracee.proxy = proxy
        proxy.start()
        standin.park(tracee.pid, registers)
        return STALL

    def _on_exec_finished(self, pid: int, result: ExecResult) -> None:
        """Called from an ExecProxy thread once the remote command is done."""
        self._completions.put((pid, result))
        with contextlib.suppress(OSError, ValueError):
            os.write(self._wake_write, b"\x01")

    def _drain_completions(self) -> None:
        while True:
            try:
                pid, result = self._completions.get_nowait()
            except queue.Empty:
                return
            self._release_stalled(pid, result)

    def _release_stalled(self, pid: int, result: ExecResult) -> None:
        """Turn the stalled ``execve`` into an exit carrying the remote status."""
        tracee = self._tracees.get(pid)
        if tracee is None or tracee.proxy is None:
            return
        tracee.proxy = None
        # Anything the command did on the target invalidates our mirror.
        self.shadow.invalidate()
        try:
            if result.signal in _FATAL_SIGNALS:
                # Let the stand-in die from the very signal that killed the
                # command, so the agent's wait() reports it as a signal death
                # rather than an exit code -- what a local child would do.
                ptrace.cont(pid, result.signal or 0)
                return
            registers = ptrace.getregs(pid)
            registers.syscall_number = NR.EXIT_GROUP
            registers.set_arg(0, result.wait_status)
            ptrace.setregs(pid, registers)
            ptrace.cont(pid)
        except OSError:
            log.debug("pid %d vanished before it could be released", pid)

    # ------------------------------------------------------- signal relaying

    def _relay_pending_signals(self) -> None:
        """Forward cancellation signals queued against a parked tracee.

        A process stopped by ptrace never dequeues ordinary signals, so an
        agent's ``SIGTERM`` would otherwise be invisible.  Reading the pending
        mask lets the remote command see it instead.
        """
        for tracee in list(self._tracees.values()):
            if tracee.proxy is None:
                continue
            pending = _pending_signals(tracee.pid)
            for signum in _CANCEL_SIGNALS:
                if pending & (1 << (signum - 1)):
                    tracee.proxy.forward_signal(int(signum))


def _ignore(*_: object) -> None:
    """Wake the event loop without doing anything else."""


def _drain(fd: int) -> None:
    try:
        while os.read(fd, 4096):
            pass
    except (BlockingIOError, OSError):
        pass


def _try(function: Any, *args: Any) -> None:
    """Run a ptrace call, tolerating a tracee that has already exited."""
    try:
        function(*args)
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            log.debug(
                "%s%r failed: %s", getattr(function, "__name__", function), args, exc
            )


def _steal(pid: int, fd: int) -> int:
    """Duplicate one of the tracee's standard descriptors, or ``-1``.

    Warned about rather than logged quietly: without the descriptor the remote
    command still runs but its output goes nowhere, which is baffling unless
    the cause is visible at the default log level.
    """
    try:
        return procfs.steal_fd(pid, fd)
    except OSError as exc:
        log.warning("could not borrow fd %d from pid %d: %s", fd, pid, exc)
        return -1


def _pending_signals(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as handle:
            mask = 0
            for line in handle:
                if line.startswith(("SigPnd:", "ShdPnd:")):
                    mask |= int(line.split()[1], 16)
            return mask
    except (OSError, ValueError):
        return 0
