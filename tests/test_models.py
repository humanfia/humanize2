"""What each backend runs, asked of that backend and kept per account.

Every backend here is a stand-in first on PATH, printing what the real one prints: the point
of this module is that nothing is written down, so what is checked is that each backend's own
way of being asked is read the way that backend answers it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz import models, providers
from hmz.backends import named

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("asking")

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

#: Claude's official custom-model hook reports a hidden subscription model by its alias. The
#: resolved id is deliberately different: hmz must keep the alias because that is what a user
#: can pass to `/model` and to `--model`.
CLAUDE_FABLE = json.dumps(
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


def test_claude_keeps_the_alias_of_a_custom_model_and_requests_fable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alias is what Claude accepts, even though its response has a canonical id too."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE_FABLE)

    found = models.ask("claude")

    assert [model.name for model in found] == ["fable"]
    environment = seen(bin_, "claude")["env"]
    assert isinstance(environment, dict)
    assert environment["ANTHROPIC_CUSTOM_MODEL_OPTION"] == "fable"


def test_claude_does_not_replace_an_existing_custom_model_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller's custom model remains the value Claude is asked to list."""
    monkeypatch.setenv("ANTHROPIC_CUSTOM_MODEL_OPTION", "my-model")
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)

    models.ask("claude")

    environment = seen(bin_, "claude")["env"]
    assert isinstance(environment, dict)
    assert environment["ANTHROPIC_CUSTOM_MODEL_OPTION"] == "my-model"


def test_claude_key_accounts_are_not_given_the_subscription_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fable is opt-in for a subscription, not a guess for a Claude API key."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    providers.add("claude", "key", "key", {"ANTHROPIC_API_KEY": "sk-x"})

    found = models.ask("claude", "key")

    assert "fable" not in [model.name for model in found]
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


def test_an_account_is_asked_under_its_own_credentials_and_without_anybody_elses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a turn of it is run: what it sets, and none of what its backend would rather have."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses")
    providers.add("claude", "mine", "gateway", {"ANTHROPIC_BASE_URL": "https://mine"})

    models.ask("claude", "mine")

    environ = seen(bin_, "claude")["env"]
    assert isinstance(environ, dict)
    assert environ["ANTHROPIC_BASE_URL"] == "https://mine"
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
