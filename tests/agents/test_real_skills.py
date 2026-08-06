"""What each CLI really reads, asked of the CLI itself rather than believed.

Where a backend looks for skills is written down in `hmz.backends`, and a list written down is
a list that drifts: a CLI adds a directory, or stops reading one, and nothing here would
notice. What a person is shown would then be either short of what their agent carries or full
of skills it has not got, and neither reads as wrong until a turn behaves as though a skill
were missing.

So this asks. Three of these CLIs can say what they found without a turn being taken --
`grok inspect`, and `opencode`/`mimo debug skill` -- and each is asked in a home and a project
of its own, with one skill planted in every directory `hmz.backends` claims it reads. What it
answers must be exactly what humanize would list: nothing declared that the CLI ignores, and
nothing read that humanize does not know about.

No model is asked anything and no tokens are spent, but a real binary is run, so these are
opt-in with the rest of the tests that need one installed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.agents.skills import skills
from hmz.backends import named

if TYPE_CHECKING:
    from hmz.backends import Profile

SKILL = (
    "---\nname: {name}\ndescription: planted where {backend} is said to read one\n---\n"
)

#: How long one of these is given to look at an empty home and say what it found.
_SECONDS = 180


def _plant(profile: Profile, home: Path, config: Path, project: Path) -> list[str]:
    """Puts one skill in every directory this backend is written down as reading.

    Args:
      profile: The backend, whose globs say where those directories are.
      home: The user's own home, which `shared` is under.
      config: The configuration home, which `config` is under.
      project: The workspace, which `works` is under.

    Returns:
      What each planted skill is called, one name per directory, so that a name that comes
      back names the directory it was read from.
    """
    planted: list[str] = []
    for tier, root, globs in (
        ("home", profile.directory(), profile.skills),
        ("config", config, profile.config),
        ("shared", home, profile.shared),
        ("works", project, profile.works),
    ):
        for pattern in globs:
            # `a/b/*/SKILL.md` is one skill directory per name under `a/b`, which is the
            # layout every one of these reads. Named for the tier and the directory both,
            # with the separators flattened: a name is one skill to these CLIs, so two that
            # flattened alike -- `opencode/skills` under the configuration home and
            # `.opencode/skills` under the project -- would be one, and either could then
            # stand in for the other going unread.
            under, _, _ = pattern.partition("/*/")
            flattened = under.strip(".").replace("/", "-").replace(".", "-")
            name = f"planted-{tier}-{flattened}"
            (root / under / name).mkdir(parents=True, exist_ok=True)
            (root / under / name / "SKILL.md").write_text(
                SKILL.format(name=name, backend=profile.name), encoding="utf-8"
            )
            planted.append(name)
    return planted


def _homes(
    backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Profile, list[str]]:
    """A home, a configuration home and a project, each with this backend's skills planted."""
    profile = named(backend)
    assert profile is not None
    home, config, project = (tmp_path / one for one in ("home", "config", "project"))
    for one in (home, config, project):
        one.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    if profile.home_var:
        monkeypatch.setenv(profile.home_var, str(tmp_path / "backend-home"))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)
    return profile, _plant(profile, home, config, project)


def _somebodys(one: dict[str, object], profile: Profile, tmp_path: Path) -> bool:
    """Whether one skill a CLI listed is one a person put there rather than one it ships.

    Args:
      one: The skill, as that CLI described it.
      profile: The backend, which says whether it reads a person's skills out of its own
        data home at all.
      tmp_path: The sandbox everything planted here is under.

    Returns:
      Whether it counts. A skill under the backend's data home is the CLI's own -- opencode
      and mimocode both keep what they ship there, and neither is written down as reading a
      person's from it -- and a skill outside the sandbox belongs to whoever is at this
      machine rather than to this test.
    """
    where = Path(str(one.get("location", "")))
    if tmp_path not in where.parents:
        return False
    return bool(profile.skills) or profile.directory() not in where.parents


def _ran(argv: list[str], where: Path) -> str:
    """Runs one of these CLIs and answers with what it printed."""
    done = subprocess.run(
        argv, capture_output=True, text=True, timeout=_SECONDS, cwd=where, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.mark.agent
@pytest.mark.timeout(300)
def test_grok_reads_every_directory_it_is_written_down_as_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`grok inspect` says what it discovered for this directory, and nothing else is here."""
    if shutil.which("grok") is None:
        pytest.skip("grok is not installed here")
    _, planted = _homes("grok", tmp_path, monkeypatch)

    said = _ran(["grok", "inspect"], tmp_path / "project")
    listed = re.search(r"Skills \(\d+\)\n(.*?)(?:\n\n|\Z)", said, re.DOTALL)
    assert listed is not None, said
    found = {line.split()[1] for line in listed.group(1).splitlines() if line.strip()}

    assert found == set(planted)
    assert {one.name for one in skills("grok")} == found


@pytest.mark.agent
@pytest.mark.timeout(300)
@pytest.mark.parametrize("backend", ["opencode", "mimo"])
def test_a_configured_backend_reads_every_directory_it_is_written_down_as_reading(
    backend: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`debug skill` answers with each skill and where it read it, built-in ones included."""
    if shutil.which(backend) is None:
        pytest.skip(f"{backend} is not installed here")

    profile, planted = _homes(backend, tmp_path, monkeypatch)

    said = _ran([backend, "debug", "skill"], tmp_path / "project")
    found = {
        one["name"] for one in json.loads(said) if _somebodys(one, profile, tmp_path)
    }

    assert found == set(planted)
    assert {one.name for one in skills(backend)} == found
