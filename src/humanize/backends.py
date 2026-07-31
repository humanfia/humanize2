"""What is true of each coding agent CLI, written down once.

Facts rather than code: what a backend is called, what it answers to on a command line, what
it runs, where it keeps its home and which files under it a session is logged to. Four things
need these and none of them needs the others -- driving a backend, reading a run's cost as it
happens, gathering its trajectories afterwards, offering its models at a prompt -- so they are
here rather than in whichever of those was written first.

Nothing is imported to read this, which is what lets `hmz collect` and the prompt's model list
have it without paying for the agents themselves. The code that acts on a fact lives where its
purpose does: driving in :mod:`humanize.agents`, reading back in :mod:`humanize.tracing`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PROFILES", "Model", "Profile", "named", "read"]


@dataclass(frozen=True, slots=True)
class Model:
    """One model a backend runs, and the efforts it runs at.

    Attributes:
      name: What to ask the backend for.
      efforts: The efforts this model takes, which is not always all of them.
      swarms: Whether it also runs a turn as a fleet of subagents rather than as one agent,
        which is a second thing to say about a turn and not a harder version of the first --
        so it is chosen alongside the effort rather than among them.
    """

    name: str
    efforts: tuple[str, ...]
    swarms: bool = False


@dataclass(frozen=True, slots=True)
class Profile:
    """One coding agent CLI, as everything outside its driver needs to know it.

    Attributes:
      name: What this backend is called here, which is the command it is installed as.
      aliases: What a command line may call it, this name included. A backend is named twice
        where both spellings are what people call it, and neither is ambiguous.
      home_var: The environment variable that moves its home directory.
      home_dir: Where that home is by default, under this user's own.
      logs: The files one session is logged to under that home, as globs taking `{ident}`.
        Claude gets two -- a sub-agent it starts writes its own transcript, and the tokens it
        spends are the run's.
      skills: The skill files under that home, as globs, each naming the `SKILL.md` of one
        skill -- which is where the CLI itself looks for the skills a user has installed.
        Empty for a backend that can be given no skills, and for one that offers no way of
        being told which of them to load: a list to choose from that nothing acts on is a
        list that lies.
      shared: The same, under the user's own home rather than under the backend's: `.agents`
        is the directory more than one of these has agreed to read, and a backend that reads
        it goes on reading it wherever `home_var` has moved its own home to.
      works: The same, under the workspace rather than under either home: a skill kept beside
        the project it is for. A backend may read more than one such directory.
      models: What it runs, in the order they are offered: by tier and then newest first.
        Nothing sorts them, because nothing can -- a tier is not in the name and a version is
        not a number. Model ids only, never the aliases a backend also answers to: `opus` is
        whichever Opus is newest today and something else tomorrow, so a cycle that recorded
        it says nothing about what actually ran.
    """

    name: str
    aliases: tuple[str, ...]
    home_var: str
    home_dir: str
    logs: tuple[str, ...]
    models: tuple[Model, ...]
    skills: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    works: tuple[str, ...] = ()

    def directory(self) -> Path:
        """Where this backend keeps its state and its logs, wherever it has been moved to.

        Returns:
          The home directory. It may not exist: a backend that has never run has none.
        """
        return Path(os.environ.get(self.home_var) or Path.home() / self.home_dir)


#: What Claude Code documents on its own command line, for every model it runs, and above them
#: the one it does not document but takes: `ultracode` is `xhigh` with the turn opted into
#: orchestrating a fleet of its own, which is more work than any single-agent effort and so is
#: the top of this list. Hardest first, as every effort here is: the one to reach for is the
#: one at the top.
_CLAUDE = ("ultracode", "max", "xhigh", "high", "medium", "low")

#: Every backend humanize drives, as each of them reported itself. Codex says which efforts
#: each of its models takes and they differ, so they are written down as it gave them.
PROFILES = (
    Profile(
        name="claude",
        aliases=("claude", "claude-code"),
        home_var="CLAUDE_CONFIG_DIR",
        home_dir=".claude",
        logs=("projects/*/{ident}.jsonl", "projects/*/{ident}/subagents/**/*.jsonl"),
        # The skills a person installs, which is what there is to choose between: the ones
        # Claude ships with and the ones a plugin brought are the plugin's to say. Its own
        # two directories and no more -- it does not read the shared one, which is why a
        # skill kept there is symlinked into this. A turn is told which of these it may not
        # reach for, as `Skill(<name>)`.
        skills=("skills/*/SKILL.md",),
        works=(".claude/skills/*/SKILL.md",),
        models=(
            Model("claude-fable-5", _CLAUDE),
            Model("claude-opus-5", _CLAUDE),
            Model("claude-opus-4-8", _CLAUDE),
            Model("claude-opus-4-7", _CLAUDE),
            Model("claude-opus-4-6", _CLAUDE),
            Model("claude-sonnet-5", _CLAUDE),
            Model("claude-sonnet-4-6", _CLAUDE),
            Model("claude-haiku-4-5", _CLAUDE),
        ),
    ),
    Profile(
        name="codex",
        aliases=("codex",),
        home_var="CODEX_HOME",
        home_dir=".codex",
        logs=("sessions/**/rollout-*{ident}.jsonl",),
        # Four places, which is what `skills/list` answers with: its own home, the shared
        # one under yours, and both of the directories a project may keep them in. A turn is
        # given the ones left on, as `skills.config` says which are off.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".agents/skills/*/SKILL.md", ".codex/skills/*/SKILL.md"),
        models=(
            Model("gpt-5.6-sol", ("ultra", "max", "xhigh", "high", "medium", "low")),
            Model("gpt-5.6-terra", ("ultra", "max", "xhigh", "high", "medium", "low")),
            Model("gpt-5.6-luna", ("max", "xhigh", "high", "medium", "low")),
            Model("gpt-5.5", ("xhigh", "high", "medium", "low")),
        ),
    ),
    Profile(
        name="kimi",
        aliases=("kimi", "kimi-code"),
        home_var="KIMI_CODE_HOME",
        home_dir=".kimi-code",
        logs=("server/events/{ident}.jsonl",),
        # None named: `--skills-dir` is a flag of the command line, and a session here is a
        # thread on `kimi web`, which takes none. A skill Kimi finds is a skill it loads, so
        # there is nothing here to be offered a choice about.
        models=(
            Model("kimi-code/k3", ("max", "high", "medium", "low"), swarms=True),
            Model("kimi-code/k3-256k", ("max", "high", "medium", "low"), swarms=True),
            Model(
                "kimi-code/kimi-for-coding",
                ("max", "high", "medium", "low"),
                swarms=True,
            ),
        ),
    ),
)


def named(backend: str) -> Profile | None:
    """The backend a name stands for, whichever of its spellings was used.

    Args:
      backend: What it was called.

    Returns:
      Its profile, or None for a name no backend answers to.
    """
    return next((one for one in PROFILES if backend in one.aliases), None)


def read(spec: str) -> tuple[Profile, str, str]:
    """Reads one `-a` into the backend to drive and what to drive it at.

    Args:
      spec: `CLI/MODEL:EFFORT`, or `cli=CLI,model=MODEL,effort=EFFORT` written out -- which is
        where a model or an effort holding the punctuation the short form separates on goes.

    Returns:
      The backend, the model and the effort.

    Raises:
      ValueError: If it is neither spelling, or names no backend there is. What it says is
        what a command line reports after the agent it could not read.
    """
    if "=" in spec:
        given = {
            key.strip(): value.strip()
            for key, _, value in (part.partition("=") for part in spec.split(","))
        }
        backend, model, effort = (
            given.pop("cli", ""),
            given.pop("model", ""),
            given.pop("effort", ""),
        )
        if given:
            raise ValueError(f"{', '.join(sorted(given))} is not cli, model or effort")
    else:
        # Read from both ends: a model may hold slashes of its own -- Kimi's are
        # `kimi-code/k3` -- while a CLI and an effort never do.
        backend, _, rest = spec.partition("/")
        model, _, effort = rest.rpartition(":")
    profile = named(backend.strip())
    if profile is None or not model.strip() or not effort.strip():
        raise ValueError(
            "expected CLI/MODEL:EFFORT or cli=CLI,model=MODEL,effort=EFFORT"
        )
    return profile, model.strip(), effort.strip()
