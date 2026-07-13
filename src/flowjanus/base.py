"""The agent base class. A concrete agent only has to say how to build its CLI command."""

from __future__ import annotations

import subprocess
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
        """Run one turn and return the agent's final text. Raises :class:`AgentError` on failure."""
        argv, stdin = self._command(prompt)
        proc = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=self.cwd,
            check=False,
        )
        if proc.returncode != 0:
            raise AgentError(f"{argv[0]} exited {proc.returncode}: {proc.stderr.strip()[:500]}")
        return proc.stdout.strip()
