"""Process-lifecycle checks for the Codex app-server harness."""

from __future__ import annotations

import contextlib
import os
import signal
import sys
import textwrap
import time
from typing import TYPE_CHECKING

import pytest

from hmz.agents import codex as codex_backend

if TYPE_CHECKING:
    from pathlib import Path

#: A stand-in `codex app-server` that answers the handshake, keeps a child of its own, and
#: will not go for a `SIGTERM` -- which is the shape of the thing being guarded against: a
#: provider wrapper holding the real server under it, told to stop and not stopping.
SERVER = """
import json
import pathlib
import signal
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
pathlib.Path({pid!r}).write_text(str(child.pid))
signal.signal(signal.SIGTERM, signal.SIG_IGN)
for line in sys.stdin:
    message = json.loads(line)
    if "id" in message:
        print(json.dumps({{"jsonrpc": "2.0", "id": message["id"], "result": {{}}}}), flush=True)
time.sleep(60)
"""


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups are unavailable")
def test_codex_server_stop_terminates_its_entire_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider wrapper cannot leave its Codex child behind after a flow stops."""
    program = tmp_path / "server.py"
    program.write_text(
        textwrap.dedent(SERVER).format(pid=str(tmp_path / "child.pid")),
        encoding="utf-8",
    )
    monkeypatch.setattr(codex_backend, "_STOP_SECONDS", 0.05)
    server = codex_backend._AppServer([sys.executable, str(program)])
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
                pytest.fail("Codex process group was not reaped")
            time.sleep(0.01)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process_group, signal.SIGKILL)
