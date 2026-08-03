"""Which account an agent's turns run as: made here, given to one agent, and kept.

An account is credentials rather than a way of running a model, so it is asked about where
the agent is chosen and not where the flow is -- two agents of one CLI may be two accounts.
Nothing here signs anything in: a CLI's own login is the only thing that can perform that
CLI's login, so it is patched out and what is tested is the walk up to it.
"""

from __future__ import annotations

import json
import unittest.mock
from typing import TYPE_CHECKING

import pytest
from textual import events
from textual.widgets import Label, OptionList, Static

from hmz import providers
from hmz.backends import Model
from hmz.tui import Humanize
from hmz.tui.pick import (
    Backends,
    Models,
    Providers,
    Runs,
    RunsAs,
    Signing,
    Ways,
    reads,
)
from hmz.tui.settings import Settings

from .test_app import _transcript, until

if TYPE_CHECKING:
    from pathlib import Path

#: What one installed CLI looks like, for the tests that walk the agents sheet.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}


def _kept(cli: str, name: str = "") -> tuple[Model, ...]:
    """Writes down what one account's CLI said it runs, which is what asking it leaves.

    Args:
      cli: The backend.
      name: The account, or "" for the CLI as this machine already runs it.

    Returns:
      What was written, which is the one model these walks choose between.
    """
    from hmz import models

    at = models.where(cli, name)
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        json.dumps(
            {
                "asked": "2026-08-12T00:00:00Z",
                "models": [
                    {"name": model.name, "efforts": list(model.efforts)}
                    for model in CLAUDE[cli]
                ],
            }
        )
    )
    return CLAUDE[cli]


def _account(name: str = "deepseek", cli: str = "claude") -> providers.Provider:
    """Writes one account down, as `hmz providers add` does, signing nothing in.

    And with the models that account runs already asked for, which is what making one does:
    a walk that has to press a key before there is anything to choose from is a walk nobody
    takes, and this is about the account rather than about the asking.
    """
    made = providers.add(cli, name, way="key", env={"ANTHROPIC_API_KEY": "not-a-key"})
    _kept(cli, name)
    return made


@pytest.mark.timeout(60)
async def test_the_command_opens_the_sheet_of_accounts() -> None:
    """A command of its own, because an account outlives the flow that was set up with it."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        rows = [str(option.prompt) for option in listing.options]
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)

    # The CLI it is under as a heading, and under it the name, the way and the variables.
    assert any("claude" in row for row in rows)
    assert any("deepseek" in row and "key" in row for row in rows)
    assert any("ANTHROPIC_API_KEY" in row for row in rows)
    # Their names and never a value: this is drawn where somebody can read it.
    assert all("not-a-key" not in row for row in rows)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.providers.login.sign_in", return_value=0)
async def test_an_account_made_on_the_sheet_lands_in_the_store(
    signed_in: unittest.mock.MagicMock,
) -> None:
    """Three questions, because each is only answerable once the one before it has been."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)

        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        backends = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(backends.options), driver)
        assert str(backends.get_option_at_index(0).id) == "=claude"
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Ways), driver)
        ways = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(ways.options), driver)
        assert str(ways.get_option_at_index(0).id) == "=login"
        await driver.press("enter")

        # Only what to call it: the way that signs in to an account asks nothing else, the
        # CLI's own login being what asks the rest.
        await until(lambda: isinstance(app.screen, Signing), driver)
        await driver.press(*"mine")
        await driver.press("enter")

        # And the sheet comes back with the new one on it.
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)
        said = _transcript(app)

    made = providers.find("claude", "mine")
    assert made is not None
    assert made.way == "login"
    # The CLI's own way in ran, under this account's own paths, and nothing else did.
    assert signed_in.call_count == 1
    assert "claude/mine is written down at" in said
    assert "claude/mine is signed in" in said


@pytest.mark.timeout(60)
async def test_deepseek_offers_only_api_key_login_from_providers() -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        backends = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(backends.options), driver)
        ids = [str(option.id) for option in backends.options]
        for _ in range(ids.index("=dsh")):
            await driver.press("down")
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Ways), driver)
        ways = app.screen.query_one("#choices", OptionList)
        assert [str(option.id) for option in ways.options] == ["=key"]
        assert "DeepSeek API key" in str(ways.get_option_at_index(0).prompt)

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Backends), driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.providers.login.sign_in", return_value=0)
async def test_a_secret_is_never_drawn_back(signed_in: unittest.mock.MagicMock) -> None:
    """It is on its way into a credential store, and a screen is somewhere it is read off."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")

        # `key`, which is a variable rather than a login: it asks, and nothing is run.
        await until(lambda: isinstance(app.screen, Ways), driver)
        ways = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(ways.options), driver)
        await driver.press("down", "down")
        await driver.pause()
        assert str(ways.get_option_at_index(ways.highlighted or 0).id) == "=key"
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Signing), driver)
        form = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(form.options), driver)
        await driver.press(*"mine")
        await driver.press("down")
        await driver.press(*"sk-secret")
        await driver.pause()
        rows = [str(option.prompt) for option in form.options]
        assert all("sk-secret" not in row for row in rows)
        assert any("•" * len("sk-secret") in row for row in rows)

        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)

    made = providers.find("claude", "mine")
    assert made is not None
    assert made.env == {"ANTHROPIC_API_KEY": "sk-secret"}
    # A way that is only answers has already happened, having been written down.
    assert signed_in.call_count == 0


@pytest.mark.timeout(60)
async def test_a_pasted_secret_is_stored_without_its_trailing_newline() -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        backends = app.screen.query_one("#choices", OptionList)
        ids = [str(option.id) for option in backends.options]
        for _ in range(ids.index("=dsh")):
            await driver.press("down")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Ways), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Signing), driver)
        form = app.screen.query_one("#choices", OptionList)
        await driver.press(*"mine")
        await driver.press("down")
        form.post_message(events.Paste("sk-pasted\r\nignored"))
        await driver.pause()
        rows = [str(option.prompt) for option in form.options]
        assert all("sk-pasted" not in row for row in rows)
        assert any("•" * len("sk-pasted") in row for row in rows)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)

    made = providers.find("dsh", "mine")
    assert made is not None
    assert made.env == {"DEEPSEEK_API_KEY": "sk-pasted"}


@pytest.mark.timeout(60)
@pytest.mark.parametrize("key", ["shift+enter", "ctrl+j"])
@unittest.mock.patch("hmz.providers.login.sign_in", return_value=0)
async def test_variables_of_your_own_are_given_a_line_apiece(
    signed_in: unittest.mock.MagicMock,
    key: str,
) -> None:
    """The row that takes a list rather than a value, so it is the row a line breaks in."""
    del signed_in
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")
        # `env`, the way every backend has: variables of its own, which is the last of them.
        await until(lambda: isinstance(app.screen, Ways), driver)
        ways = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(ways.options), driver)
        await driver.press("up")  # round the end of the list, onto the last row
        await driver.pause()
        assert str(ways.get_option_at_index(ways.highlighted or 0).id) == "=env"
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Signing), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press(*"mine")
        await driver.press("down")  # onto the variables, which is where a list goes
        await driver.press(*"ANTHROPIC_BASE_URL=https://example.test")
        await driver.press(key)
        await driver.press(*"ANTHROPIC_AUTH_TOKEN=sk-secret")
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)

    made = providers.find("claude", "mine")
    assert made is not None
    # Two of them, which is two lines: one line would have been one variable to correct.
    assert made.env == {
        "ANTHROPIC_BASE_URL": "https://example.test",
        "ANTHROPIC_AUTH_TOKEN": "sk-secret",
    }


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_account_an_agent_runs_as_is_the_first_thing_asked_about_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """It decides which credentials the turns run under, which is no side question at all.

    So it is a step of the walk rather than a chord on the models: under the tab of the CLI
    whose accounts they are, since an account is one backend's, and read back on the step
    after as what was already settled.
    """
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        # The first step of the first agent, without anything being reached for.
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # This machine's own first, which is what every agent ran as before there were any.
        assert [str(option.id) for option in listing.options] == ["=", "=deepseek"]

        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "max effort" in str(tuning.content), driver)
        # Not read back here and not adjustable here: a step of its own answered it, and a
        # setting shown where it cannot be changed is a setting somebody tries to change.
        assert "deepseek" not in str(tuning.content)
        assert "deepseek" not in str(app.screen.query_one("#keys", Label).content)

        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)
        await driver.pause()
        # And on the line above the prompt, beside what it runs.
        assert "deepseek" in str(app.query_one("#above", Static).content)

    chosen = Runs("claude/claude-opus-5:max", "", None, "", "deepseek")
    assert app._models == [chosen]
    assert app.settings.agents(app._flow_named) == [chosen]
    assert reads(("builder",), [chosen]) == [
        "builder · claude/claude-opus-5:max · deepseek"
    ]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_an_account_can_be_made_from_the_sheet_that_asks_for_one(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The moment somebody finds out they have no account is the moment to offer them one.

    So making one is a key on the question rather than a walk out of it, and what comes back
    is the account chosen: making one here is choosing it -- with the models that account
    runs already asked for, which is what makes the step after it answerable.
    """
    import hmz.models

    asked: list[tuple[str, str]] = []

    def note(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        asked.append((cli, provider))
        return _kept(cli, provider)

    monkeypatch.setattr(hmz.models, "ask", note)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        # Nothing to choose but this machine's own, which is where somebody finds out.
        assert [
            str(option.id)
            for option in app.screen.query_one("#choices", OptionList).options
        ] == ["="]

        await driver.press("ctrl+n")
        # Straight to the ways in: the backend is the tab the sheet is open on.
        await until(lambda: isinstance(app.screen, Ways), driver)
        await driver.press("down", "down", "enter")  # `key`, which asks for one thing
        await until(lambda: isinstance(app.screen, Signing), driver)
        await driver.press(*"mine")
        await driver.press("down")
        await driver.press(*"not-a-key")
        await driver.press("enter")

        # On to the models, with the account made and given to this one: making one here is
        # choosing it, so the step it was asked in is answered.
        await until(lambda: isinstance(app.screen, Models), driver)
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "max effort" in str(tuning.content), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)
        await driver.pause()

    made = providers.find("claude", "mine")
    assert made is not None
    assert dict(made.env) == {"ANTHROPIC_API_KEY": "not-a-key"}
    assert app._models == [Runs("claude/claude-opus-5:max", "", None, "", "mine")]
    # The backends installed here are asked as the interface opens, and an account as it
    # lands: an account is made in order to run turns as, and which models those turns may
    # name is the account's rather than this machine's.
    assert asked == [("claude", ""), ("claude", "mine")]


@pytest.mark.timeout(60)
async def test_walking_out_of_the_ways_steps_back_into_the_backends() -> None:
    """Esc is the step before, and the step before the ways is which CLI they are of."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Ways), driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Backends), driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)

    assert providers.providers() == []


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_making_one_and_walking_out_of_it_changes_nothing(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Esc off the making is the account question again, with nothing written down."""
    app = Humanize()
    was = None
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        was = list(app._models)
        await driver.press("ctrl+n")
        await until(lambda: isinstance(app.screen, Ways), driver)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        # And esc off the first step of the first agent is out of the walk altogether.
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, RunsAs), driver)

    assert providers.providers("claude") == []
    assert app._models == was  # walking out changed nothing at all


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_cli_with_no_accounts_says_where_they_come_from(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """A sheet holding one row that changes nothing has to say why it is the only one."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        said = str(app.screen.query_one("#tuning", Label).content)

        assert "claude has no accounts here yet" in said
        # And says where one comes from without sending anybody out of the question: the
        # moment somebody finds out they have none is the moment to be offered one.
        assert "ctrl+n makes one" in said
        assert "ctrl+n to make one" in str(app.screen.query_one("#keys", Label).content)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_first_row_leaves_the_agent_running_as_this_machine(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Which is what every agent ran as before there were any accounts to choose between."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await driver.press("down")  # walked to the account and then off it again
        await driver.press("up")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "effort" in str(tuning.content), driver)
        # The account was the step before this one, so it is not read back here: a setting
        # shown where it cannot be changed is a setting somebody tries to change.
        assert "as installed" not in str(tuning.content)
        assert "deepseek" not in str(tuning.content)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    assert app._models == [Runs("claude/claude-opus-5:max")]


@pytest.mark.timeout(60)
async def test_walking_out_of_the_accounts_makes_nothing_and_loses_nothing() -> None:
    """Esc is the step before, and the step before the first one is out."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)

        await driver.press("a")
        await until(lambda: isinstance(app.screen, Backends), driver)
        await driver.press("escape")
        # Back to the accounts, which is where making one was asked for.
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)

    assert [one.name for one in providers.providers()] == ["deepseek"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.providers.login.sign_in", return_value=0)
async def test_an_account_is_signed_in_again_by_the_way_it_was_made_with(
    signed_in: unittest.mock.MagicMock,
) -> None:
    """A token expires and a subscription is signed out of, and neither remakes the account."""
    providers.add("claude", "deepseek", way="login")
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await driver.press("l")
        await until(lambda: signed_in.call_count == 1, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)
        said = _transcript(app)

    assert "claude/deepseek is signed in" in said


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.providers.login.sign_in", return_value=0)
async def test_signing_in_again_asks_only_what_is_not_written_down(
    signed_in: unittest.mock.MagicMock,
) -> None:
    """A key the CLI keeps in its own store was never kept here, so it is asked for again."""
    providers.add("codex", "work", way="key")
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await driver.press("l")
        await until(lambda: isinstance(app.screen, Signing), driver)
        form = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(form.options), driver)
        # And only that: what to call an account that already has a name is not a question.
        assert [str(option.id) for option in form.options] == ["=OPENAI_API_KEY"]

        await driver.press(*"sk-1")
        await driver.press("enter")
        await until(lambda: signed_in.call_count == 1, driver)
        await until(lambda: isinstance(app.screen, Providers), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)

    assert signed_in.call_args.args[2] == {"OPENAI_API_KEY": "sk-1"}


@pytest.mark.timeout(60)
async def test_taking_an_account_away_says_what_went_with_it() -> None:
    """Credentials are what is going, and a line that said less would be understating it."""
    _account()
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/providers")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Providers), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        await driver.press("r")
        await until(lambda: not providers.providers(), driver)
        # The sheet comes back, with nothing on it now.
        await until(
            lambda: (
                isinstance(app.screen, Providers)
                and not app.screen.query_one("#choices", OptionList).options
            ),
            driver,
        )
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Providers), driver)
        said = _transcript(app)

    assert "claude/deepseek is gone, credentials and all" in said
    assert providers.find("claude", "deepseek") is None


def test_an_agent_is_made_as_the_account_it_was_given() -> None:
    """What the sheet answered is a setting of the agent, done to it before the flow starts."""
    from hmz.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

    _account()
    app = Humanize()
    app._models = [Runs("claude/m:high", "", None, "", "deepseek")]
    made = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))

    (agent,) = app._as_they_were_set_up([made])

    assert agent.config.provider == "deepseek"
    assert agent.config.machine is None  # it works here, as it did before

    # And one nobody named an account for is the agent that was made, untouched.
    app._models = [Runs("claude/m:high")]
    again = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    assert app._as_they_were_set_up([again]) == [again]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_an_agent_told_to_run_as_nobody_is_a_line_to_correct(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """An agent that cannot find its account must not quietly run as whoever started it."""
    app = Humanize()
    async with app.run_test() as driver:
        app._models = [Runs("claude/claude-opus-5:max", "", None, "", "nonesuch")]
        await driver.press(*"go")
        await driver.press("enter")
        await until(lambda: "nonesuch" in _transcript(app), driver)
        said = _transcript(app)

    assert "hmz: no claude provider called 'nonesuch'" in said
    assert (
        "Traceback" not in said
    )  # said at the prompt, rather than raised out of a thread
    assert not app._agents  # and nothing started


def test_what_an_agent_runs_as_is_kept_and_read_back(tmp_path: Path) -> None:
    """As the anchor and the skills are: written only where there is an account to write."""
    kept = Settings(tmp_path)
    kept.remember(
        "rlar",
        ("actor", "reviewer"),
        [Runs("claude/m:high", "", None, "", "deepseek"), Runs("codex/n:low")],
    )

    assert Settings(tmp_path).agents("rlar") == [
        Runs("claude/m:high", "", None, "", "deepseek"),
        Runs("codex/n:low"),
    ]
    held = Settings(tmp_path)._read()
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert agents["actor"]["provider"] == "deepseek"
    # An agent nobody named one for says nothing, which is what a file written before there
    # were any says too -- and reads back as this machine's own account.
    assert "provider" not in agents["reviewer"]
