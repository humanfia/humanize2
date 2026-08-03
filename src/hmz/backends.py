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

Nothing is imported to read this, which is what lets `hmz collect` and the prompt's model list
have it without paying for the agents themselves. The code that acts on a fact lives where its
purpose does: driving in :mod:`hmz.agents`, reading back in :mod:`hmz.tracing`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PROFILES", "Asked", "Model", "Profile", "Way", "named", "read"]


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
        `opus` is whichever Opus is newest today and something else tomorrow, so a cycle that
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
      efforts: How hard this backend can be asked to think, hardest first, in its own wording.
        The whole ladder it has words for; a model of it takes some of them, and which ones is
        the backend's to say when it is asked what it runs.
      beyond: The rungs of that ladder it takes but does not list -- a way of running a model
        that is real and undocumented. Written here because no listing of the backend's own
        will ever name one, so a model asked about would otherwise lose it.
      swarms: Whether a turn of this backend also runs as a fleet of subagents rather than as
        one agent. A property of the backend rather than of a model: it is a way of taking a
        turn, and every model that takes turns here takes them that way too.
      creds: What a login to this backend leaves behind: the paths it reads its credentials
        back out of and writes its refreshed ones to. One under this backend's home per entry,
        or one under the user's own home where the entry starts with `~/` -- which is where
        some of them keep a second file. A directory names everything inside it. These are the
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
    home_in: str = ""
    skills: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    works: tuple[str, ...] = ()
    beyond: tuple[str, ...] = ()
    swarms: bool = False
    creds: tuple[str, ...] = ()
    ways: tuple[Way, ...] = ()
    ambient: tuple[str, ...] = ()

    def directory(self) -> Path:
        """Where this backend keeps its state and its logs, wherever it has been moved to.

        Returns:
          The home directory. It may not exist: a backend that has never run has none.
        """
        moved = os.environ.get(self.home_var)
        return Path(moved) / self.home_in if moved else Path.home() / self.home_dir

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

    def credentials(self) -> tuple[tuple[str, str], ...]:
        """Every path this backend keeps a credential at, and where it is kept relative to.

        Read here rather than written down twice: a path under the backend's own home moves
        with the variable that moves the home, and one written `~/...` is under the user's own
        wherever that home went.

        Returns:
          One `(absolute path, name to keep it under)` pair per credential, the name being the
          path with the root it is under taken off -- `home/...` for the backend's own and
          `user/...` for the user's, so that two files of the same name are two files.
        """
        held: list[tuple[str, str]] = []
        for said in self.creds:
            if said.startswith("~/"):
                held.append((str(Path.home() / said[2:]), f"user/{said[2:]}"))
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

#: Every backend humanize drives, as each of them reported itself. Codex says which efforts
#: each of its models takes and they differ, so they are written down as it gave them.
PROFILES = (
    Profile(
        name="claude",
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
        # Two files, and the second of them is the one people forget: the session lives in
        # `.credentials.json`, and the account it belongs to -- with the API key a run was
        # approved for beside it -- lives in `.claude.json`, which sits outside the home
        # directory until `CLAUDE_CONFIG_DIR` moves it inside. Both spellings, so that a
        # provider works whether or not the home has been moved.
        creds=(".credentials.json", ".claude.json", "~/.claude.json"),
        # Everything else Claude Code would read an account out of: the two the ways already
        # name are there too, through `accounts()`.
        ambient=(
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
        name="codex",
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
        # One file, whichever way it was signed into: the subscription's tokens and an API
        # key land in the same place, under the mode that says which of them is in force.
        creds=("auth.json",),
        ambient=("CODEX_API_KEY", "OPENAI_BASE_URL"),
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
        name="kimi",
        aliases=("kimi", "kimi-code"),
        home_var="KIMI_CODE_HOME",
        home_dir=".kimi-code",
        logs=("server/events/{ident}.jsonl",),
        efforts=_KIMI,
        # Every model Kimi runs takes a turn as a fleet as well as as one agent: `swarmmax`
        # and `max` are the same thinking at two widths.
        swarms=True,
        # None named: `--skills-dir` is a flag of the command line, and a session here is a
        # thread on `kimi web`, which takes none. A skill Kimi finds is a skill it loads, so
        # there is nothing here to be offered a choice about.
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
        # None named: pi is told which skills to load rather than which to leave, by the path
        # of each, and it finds none of its own to be left out of that -- there is no
        # directory it reads them from, so there is nothing here to offer a choice about.
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
        efforts=_VARIANTS,
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
        aliases=("mimo", "mimocode", "mimo-code"),
        home_var="XDG_DATA_HOME",
        home_in="mimocode",
        home_dir=".local/share/mimocode",
        logs=(),
        efforts=_VARIANTS,
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
)


def named(backend: str) -> Profile | None:
    """The backend a name stands for, whichever of its spellings was used.

    Args:
      backend: What it was called.

    Returns:
      Its profile, or None for a name no backend answers to.
    """
    return next((one for one in PROFILES if backend in one.aliases), None)


def read(spec: str) -> tuple[Profile, str, str, str, str | None]:
    """Reads one `-a` into the backend to drive, what to drive it at, and as whom.

    Args:
      spec: `CLI/MODEL:EFFORT`, or `cli=CLI,model=MODEL,effort=EFFORT` written out -- which is
        where a model or an effort holding the punctuation the short form separates on goes.
        The CLI may name a provider after an `@`, as `claude@deepseek/MODEL:EFFORT`, which is
        the account that agent's turns run as; `provider=` says the same thing written out.
        The written-out form may also name the agent's permission rung as `permission=`.

    Returns:
      The backend, the model, the effort, the provider -- which is "" for an agent that runs
      as whoever is at this machine already runs its CLI -- and the permission, which is None
      for an agent that runs at the default rung.

    Raises:
      ValueError: If it is neither spelling, or names no backend there is. What it says is
        what a command line reports after the agent it could not read.
    """
    provider = ""
    permission: str | None = None
    if "=" in spec:
        given = {
            key.strip(): value.strip()
            for key, _, value in (part.partition("=") for part in spec.split(","))
        }
        backend, model, effort, provider, permission = (
            given.pop("cli", ""),
            given.pop("model", ""),
            given.pop("effort", ""),
            given.pop("provider", ""),
            given.pop("permission", None),
        )
        if given:
            raise ValueError(
                f"{', '.join(sorted(given))} is not cli, model, effort, provider or permission"
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
            "cli=CLI,model=MODEL,effort=EFFORT[,provider=PROVIDER]"
            "[,permission=PERMISSION]"
        )
    return profile, model.strip(), effort.strip(), provider.strip(), permission
