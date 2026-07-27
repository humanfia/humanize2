"""amflows: flows of coding agents, and the runs of them."""

from __future__ import annotations

import os
import pathlib

__all__ = ["home"]


def home() -> pathlib.Path:
    """Where amflows keeps what outlives one run of one flow.

    Under your home directory, unless `AMFLOWS_HOME` says otherwise -- which is what a test
    says, and what a machine holding more than one of these would.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    return pathlib.Path(
        os.environ.get("AMFLOWS_HOME") or pathlib.Path.home() / ".amflows"
    )
