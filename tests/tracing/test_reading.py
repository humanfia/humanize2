"""The handful of readers every backend's log goes through on its way to a slice.

One log format per backend, and five functions they all share: what a record is, what fits on
a slice, what a trace may carry without becoming unloadable, what text is buried in a content
block, and what a tool call is named after. They are exercised sideways by every reader suite
here, which means each is covered for the shapes that backend happens to write and for no
others -- and the shapes that matter are the ones somebody's log turns out to have.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from hmz.runtime.tracing.session import (
    label,
    mapping,
    records,
    summarize,
    text_of,
    truncate,
)

if TYPE_CHECKING:
    from pathlib import Path

# ------------------------------------------------------------------ what a record is


def test_a_log_is_read_a_record_at_a_time_in_the_order_it_was_written(
    tmp_path: Path,
) -> None:
    at = tmp_path / "log.jsonl"
    at.write_text('{"at": 1}\n{"at": 2}\n', encoding="utf-8")

    assert [one["at"] for one in records(at)] == [1, 2]


def test_a_line_that_is_not_a_record_is_read_past(tmp_path: Path) -> None:
    """A log is appended to while it is being written, so the last line is often half of one."""
    at = tmp_path / "log.jsonl"
    at.write_text('{"at": 1}\nnot json at all\n{"at": 2}\n{"half":\n', encoding="utf-8")

    assert [one["at"] for one in records(at)] == [1, 2]


def test_a_record_that_is_not_a_mapping_is_not_a_record(tmp_path: Path) -> None:
    at = tmp_path / "log.jsonl"
    at.write_text('[1, 2, 3]\n"a string"\n{"at": 1}\n', encoding="utf-8")

    assert [one["at"] for one in records(at)] == [1]


# ------------------------------------------------------------- what fits on a slice


def test_what_a_slice_is_named_is_one_line_however_many_it_was() -> None:
    assert summarize("one\n  two\tthree ") == "one two three"


def test_a_name_too_long_for_a_slice_is_cut_short() -> None:
    said = summarize("x" * 200)

    assert len(said) == 96
    assert said.endswith("…")


def test_a_name_that_fits_is_left_whole() -> None:
    assert summarize("short enough") == "short enough"


# ------------------------------------------ what a trace may carry and stay loadable


def test_a_long_string_says_how_much_of_it_was_left_out() -> None:
    said = truncate("x" * 5000)

    assert said.startswith("x" * 4096)
    assert "+904 chars" in said


def test_a_string_that_fits_is_left_alone() -> None:
    assert truncate("short enough") == "short enough"


def test_a_wide_list_says_how_many_more_there_were() -> None:
    said = cast("list[Any]", truncate(list(range(500))))

    assert str(said[-1]).startswith("… (+")
    assert len(said) < 500


def test_the_strings_inside_a_structure_are_clipped_too() -> None:
    """A trace is made unloadable by one long value as easily as by a long top-level one."""
    said = truncate({"out": ["y" * 5000], "kept": 3}, 10)

    assert said["kept"] == 3
    assert "+4990 chars" in said["out"][0]


def test_the_names_inside_a_structure_come_back_as_strings() -> None:
    """JSON has no integer key, and a trace is JSON before anybody reads it."""
    assert truncate({1: "one"}) == {"1": "one"}


def test_what_is_neither_a_string_nor_a_container_is_left_as_it_is() -> None:
    assert truncate(7) == 7
    assert truncate(None) is None
    assert truncate(True) is True


# -------------------------------------------------------------- reading a log field


def test_a_field_that_is_a_mapping_is_read_as_one() -> None:
    assert mapping({"one": 1}) == {"one": 1}


def test_a_field_that_is_anything_else_is_read_as_an_absent_one() -> None:
    """Every backend writes a field it sometimes omits, and a reader must not stop for it."""
    assert mapping(None) == {}
    assert mapping("a string") == {}
    assert mapping([1, 2]) == {}


# --------------------------------------------------- the text inside a content block


def test_a_message_that_is_already_text_is_that_text() -> None:
    assert text_of("said outright") == "said outright"


def test_a_message_that_is_nothing_at_all_is_nothing() -> None:
    assert text_of(None) == ""


def test_the_blocks_of_a_message_are_joined_in_the_order_they_were_written() -> None:
    said = text_of(
        [
            {"type": "text", "text": "first"},
            "a bare string",
            {"type": "thinking", "thinking": "second"},
        ]
    )

    assert said == "first\na bare string\nsecond"


def test_a_block_says_its_text_under_whichever_name_that_backend_uses() -> None:
    """One writes `text`, one `thinking`, one `output`: the same thing under four names."""
    for name in ("text", "think", "thinking", "output", "content"):
        assert text_of([{name: "what it said"}]) == "what it said"


def test_a_block_that_carries_no_text_at_all_adds_nothing() -> None:
    assert text_of([{"type": "image", "source": {}}, {"text": "kept"}]) == "kept"


def test_something_in_the_list_that_is_not_a_block_is_read_past() -> None:
    assert text_of([7, None, {"text": "kept"}]) == "kept"


def test_a_message_written_as_a_mapping_is_read_through_it() -> None:
    assert text_of({"content": [{"text": "inside"}]}) == "inside"


def test_something_that_is_none_of_these_is_written_out_as_it_stands() -> None:
    """A reader that dropped it would leave a slice with nothing on it at all."""
    said = text_of(7)

    assert json.loads(said) == 7


# ------------------------------------------------------- what a tool call is named


def test_a_tool_given_a_string_is_named_after_it() -> None:
    assert label("shell", "cat one.py") == "shell: cat one.py"


def test_a_tool_is_named_after_the_most_descriptive_field_it_was_given() -> None:
    assert label("Bash", {"command": "cat one.py"}).startswith("Bash: ")


def test_a_tool_given_nothing_worth_saying_is_named_after_itself() -> None:
    assert label("Bash", {}) == "Bash"
    assert label("Bash", None) == "Bash"
    assert label("Bash", "   ") == "Bash"


def test_a_field_that_is_there_and_empty_is_not_the_one_to_name_it_after() -> None:
    assert label("Bash", {"command": "   "}) == "Bash"
