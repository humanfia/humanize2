"""What is true of each coding agent CLI, written down once.

Facts rather than code: what a backend is called, what it answers to on a command line, how
hard it thinks, where it keeps its home and which files under it a session is logged to. Four
things need these and none of them needs the others -- driving a backend, reading a run's cost
as it happens, gathering its trajectories afterwards, offering what it runs at a prompt -- so
they are here rather than in whichever of those was written first.

What it runs is not here, and cannot be: a model id is whatever that CLI shipped this week, on
whatever account the turns run as. :mod:`hmz.models` asks the backend itself and keeps what it
says. The efforts are, because they are the backend's own vocabulary rather than a catalogue --
`xhigh` means the same thing next release -- and a model narrows them to the ones it takes.

Nothing is imported to read this, which is what lets `hmz trace collect` and the model list
have it without paying for the agents themselves. The code that acts on a fact lives where its
purpose does: driving in :mod:`hmz.agents`, reading back in :mod:`hmz.tracing`.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "ALIKE",
    "PROFILES",
    "Asked",
    "Model",
    "Profile",
    "Way",
    "alike",
    "elsewhere",
    "forget",
    "named",
    "profiles",
    "program",
    "read",
    "remember",
    "serves",
    "speaking",
]


@dataclass(frozen=True, slots=True)
class Asked:
    """One thing a person has to say for a way in to be usable.

    Attributes:
      env: The environment variable the answer becomes, which is how every one of these CLIs
        takes a credential that was not left behind by a login. It is also what the answer is
        called wherever it is written down.
      about: The question, as it is put to whoever is answering it.
      secret: Whether what they type is a secret, and so is neither echoed nor shown again.
      keep: Whether the answer is kept as that variable. False for one that is only handed to
        the command the way runs -- a key read off stdin ends up inside the CLI's own store,
        and keeping a second copy of it in an environment would be a second place to leak it.
      fixed: What it is when nobody is asked, for a question with an answer that is usually
        right.
    """

    env: str
    about: str
    secret: bool = False
    keep: bool = True
    fixed: str = ""


@dataclass(frozen=True, slots=True)
class Way:
    """One way of getting credentials into a backend, as that backend offers it.

    A CLI has more than one: the subscription it signs into, an API key of the vendor's own,
    a gateway speaking the vendor's protocol, an account on somebody's console. Each is a
    different thing to be told and lands somewhere different -- a login writes the CLI's own
    store, a key is an environment variable -- and a provider is one of these, answered.

    Attributes:
      name: What this way is called, which is what a provider says it was made by.
      about: One line saying what it is, for whoever is choosing between them.
      argv: The backend's own command to run for it, under the provider's own paths, with the
        terminal handed over -- which is what makes a login a login rather than a form. Empty
        for a way that is only answers.
      asks: What to ask before running it, in the order to ask.
      sets: What this way sets whatever the answers are, such as the variable that switches a
        backend onto a vendor's cloud.
      args: What to add to the backend's own command line for a turn run under it, with
        `{VARIABLE}` filled in from the answers -- for a backend told about a provider on its
        command line rather than through its environment.
      stdin: The variable whose answer is written to `argv`'s standard input, for a command
        that reads a key rather than prompting for one.
    """

    name: str
    about: str
    argv: tuple[str, ...] = ()
    asks: tuple[Asked, ...] = ()
    sets: tuple[tuple[str, str], ...] = ()
    args: tuple[str, ...] = ()
    stdin: str = ""


@dataclass(frozen=True, slots=True)
class Model:
    """One model a backend runs, and the efforts it runs at.

    What a backend answered when it was asked what it runs, rather than anything written down
    here: :mod:`hmz.models` is what asks and what keeps the answer.

    Attributes:
      name: What to ask the backend for. The id it answers to, never an alias it also takes:
        `opus` is whichever Opus is newest today and something else tomorrow, so an epic that
        recorded it says nothing about what actually ran.
      efforts: The efforts this model takes, hardest first, which is not always all of the
        ones its backend has.
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
      name: What this backend is called here, which is the command it is installed as unless
        `command` says otherwise.
      command: What it is actually installed as, where that is not what it is called. Cursor's
        agent is `cursor-agent`; everything else here is installed under its own name, so this
        is empty for them.
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
      config: The same, under the directory every program keeps its configuration in --
        whatever `XDG_CONFIG_HOME` names, or `~/.config` where nothing has moved it. Each
        glob carries the backend's own directory under it, as `shared`'s carry `.agents`.
        Empty for a backend that keeps its skills beside its data, which is most of them:
        this is for opencode and mimocode, whose sessions and credentials are under the data
        home and whose skills are not, so that one `home_var` cannot name both.
      works: The same, under the workspace rather than under either home: a skill kept beside
        the project it is for. A backend may read more than one such directory.
      mounts: Which of those directories a flow's own skills are mounted into for the length
        of a session -- written as the directory rather than as a glob, since this is the one
        that is written to rather than read. Empty for a backend that reads none, whose
        skills are all its own installed ones: a flow that brings skills brings that backend
        none, which is a turn run without them rather than a run that will not start.
      efforts: How hard this backend can be asked to think, hardest first, in its own wording.
        The whole ladder it has words for; a model of it takes some of them, and which ones is
        the backend's to say when it is asked what it runs.
      beyond: The rungs of that ladder it takes but does not list -- a way of running a model
        that is real and undocumented. Written here because no listing of the backend's own
        will ever name one, so a model asked about would otherwise lose it.
      swarms: Whether a turn of this backend also runs as a fleet of subagents rather than as
        one agent. A property of the backend rather than of a model: it is a way of taking a
        turn, and every model that takes turns here takes them that way too.
      searches: Whether this backend can be told whether its agents may search the web. A
        property of the backend rather than of a model, for the reason `swarms` is: reaching
        the web is a tool the CLI hands its agent, and the CLI is what hands it. False for one
        with no way of being told, whose agents go on reaching the web exactly as that CLI
        lets them -- an agent configured not to search on a backend that cannot be told would
        be a setting that lies, so it is refused where it is written instead.
      creds: What a login to this backend leaves behind: the paths it reads its credentials
        back out of and writes its refreshed ones to. One under this backend's home per entry,
        one under the user's own home where the entry starts with `~/` -- which is where some
        of them keep a second file -- and one under whatever `XDG_CONFIG_HOME` names where it
        starts with `config/`, which is where a CLI that shares a vendor's account with the
        vendor's other programs keeps it. A directory names everything inside it. These are the
        paths, and only these, that a turn run under a provider is pointed somewhere else: the
        sessions, the settings and the skills are the same ones the CLI already has.
      ways: How credentials get into this backend, one entry per kind it offers -- the
        subscription it signs into, a key, a gateway, an account on a console. What a person
        is offered when they make a provider for it, and what says nothing at all for a
        backend nobody has written the ways of down yet.
      ambient: The other variables this backend would take an account from, which no way of
        its own uses: the vendor's own name for a key, an endpoint somebody exported once, a
        switch onto a cloud. Named so that a turn under a provider can be run without them --
        a key in a shell profile is a key this CLI would rather have than the one it was
        signed in with, and nothing about that reads as wrong until the bill arrives.
    """

    name: str
    aliases: tuple[str, ...]
    home_var: str
    home_dir: str
    logs: tuple[str, ...]
    efforts: tuple[str, ...]
    command: str = ""
    home_in: str = ""
    skills: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    config: tuple[str, ...] = ()
    works: tuple[str, ...] = ()
    mounts: str = ""
    beyond: tuple[str, ...] = ()
    swarms: bool = False
    searches: bool = False
    creds: tuple[str, ...] = ()
    ways: tuple[Way, ...] = ()
    ambient: tuple[str, ...] = ()

    def runs(self) -> str:
        """The command that starts this backend, which is its name unless it says otherwise.

        Read here rather than written down twice: everything that looks for a backend, asks
        one what it runs, or starts a turn of one asks this, so a CLI installed under a name
        that is not what it is called is one thing to say and not four.

        Returns:
          The command, as `PATH` would name it.
        """
        return self.command or self.name

    def directory(self) -> Path:
        """Where this backend keeps its state and its logs, wherever it has been moved to.

        Returns:
          The home directory. It may not exist: a backend that has never run has none.
        """
        moved = os.environ.get(self.home_var)
        return Path(moved) / self.home_in if moved else Path.home() / self.home_dir

    @staticmethod
    def configuration() -> Path:
        """The directory programs keep their configuration in, wherever it has been moved to.

        Not this backend's own: `XDG_CONFIG_HOME` is the one variable every program that
        follows it shares, so what belongs to a backend is the directory under it, which
        `config` names as part of each glob.

        Returns:
          That directory. It may not exist, and a backend keeping nothing there never looks.
        """
        moved = os.environ.get("XDG_CONFIG_HOME")
        return Path(moved) if moved else Path.home() / ".config"

    def accounts(self) -> frozenset[str]:
        """Every variable this backend would take an account from, whoever set it.

        What the ways in name, and what is written down beside them: a CLI reads a key, a
        token or an endpoint out of the environment, and it does not care whether the person
        at this machine exported it or a provider did. So a turn under a provider has to be
        run with these unset unless that provider set them -- an `ANTHROPIC_API_KEY` left in
        somebody's shell profile outranks the credentials file a provider was signed into,
        and the turn would be taken as the wrong account without anything looking wrong.

        Returns:
          The variable names, which is nothing at all for a backend whose ways nobody has
          written down.
        """
        named = {one.env for way in self.ways for one in way.asks}
        named |= {name for way in self.ways for name, _ in way.sets}
        return frozenset(named | set(self.ambient))

    def hushes(self) -> frozenset[str]:
        """`accounts()`, and every other spelling of each that names the same credential.

        What a turn under a provider is actually run without. A CLI that reads one name for a
        credential reads its aliases too -- kimi takes an account from `MOONSHOT_API_KEY` as
        well as `KIMI_API_KEY`, opencode from `GOOGLE_API_KEY` as well as `GEMINI_API_KEY` --
        so one of those left in the environment is the same wrong account whichever of the two
        spellings carried it, and hushing only the name a backend's ways happened to write
        down would leave the other to supply it. `serves()` copies an account by its declared
        name, which is why that keeps the literal `accounts()`; this strips it by every name it
        answers to, and hushing one no backend reads costs nothing.

        Returns:
          The account variables and their aliases, to take away before a provider's turn.
        """
        return frozenset(name for one in self.accounts() for name in alike(one))

    def credentials(self) -> tuple[tuple[str, str], ...]:
        """Every path this backend keeps a credential at, and where it is kept relative to.

        Read here rather than written down twice: a path under the backend's own home moves
        with the variable that moves the home, one written `~/...` is under the user's own
        wherever that home went, and one written `config/...` is under whatever
        `XDG_CONFIG_HOME` names. Three roots because a CLI that keeps its account where every
        program keeps its configuration keeps it somewhere neither of the other two moves.

        Returns:
          One `(absolute path, name to keep it under)` pair per credential, the name being the
          path with the root it is under taken off -- `home/...` for the backend's own,
          `user/...` for the user's and `config/...` for the shared configuration directory,
          so that two files of the same name are two files.
        """
        held: list[tuple[str, str]] = []
        for said in self.creds:
            if said.startswith("~/"):
                held.append((str(Path.home() / said[2:]), f"user/{said[2:]}"))
            elif said.startswith("config/"):
                held.append((str(self.configuration() / said[len("config/") :]), said))
            else:
                held.append((str(self.directory() / said), f"home/{said}"))
        return tuple(held)


#: What Claude Code documents on its own command line, for every model it runs, and above them
#: the one it does not document but takes: `ultracode` is `xhigh` with the turn opted into
#: orchestrating a fleet of its own, which is more work than any single-agent effort and so is
#: the top of this list. Hardest first, as every effort here is: the one to reach for is the
#: one at the top.
_CLAUDE = ("ultracode", "max", "xhigh", "high", "medium", "low")

#: What codex calls its reasoning levels. Which of them a model takes differs across its
#: models, and codex says which where it says what it runs.
_CODEX = ("ultra", "max", "xhigh", "high", "medium", "low")

#: What Kimi Code calls its thinking levels. It says which its models take too, and they
#: differ: this is the ladder, not a promise that every model has every rung.
_KIMI = ("max", "high", "medium", "low")

#: What pi calls its thinking levels, hardest first. `off` is the model asked not to think at
#: all, which is an effort like any other here: it is the least of them, not the absence of a
#: setting.
_PI = ("max", "xhigh", "high", "medium", "low", "minimal", "off")

#: What the official DeepSeek adapter in DeepSeek Harness calls its reasoning levels.
_DSH = ("max", "high", "off")

#: What Grok Build calls its reasoning levels, hardest first, which is what it says when it
#: is given one it has not got: `unknown effort level; use one of: xhigh, high, medium, low`.
#: Written as it enumerates them rather than as the fuller ladders beside it: a rung it
#: refuses is a turn that never starts, and it refuses one before it does anything else.
_GROK = ("xhigh", "high", "medium", "low")

#: What Qwen Code calls its reasoning levels, hardest first. It has no flag for them -- they
#: are a setting of its own `settings.json`, which is why a turn is pointed at one of ours.
_QWEN = ("max", "xhigh", "high", "medium", "low")

#: What opencode and mimocode call a reasoning effort: a variant of the model, given as
#: `--variant`, and provider-specific. These are the ones the models they front take; a
#: provider with no variants of its own takes the flag and ignores it.
_VARIANTS = ("xhigh", "high", "medium", "low", "minimal")

#: What a gateway is asked for, whichever backend is being pointed at one: where it is and
#: what it takes. Written once because it is one question -- an endpoint speaking a vendor's
#: protocol is the same arrangement whoever is dialling it.
_GATEWAY = (
    "an endpoint speaking this CLI's own protocol -- a proxy, a router, another vendor"
)

#: What Antigravity CLI calls its reasoning levels, hardest first.
_AGY = ("high", "medium", "low")

#: What Cursor calls a reasoning effort, hardest first. Not a flag of its own: its models are
#: parameterized, and how hard one thinks is written into the model it is asked for, as
#: `claude-opus-4-8[effort=high]` -- which is the spelling its own command line documents. The
#: three rungs are the ones its model list names, where a variant of a model carries the rung
#: in its name: `gpt-5-high`, `gpt-5-low-fast`, and the ones it says run at a fixed medium.
_CURSOR = ("high", "medium", "low")

#: What ZCode calls a thought level, hardest first. Two ladders rather than one, because its
#: models have two: the ones that take a budget are asked for `max`, `high` or `low`, and the
#: ones that only take thinking or no thinking are asked for `enabled` or `disabled`. `nothink`
#: is what the first kind calls the bottom of its own. They are one list here because a
#: backend's efforts are one list, and a model narrows it to the rungs it answered with.
_ZCODE = ("max", "high", "low", "enabled", "nothink", "disabled")

#: Every backend humanize drives, as each of them reported itself. Codex says which efforts
#: each of its models takes and they differ, so they are written down as it gave them.
PROFILES = (
    Profile(
        name="claude",
        # `WebSearch` and `WebFetch` are tools like any other to Claude, and
        # `--disallowedTools` is the flag that takes a tool away.
        searches=True,
        aliases=("claude", "claude-code"),
        home_var="CLAUDE_CONFIG_DIR",
        home_dir=".claude",
        logs=("projects/*/{ident}.jsonl", "projects/*/{ident}/subagents/**/*.jsonl"),
        efforts=_CLAUDE,
        # `ultracode` is real and undocumented, so the catalogue Claude Code answers with
        # will never name it: a model asked about keeps it whatever that list says.
        beyond=("ultracode",),
        # The skills a person installs, which is what there is to choose between: the ones
        # Claude ships with and the ones a plugin brought are the plugin's to say. Its own
        # two directories and no more -- it does not read the shared one, which is why a
        # skill kept there is symlinked into this. A turn is told which of these it may not
        # reach for, as `Skill(<name>)`.
        skills=("skills/*/SKILL.md",),
        works=(".claude/skills/*/SKILL.md",),
        # Where a flow's own skills go for the length of a session: the directory Claude
        # reads a project's skills out of, which is the one place a skill can be given to it
        # without touching what the person at this machine has installed.
        mounts=".claude/skills",
        # Three places, and the last of them is the one people forget: the session lives in
        # `.credentials.json`, the account it belongs to -- with the API key a run was
        # approved for beside it -- lives in `.claude.json`, which sits outside the home
        # directory until `CLAUDE_CONFIG_DIR` moves it inside, and the account Claude shares
        # with the vendor's other programs lives under `XDG_CONFIG_HOME`, which neither of
        # those moves. Both spellings of the second, so that a provider works whether or not
        # the home has been moved; and the third because a machine signed in there and
        # nowhere else would answer every provider's turns with its own account.
        creds=(
            ".credentials.json",
            ".claude.json",
            "~/.claude.json",
            "config/anthropic",
        ),
        # Everything else Claude Code would read an account out of: the two the ways already
        # name are there too, through `accounts()`. `ANTHROPIC_CONFIG_DIR` is an account for
        # the reason the others are -- it moves the shared configuration directory whole, and
        # a turn that read one this table had never heard of would be the wrong account.
        ambient=(
            "ANTHROPIC_CONFIG_DIR",
            "ANTHROPIC_CUSTOM_HEADERS",
            "ANTHROPIC_MODEL",
            "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
            "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
            "CLAUDE_CODE_USE_FOUNDRY",
            "CLAUDE_CODE_USE_GATEWAY",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_BEDROCK",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to an Anthropic account, as `claude auth login` does",
                argv=("claude", "auth", "login"),
            ),
            Way(
                name="token",
                about="a long-lived token, as `claude setup-token` prints one",
                asks=(
                    Asked(
                        env="CLAUDE_CODE_OAUTH_TOKEN",
                        about="the token `claude setup-token` printed",
                        secret=True,
                    ),
                ),
            ),
            Way(
                name="key",
                about="an Anthropic API key, from the console",
                asks=(
                    Asked(
                        env="ANTHROPIC_API_KEY",
                        about="the API key",
                        secret=True,
                    ),
                ),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(
                        env="ANTHROPIC_BASE_URL",
                        about="where it is, as a URL",
                    ),
                    # A bearer rather than a key: it is sent as `Authorization` and outranks
                    # the key, and it is the one an endpoint of somebody else's takes.
                    Asked(
                        env="ANTHROPIC_AUTH_TOKEN",
                        about="the token it takes",
                        secret=True,
                    ),
                ),
            ),
            Way(
                name="bedrock",
                about="Anthropic's models on an AWS account of yours",
                sets=(("CLAUDE_CODE_USE_BEDROCK", "1"),),
                asks=(
                    Asked(env="AWS_PROFILE", about="the AWS profile to run as"),
                    Asked(env="AWS_REGION", about="the region", fixed="us-east-1"),
                ),
            ),
            Way(
                name="vertex",
                about="Anthropic's models on a Google Cloud project of yours",
                sets=(("CLAUDE_CODE_USE_VERTEX", "1"),),
                asks=(
                    Asked(env="ANTHROPIC_VERTEX_PROJECT_ID", about="the project id"),
                    Asked(env="CLOUD_ML_REGION", about="the region", fixed="us-east5"),
                ),
            ),
        ),
    ),
    Profile(
        name="agy",
        aliases=("agy", "antigravity"),
        # Nothing moves it: no variable of its own, and neither `XDG_CONFIG_HOME` nor the
        # names its siblings use are read. Only the home directory it is under, and a hidden
        # flag. So there is no variable to name here, and `directory()` reads the one place.
        home_var="",
        home_dir=".gemini/antigravity-cli",
        # None: a conversation here is rows of a SQLite database whose payloads are protobuf,
        # so there is no log to read a run's cost out of as it is spent, and none to gather.
        logs=(),
        efforts=_AGY,
        # One place: the `skills/` of its own home, which is the global customization root it
        # loads whatever else it is doing. Its other root is `.agents` under the workspace,
        # and that one is not listed -- a turn is run as `--print`, which opens no project,
        # and a skill left there is a skill such a turn never sees. So nothing is mounted for
        # it either: what reads as a skill this agent has is a skill this agent has.
        skills=("skills/*/SKILL.md",),
        # What a sign-in leaves behind where there is no keyring to put it in -- a session on
        # a machine with no desktop, which is where a flow runs. The keyring is the first
        # choice and is not a path.
        creds=("antigravity-oauth-token",),
        ambient=(
            "AGY_ADC_AUTH",
            "CLOUD_CODE_URL",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a Google account, in a session opened for it",
                # It signs in from inside itself, so the way in is agy with the terminal
                # handed over: a headless turn then runs on what that left behind.
                argv=("agy",),
            ),
            Way(
                name="key",
                about="a Gemini API key, from AI Studio",
                asks=(Asked(env="GEMINI_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="adc",
                about="Google Application Default Credentials, for a service account",
                sets=(("AGY_ADC_AUTH", "1"),),
                asks=(
                    Asked(
                        env="GOOGLE_APPLICATION_CREDENTIALS",
                        about="the service account file, as a path",
                    ),
                ),
            ),
        ),
    ),
    Profile(
        name="codex",
        # `tools.web_search` is a setting of the app server, and is sent in both
        # directions: Codex searches nothing until it is asked to.
        searches=True,
        aliases=("codex",),
        home_var="CODEX_HOME",
        home_dir=".codex",
        logs=("sessions/**/rollout-*{ident}.jsonl",),
        efforts=_CODEX,
        # Four places, which is what `skills/list` answers with: its own home, the shared
        # one under yours, and both of the directories a project may keep them in. A turn is
        # given the ones left on, as `skills.config` says which are off.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".agents/skills/*/SKILL.md", ".codex/skills/*/SKILL.md"),
        # The shared one of its two, being the directory more than one of these CLIs has
        # agreed to read: a flow's skill mounted there is one whichever of them is driving.
        mounts=".agents/skills",
        # One file, whichever way it was signed into: the subscription's tokens and an API
        # key land in the same place, under the mode that says which of them is in force.
        creds=("auth.json",),
        # `CODEX_AUTHAPI_BASE_URL` is an account for the reason a key is: codex sends the
        # credential it was signed in with to whatever it names, so a turn run under a
        # provider with somebody's copy of it still exported would hand that provider's token
        # to somebody's endpoint.
        ambient=("CODEX_API_KEY", "CODEX_AUTHAPI_BASE_URL", "OPENAI_BASE_URL"),
        ways=(
            Way(
                name="login",
                about="sign in to a ChatGPT account, in a browser",
                argv=("codex", "login"),
            ),
            Way(
                name="device",
                about="the same, from a machine with no browser on it",
                argv=("codex", "login", "--device-auth"),
            ),
            Way(
                name="key",
                about="an OpenAI API key, which codex keeps in its own store",
                argv=("codex", "login", "--with-api-key"),
                # Read off stdin by the command, which writes it where it keeps its own: an
                # environment holding a second copy would be a second place to leak it.
                asks=(
                    Asked(
                        env="OPENAI_API_KEY",
                        about="the API key",
                        secret=True,
                        keep=False,
                    ),
                ),
                stdin="OPENAI_API_KEY",
            ),
            Way(
                name="token",
                about="an access token, which is how an organisation hands one out",
                argv=("codex", "login", "--with-access-token"),
                asks=(
                    Asked(
                        env="CODEX_ACCESS_TOKEN",
                        about="the access token",
                        secret=True,
                        keep=False,
                    ),
                ),
                stdin="CODEX_ACCESS_TOKEN",
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(env="CODEX_PROVIDER_URL", about="where it is, as a URL"),
                    Asked(
                        env="CODEX_PROVIDER_KEY", about="the key it takes", secret=True
                    ),
                    Asked(
                        env="CODEX_PROVIDER_WIRE",
                        about="the protocol it speaks: chat or responses",
                        fixed="chat",
                    ),
                ),
                # Codex takes a provider as settings rather than as variables, and `-c` is
                # how a setting is given for one run without writing anybody's config file.
                args=(
                    "-c",
                    "model_provider=humanize",
                    "-c",
                    "model_providers.humanize.name=humanize",
                    "-c",
                    "model_providers.humanize.base_url={CODEX_PROVIDER_URL}",
                    "-c",
                    "model_providers.humanize.env_key=CODEX_PROVIDER_KEY",
                    "-c",
                    "model_providers.humanize.wire_api={CODEX_PROVIDER_WIRE}",
                ),
            ),
        ),
    ),
    Profile(
        name="dsh",
        aliases=("dsh", "deepseek-harness"),
        home_var="DSH_HOME",
        home_dir=".dsh",
        # The Python SDK's bundled JSONL persistence groups sessions under one project
        # directory. humanize's composition keeps these logs uncompressed so the running
        # tally can read complete rows as they land.
        logs=("sessions/*/{ident}/session.jsonl",),
        efforts=_DSH,
        # None, and not for want of looking: the `dsh` command line reads `.dsh/skills` and
        # `.agents/skills`, but that is its web profile's own harness. What humanize drives is
        # the Python SDK, which carries no skills at all -- so a list here would be of skills
        # nothing in this session would ever load.
        ambient=("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
        ways=(
            Way(
                name="key",
                about="a DeepSeek API key, from the platform",
                asks=(Asked(env="DEEPSEEK_API_KEY", about="the API key", secret=True),),
            ),
        ),
    ),
    Profile(
        name="grok",
        # `web_search` and `web_fetch` are the two Grok Build already names where a
        # rung takes the reaching outside the workspace away.
        searches=True,
        # `grokbuild` among them because that is what the class driving it is called, and an
        # agent names its backend by its own class name.
        aliases=("grok", "grok-build", "grokbuild"),
        home_var="GROK_HOME",
        home_dir=".grok",
        # A directory per session, under one per directory the work was done in: the id names
        # the directory rather than a file, and `updates.jsonl` is the conversation itself --
        # the others beside it are the plan, the rewind points and what it was told.
        logs=("sessions/*/{ident}/updates.jsonl",),
        efforts=_GROK,
        # Eight places, which is what `grok inspect` answers with: its own home and the
        # shared one under yours, both of the directories a project may keep them in, and
        # the two other harnesses' directories it reads for compatibility -- at both tiers,
        # and on by default, as its own `Harness Compatibility` says.
        skills=("skills/*/SKILL.md",),
        shared=(
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".cursor/skills/*/SKILL.md",
        ),
        works=(
            ".grok/skills/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".cursor/skills/*/SKILL.md",
        ),
        # The shared one of the four, being the directory more than one of these CLIs has
        # agreed to read: a skill mounted there is a skill Codex and Kimi read too.
        mounts=".agents/skills",
        #
        # Two files: the accounts it has signed into, keyed by the way each was signed in, and
        # the tokens its MCP servers handed back, which are somebody else's and kept apart.
        creds=("auth.json", "mcp_credentials.json"),
        ambient=(
            "GROK_AUTH",
            "GROK_AUTH_PATH",
            "GROK_AUTH_PROVIDER_COMMAND",
            "GROK_CLI_CHAT_PROXY_BASE_URL",
            "GROK_CODE_XAI_API_KEY",
            "GROK_DEFAULT_MODEL",
            "GROK_MODELS_BASE_URL",
            "GROK_MODELS_LIST_URL",
            "GROK_OAUTH2_CLIENT_ID",
            "GROK_OAUTH2_ISSUER",
            "GROK_OIDC_CLIENT_ID",
            "GROK_OIDC_ISSUER",
            "GROK_XAI_API_BASE_URL",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to an xAI account, in a browser",
                argv=("grok", "login"),
            ),
            Way(
                name="device",
                about="the same, from a machine with no browser on it",
                argv=("grok", "login", "--device-auth"),
            ),
            Way(
                name="key",
                about="an xAI API key, from the console",
                asks=(Asked(env="XAI_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(
                        env="GROK_MODELS_BASE_URL",
                        about="where it is, as a URL: its models are listed at /models",
                    ),
                    Asked(env="XAI_API_KEY", about="the key it takes", secret=True),
                ),
            ),
            Way(
                name="oidc",
                about="your own identity provider, for an organisation that signs in through one",
                asks=(
                    Asked(env="GROK_OIDC_ISSUER", about="the issuer, as a URL"),
                    Asked(env="GROK_OIDC_CLIENT_ID", about="the client id"),
                ),
            ),
        ),
    ),
    Profile(
        name="kimi",
        aliases=("kimi", "kimi-code"),
        home_var="KIMI_CODE_HOME",
        home_dir=".kimi-code",
        logs=("server/events/{ident}.jsonl",),
        efforts=_KIMI,
        # Every model Kimi runs takes a turn as a fleet as well as as one agent: `swarmmax`
        # and `max` are the same thinking at two widths.
        swarms=True,
        # Kimi Code discovers both its own and the shared skill directories without a command
        # line flag, including for sessions served by `kimi web`. The shared project directory
        # is also where a flow can mount one skill for Claude, Codex or Kimi without installing
        # it into any of their homes.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".kimi-code/skills/*/SKILL.md", ".agents/skills/*/SKILL.md"),
        mounts=".agents/skills",
        #
        # A directory apiece: kimi keeps one file per endpoint it has signed into, named
        # after that endpoint, and a lock beside it that two of its processes rotate a
        # refresh token under. Both move together or a provider would refresh into the
        # other one's token.
        creds=("credentials", "oauth"),
        ambient=(
            "KIMI_API_KEY",
            "KIMI_BASE_URL",
            "KIMI_CODE_BASE_URL",
            "KIMI_CODE_CUSTOM_HEADERS",
            "KIMI_CODE_OAUTH_HOST",
            "KIMI_OAUTH_HOST",
            "KIMI_REGISTRY_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a Kimi account, by the code it prints",
                argv=("kimi", "login"),
            ),
            Way(
                name="model",
                about=_GATEWAY,
                # Kimi builds a whole provider out of these and makes it the default, in
                # memory: nothing is written to the config file it would otherwise be in.
                asks=(
                    Asked(
                        env="KIMI_MODEL_NAME", about="the model to run, as it names it"
                    ),
                    Asked(env="KIMI_MODEL_API_KEY", about="the key", secret=True),
                    Asked(env="KIMI_MODEL_BASE_URL", about="where it is, as a URL"),
                    Asked(
                        env="KIMI_MODEL_PROVIDER_TYPE",
                        about="the protocol it speaks: anthropic, openai or kimi",
                        fixed="openai",
                    ),
                ),
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
        efforts=_PI,
        # Two places, and both are yours: the `skills/` of its own home, and the shared one
        # under yours. Nothing under the workspace, though pi reads `.pi/skills` and
        # `.agents/skills` there too -- those are gated on the project having been trusted,
        # which is `--approve` and a person to press it, and a turn driven here is neither.
        # So a flow's skills are not mounted for pi: they would be copied into a directory
        # the session is not permitted to read, which is a mount that quietly does nothing.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        #
        # One file holding every provider it has been signed into, and the lock its own
        # processes serialize a refresh under.
        # Every provider pi knows reads its own key out of the environment, and an agent under
        # a provider must not be handed one of somebody else's. The vendors' own names, which
        # is what pi looks for; a provider that wants one sets it itself.
        creds=("auth.json", "auth.json.lock"),
        ambient=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_OAUTH_TOKEN",
            "DEEPSEEK_API_KEY",
            "GEMINI_API_KEY",
            "GROQ_API_KEY",
            "MISTRAL_API_KEY",
            "MOONSHOT_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "XAI_API_KEY",
            "ZAI_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="pi's own /login, in a session opened for it",
                # pi signs in from inside itself, so the way in is pi, handed the terminal:
                # `/login`, whichever provider, and `/exit` when it has landed.
                argv=("pi",),
            ),
        ),
    ),
    Profile(
        name="qwen",
        # `web_search` and `web_fetch` are what Qwen Code calls the two, and
        # `--exclude-tools` is what it takes a tool away with.
        searches=True,
        aliases=("qwen", "qwen-code"),
        home_var="QWEN_HOME",
        home_dir=".qwen",
        # One file per session, named for the session and nothing else, under a directory per
        # directory the work was done in.
        logs=("projects/*/chats/{ident}.jsonl",),
        efforts=_QWEN,
        # Four places: its own home and the shared one under yours, and both of the
        # directories a project may keep them in -- `.qwen` and `.agents`, which is the pair
        # its own loader is written in terms of. The ones it ships with itself are not among
        # them: those are the CLI's, not a person's to add to or switch off.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".qwen/skills/*/SKILL.md", ".agents/skills/*/SKILL.md"),
        # The shared one of its two, so a flow's skills reach it there.
        mounts=".agents/skills",
        #
        # What its own sign-in leaves behind, and the lock two of its processes rotate the
        # token under. Everything else it runs as is a variable.
        creds=("oauth_creds.json", "oauth_creds.lock"),
        ambient=(
            "OPENAI_API_BASE",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "QWEN_API_KEY",
            "QWEN_BASE_URL",
            "QWEN_CODE_MODEL",
            "QWEN_MODEL",
            "QWEN_OAUTH_MODELS",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a Qwen account, in a session opened for it",
                # It signs in from inside itself, so the way in is qwen with the terminal
                # handed over: `/auth`, whichever provider, and `/quit` when it has landed.
                argv=("qwen",),
            ),
            Way(
                name="key",
                about="a key for the OpenAI-compatible endpoint it runs against",
                asks=(
                    Asked(env="OPENAI_API_KEY", about="the API key", secret=True),
                    Asked(
                        env="OPENAI_BASE_URL",
                        about="where it is, as a URL",
                        fixed="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    ),
                ),
            ),
        ),
    ),
    Profile(
        name="opencode",
        # `webfetch` is the one reaching-out tool opencode names, and its permission
        # table is where each tool is allowed or denied.
        searches=True,
        aliases=("opencode",),
        # No home variable of its own: it keeps its data where every other program does, in a
        # directory of its own under the one `XDG_DATA_HOME` names.
        home_var="XDG_DATA_HOME",
        home_in="opencode",
        home_dir=".local/share/opencode",
        # None: a session here is rows of a database rather than a file, so there is no log to
        # read a run's cost out of as it is spent, and none to gather afterwards.
        logs=(),
        efforts=_VARIANTS,
        # Its own are under the configuration home rather than the data home this backend is
        # otherwise kept under -- `~/.config/opencode`, where its `opencode.json` is, not
        # `~/.local/share/opencode`, where its sessions and its logins are. Singular and
        # plural both: it reads `skill/` and `skills/` wherever it reads either.
        config=("opencode/skills/*/SKILL.md", "opencode/skill/*/SKILL.md"),
        # And the two it auto-loads from outside its own directories, which it calls external
        # skills: another harness's, and the shared one.
        shared=(".agents/skills/*/SKILL.md", ".claude/skills/*/SKILL.md"),
        works=(
            ".opencode/skills/*/SKILL.md",
            ".opencode/skill/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
        ),
        # The shared one of its three, as for the others that read it.
        mounts=".agents/skills",
        # One file per kind of thing signed into: the providers in one, the servers a session
        # reaches out to in the other.
        creds=("auth.json", "mcp-auth.json"),
        # The one that would bypass the file outright, and the vendors' own names it reads a
        # key under. Its catalogue knows a hundred and eighty of those; these are the ones a
        # machine is likely to be carrying already.
        ambient=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "DEEPSEEK_API_KEY",
            "GEMINI_API_KEY",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "OPENCODE_AUTH_CONTENT",
            "OPENCODE_CONFIG_CONTENT",
            "OPENROUTER_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="opencode's own provider list, and whichever way that one takes",
                argv=("opencode", "auth", "login"),
            ),
            Way(
                name="wellknown",
                about="a provider that hands out its own credential, by URL",
                argv=("opencode", "auth", "login", "{OPENCODE_WELLKNOWN}"),
                asks=(
                    Asked(
                        env="OPENCODE_WELLKNOWN",
                        about="the URL to ask, which answers at /.well-known/opencode",
                        keep=False,
                    ),
                ),
            ),
            Way(
                name="zen",
                about="an OpenCode Zen key, which its own models run on",
                asks=(Asked(env="OPENCODE_API_KEY", about="the key", secret=True),),
            ),
        ),
    ),
    Profile(
        name="mimo",
        # mimocode is opencode's, permission table and all.
        searches=True,
        aliases=("mimo", "mimocode", "mimo-code"),
        home_var="XDG_DATA_HOME",
        home_in="mimocode",
        home_dir=".local/share/mimocode",
        logs=(),
        efforts=_VARIANTS,
        # The same arrangement as opencode, which it is a fork of, and one directory more:
        # it reads Codex's as well as Claude Code's. The ones it ships under its own data
        # home -- its builtins, and the bundle its compose flows work by -- are not listed:
        # those came with the CLI rather than from whoever is running it.
        config=("mimocode/skills/*/SKILL.md", "mimocode/skill/*/SKILL.md"),
        shared=(
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".codex/skills/*/SKILL.md",
        ),
        works=(
            ".mimocode/skills/*/SKILL.md",
            ".mimocode/skill/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".codex/skills/*/SKILL.md",
        ),
        mounts=".agents/skills",
        creds=("auth.json", "mcp-auth.json"),
        ambient=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "MIMOCODE_AUTH_CONTENT",
            "MIMOCODE_CONFIG_CONTENT",
            "MIMO_API_KEY",
            "OPENAI_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="mimocode's own provider list, and whichever way that one takes",
                argv=("mimo", "auth", "login"),
            ),
            Way(
                name="key",
                about="a MiMo key, which its own models run on",
                asks=(Asked(env="XIAOMI_API_KEY", about="the key", secret=True),),
            ),
        ),
    ),
    Profile(
        name="zcode",
        # `WebFetch` and `WebSearch` are the two tools it reaches outside the workspace with,
        # and a session may be opened with a denylist naming them.
        searches=True,
        aliases=("zcode", "zcode-cli"),
        # None: its configuration, its sessions and its skills are all under `~/.zcode`, and
        # the one variable it does read moves the part the desktop app shares rather than the
        # part a turn runs out of. What moves the whole of it is `HOME`.
        home_var="",
        home_dir=".zcode",
        # One file per session, a line per request the turn made: what was sent, what came
        # back and what it cost. Under `cli/`, which is where the command line keeps what is
        # its own rather than the desktop app's.
        logs=("cli/rollout/model-io-{ident}.jsonl",),
        efforts=_ZCODE,
        # Four places, which is what `zcode skills list` answers with: its own directory and
        # the shared one under your home, and the same pair under the project. Both tiers, and
        # no flag to turn either off.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".zcode/skills/*/SKILL.md", ".agents/skills/*/SKILL.md"),
        # The shared one of its two, being the directory more than one of these CLIs has
        # agreed to read: a skill mounted there is a skill Codex and Kimi read too.
        mounts=".agents/skills",
        # One file, and the desktop app's rather than the command line's: a login is shared
        # between them, encrypted with a key derived from this machine and this user.
        creds=("v2/credentials.json",),
        ambient=(
            # Its own, which outrank the file whichever way it was signed in.
            "ZCODE_API_KEY",
            "ZCODE_BASE_URL",
            "ZCODE_CREDENTIAL_SECRET",
            "ZCODE_DATA_BASE_DIR",
            "ZCODE_ENDPOINT_ORIGIN",
            # And the vendors' own names, which it reads a key under for a provider speaking
            # that vendor's protocol -- which the Z.AI plan it ships with is one of.
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "ZAI_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a Z.AI account, in a browser",
                argv=("zcode", "login"),
            ),
            Way(
                name="device",
                about="the same, from a machine with no browser on it",
                argv=("zcode", "login", "--no-browser"),
            ),
            Way(
                name="key",
                about="a Z.AI or BigModel coding plan key, which its own models run on",
                asks=(Asked(env="ZCODE_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(env="ZCODE_BASE_URL", about="where it is, as a URL"),
                    Asked(env="ZCODE_API_KEY", about="the key it takes", secret=True),
                ),
            ),
        ),
    ),
    Profile(
        name="cursor",
        # Its own command line has no way of taking a tool away: what an agent may reach for
        # is `~/.cursor/cli-config.json`, which is the person at this machine's file and not
        # one a driver writes. So web search is refused off here rather than said and ignored.
        searches=False,
        # Installed under two names, `agent` being the one its installer calls primary and
        # `cursor-agent` the one it has always also written. The second, because `agent` is a
        # name anything on a machine could have taken and this one has to be that CLI.
        command="cursor-agent",
        aliases=("cursor", "cursor-agent", "cursor-cli"),
        # Its own variable, else the directory every program keeps its configuration in, else
        # `~/.cursor` -- which is what `config` below covers the middle of.
        home_var="CURSOR_CONFIG_DIR",
        home_dir=".cursor",
        # None to read: a chat is kept in the agent store rather than as a file per session,
        # so there is no trajectory here for a trace to gather.
        logs=(),
        efforts=_CURSOR,
        # Both tiers, under the layout every one of these CLIs reads a skill in. It reads
        # several other CLIs' directories too, and those are theirs rather than this one's.
        skills=("skills/*/SKILL.md",),
        config=("cursor/skills/*/SKILL.md",),
        works=(".cursor/skills/*/SKILL.md",),
        mounts=".cursor/skills",
        # What a login leaves behind, beside the settings it keeps in the same directory.
        creds=("cli-config.json", "auth.json"),
        ambient=(
            "CURSOR_API_ENDPOINT",
            "CURSOR_API_KEY",
            "CURSOR_API_URL",
            "CURSOR_AUTH_TOKEN",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a Cursor account, in a browser",
                argv=("cursor-agent", "login"),
            ),
            Way(
                name="key",
                about="a Cursor API key, from the dashboard",
                asks=(Asked(env="CURSOR_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(env="CURSOR_API_ENDPOINT", about="where it is, as a URL"),
                    Asked(env="CURSOR_API_KEY", about="the key it takes", secret=True),
                ),
            ),
        ),
    ),
)


#: Where the CLIs somebody added themselves are written down, under humanize's own home. A
#: file rather than a setting of one workspace: a CLI is installed on a machine, and a flow
#: run in the next directory along is run against the same one.
_SPOKEN = "acp.json"

#: What is offered for a CLI that speaks only the Agent Client Protocol. The protocol says
#: nothing about which models an agent runs or how hard it may be asked to think -- both are
#: the agent's own -- so one of each is offered and neither is sent.
_UNSAID = "as configured"


def _spoken() -> Path:
    """Where the added CLIs are kept."""
    from hmz import home

    return home() / _SPOKEN


def speaking() -> dict[str, tuple[str, ...]]:
    """Every CLI somebody has added, and the command that starts each one.

    Returns:
      One entry per CLI, by the name it was added under, holding the command to run. Nothing
      at all where none has been added or where what was written cannot be read back -- a
      file nobody can read is a list to fill rather than a reason to refuse to start.
    """
    import json

    try:
        held = json.loads(_spoken().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(held, dict):
        return {}
    found: dict[str, tuple[str, ...]] = {}
    for name, argv in cast("dict[str, object]", held).items():
        if not isinstance(argv, list):
            continue
        given = tuple(str(one) for one in cast("list[object]", argv))
        if given:
            found[name] = given
    return found


def remember(name: str, command: Sequence[str]) -> None:
    """Writes down a CLI that speaks the protocol, so that it is a backend from now on.

    Args:
      name: What to call it, which is what an `-a` will name and what the prompt will show.
        The command it is installed as, by convention, since that is how every other backend
        here is named.
      command: What to run to start it, as argv -- `["my-agent", "--acp"]`. There is no
        discovery in the protocol and no flag every agent agrees on, so this is asked for.

    Raises:
      ValueError: If it is not named, has no command, or would shadow a backend humanize
        already drives -- two backends answering to one name is a name nobody can resolve.
    """
    import json

    named_as = name.strip()
    argv = [str(one) for one in command if str(one).strip()]
    if not named_as or not argv:
        raise ValueError("an added CLI needs a name and a command to start it with")
    if any(named_as in one.aliases for one in PROFILES):
        raise ValueError(f"{named_as} is already a backend humanize drives")
    held = speaking()
    held[named_as] = tuple(argv)
    at = _spoken()
    at.parent.mkdir(parents=True, exist_ok=True)
    # Whole and then moved into place, so that a list read while it is being written is
    # either the old one or the new one and never half of each.
    beside = at.parent / f".{at.name}.new"
    beside.write_text(
        json.dumps({one: list(argv) for one, argv in held.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    beside.replace(at)


def forget(name: str) -> bool:
    """Takes an added CLI away again.

    Args:
      name: What it was added under.

    Returns:
      Whether there was one to take away.
    """
    import json

    held = speaking()
    if name not in held:
        return False
    del held[name]
    at = _spoken()
    at.write_text(
        json.dumps({one: list(argv) for one, argv in held.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def profiles() -> tuple[Profile, ...]:
    """Every backend there is: the ones humanize drives, and the ones somebody added.

    Read each time rather than settled at import: a CLI added at the prompt is a backend from
    that moment, and a list built once would be a list that says otherwise until the next run.

    Returns:
      The built-in profiles in their own order, and then the added ones in the order they
      were written down.
    """
    return (*PROFILES, *(_speaks(name) for name in speaking()))


def _speaks(name: str) -> Profile:
    """The profile of a CLI known only by the protocol it speaks.

    Args:
      name: What it was added under.

    Returns:
      A profile saying the little there is to say: it has no home humanize can find, no logs
      it can read, and one rung of an effort ladder, because the protocol describes none of
      those. What it does have is a name to be chosen by.
    """
    return Profile(
        name=name,
        aliases=(name,),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(_UNSAID,),
    )


#: The credentials more than one of these backends runs on, and what each of them calls one.
#: A vendor's key is the vendor's rather than the CLI's -- an Anthropic key is an Anthropic
#: key whether Claude Code, pi, opencode or mimocode is holding it -- so an account made for
#: one backend is an account the others could be run as too.
#:
#: One entry per credential, holding every name it goes by. Most go by one: the variable is
#: the vendor's own and every CLI that reads it reads it under that name. The ones with two
#: are where a CLI named a vendor's credential after itself.
#:
#: Which backends actually read each of them is not written here: it is already written, as
#: what each backend's ways ask for and what it says it would take an account from. This is
#: only the sameness -- that `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_OAUTH_TOKEN` are one
#: subscription under two names.
ALIKE: tuple[tuple[str, ...], ...] = (
    ("ANTHROPIC_API_KEY",),
    ("ANTHROPIC_AUTH_TOKEN",),
    ("ANTHROPIC_BASE_URL",),
    ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN"),
    ("DEEPSEEK_API_KEY",),
    ("DEEPSEEK_BASE_URL",),
    ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
    ("OPENAI_API_KEY",),
    ("OPENAI_BASE_URL", "OPENAI_API_BASE"),
    ("XAI_API_KEY", "GROK_CODE_XAI_API_KEY"),
)


def alike(variable: str) -> tuple[str, ...]:
    """Every name one credential goes by, across the backends that read it.

    Args:
      variable: What one of them calls it.

    Returns:
      All of its names, that one included, and just that one for a credential nothing else
      has a name for.
    """
    for held in ALIKE:
        if variable in held:
            return held
    return (variable,)


def serves(env: Mapping[str, str], backend: str) -> dict[str, str] | None:
    """What one account would be, spelled as another backend reads it.

    A vendor's key is the vendor's: an account made as an Anthropic key is an account pi,
    opencode and mimocode could each be run as, under whatever each of them calls it. What
    cannot travel is an account that is not variables at all -- a subscription signed into
    writes the CLI's own credential store, in that CLI's own format, and nothing else reads
    it.

    Args:
      env: What a turn under the account is run with.
      backend: The backend it would be copied to, by any name it answers to.

    Returns:
      The same account under the names that backend reads, or None where it could not be run
      as that backend at all -- because the backend is not one humanize drives, because the
      account holds nothing but files, or because one of the things it holds is a credential
      that backend has no name for.
    """
    profile = named(backend)
    if profile is None or not env:
        return None
    reads = profile.accounts()
    held: dict[str, str] = {}
    for variable, value in env.items():
        under = next((one for one in alike(variable) if one in reads), "")
        if not under:
            return None
        held[under] = value
    return held


def named(backend: str) -> Profile | None:
    """The backend a name stands for, whichever of its spellings was used.

    Args:
      backend: What it was called.

    Returns:
      Its profile, or None for a name no backend answers to.
    """
    return next((one for one in profiles() if backend in one.aliases), None)


#: Where a coding agent's CLI lands when it is installed, besides wherever `PATH` names. A flow
#: is not always started from a shell somebody set up: a notebook kernel, a service, the
#: launcher of a runtime platform each hand their child the `PATH` they were given, and one
#: that is missing the directory an installer wrote to would make an agent that is installed
#: read as one that is not. Looked in after `PATH`, so whatever somebody put in front stays in
#: front, and only for a name -- a command given as a path is that path or nothing.
_INSTALLED_AT = (
    "~/.local/bin",  # where an installer run as a person puts it
    "/usr/local/bin",  # and where one run as root does
    "/opt/homebrew/bin",  # homebrew on apple silicon, which a bare login shell misses
    "/usr/bin",
    "/bin",
)


def program(command: str) -> str | None:
    """The program a backend's command runs, as the path to actually spawn.

    Args:
      command: What the CLI is installed as -- `codex` -- or a path to it.

    Returns:
      The program to run, and None where there is none: a name `PATH` does not have and no
      installer left anywhere this looks is a backend that is not installed here.
    """
    if os.sep in command:
        return command if _runnable(Path(command)) else None
    return shutil.which(command) or elsewhere(command)


def elsewhere(command: str) -> str | None:
    """Where a CLI is installed, for a command this machine's `PATH` does not name.

    Args:
      command: What the CLI is installed as.

    Returns:
      The path to run instead, and None for a command `PATH` already names -- which is run by
      the name it was written with, exactly as it always was -- and for one nothing has
      installed anywhere this looks.
    """
    if os.sep in command or shutil.which(command) is not None:
        return None
    return next(
        (
            str(at)
            for directory in _INSTALLED_AT
            if _runnable(at := Path(directory).expanduser() / command)
        ),
        None,
    )


def _runnable(path: Path) -> bool:
    """Whether that path is a program this machine would run."""
    return path.is_file() and os.access(path, os.X_OK)


def read(
    spec: str,
) -> tuple[
    Profile, str, str, str, str, str | None, bool | None, tuple[tuple[str, str], ...]
]:
    """Reads one `-a` into the backend to drive, what to drive it at, and as whom.

    Args:
      spec: `CLI/MODEL:EFFORT`, or `cli=CLI,model=MODEL,effort=EFFORT` written out -- which is
        where a model or an effort holding the punctuation the short form separates on goes.
        The CLI may name a provider after an `@`, as `claude@deepseek/MODEL:EFFORT`, which is
        the account that agent's turns run as; `provider=` says the same thing written out.
        The written-out form may also name the common provider latency tier as
        `service_tier=`, the agent's permission rung as `permission=`, and backend-native
        settings as `config.KEY=VALUE`. Codex accepts app-server overrides and Claude one
        exact `allowed_tools` rule. `web_search=` says whether the agent may search the web,
        as `on` or `off`.

    Returns:
      The backend, model, effort, common service tier, provider -- which is "" for an agent
      that runs as whoever is at this machine already runs its CLI -- permission, which is
      None at the default rung, whether it may search the web, which is None where nobody
      said, and the `config.KEY` pairs, which is () where none were named.

    Raises:
      ValueError: If it is neither spelling, or names no backend there is. What it says is
        what a command line reports after the agent it could not read.
    """
    provider = ""
    service_tier = "default"
    permission: str | None = None
    searching: str | None = None
    overrides: list[tuple[str, str]] = []
    if "=" in spec:
        given = {
            key.strip(): value.strip()
            for key, _, value in (part.partition("=") for part in spec.split(","))
        }
        backend, model, effort, service_tier, provider, permission, searching = (
            given.pop("cli", ""),
            given.pop("model", ""),
            given.pop("effort", ""),
            given.pop("service_tier", "default"),
            given.pop("provider", ""),
            given.pop("permission", None),
            given.pop("web_search", None),
        )
        for key, value in list(given.items()):
            if key.startswith("config."):
                name = key.removeprefix("config.")
                if not name:
                    raise ValueError("expected config.KEY=VALUE")
                overrides.append((name, value))
                del given[key]
        if given:
            raise ValueError(
                f"{', '.join(sorted(given))} is not cli, model, effort, service_tier, "
                "provider, permission, web_search or config.KEY"
            )
    else:
        # Read from both ends: a model may hold slashes of its own -- Kimi Code's and
        # opencode's are `provider/id` -- while a CLI and an effort never do.
        backend, _, rest = spec.partition("/")
        model, _, effort = rest.rpartition(":")
    # The account, if one was named: a CLI is never spelled with an `@` in it, so the two are
    # told apart wherever the agent was written -- `-a`, a settings file, an interface. An
    # `@` with nothing after it is a line to correct rather than a line saying nothing: it
    # was typed to name an account, and running as whoever is at this machine is not that.
    backend, at, said = backend.partition("@")
    if at and not said.strip():
        raise ValueError(
            "expected an account after @, as in claude@deepseek/MODEL:EFFORT"
        )
    provider = said.strip() if at else provider
    profile = named(backend.strip())
    if profile is None or not model.strip() or not effort.strip():
        raise ValueError(
            "expected CLI[@PROVIDER]/MODEL:EFFORT or "
            "cli=CLI,model=MODEL,effort=EFFORT[,service_tier=SERVICE_TIER]"
            "[,provider=PROVIDER]"
            "[,permission=PERMISSION][,web_search=on|off][,config.KEY=VALUE]"
        )
    if not service_tier.strip():
        raise ValueError("service_tier cannot be empty")
    if overrides and profile.name not in {"claude", "codex"}:
        raise ValueError("config.KEY is only for Claude or Codex")
    if profile.name == "claude" and any(
        key != "allowed_tools" for key, _value in overrides
    ):
        raise ValueError("Claude config only accepts allowed_tools")
    return (
        profile,
        model.strip(),
        effort.strip(),
        service_tier.strip(),
        provider.strip(),
        permission,
        _switched(searching),
        tuple(overrides),
    )


def _switched(said: str | None) -> bool | None:
    """One on-or-off setting as it was written out, or nothing where nobody wrote it.

    The words are the ones every switch here is written with, and nothing else is taken: a
    line that meant off and was spelled some other way is a line to correct rather than a
    setting quietly left on.

    Args:
      said: What was written, or None where the setting was not named at all.

    Returns:
      True, False, or None for a setting nobody said anything about.

    Raises:
      ValueError: If it was said and is neither word.
    """
    if said is None:
        return None
    held = {
        "on": True,
        "true": True,
        "yes": True,
        "off": False,
        "false": False,
        "no": False,
    }.get(said.strip().lower())
    if held is None:
        raise ValueError(f"web_search must be on or off, not {said!r}")
    return held
