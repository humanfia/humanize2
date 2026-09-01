"""What a place comes to, and how much of that is known before anything has been started.

The setting answers for itself, so that a flow may refuse a place before its first turn, and
the machine answers for the one thing only a machine can say: the platform it turns out to be
running, read from the handshake a turn opens. Both halves are driven against real targets --
a `local:` one, which is a `serve` on the other end of a pipe, and a container where there is
a daemon to run one -- so a platform that is reported here really did cross the wire.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.machines import AnchoredConfig, DockerConfig, MachineBase, MachineConfig
from tests.machines.conftest import IMAGE

if TYPE_CHECKING:
    from pathlib import Path

#: What this machine is, which is what a target served from here says of itself.
HERE = sys.platform

#: And what it is not, for the refusal: a setting promising this cannot be made good on by
#: anything started here, whichever of the two this machine happens to be.
ELSEWHERE = "darwin" if HERE == "linux" else "linux"


class _Claiming(MachineBase):
    """A machine that brings up nothing and has the target make good on what was claimed."""

    _config: _ClaimingConfig

    def start(self) -> AnchorConfig:
        anchor = self._config.anchor
        self.observe(anchor)
        return anchor


@dataclass(frozen=True, kw_only=True)
class _ClaimingConfig(MachineConfig):
    """Settings that promise whatever a test hands them, or nothing at all for None."""

    anchor: AnchorConfig
    claimed: frozenset[str] | None = None

    @property
    def capabilities(self) -> frozenset[str]:
        return super().capabilities if self.claimed is None else self.claimed

    def create(self) -> _Claiming:
        return _Claiming(self)


def _anchor(target: Path) -> AnchorConfig:
    """A target of its own: a `serve` on the far end of a pipe, in a directory of its own.

    Which is `remote` like any other, a target standing in for a machine being reached down
    the same road as one that really is elsewhere. The workspace is on neither side of it, so
    a handshake that answered at all answered from the target rather than out of this
    directory.
    """
    target.mkdir(exist_ok=True)
    return AnchorConfig(target=f"local:{target}", workspace="/machines-project")


def test_a_setting_says_what_its_place_comes_to_without_starting_anything() -> None:
    """Which is the whole point of its being the setting's answer rather than the machine's.

    Neither of these is reachable and neither has been brought up, and both say what they
    would come to all the same -- which is what lets a flow refuse a place before its first
    turn rather than after an image has been pulled for it.
    """
    anchored = AnchoredConfig(anchor=AnchorConfig(target="ssh://build-box"))

    assert anchored.capabilities == frozenset({"remote"})
    assert DockerConfig(image=IMAGE).capabilities == frozenset(
        {"isolated", "linux", "managed", "remote"}
    )
    # And a machine that says nothing comes to nothing, rather than being read as coming to
    # everything it never got round to denying.
    assert _ClaimingConfig(anchor=anchored.anchor).capabilities == frozenset()


def test_a_machine_nobody_here_brought_up_is_not_one_anybody_here_may_take_down() -> None:
    """`managed` is drawn on the same line `stop` is, so the two have to agree."""
    already = AnchoredConfig(anchor=AnchorConfig(target="ssh://build-box"))

    assert "managed" not in already.capabilities
    assert "managed" in DockerConfig().capabilities


def test_an_anchor_says_how_a_turn_reaches_a_machine_rather_than_where_it_lands() -> None:
    """The other axis of the same question, and the one the anchor is the only answer to.

    Where the work lands is the machine's setting to say; how a turn gets there is the
    anchor's, since the same machine reached two ways is two different sets of things a turn
    may be asked to do. Today there is one way, and it is the same way whatever the target.
    """
    assert AnchorConfig(target="ssh://build-box").capabilities == frozenset(
        {"anchor:supervised"}
    )
    assert AnchorConfig().capabilities == AnchorConfig(target="docker://one").capabilities


def test_the_platform_a_machine_runs_is_read_from_the_handshake_rather_than_declared(
    tmp_path: Path,
) -> None:
    """The half no setting can promise: somebody else's machine is whatever it turns out to be."""
    machine = AnchoredConfig(anchor=_anchor(tmp_path / "target")).create()
    assert machine.capabilities == frozenset({"remote"})  # nothing has been asked yet

    observed = machine.observe(machine.start())

    assert observed == frozenset({"remote", HERE})
    assert machine.capabilities == frozenset({"remote", HERE})


def test_a_machine_that_cannot_serve_what_was_asked_of_it_is_refused_as_it_starts(
    tmp_path: Path,
) -> None:
    """And says which capability it could not serve, and what it is instead.

    A place refused for being the wrong one is no use to whoever now has to go and find
    another, so the refusal names both ends of the mismatch.
    """
    machine = _ClaimingConfig(
        anchor=_anchor(tmp_path / "target"), claimed=frozenset({ELSEWHERE})
    ).create()

    with pytest.raises(RuntimeError, match=ELSEWHERE) as refused:
        machine.start()

    assert HERE in str(refused.value)


def test_a_container_confirms_the_platform_its_setting_promised(
    daemon: None, tmp_path: Path
) -> None:
    """Declared before the container exists, and made good on by the container itself.

    Which is the pair working as it should: `linux` is refusable before anything is pulled,
    and it is still the running container that is asked whether it is true.
    """
    machine = DockerConfig(image=IMAGE, workspace=str(tmp_path)).create()

    try:
        machine.start()

        assert machine.capabilities == frozenset(
            {"isolated", "linux", "managed", "remote"}
        )
        # And the platform among them came off the wire rather than out of the settings.
        assert machine._seen == frozenset({"linux"})
    finally:
        machine.stop()
