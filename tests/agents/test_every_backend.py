"""One real turn on every backend installed here, which is the only test of `it works`.

The rest of the suite drives stand-ins that print each backend's protocol, which is what makes
it runnable on a machine with nothing installed -- and what makes it blind to the half that
only the real thing has: an account that has expired, a model the account may not name, a
service that has been withdrawn, a flag the CLI stopped taking in the version that shipped
this morning. None of those is a bug in humanize, and all of them are `this CLI does not work`
to whoever is at the prompt.

So this drives whatever is installed, at whatever that CLI last said it runs, and asks it for
one word. What it pins is that a turn lands, that the session it landed in is named, and that
a turn which does not land says why in words a person can act on -- which is the difference
between `your account cannot run that model` and `returned non-zero exit status 1`.

Costs tokens and needs network access, so it only runs with ``pytest --run-agents``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz import backends
from hmz.agents import Failed, driver

if TYPE_CHECKING:
    from hmz.agents import AgentBase

pytestmark = pytest.mark.agent

#: Where this machine keeps what each backend last said it runs. Read from the real home
#: rather than through `hmz.models`, which the suite points at a directory of its own: what
#: is wanted here is what this machine's own accounts may actually name.
_KEPT = Path.home() / ".humanize" / "models"

#: What to ask for. One word, no tools, nothing to think about: what is being tested is that
#: a turn lands at all.
_ASKED = "Reply with exactly: OK"


def _model(cli: str) -> tuple[str, str]:
    """What to run one backend at: the first model it named, at the least effort it takes.

    The first because that is the backend's own idea of what it runs, which is what the
    interface opens on; the least effort because this is a turn that says one word.

    Args:
      cli: The backend.

    Returns:
      The model and the effort.
    """
    try:
        said = json.loads((_KEPT / f"{cli}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip(f"nothing has asked {cli} what it runs on this machine")
    held = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    models = cast("list[dict[str, Any]]", held.get("models") or [])
    if not models:
        pytest.skip(f"{cli} has said nothing about what it runs on this machine")
    first = models[0]
    efforts = cast("list[str]", first.get("efforts") or [])
    # The least of the efforts it takes, and none at all for a model that takes none: a
    # backend whose models carry their own effort refuses one said beside the name.
    return str(first["name"]), str(efforts[-1]) if efforts else ""


def _installed(cli: str) -> bool:
    """Whether this backend is on this machine at all."""
    if cli == "dsh":
        import importlib.util

        return importlib.util.find_spec("deepseek_harness") is not None
    return shutil.which(cli) is not None


@pytest.mark.timeout(900)
@pytest.mark.parametrize(
    "cli", [one.name for one in backends.PROFILES], ids=lambda one: one
)
def test_a_turn_lands_on_every_backend_installed_here(
    cli: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn, an answer, and the session it landed in -- on the real thing.

    A turn the vendor refuses is not a failure of this test's: an account that may not name a
    model and a service that has been withdrawn are things about that account. What is
    checked then is that humanize said which, in words rather than in an exit status.
    """
    if not _installed(cli):
        pytest.skip(f"{cli} is not installed here")
    monkeypatch.chdir(tmp_path)  # so an agent that tidies up tidies up nothing of ours
    model, effort = _model(cli)
    agent, config = driver(cli)
    one: AgentBase = agent(config(model=model, effort=effort))
    session = one.new()

    said = ""
    refused: subprocess.CalledProcessError | None = None
    try:
        said = session(_ASKED)
    except subprocess.CalledProcessError as why:
        refused = why
    if refused is not None:
        # The turn did not land. Whether that is this machine's account or this CLI's day,
        # the one thing humanize owes whoever is at the prompt is which -- so the failure
        # has to say something beyond the exit status it stopped on.
        assert isinstance(refused, Failed), (
            f"{cli}: a turn that failed must say why, and this said only its exit status"
        )
        told = str(refused).partition("status")[2]
        assert told.strip(" .0123456789"), (
            f"{cli}: nothing was said about why it failed"
        )
        pytest.skip(f"{cli} would not take a turn on this machine: {refused}")

    assert "OK" in said
    assert session.id, f"{cli}: the turn landed and the session was never named"
    assert session.id in one.opened
