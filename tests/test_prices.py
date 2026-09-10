"""What a token costs in money, and what is answered where nobody says.

Nothing here reaches the network. The suite points `HUMANIZE_PRICES` at a file written by the
test, which is the same path the real fetch takes once the bytes are in hand -- and the one
case that matters most is the one with no bytes at all, where a run still has to say what it
spent in tokens without inventing a bill of nothing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz import prices

if TYPE_CHECKING:
    from pathlib import Path


def _listing(*models: dict[str, Any]) -> dict[str, Any]:
    """A document shaped as OpenLLMPrices writes one.

    Args:
      models: The models it lists, newest version only.

    Returns:
      The whole document, ready to be written where the fetch will read it.
    """
    return {
        "schemaVersion": 4,
        "currency": "USD",
        "unit": "per 1M tokens",
        "versions": [
            {"date": "2026-09-10", "models": list(models)},
            {"date": "2019-01-01", "models": []},  # last year's, which is never read
        ],
    }


def _model(
    ident: str, name: str = "", **priced: float | tuple[float, ...]
) -> dict[str, Any]:
    """One model of that document, at one price per kind or several tiers of one.

    Args:
      ident: The id the list gives it.
      name: What it is called, which is another way of naming the same model.
      priced: Dollars per million tokens, by the category the list writes.

    Returns:
      The model.
    """
    items: list[dict[str, Any]] = [
        {"category": kind, "price": tier, "unit": "1M tokens"}
        for kind, asked in priced.items()
        for tier in (asked if isinstance(asked, tuple) else (asked,))
    ]
    return {
        "provider": "Somebody",
        "id": ident,
        "name": name or ident,
        "pricingItems": items,
    }


@pytest.fixture
def listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Puts a price list where the fetch will find it, and fetches it.

    Returns:
      A callable taking the models to list, which leaves them fetched and kept.
    """

    def writing(*models: dict[str, Any]) -> bool:
        source = tmp_path / "source.json"
        source.write_text(json.dumps(_listing(*models)), encoding="utf-8")
        monkeypatch.setenv(prices.WHENCE, str(source))
        prices._tried = 0.0
        return prices.refresh(wait=True)

    return writing


def test_a_model_nobody_lists_has_no_price_rather_than_a_price_of_nothing(
    listed: Any,
) -> None:
    """The whole honesty of this: a bill of zero is a claim, and a wrong one."""
    assert listed(_model("gpt-5.6-sol", input_tokens=4, output_tokens=20))

    assert prices.price("some-model-nobody-has-heard-of") is None
    assert prices.cost({"input": 1_000_000}, "some-model-nobody-has-heard-of") is None


def test_what_a_turn_cost_is_the_kinds_at_their_own_rates(listed: Any) -> None:
    """An input token and an output token of one model differ several times over in price."""
    assert listed(
        _model(
            "claude-haiku-4.5", input_tokens=1, output_tokens=5, cache_read_tokens=0.1
        )
    )

    spent = prices.cost({"input": 1000, "output": 40}, "claude-haiku-4.5")

    assert spent == pytest.approx(1000 / 1e6 * 1 + 40 / 1e6 * 5)


def test_a_model_is_matched_however_its_backend_spells_it(listed: Any) -> None:
    """The provider in front, the release date behind, and the punctuation in between."""
    assert listed(_model("claude-haiku-4.5", name="Claude Haiku 4.5", input_tokens=1))

    for spelling in (
        "claude-haiku-4.5",
        "claude-haiku-4-5-20251001",
        "anthropic/claude-haiku-4-5",
        "us.anthropic.claude-haiku-4-5-v1:0",
        "Claude Haiku 4.5",
    ):
        found = prices.price(spelling)
        assert found is not None, spelling
        assert found.model == "claude-haiku-4.5"


def test_a_gateway_route_in_front_of_a_model_is_not_part_of_the_model(
    listed: Any,
) -> None:
    """A gateway in front of several clouds writes which cloud into the id.

    These are the spellings one real gateway serves: `azure/anthropic/claude-opus-5`,
    `aws/anthropic/bedrock-claude-opus-5` and plain `claude-opus-5` are one model reached
    three ways, and one bill.
    """
    assert listed(_model("claude-opus-5", input_tokens=5, output_tokens=25))

    for spelling in (
        "azure/anthropic/claude-opus-5",
        "aws/anthropic/bedrock-claude-opus-5",
        "switchyard/anthropic/claude-opus-5",
        "claude-opus-5",
    ):
        found = prices.price(spelling)
        assert found is not None, spelling
        assert found.model == "claude-opus-5"


def test_a_model_the_gateway_serves_that_nobody_prices_is_still_a_miss(
    listed: Any,
) -> None:
    """The gateway offers hundreds; the list has dozens. Most of them are unpriced."""
    assert listed(_model("claude-opus-5", input_tokens=5))

    assert prices.price("nvidia/meta/llama-3.1-8b-instruct") is None
    assert prices.price("azure/openai/gpt-5-nano") is None
    assert prices.cost({"input": 1000}, "nvidia/meta/llama-3.1-8b-instruct") is None


def test_a_near_miss_is_a_miss(listed: Any) -> None:
    """Nothing here guesses: the price of the neighbour is not this model's price."""
    assert listed(_model("gpt-5.6-sol", input_tokens=4))

    assert prices.price("gpt-5") is None
    assert prices.price("gpt-5.6") is None
    assert prices.price("gpt-5.6-sol-turbo") is None


def test_the_standard_tier_is_the_one_taken(listed: Any) -> None:
    """A model priced twice over by context length is taken at the price it starts at.

    Nothing here knows how long the prompt was, so the first tier -- which is the standard
    price -- is what is used, and the docs say a very long turn cost more than this shows.
    """
    assert listed(_model("wide-model", input_tokens=(2.0, 4.0)))

    found = prices.price("wide-model")

    assert found is not None
    assert found.per_million["input"] == 2.0


def test_a_cache_write_nobody_prices_separately_is_taken_at_the_input_price(
    listed: Any,
) -> None:
    """A cache write is an input token and a surcharge, so the input price is a floor on it."""
    assert listed(_model("plain-model", input_tokens=2, output_tokens=6))

    spent = prices.cost({"cache_write": 1_000_000}, "plain-model")

    assert spent == pytest.approx(2.0)


def test_a_cache_read_nobody_prices_separately_is_left_out_rather_than_overstated(
    listed: Any,
) -> None:
    """A cached read is a tenth of an input token, and a turn is mostly cached reads.

    Priced as input it would put the bill several times over the truth, which is the one
    direction this must never go: the figure is a floor.
    """
    assert listed(_model("plain-model", input_tokens=2, output_tokens=6))

    spent = prices.cost({"input": 1_000_000, "cache_read": 9_000_000}, "plain-model")

    assert spent == pytest.approx(2.0)  # the input alone


def test_tokens_of_no_named_kind_at_all_are_counted_and_not_priced(listed: Any) -> None:
    """Some backends say a total and no kinds. That is tokens, and no bill beside them."""
    assert listed(_model("plain-model", input_tokens=2, output_tokens=6))

    assert prices.cost({"": 1000}, "plain-model") is None


def test_reasoning_counted_beside_the_output_is_bought_as_output(listed: Any) -> None:
    """A backend that counts its thinking apart from its answer still bought output."""
    assert listed(_model("thinker", input_tokens=1, output_tokens=10))

    spent = prices.cost({"reasoning": 1_000_000}, "thinker")

    assert spent == pytest.approx(10.0)


def test_only_the_newest_version_is_kept(listed: Any, tmp_path: Path) -> None:
    """The source is three years of dated snapshots; what a run costs is today's price."""
    assert listed(_model("today-model", input_tokens=3))

    kept = json.loads(prices.where().read_text(encoding="utf-8"))

    assert kept["date"] == "2026-09-10"
    assert list(kept["models"]) == ["today-model"]


def test_what_was_kept_is_parsed_once_however_often_it_is_asked_for(
    listed: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing at a prompt reaches a network.

    And a screen redrawn twice a second is one that would otherwise parse the same file
    twice a second.
    """
    assert listed(_model("kept-model", input_tokens=3))
    prices.price("kept-model")  # the read that fills it
    reads = 0
    was = prices._read

    def counting(kept: Path) -> dict[str, prices.Price]:
        nonlocal reads
        reads += 1
        return was(kept)

    monkeypatch.setattr(prices, "_read", counting)

    assert prices.price("kept-model") is not None
    assert prices.price("kept-model") is not None
    assert reads == 0  # nothing has moved under it, so nothing is read again


def test_a_source_that_cannot_be_read_leaves_what_was_kept_serving(
    listed: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The network being gone is not a reason to stop saying what a run has cost."""
    assert listed(_model("kept-model", input_tokens=3))

    monkeypatch.setenv(prices.WHENCE, str(tmp_path / "nowhere.json"))
    prices._tried = 0.0

    assert prices.refresh(wait=True) is False
    assert prices.price("kept-model") is not None


def test_an_etag_is_not_replayed_at_a_source_it_did_not_come_from(
    listed: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second source answering 304 to the first one's etag must not date the first forward.

    Which is only ever a mistake: the tag means *what you already have*, and what is already
    here came from somebody else.
    """
    assert listed(_model("first-model", input_tokens=3))

    beside = tmp_path / "another.json"
    beside.write_text(
        json.dumps(_listing(_model("second-model", input_tokens=7))), encoding="utf-8"
    )
    monkeypatch.setenv(prices.WHENCE, str(beside))
    prices._tried = 0.0

    assert prices.refresh(wait=True)

    assert prices.price("second-model") is not None
    assert prices.price("first-model") is None  # the other source's, and gone with it


def test_tokens_of_a_kind_nobody_prices_are_not_a_bill_of_nothing(listed: Any) -> None:
    """A model listed, and a reckoning of it none of whose priced kinds hold anything."""
    assert listed(_model("plain-model", input_tokens=2, output_tokens=6))

    assert prices.cost({"input": 0.0, "cache_read": 800.0}, "plain-model") is None


def test_a_document_priced_in_another_currency_is_refused(
    listed: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Showing the wrong money is worse than showing none."""
    assert listed(_model("kept-model", input_tokens=3))

    said = _listing(_model("kept-model", input_tokens=30))
    said["currency"] = "JPY"
    source = tmp_path / "yen.json"
    source.write_text(json.dumps(said), encoding="utf-8")
    monkeypatch.setenv(prices.WHENCE, str(source))
    prices._tried = 0.0

    assert prices.refresh(wait=True) is False

    found = prices.price("kept-model")
    assert found is not None
    assert found.per_million["input"] == 3  # the dollars that were kept, not the yen


def test_nothing_is_fetched_where_somebody_has_said_not_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is what an air-gapped install wants, and what this suite runs under."""
    monkeypatch.setenv(prices.WHENCE, "off")
    prices._tried = 0.0

    assert prices.refresh(wait=True) is False


def test_nothing_kept_is_no_price_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """A first start, before anything has been fetched: tokens, and no bill beside them."""
    monkeypatch.setenv(prices.WHENCE, "off")

    assert prices.price("claude-haiku-4.5") is None
    assert prices.cost({"input": 1000}, "claude-haiku-4.5") is None


@pytest.mark.parametrize(
    ("dollars", "said"),
    [
        (0.0, "$0.00"),
        (0.0012, "$0.0012"),
        (0.42, "$0.42"),
        (12.345, "$12.35"),
        (1234.5, "$1,234"),
    ],
)
def test_a_bill_is_written_to_what_can_be_read_at_a_glance(
    dollars: float, said: str
) -> None:
    """And to four places under a cent: a tenth of one is still something spent."""
    assert prices.money(dollars) == said
