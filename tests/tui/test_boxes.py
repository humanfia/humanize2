"""Where the questions that arrive rather than being walked to are drawn.

A sheet is walked to and fills the width it is drawn in, so one drawn from the top left is a
sheet drawn right. A box is the other kind of question -- it arrives over whatever was there,
says one thing and is answered in a keypress -- and one drawn from the top left is a box that
has lost the thing that made it one.

All of them together in one test, because being in the middle is a rule each box says under
its own name: what a sheet is drawn from is scoped to that sheet, so a rule naming another one
matches nothing. A box that inherited the box and not the rule is drawn in the corner, and
nothing but the drawing says so.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pytest

from hmz.tui import Humanize
from hmz.tui.pick import Confirms, Leaves, Popup, Reports
from tests.tui.conftest import until

if TYPE_CHECKING:
    from collections.abc import Callable

#: A terminal big enough that the middle is nowhere near the corner: the box is 66 columns
#: wide, so anything narrower than that would be centred at the left edge either way.
WIDE, TALL = 100, 40


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "opens",
    [
        pytest.param(Confirms, id="confirms"),
        pytest.param(partial(Leaves, held=False), id="leaves"),
        pytest.param(Reports, id="reports"),
    ],
)
async def test_a_box_is_drawn_in_the_middle_of_the_screen(
    opens: Callable[[], Popup],
) -> None:
    app = Humanize()
    async with app.run_test(size=(WIDE, TALL)) as driver:
        await app.push_screen(opens())
        await until(lambda: isinstance(app.screen, Popup), driver)
        drawn = app.screen.query_one("#sheet").region

    # A box that filled the width would be in the middle of it by accident.
    assert drawn.width < WIDE
    assert drawn.x == (WIDE - drawn.width) // 2
    assert drawn.y == (TALL - drawn.height) // 2
