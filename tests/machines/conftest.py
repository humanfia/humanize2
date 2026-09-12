"""What a machine test needs and cannot make for itself: a daemon holding the image.

Shared rather than written out twice, since every file here that drives a real container
skips for want of one in exactly the same way.
"""

from __future__ import annotations

import subprocess

import pytest

#: Small, and has the `python3` a target needs. Pulled by hand rather than by the test, so a
#: machine without it skips instead of spending a minute on a download.
IMAGE = "python:3.12-slim"


@pytest.fixture
def daemon() -> None:
    """A docker daemon holding the image, or a skip: these tests run a container for real."""
    try:
        ready = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
        )
    except OSError as reason:
        pytest.skip(f"needs the docker command: {reason}")
    if ready.returncode != 0:
        pytest.skip(f"needs a docker daemon holding {IMAGE}")
