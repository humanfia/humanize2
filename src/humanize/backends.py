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
      home_in: What to look under inside the directory that variable names, for a backend
        whose variable is the one every program shares -- `XDG_DATA_HOME` says where all of
        them keep their data, and this one's is a directory of its own under it. Empty for a
        backend whose variable names its home outright, which is what a variable of its own
        does.
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
    home_in: str = ""
    skills: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    works: tuple[str, ...] = ()

    def directory(self) -> Path:
        """Where this backend keeps its state and its logs, wherever it has been moved to.

        Returns:
          The home directory. It may not exist: a backend that has never run has none.
        """
        moved = os.environ.get(self.home_var)
        return Path(moved) / self.home_in if moved else Path.home() / self.home_dir


#: What Claude Code documents on its own command line, for every model it runs, and above them
#: the one it does not document but takes: `ultracode` is `xhigh` with the turn opted into
#: orchestrating a fleet of its own, which is more work than any single-agent effort and so is
#: the top of this list. Hardest first, as every effort here is: the one to reach for is the
#: one at the top.
_CLAUDE = ("ultracode", "max", "xhigh", "high", "medium", "low")

#: What pi calls its thinking levels, hardest first. `off` is the model asked not to think at
#: all, which is an effort like any other here: it is the least of them, not the absence of a
#: setting.
_PI = ("max", "xhigh", "high", "medium", "low", "minimal", "off")

#: What opencode and mimocode call a reasoning effort: a variant of the model, given as
#: `--variant`, and provider-specific. These are the ones the models they front take; a
#: provider with no variants of its own takes the flag and ignores it.
_VARIANTS = ("xhigh", "high", "medium", "low", "minimal")

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
    Profile(
        name="pi",
        aliases=("pi",),
        home_var="PI_CODING_AGENT_DIR",
        home_dir=".pi/agent",
        # One file per session, named for the moment it opened and the id it was given, under
        # a directory per workspace. The id is the tail of the name, so a glob on it finds the
        # session whichever workspace it was opened in.
        logs=("sessions/*/*{ident}.jsonl",),
        # None named: pi is told which skills to load rather than which to leave, by the path
        # of each, and it finds none of its own to be left out of that -- there is no
        # directory it reads them from, so there is nothing here to offer a choice about.
        models=(
            Model("openai-codex/gpt-5.6-sol", _PI),
            Model("openai-codex/gpt-5.6-terra", _PI),
            Model("openai-codex/gpt-5.6-luna", _PI),
            Model("openai-codex/gpt-5.5", _PI),
            Model("openai-codex/gpt-5.4", _PI),
            Model("openai-codex/gpt-5.4-mini", _PI),
            Model("openai-codex/gpt-5.3-codex-spark", _PI),
        ),
    ),
    Profile(
        name="opencode",
        aliases=("opencode",),
        # No home variable of its own: it keeps its data where every other program does, in a
        # directory of its own under the one `XDG_DATA_HOME` names.
        home_var="XDG_DATA_HOME",
        home_in="opencode",
        home_dir=".local/share/opencode",
        # None: a session here is rows of a database rather than a file, so there is no log to
        # read a run's cost out of as it is spent, and none to gather afterwards.
        logs=(),
        models=(
            Model("opencode/big-pickle", _VARIANTS),
            Model("opencode/nemotron-3-ultra-free", _VARIANTS),
            Model("opencode/deepseek-v4-flash-free", _VARIANTS),
            Model("opencode/laguna-s-2.1-free", _VARIANTS),
            Model("opencode/longcat-2.0-free", _VARIANTS),
            Model("opencode/mimo-v2.5-free", _VARIANTS),
            Model("opencode/north-mini-code-free", _VARIANTS),
            Model("opencode/ling-3.0-tiny-free", _VARIANTS),
        ),
    ),
    Profile(
        name="mimo",
        aliases=("mimo", "mimocode", "mimo-code"),
        home_var="XDG_DATA_HOME",
        home_in="mimocode",
        home_dir=".local/share/mimocode",
        logs=(),
        models=(
            Model("mimo/mimo-auto", _VARIANTS),
            Model("xiaomi/mimo-v2.5-pro", _VARIANTS),
            Model("xiaomi/mimo-v2.5-pro-ultraspeed", _VARIANTS),
            Model("xiaomi/mimo-v2.5", _VARIANTS),
            Model("openai/gpt-5.6-sol", _VARIANTS),
            Model("openai/gpt-5.6-terra", _VARIANTS),
            Model("openai/gpt-5.6-luna", _VARIANTS),
            Model("openai/gpt-5.5", _VARIANTS),
            Model("openai/gpt-5.4", _VARIANTS),
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
