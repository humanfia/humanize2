"""Process-lifecycle checks for the Kimi Code app-server harness."""

from __future__ import annotations

import contextlib
import os
import signal
import sys
import textwrap
import time
from typing import TYPE_CHECKING

import pytest

from hmz.agents import kimi as kimi_backend

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups are unavailable")
def test_kimi_server_stop_terminates_its_entire_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider wrapper cannot leave its Kimi child behind after a flow stops."""
    program = tmp_path / "server.py"
    child_pid = tmp_path / "child.pid"
    program.write_text(
        textwrap.dedent(
            f"""
            import pathlib
            import signal
            import subprocess
            import sys
            import time

            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            print("Kimi server: http://127.0.0.1:1/#token=test", flush=True)
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(kimi_backend, "_STOP_SECONDS", 0.05)
    server = kimi_backend._AppServer([sys.executable, str(program)])
    process_group = server._proc.pid
    try:
        server.stop()
        server.stop()
        assert server._proc.poll() is not None
        deadline = time.monotonic() + 5
        while True:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                pytest.fail("Kimi process group was not reaped")
            time.sleep(0.01)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process_group, signal.SIGKILL)
