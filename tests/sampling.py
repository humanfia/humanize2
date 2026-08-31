"""Whether the sampler can be run on the machine running the suite.

:mod:`hmz.tracing.profile` watches what a run started by asking the operating system about
every process under this one, a hundred times a second. On one cell of the matrix -- macOS
under Python 3.13, and not the 3.12 or 3.14 beside it -- doing that wedges the whole
interpreter: the call it is inside does not come back and does not let another thread run
either, so not even pytest's own per-test ceiling can end it. The job reaches the wall having
said nothing, which is the one outcome a ceiling exists to prevent.

Narrow on purpose. This is a thing to fix rather than a platform that cannot have it: the
same file runs in two seconds on every other cell, and profiling is off unless a workspace
asks for it. Written down here rather than as a bare `skipif` in two files so that there is
one place saying what is known and one place to delete when it is fixed.
"""

from __future__ import annotations

import sys

import pytest

#: The one combination the sampler cannot be started on.
WEDGES = sys.platform == "darwin" and sys.version_info[:2] == (3, 13)

#: The mark for a test that starts one.
sampled = pytest.mark.skipif(
    WEDGES,
    reason="the sampler wedges this interpreter (macOS on Python 3.13) -- see tests/sampling.py",
)
