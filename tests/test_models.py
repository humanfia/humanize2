"""What each backend runs, asked of that backend and kept per account.

Every backend here is a stand-in first on PATH, printing what the real one prints: the point
of this module is that nothing is written down, so what is checked is that each backend's own
way of being asked is read the way that backend answers it.
"""

from __future__ import annotations

import contextlib
import json
import os
import socketserver
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

from hmz import backends, models, providers
from hmz.backends import named
from tests.supervising import traced

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("asking")


@pytest.fixture(autouse=True)
def _no_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaves no endpoint of whoever is running this suite for a test to go and ask.

    Asking one is right, and reaching anybody's network from a suite is not. Every base URL
    a backend would read is taken away here, so a test about the asking asks a loopback
    server it started itself and every other one falls back to its stand-in CLI.
    """
    for profile in backends.PROFILES:
        if profile.endpoint:
            monkeypatch.delenv(profile.endpoint, raising=False)


#: What Claude Code answers the control request with: the default under its own name as well
#: as under `default`, a window written on the end of an id, and one model that takes no
#: effort at all.
CLAUDE = json.dumps(
    {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "models",
            "response": {
                "models": [
                    {
                        "value": "default",
                        "resolvedModel": "claude-nine[1m]",
                        "supportedEffortLevels": ["low", "high", "max"],
                    },
                    {
                        "value": "claude-nine[1m]",
                        "resolvedModel": "claude-nine",
                        "supportedEffortLevels": ["low", "high", "max"],
                    },
                    {"value": "haiku", "resolvedModel": "claude-quick"},
                ]
            },
        },
    }
)

#: What Claude answers when somebody has set `ANTHROPIC_CUSTOM_MODEL_OPTION` themselves. The
#: resolved id is deliberately a different name: the alias is the one they chose and the one
#: `--model` takes, so it is the one a catalogue keeps.
CLAUDE_CUSTOM = json.dumps(
    {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": "models",
            "response": {
                "models": [
                    {
                        "value": "fable",
                        "resolvedModel": "claude-fable-5",
                        "description": "Custom model (fable)",
                        "supportedEffortLevels": ["high", "max"],
                    }
                ]
            },
        },
    }
)

#: What `codex debug models` renders: the efforts per model, and the ones it does not offer.
CODEX = json.dumps(
    {
        "models": [
            {
                "slug": "gpt-nine",
                "visibility": "list",
                "supported_reasoning_levels": [
                    {"effort": "low"},
                    {"effort": "high"},
                    {"effort": "ultra"},
                ],
            },
            {
                "slug": "gpt-eight",
                "visibility": "list",
                "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
            },
            {
                "slug": "gpt-hidden",
                "visibility": "hide",
                "supported_reasoning_levels": [{"effort": "low"}],
            },
        ]
    }
)

#: What `kimi provider list --json` dumps: the models are the keys, and only some of them say
#: which efforts they take.
KIMI = json.dumps(
    {
        "providers": {"managed:kimi-code": {"type": "kimi"}},
        "models": {
            "kimi-code/kthree": {
                "provider": "managed:kimi-code",
                "supportEfforts": ["low", "high", "max"],
            },
            "kimi-code/kold": {"provider": "managed:kimi-code"},
        },
    }
)

#: What `pi --list-models` prints, which is a table with the columns named across the top.
PI = """\
provider      model     context  max-out  thinking  images
openai-codex  gpt-nine  272K     128K     yes       yes
anthropic     opus-ten  200K     64K      yes       yes
"""

#: What `agy models` prints: a slug and the name its own picker shows, two columns a line --
#: and the slug carries the effort, since it lists a model at three efforts as three models.
AGY = """gemini-nine-high	Gemini Nine (High)
gemini-nine-low	Gemini Nine (Low)
claude-sonnet-nine	Claude Sonnet Nine (Thinking)
"""

#: What `zcode app-server --stdio` answers `workspace/readState` with. Its command line has no
#: `models`: a model there belongs to a provider its configuration names, and the app server is
#: what resolves the one into the other. The thought levels are the model's own, and its models
#: really do have two vocabularies of them.
ZCODE = (
    json.dumps(
        {
            "id": "server-1",
            "method": "interaction/requestOfficialMcpAuthHeaders",
            "params": {"mcpKey": "image_search"},
        }
    )
    + "\n"
    + json.dumps(
        {
            "id": 1,
            "result": {
                "modelCatalog": {
                    "available": [
                        {
                            "ref": {"providerId": "zai", "modelId": "glm-nine"},
                            "label": "GLM Nine",
                            "reasoning": {
                                "enabled": True,
                                "levels": [
                                    {"value": "low", "label": "low"},
                                    {"value": "high", "label": "high"},
                                    {"value": "max", "label": "max"},
                                ],
                            },
                        },
                        {
                            "ref": {"providerId": "zai", "modelId": "glm-quick"},
                            "label": "GLM Quick",
                            "reasoning": {
                                "enabled": True,
                                "levels": [
                                    {"value": "enabled", "label": "enabled"},
                                    {"value": "disabled", "label": "disabled"},
                                ],
                            },
                        },
                    ]
                }
            },
        }
    )
    + "\n"
)

#: What `opencode models` prints, and what `mimo models` prints, which is the same list with
#: the size of each written after it.
OPENCODE = "opencode/big-pickle\nopencode/small-pickle\n"
MIMO = "mimo/mimo-auto — window 1M, compacts at 960K\nopenai/gpt-nine — window 272K\n"


def stands_in(
    monkeypatch: pytest.MonkeyPatch,
    at: Path,
    name: str,
    prints: str,
    *,
    code: int = 0,
    says: str = "",
) -> Path:
    """Puts a backend of that name first on PATH, printing what the real one would print.

    Args:
      monkeypatch: What puts it on PATH, and takes it off again afterwards.
      at: The directory to keep it in.
      name: What the backend is called, since that is what is run.
      prints: What it prints where anybody would read it.
      code: What it exits with.
      says: What it prints where the trouble goes.

    Returns:
      The program, which also writes down the arguments and the environment it was given.
    """
    at.mkdir(parents=True, exist_ok=True)
    program = at / name
    program.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"json.dump({{'argv': sys.argv[1:], 'env': dict(os.environ), "
        "'said': sys.stdin.read()}, "
        f"open({str(at / f'{name}.seen')!r}, 'w'))\n"
        f"sys.stdout.write({prints!r})\n"
        f"sys.stderr.write({says!r})\n"
        f"raise SystemExit({code})\n"
    )
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{at}{os.pathsep}{os.environ['PATH']}")
    return program


def seen(at: Path, name: str) -> dict[str, object]:
    """What the stand-in was run with."""
    return json.loads((at / f"{name}.seen").read_text())


@pytest.mark.parametrize(
    ("cli", "prints", "wanted"),
    [
        ("claude", CLAUDE, ["claude-nine", "claude-quick"]),
        ("codex", CODEX, ["gpt-nine", "gpt-eight"]),
        ("kimi", KIMI, ["kimi-code/kthree", "kimi-code/kold"]),
        ("pi", PI, ["openai-codex/gpt-nine", "anthropic/opus-ten"]),
        ("opencode", OPENCODE, ["opencode/big-pickle", "opencode/small-pickle"]),
        ("mimo", MIMO, ["mimo/mimo-auto", "openai/gpt-nine"]),
        ("agy", AGY, ["gemini-nine-high", "gemini-nine-low", "claude-sonnet-nine"]),
        ("zcode", ZCODE, ["zai/glm-nine", "zai/glm-quick"]),
    ],
)
def test_every_backend_is_asked_the_way_that_backend_answers(
    cli: str,
    prints: str,
    wanted: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A control request, a debug command, a provider dump, a table, a list of lines."""
    stands_in(monkeypatch, tmp_path / "bin", cli, prints)

    found = models.ask(cli)

    assert [model.name for model in found] == wanted


def test_claude_keeps_the_alias_of_a_custom_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alias is what Claude accepts, even though its response has a canonical id too."""
    monkeypatch.setenv("ANTHROPIC_CUSTOM_MODEL_OPTION", "fable")
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE_CUSTOM)

    found = models.ask("claude")

    assert [model.name for model in found] == ["fable"]
    environment = seen(bin_, "claude")["env"]
    assert isinstance(environment, dict)
    # Passed through as it was set, rather than replaced by one of humanize's own choosing.
    assert environment["ANTHROPIC_CUSTOM_MODEL_OPTION"] == "fable"


@traced
@pytest.mark.parametrize("provider", ["", "subscribed"])
def test_claude_is_never_asked_about_a_model_humanize_thought_of(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude lists a custom model without checking the account can run it.

    So naming one to get a hidden model listed would put a model in the catalogue for every
    account that cannot run it -- which is the one thing a catalogue asked for rather than
    written down exists to avoid.
    """
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    if provider:
        providers.add("claude", provider, "login", {})

    found = models.ask("claude", provider)

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]
    environment = seen(bin_, "claude")["env"]
    assert isinstance(environment, dict)
    assert "ANTHROPIC_CUSTOM_MODEL_OPTION" not in environment


def test_an_antigravity_model_takes_the_effort_its_own_name_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It lists one model at three efforts as three models, and refuses a fourth beside them.

    `--model gemini-nine-high --effort low` is `conflicts with --effort=low`, and a model
    whose name carries no effort is `--effort is not supported for model` -- so the effort is
    chosen by choosing the model, and the catalogue is what says so.
    """
    stands_in(monkeypatch, tmp_path / "bin", "agy", AGY)

    found = {one.name: one.efforts for one in models.ask("agy")}

    assert found["gemini-nine-high"] == ("high",)
    assert found["gemini-nine-low"] == ("low",)
    # And one whose name carries none runs at its own level whatever it is asked for.
    assert found["claude-sonnet-nine"] == named("agy").efforts  # pyright: ignore[reportOptionalMemberAccess]


def test_grok_takes_the_efforts_it_says_it_takes() -> None:
    """The ladder written down is the one its own refusal enumerates.

    `unknown effort level 'max'; use one of: xhigh, high, medium, low` -- said before it does
    anything else, so a rung it has not got is a turn that never starts.
    """
    held = named("grok")
    assert held is not None
    assert held.efforts == ("xhigh", "high", "medium", "low")


def test_dsh_uses_the_official_adapter_catalogue_without_starting_a_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def started(*args: object, **kwargs: object) -> None:
        raise AssertionError("dsh model discovery must not start a CLI")

    monkeypatch.setattr(subprocess, "run", started)

    found = models.ask("deepseek-harness")

    assert [model.name for model in found] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    assert all(model.efforts == ("max", "high", "off") for model in found)
    assert models.offered("dsh") == found


def test_dsh_offers_the_official_catalogue_before_it_has_been_asked() -> None:
    found = models.offered("deepseek-harness")

    assert [model.name for model in found] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    assert all(model.efforts == ("max", "high", "off") for model in found)


def test_a_model_takes_the_efforts_its_backend_said_that_model_takes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which differ between the models of one backend, and are hardest first either way."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    found = {model.name: model.efforts for model in models.ask("codex")}

    assert found["gpt-nine"] == ("ultra", "high", "low")
    assert found["gpt-eight"] == ("high", "low")


def test_a_model_its_backend_says_nothing_about_takes_the_whole_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn has to be asked for at some effort, and it said nothing to narrow them by."""
    stands_in(monkeypatch, tmp_path / "bin", "kimi", KIMI)

    found = {model.name: model.efforts for model in models.ask("kimi")}
    profile = named("kimi")
    assert profile is not None

    assert found["kimi-code/kthree"] == (
        "max",
        "high",
        "low",
    )  # no `medium`, as it said
    assert found["kimi-code/kold"] == profile.efforts


def test_the_rung_a_backend_does_not_document_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No listing of Claude Code's own will ever name `ultracode`, and it takes it."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    found = {model.name: model.efforts for model in models.ask("claude")}

    assert found["claude-nine"] == ("ultracode", "max", "high", "low")


def test_a_model_named_twice_is_one_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code offers its default under `default` as well as under its own name."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    found = models.ask("claude")

    assert [model.name for model in found].count("claude-nine") == 1


def test_the_window_on_the_end_of_an_id_is_not_part_of_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[1m]` is a way of running the model; the backend asked for one under it says no."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    assert all("[" not in model.name for model in models.ask("claude"))


def test_a_swarm_is_the_backends_own_rather_than_a_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every model Kimi runs takes a turn wide as well as hard, and no other backend does."""
    stands_in(monkeypatch, tmp_path / "bin", "kimi", KIMI)
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    assert all(model.swarms for model in models.ask("kimi"))
    assert not any(model.swarms for model in models.ask("codex"))


def test_what_was_asked_for_is_kept_and_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading it back is one file read, which is what lets a prompt do it."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    asked = models.ask("codex")

    assert models.offered("codex") == asked
    assert models.asked("codex").endswith("Z")


def test_a_backend_nobody_has_asked_offers_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty rather than guessed at: a model nobody can run is worse than a list to fill."""
    assert models.offered("codex") == ()
    assert models.asked("codex") == ""


def test_a_catalogue_written_by_something_else_is_no_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt reads this, and a file it cannot read is a list to fill rather than a crash."""
    at = models.where("codex")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text("not json at all")

    assert models.offered("codex") == ()


@traced
def test_two_accounts_of_one_backend_are_two_catalogues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which models a turn may name is the account's, so what is kept is the account's."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "codex", CODEX)
    providers.add("codex", "mine", "key", {"OPENAI_API_KEY": "sk-x"})
    models.ask("codex")

    stands_in(monkeypatch, bin_, "codex", json.dumps({"models": []}))
    models.ask("codex", "mine")

    assert [model.name for model in models.offered("codex")] == [
        "gpt-nine",
        "gpt-eight",
    ]
    assert models.offered("codex", "mine") == ()


@traced
def test_what_an_account_runs_is_kept_with_the_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """So that taking the account away takes what it runs with it: they are one fact."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)
    provider = providers.add("codex", "mine", "key", {"OPENAI_API_KEY": "sk-x"})
    models.ask("codex", "mine")

    assert models.where("codex", "mine").parent == provider.at
    assert providers.remove("codex", "mine")
    assert models.offered("codex", "mine") == ()


@traced
def test_an_account_is_asked_under_its_own_credentials_and_without_anybody_elses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a turn of it is run: what it sets, and none of what its backend would rather have."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses")
    # A gateway with nothing listening at it, so this is about the environment the CLI is
    # run under rather than about the endpoint being asked -- which nothing answers.
    at = "http://127.0.0.1:1"
    providers.add("claude", "mine", "gateway", {"ANTHROPIC_BASE_URL": at})

    models.ask("claude", "mine")

    environ = seen(bin_, "claude")["env"]
    assert isinstance(environ, dict)
    assert environ["ANTHROPIC_BASE_URL"] == at
    assert "ANTHROPIC_API_KEY" not in environ


def test_a_backend_that_exits_badly_says_what_it_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI that is not signed in cannot say what it runs, and that is worth reading."""
    stands_in(
        monkeypatch, tmp_path / "bin", "codex", "", code=3, says="not logged in\n"
    )

    with pytest.raises(ValueError, match="not logged in"):
        models.ask("codex")


def test_a_backend_that_answers_with_nothing_readable_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream with no answer in it is a backend that did not answer the question."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", '{"type": "system"}\n')

    with pytest.raises(ValueError, match="said nothing"):
        models.ask("claude")


def test_a_backend_that_refuses_the_question_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code answers a control request it will not carry out with the reason."""
    stands_in(
        monkeypatch,
        tmp_path / "bin",
        "claude",
        json.dumps(
            {
                "type": "control_response",
                "response": {
                    "subtype": "error",
                    "request_id": "models",
                    "error": "no catalogue here",
                },
            }
        ),
    )

    with pytest.raises(ValueError, match="no catalogue here"):
        models.ask("claude")


def test_a_backend_nobody_has_heard_of_is_refused() -> None:
    """Every caller of this names a backend, and one that is not one is a caller's mistake."""
    with pytest.raises(ValueError, match="no such coding agent"):
        models.ask("emacs")
    with pytest.raises(ValueError, match="no such coding agent"):
        models.where("emacs")
    assert models.offered("emacs") == ()


def test_an_account_that_is_not_that_backends_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking as an account that does not exist would be asking as this machine instead."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    with pytest.raises(ValueError, match="no account called"):
        models.ask("codex", "nobody")


def test_a_backend_is_asked_by_the_name_it_is_installed_as(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whichever of its spellings was used: `kimi-code` and `kimi` are one backend."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "kimi", KIMI)

    found = models.ask("kimi-code")

    assert [model.name for model in found] == ["kimi-code/kthree", "kimi-code/kold"]
    assert models.offered("kimi") == found
    assert seen(bin_, "kimi")["argv"] == ["provider", "list", "--json"]


#: What an OpenAI-shaped `/v1/models` answers with, which is the shape an Anthropic-shaped one
#: answers in too: the ids under `data`, route-prefixed the way a gateway in front of several
#: clouds writes them. The empty one is what a list with a hole in it looks like.
SERVED = json.dumps(
    {
        "object": "list",
        "data": [
            {"id": "azure/anthropic/claude-haiku-4-5", "object": "model"},
            {"id": "azure/openai/gpt-5.6-sol", "object": "model"},
            {"id": "", "object": "model"},
        ],
    }
)


@contextlib.contextmanager
def endpoint(
    body: str, *, status: int = 200, moved: str = ""
) -> Generator[tuple[str, list[list[str]]]]:
    """One endpoint on the loopback, answering that and writing down what it was asked.

    Args:
      body: What it answers with.
      status: What it answers it under.
      moved: Where it sends the first request instead, for an endpoint that redirects. The
        one after it is answered, so that a redirect it is right to follow lands somewhere.

    Yields:
      Where it is, and one `[path, authorization]` per request it took.
    """
    asked: list[list[str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            asked.append([self.path, self.headers.get("Authorization", "")])
            sending = moved and len(asked) == 1
            said = body.encode()
            self.send_response(302 if sending else status)
            if sending:
                self.send_header("Location", moved)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(said)))
            self.end_headers()
            self.wfile.write(said)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Nothing: a suite is not somewhere a web server keeps a log."""

    class Serving(ThreadingHTTPServer):
        """The same, without the reverse lookup it names itself by.

        On a machine whose resolver has nothing to say about `127.0.0.1` that lookup blocks
        for the resolver's own timeout, which is half a minute.
        """

        def server_bind(self) -> None:
            socketserver.TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name, self.server_port = str(host), int(port)

    running = Serving(("127.0.0.1", 0), Handler)
    reader = threading.Thread(target=running.serve_forever, daemon=True)
    reader.start()
    try:
        yield f"http://127.0.0.1:{running.server_port}", asked
    finally:
        running.shutdown()
        running.server_close()
        reader.join(timeout=2)


def test_an_account_on_an_endpoint_is_asked_the_endpoint_and_not_its_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI pointed at somebody's gateway answers with the models it ships.

    Which are the models the gateway refuses -- so the catalogue is fresh and wrong, and
    asking again changes nothing. What a turn of that account may name is what is at the
    other end of the base URL it sets.
    """
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    profile = named("claude")
    assert profile is not None
    with endpoint(SERVED) as (base, asked):
        providers.add(
            "claude",
            "gateway",
            "gateway",
            {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
        )

        found = models.ask("claude", "gateway")

    assert [model.name for model in found] == [
        "azure/anthropic/claude-haiku-4-5",
        "azure/openai/gpt-5.6-sol",
    ]
    # The whole ladder: a catalogue says nothing about how hard a model may be asked to
    # think, and a model nothing narrowed is one its backend will take any rung for.
    assert found[0].efforts == profile.efforts
    assert [path for path, _ in asked] == ["/v1/models"]
    # And the CLI was never started. It has nothing to add and costs the seconds.
    assert not (bin_ / "claude.seen").exists()


def test_an_endpoint_written_with_its_version_is_not_asked_for_a_second_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`https://host` and `https://host/v1` are two spellings of one gateway."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(SERVED) as (base, asked):
        providers.add(
            "claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": f"{base}/v1/"}
        )

        models.ask("claude", "gateway")

    assert [path for path, _ in asked] == ["/v1/models"]


@traced
def test_an_account_that_names_no_endpoint_is_asked_of_its_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subscription is not a gateway: there is nothing to ask but the CLI, and it knows."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    providers.add("claude", "subscribed", "token", {"CLAUDE_CODE_OAUTH_TOKEN": "mine"})

    found = models.ask("claude", "subscribed")

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ('{"error": {"message": "key not allowed to access model"}}', 403),
        (json.dumps({"object": "error", "message": "no catalogue here"}), 200),
        ("<html>somebody else's login page</html>", 200),
    ],
)
@traced
def test_an_endpoint_that_will_not_say_leaves_the_cli_to_answer(
    body: str, status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It refused, it answered something else, or it answered nothing that is a list.

    None of them is a reason to have no catalogue: an account with no models is an account
    nothing can be run as, and the CLI's own answer is better than that.
    """
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(body, status=status) as (base, _):
        providers.add("claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": base})

        found = models.ask("claude", "gateway")

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


@traced
def test_an_endpoint_nothing_is_listening_at_leaves_the_cli_to_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gateway that is down is a gateway to ask again, not a catalogue to throw away."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    providers.add(
        "claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": "http://127.0.0.1:1"}
    )

    found = models.ask("claude", "gateway")

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


def test_the_accounts_own_credential_is_sent_and_never_written_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint is asked as that account, and what makes it that account goes no further.

    It reaches the request and nothing else: not the catalogue, not a log, not a message.
    """
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses")
    with endpoint(SERVED) as (base, asked):
        providers.add(
            "claude",
            "gateway",
            "gateway",
            {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
        )

        models.ask("claude", "gateway")

    assert [sent for _, sent in asked] == ["Bearer the-secret"]
    assert "the-secret" not in models.where("claude", "gateway").read_text("utf-8")


@traced
def test_a_backend_whose_ids_are_a_providers_is_never_asked_an_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencode, mimocode, pi and zcode name a model `provider/id`, out of several at once.

    An endpoint would answer with the ids of the one it fronts, without the provider that
    says which of them serves it -- a list of models that CLI cannot name, which is the
    failure being fixed rather than the fix.
    """
    stands_in(monkeypatch, tmp_path / "bin", "opencode", OPENCODE)
    with endpoint(SERVED) as (base, asked):
        providers.add("opencode", "gateway", "env", {"ANTHROPIC_BASE_URL": base})

        found = models.ask("opencode", "gateway")

    assert [model.name for model in found] == [
        "opencode/big-pickle",
        "opencode/small-pickle",
    ]
    assert asked == []


@traced
def test_the_credential_does_not_follow_a_redirect_to_another_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A machine only asking what models there are does not hand its key to a third party.

    urllib sends the headers it was given again wherever it is sent, so an endpoint that
    answers `302 somewhere-else` would be handing the account's own key to somewhere the
    account never named. Refused, which reads here as an endpoint that would not say.
    """
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(SERVED) as (elsewhere, theirs):
        with endpoint("", moved=f"{elsewhere}/v1/models") as (base, ours):
            providers.add(
                "claude",
                "gateway",
                "gateway",
                {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
            )

            found = models.ask("claude", "gateway")

        assert [sent for _, sent in ours] == ["Bearer the-secret"]
        # The other host was never asked at all, so it never saw the key.
        assert theirs == []
    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


def test_an_endpoint_that_moves_its_own_path_is_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same host over the same scheme is where the credential already was."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(SERVED, moved="/models") as (base, asked):
        providers.add(
            "claude",
            "gateway",
            "gateway",
            {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
        )

        found = models.ask("claude", "gateway")

    assert [model.name for model in found] == [
        "azure/anthropic/claude-haiku-4-5",
        "azure/openai/gpt-5.6-sol",
    ]
    assert [path for path, _ in asked] == ["/v1/models", "/models"]
