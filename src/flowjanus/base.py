"""The agent base class. A concrete agent only has to say how to build its CLI command."""

from __future__ import annotations

import subprocess
import sys
import threading
from abc import ABC, abstractmethod


class AgentError(RuntimeError):
    """The underlying agent CLI failed (nonzero exit)."""


class AgentBase(ABC):
    """A coding agent behind a uniform interface. Subclasses implement :meth:`_command`; callers
    only ever touch :meth:`run`, so the concrete backend is hidden."""

    def __init__(
        self,
        *,
        model: str | None = None,
        effort: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.cwd = cwd

    @abstractmethod
    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        """Return ``(argv, stdin)``. ``stdin=None`` means the prompt is already inside ``argv``."""

    def run(self, prompt: str) -> str:
        """Run one turn, streaming the agent's stdout live while capturing it.

        Returns the captured stdout (stripped); raises :class:`AgentError` on a nonzero exit.
        """
        argv, stdin = self._command(prompt)
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd,
        )

        stderr_chunks: list[str] = []

        def drain_stderr() -> None:
            assert proc.stderr is not None
            stderr_chunks.append(proc.stderr.read())

        stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
        stderr_thread.start()

        if stdin is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin)  # the agent CLIs consume the whole prompt before replying
            proc.stdin.close()

        timer = threading.Timer(self.timeout, proc.kill) if self.timeout is not None else None
        if timer is not None:
            timer.start()

        assert proc.stdout is not None
        captured: list[str] = []
        try:
            for line in proc.stdout:
                sys.stdout.write(line)  # tee: pass the agent's output straight through
                sys.stdout.flush()
                captured.append(line)
            proc.wait()
        finally:
            if timer is not None:
                timer.cancel()
        stderr_thread.join()

        if proc.returncode != 0:
            raise AgentError(
                f"{argv[0]} exited {proc.returncode}: {''.join(stderr_chunks).strip()[:500]}"
            )
        return "".join(captured).strip()
