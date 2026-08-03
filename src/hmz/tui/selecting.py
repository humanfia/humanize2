"""The two things on the screen that are read rather than answered, and copied off it.

A terminal interface has the mouse. It asks for the drags as well as the clicks -- that is what
a scrollbar and a list under a cursor are for -- and a terminal that is sending them somewhere
is a terminal that is no longer selecting anything itself. So the selection is the interface's
to draw and the interface's to hand over, and the one thing that makes that worth having is
handing over the *text*: a terminal copies its screen, and a screen is a line broken wherever
the width ran out with the spaces that padded each row out to the edge still on it.

Textual will work out what a drag covered, but only from a widget that can say, cell by cell,
which character of which line of its own text it is drawing there. It says so by leaving that
pair on each drawn cell as it draws it, and it leaves it on nothing that came out of Rich --
which threw the text away at the moment it wrapped it. Both widgets here therefore keep what
they were given as the text it was, wrap it themselves, and say for every row which line it is
a piece of and where in that line it begins. Dragging across the four rows one long line came
out as copies one line.

The rows a widget draws and the lines it holds are two different counts, and everything in this
module is about keeping the second one straight while the first is what is on the screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NamedTuple

from rich.cells import get_character_cell_size
from rich.segment import Segment
from rich.style import Style as RichStyle
from textual import events
from textual.content import Content
from textual.geometry import Offset, Size
from textual.scroll_view import ScrollView
from textual.selection import Selection
from textual.strip import Strip
from textual.style import Style
from textual.visual import Visual, visualize
from textual.widgets import OptionList

if TYPE_CHECKING:
    from textual.geometry import Region
    from textual.widget import Widget

#: How many clicks in a row take the word under them, and how many take the whole line. What a
#: terminal gives for each, and what somebody clicking twice on a path or three times on a
#: wrapped line is asking for.
_WORD, _LINE = 2, 3


class _Row(NamedTuple):
    """One row of a transcript as it is drawn, and which line of it the row is a piece of.

    Attributes:
      strip: What to draw.
      line: Which line of the text the row came out of. Several rows share one line where the
        terminal was too narrow to hold it in one.
    """

    strip: Strip
    line: int


class _Written(NamedTuple):
    """Something put in a transcript, kept as it was given so that it can be drawn again.

    Attributes:
      content: The markup it was written as, or something Rich draws.
      shrink: Whether it is drawn to fit the width there is.
    """

    content: object
    shrink: bool


class Transcript(ScrollView, can_focus=False):
    """What has been shown, kept as the text it was written as rather than as what it drew.

    A transcript is read with the eyes and taken with the mouse: a path out of a traceback, an
    id, the paragraph one agent wrote that is going to another. So what is written is kept as
    what it was, wrapped again whenever the terminal changes width, and every row drawn says
    which line of that text it is a piece of and where in the line it starts. Dragging across
    two lines copies the one newline that is really there, and nothing of the interface is in
    what comes back -- because the interface is not what is being read from.

    A thing Rich draws rather than says -- the box the interface opens with -- is kept as the
    rows it drew, each row a line of its own. There is no text behind a box to go back to:
    what a border is is where it is, and somebody dragging across one is dragging across a
    picture.

    It does not take focus. The editor is the only thing on the screen that is typed at, and a
    click that begins a selection must not be a click that stops the prompt from working.

    It stays at the end while it is at the end. What is written is written as it happens, so
    the bottom of it is where the flow is, and it follows that until somebody scrolls away to
    read something further up -- and follows it again as soon as they come back down. Being at
    the end is therefore held as a thing that was asked for rather than worked out from where
    the scrollbar is: the transcript is one of several things sharing the height of a terminal
    -- a list of commands opens over it, the editor grows a row per line typed into it, the
    terminal itself is resized -- and each of those leaves the last line of it further up the
    screen without anybody having scrolled anything.
    """

    DEFAULT_CSS = """
    /* Lines are wrapped rather than scrolled sideways -- a row is only ever a piece of one
       line, which is what lets a selection over several be given back as that line. Sideways
       is left on all the same, for the one thing that is not a line: a box Rich drew wider
       than the terminal is reached that way rather than cut. The scrollbar down the side is
       always there, so that the width lines are wrapped to does not change under them. */
    Transcript { overflow-y: scroll; overflow-x: auto;
                 background: $surface; color: $foreground; }
    """

    def __init__(self, id: str | None = None) -> None:  # noqa: A002 -- textual's own name
        """Initializes an empty transcript.

        Args:
          id: What to call it in the stylesheet and in a query.
        """
        super().__init__(id=id)
        #: What has been written, oldest first, kept so that a resize can draw it again.
        self._written: list[_Written] = []
        #: The rows as they are drawn now, one per row of the screen.
        self._rows: list[_Row] = []
        #: The text behind them, a line apiece: what a selection over the rows gives back.
        self._lines: list[str] = []
        self._joined: str | None = None
        #: The width the rows were drawn to, so that a resize is noticed. Nothing is drawn
        #: before the interface has been laid out, which is what -1 says.
        self._drawn_at = -1
        #: The widest row there is, which is what a thing Rich drew too wide to fit can be
        #: scrolled sideways to reach.
        self._widest = 0
        #: How a selection is marked, which is a theme away and is read once rather than per
        #: row drawn.
        self._marking: RichStyle | None = None

    @property
    def text(self) -> str:
        """The whole transcript as text: what was written, not what was drawn."""
        if self._joined is None:
            self._joined = "\n".join(self._lines)
        return self._joined

    def write(self, content: object, *, shrink: bool = True) -> None:
        """Puts something at the bottom of the transcript.

        Args:
          content: Markup, or something Rich draws.
          shrink: Whether to draw it to fit rather than at the width it asks for.
        """
        written = _Written(content, shrink)
        self._written.append(written)
        if (
            self._drawn_at > 0
            and self._drawn_at == self.scrollable_content_region.width
        ):
            self._drew(written)
            self._measured()
        else:
            self._draw()

    def clear(self) -> None:
        """Empties it, and lets go of a selection that was over what is now gone."""
        self._written.clear()
        self._rows.clear()
        self._lines.clear()
        self._joined = None
        self._widest = 0
        self._let_go()
        self.virtual_size = Size(0, 0)
        self.refresh()

    def on_mount(self) -> None:
        """Starts it following the end, which is where what is being written lands.

        Textual's own anchor, which pins a widget to the bottom as it is laid out rather than
        as it is written to. That is the difference that matters: what is added to a transcript
        is not the only thing that moves its end away from the bottom of the screen, and every
        other thing that does -- the offers opening over it, the editor growing, the terminal
        being resized -- happens as a layout and not as a write.
        """
        self.anchor()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """Takes the anchor up again where somebody has scrolled back down to the end.

        Scrolling anywhere at all lets the anchor go -- which is what keeps the transcript
        still while something further up is being read -- and coming back to the bottom is how
        somebody says there is nothing up there any more. Textual takes the anchor up again
        itself for a widget that scrolls the ordinary way, but :class:`ScrollView` answers a
        scroll by drawing it and nothing else, so it is said here.

        Args:
          old_value: Where it was scrolled to.
          new_value: Where it is scrolled to now.
        """
        super().watch_scroll_y(old_value, new_value)
        if new_value >= self.max_scroll_y:
            # Said as a scroll to the end it is already at, that being what takes the anchor
            # up. Down the page only: a box Rich drew too wide for the terminal is read by
            # scrolling across it, and reaching the end is no reason to be taken back.
            self.scroll_end(animate=False, immediate=True, x_axis=False)

    def on_resize(self) -> None:
        """Draws everything again where the terminal is now a different width.

        A line is wrapped to the width it is read at, so a terminal that has changed width has
        a transcript wrapped to a width that is gone. A terminal that changed height has not:
        the same lines break in the same places, and a run of days is not worth wrapping again
        to say so.
        """
        if self._drawn_at != self.scrollable_content_region.width:
            self._draw()

    def notify_style_update(self) -> None:
        """Forgets how a selection is marked, the theme having changed under it."""
        self._marking = None
        super().notify_style_update()

    def _let_go(self) -> None:
        """Drops a selection over this, what it was made against no longer being there.

        A selection is a place in the text -- which line, and how far into it -- so it means
        what it meant only while the lines it was made against are the lines there are. Two
        things end that: emptying the transcript, and drawing it again at another width, since
        a box Rich drew is as many lines as it is rows and is a different number of rows in a
        narrower terminal. Dropped rather than moved: what is under a selection is what a copy
        will take, and a selection that quietly comes to mean the lines below the ones somebody
        dragged across is worse than one that is gone.
        """
        if self.is_attached and self in self.screen.selections:
            self.screen.clear_selection()

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """What is under a selection, as text.

        Args:
          selection: Which part of the text behind the rows is selected, as Textual worked it
            out from what each drawn cell said it was drawing.

        Returns:
          The text and what follows it, which is a newline: this is a widget of many lines, and
          whatever is under it on the screen is a line of its own.
        """
        return selection.extract(self.text), "\n"

    def on_click(self, event: events.Click) -> None:
        """Takes the word under two clicks and the whole line under three.

        Textual's own answer to both is the whole widget, which here is every line of a run
        that has been going for a day -- and, since a selection is copied as it is let go of,
        a double click would put all of it on the clipboard.

        Args:
          event: The click, whose `chain` says how many it is of.
        """
        at = self.scroll_offset.y + event.y
        if event.chain < _WORD or at >= len(self._rows):
            return
        # Textual's own is on the class this one comes from, and would run after this one and
        # select everything over the top of it.
        event.prevent_default()
        row = self._rows[at]
        _took(
            self,
            row.line,
            _wanted(
                self._lines[row.line],
                # Less the room drawn round it, since a click is where it landed on the
                # widget and a row begins where the widget's own padding ends.
                _under(row.strip, self.scroll_offset.x + event.x - self.gutter.left),
                event.chain,
            ),
        )

    def render_line(self, y: int) -> Strip:
        """Draws one row, marked where a selection covers it and saying where it came from.

        Args:
          y: Which row of the screen, counting from the top of the widget.

        Returns:
          The row.
        """
        scroll_x, scroll_y = self.scroll_offset
        width = self.scrollable_content_region.width
        at = scroll_y + y
        if at >= len(self._rows):
            # Under the last line there is: pointed at the end of it, so that a drag begun in
            # the empty room below the text is a drag from the end of the text. Said rather
            # than left blank, since a row that says nothing about itself is one Textual can
            # only take to mean the whole widget.
            ending = len(self._lines) - 1
            return Strip.blank(width, self.rich_style).apply_offsets(
                len(self._lines[ending]) if ending >= 0 else 0, max(ending, 0)
            )
        row = self._rows[at]
        selection = self.text_selection
        span = None if selection is None else selection.get_span(row.line)
        if span is not None:
            if self._marking is None:
                self._marking = Style.from_styles(
                    self.screen.get_component_styles("screen--selection")
                ).rich_style
            # Marked before it is cut, the span being a span of the line rather than of the
            # part of the line that is on the screen.
            row = row._replace(strip=_marked(row.strip, span, self._marking))
        strip = row.strip.crop_extend(scroll_x, scroll_x + width, self.rich_style)
        begins = _begins(row.strip)
        if scroll_x or begins is None:
            # Two rows that have to be said again from scratch: one cut from the left, whose
            # cells are no longer where they were, and one with nothing on it to have been
            # said by -- a line with no text on it is still a place a drag can begin.
            strip = strip.apply_offsets(
                _under(row.strip, scroll_x) if begins is not None else 0, row.line
            )
        return strip

    def _draw(self) -> None:
        """Draws everything there is at the width there is, from the top."""
        self._let_go()
        self._rows.clear()
        self._lines.clear()
        self._joined = None
        self._widest = 0
        self._drawn_at = self.scrollable_content_region.width
        if self._drawn_at <= 0:
            return  # nothing is laid out yet, and a line has no width to be wrapped to
        for written in self._written:
            self._drew(written)
        self._measured()
        self.refresh()

    def _measured(self) -> None:
        """Says how big the transcript now is, which is what there is to scroll through."""
        self.virtual_size = Size(max(self._widest, self._drawn_at), len(self._rows))

    def _drew(self, written: _Written) -> None:
        """Draws one thing that was written, adding its rows and the text behind them.

        Args:
          written: The thing, as it was given.
        """
        width, style = self._drawn_at, self.visual_style
        if not isinstance(written.content, str):
            # Something Rich draws. What it draws is a picture of its own, so each row it
            # comes out as is a line to itself: there is no text under a border.
            visual = visualize(self, written.content)
            asked = visual.get_optimal_width(self.styles.get_rules(), width)
            for strip in Visual.to_strips(
                self,
                visual,
                min(asked, width) if written.shrink else asked,
                None,
                style,
                apply_selection=False,
            ):
                at = len(self._lines)
                self._lines.append(strip.text)
                self._widest = max(self._widest, strip.cell_length)
                self._rows.append(_Row(strip.apply_offsets(0, at), at))
            self._joined = None
            return
        # Markup, taken as Rich's -- which is what it was written as, and what says which of
        # the sixteen colours it is in. Line by line, so that each row knows which line it
        # belongs to however many rows that line turns out to need.
        for line in Content.from_rich_text(written.content).split(allow_blank=True):
            at = len(self._lines)
            self._lines.append(line.plain)
            for strip in Visual.to_strips(
                self, line, width, None, style, apply_selection=False
            ):
                begins = _begins(strip)
                self._widest = max(self._widest, strip.cell_length)
                self._rows.append(
                    _Row(
                        strip.apply_offsets(0 if begins is None else begins[0], at), at
                    )
                )
        self._joined = None


class Choices(OptionList):
    """A list of things to pick from, whose rows can be read off the screen as well as picked.

    A list is answered by picking a line, so most of what is in one is not worth copying. But
    some of it is -- the model id somebody wants in a command line, the path a flow of theirs
    was found at -- and a screen where one thing can be dragged across and the thing beside it
    cannot is a screen nobody can tell by looking.

    Textual leaves the offsets a selection needs on each row it draws, but numbers them against
    the option the row came out of rather than against the list. So a row is renumbered against
    the whole of it as it is drawn, and what a selection gives back is the options' own text --
    a row too long for the list comes back as the one line it was written as, without the
    spaces that padded it out to the edge.
    """

    ALLOW_SELECT: ClassVar[bool] = True

    def __init__(self, id: str | None = None) -> None:  # noqa: A002 -- textual's own name
        """Initializes an empty list.

        Args:
          id: What to call it in the stylesheet and in a query.
        """
        super().__init__(id=id)
        #: The text of the options, a line apiece, and where each option's lines start in it.
        self._text: list[str] = []
        self._starts: list[int] = []
        #: Which options that was counted for, so that a list which has not changed is not
        #: counted again for every row of it that is drawn.
        self._counted_for: tuple[int, int, int] = (0, 0, 0)
        #: How a selection is marked, as the transcript keeps it.
        self._marking: RichStyle | None = None

    def notify_style_update(self) -> None:
        """Forgets how a selection is marked, the theme having changed under it."""
        self._marking = None
        super().notify_style_update()

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """What is under a selection, as the text of the options rather than as rows.

        Args:
          selection: Which part of that text is selected.

        Returns:
          The text and the newline that follows it.
        """
        self._counted()
        return selection.extract("\n".join(self._text)), "\n"

    def on_click(self, event: events.Click) -> None:
        """Takes the word under two clicks and the whole line under three, as anywhere else.

        Textual's own answer to both is every row of the list, which is a whole sheet on the
        clipboard for a click that landed twice.

        Args:
          event: The click.
        """
        if event.chain < _WORD:
            return
        event.prevent_default()
        self._counted()
        strip = self.render_line(event.y)
        begins = _begins(strip)
        if begins is None:
            return  # a row with nothing on it: a spacer between two groups of options
        line = begins[1]
        # Less the room drawn round it: a list is indented by its own padding, and a click is
        # where it landed on the widget rather than where the row it landed on begins.
        at = _under(strip, event.x - self.gutter.left)
        _took(self, line, _wanted(self._text[line], at, event.chain))

    def render_lines(self, crop: Region) -> list[Strip]:
        """Counts the lines the options come to, then draws as the list itself draws.

        Args:
          crop: What of it is on the screen.

        Returns:
          The rows.
        """
        self._counted()
        return super().render_lines(crop)

    def render_line(self, y: int) -> Strip:
        """Draws one row, numbered against the whole list and marked where it is selected.

        Args:
          y: Which row of the screen, counting from the top of the widget.

        Returns:
          The row.
        """
        self._counted()
        strip = super().render_line(y)
        at = self.scroll_offset.y + y
        if at >= len(self._lines):
            # Under the last option, in a list drawn taller than what is in it.
            ending = len(self._text) - 1
            return strip.apply_offsets(
                len(self._text[ending]) if ending >= 0 else 0, max(ending, 0)
            )
        option, _ = self._lines[at]
        begins = _begins(strip)
        line = self._starts[option] + (0 if begins is None else begins[1])
        # A row with nothing said on it is a row Textual can only take to mean the whole list,
        # so a spacer between two groups of options is said to be the blank line it is.
        strip = _numbered(strip, line) if begins else strip.apply_offsets(0, line)
        selection = self.text_selection
        span = None if selection is None else selection.get_span(line)
        if span is None:
            return strip
        if self._marking is None:
            self._marking = Style.from_styles(
                self.screen.get_component_styles("screen--selection")
            ).rich_style
        return _marked(strip, span, self._marking)

    def _counted(self) -> None:
        """Reads the options' own text, and where each option's lines start among them.

        What is read is what the option was made with rather than what it was drawn as: a row
        the list was too narrow to hold is drawn over two rows and is still one line, and that
        line is what a drag across both of them is asking for.
        """
        options = self.options
        # By what the options are rather than by what they say: a sheet puts its list up again
        # by making every row of it over, so the ends of it change whenever any of it does.
        seen = (
            len(options),
            id(options[0]) if options else 0,
            id(options[-1]) if options else 0,
        )
        if seen == self._counted_for:
            return
        self._counted_for = seen
        self._text, self._starts = [], []
        for option in options:
            self._starts.append(len(self._text))
            drawn = visualize(self, option.prompt)
            # Anything else is a picture rather than a line, and has no text to be read off.
            self._text.extend(
                drawn.plain.split("\n") if isinstance(drawn, Content) else [""]
            )


def _begins(strip: Strip) -> tuple[int, int] | None:
    """Where in the text a drawn row begins: the character, and the line.

    Which is what Textual worked out as it wrapped the line, and left on the row as it drew it:
    the part of a line that fell off the end of the row above starts wherever the words it took
    start.

    Args:
      strip: The row.

    Returns:
      The character and the line, or None for a row that says nothing about where it came from
      -- a line with nothing on it, and anything Rich drew.
    """
    for segment in strip:
        style = segment.style
        if style is not None and (offset := style.meta.get("offset")) is not None:
            return int(offset[0]), int(offset[1])
    return None


def _under(strip: Strip, column: int) -> int:
    """Which character of the line a row is a piece of is under a column of the screen.

    The two are not one count. A Chinese character is one character and two columns wide, and a
    row may begin part way into its line or be drawn a couple of columns in -- so what a column
    is over is asked of the row itself, cell by cell, rather than counted from its left edge.

    Args:
      strip: The row.
      column: The column, from the left of the row.

    Returns:
      The character, in the line the row came out of.
    """
    at, cells = 0, 0
    for segment in strip:
        style = segment.style
        offset = None if style is None else style.meta.get("offset")
        if offset is None:
            # Something drawn rather than written: the padding a row is filled out to the
            # edge with, or the room a list is indented by. It is columns and no characters.
            cells += segment.cell_length
            continue
        at = int(offset[0])
        for character in segment.text:
            if cells >= column:
                return at
            cells += get_character_cell_size(character)
            at += 1
    return at


def _numbered(strip: Strip, line: int) -> Strip:
    """One row, saying it is a piece of the line it is a piece of.

    A widget made of parts numbers each part's rows from that part -- an option list numbers
    them from the option -- and a selection is over one text rather than over a part of it. So
    the line is said again against the whole, and where in the line each cell is stays as it
    was.

    Args:
      strip: The row.
      line: Which line of the whole it is a piece of.

    Returns:
      The row, renumbered.
    """
    segments: list[Segment] = []
    for text, style, control in strip:
        if style is None or (offset := style.meta.get("offset")) is None:
            segments.append(Segment(text, style, control))
            continue
        renumbered = RichStyle.from_meta({**style.meta, "offset": (offset[0], line)})
        segments.append(Segment(text, style + renumbered, control))
    return Strip(segments, strip.cell_length)


def _marked(strip: Strip, span: tuple[int, int], marking: RichStyle) -> Strip:
    """One row with the selected part of it drawn as selected.

    Cut by character rather than by column, since the span is a span of the line's text: the
    two agree everywhere except where the text is wide, and there the columns are the wrong
    count to cut on. Where each part of the row sits in the line is what the row itself says,
    so a row drawn with room around it marks the words in it and not the room.

    Args:
      strip: The row.
      span: Which characters of its line are selected, as Textual's own selection reports them
        -- where -1 for the end means to the end of the line.
      marking: How the selected part is drawn.

    Returns:
      The row, marked.
    """
    start, end = span
    segments: list[Segment] = []
    for text, style, control in strip:
        offset = None if style is None else style.meta.get("offset")
        if offset is None:
            segments.append(Segment(text, style, control))
            continue
        at = int(offset[0])
        low = min(max(start - at, 0), len(text))
        high = len(text) if end == -1 else min(max(end - at, 0), len(text))
        if low >= high:
            segments.append(Segment(text, style, control))
            continue
        under = style if style is not None else RichStyle()
        cut = (
            (text[:low], style),
            (text[low:high], under + marking),
            (text[high:], style),
        )
        segments.extend(Segment(part, marks, control) for part, marks in cut if part)
    return Strip(segments, strip.cell_length)


def _wanted(line: str, at: int, chain: int) -> tuple[int, int]:
    """What clicking on a line twice takes of it, and what clicking three times takes.

    Args:
      line: The line clicked on.
      at: Which character of it was under the pointer.
      chain: How many clicks in a row this is.

    Returns:
      The characters to select, as a start and an end. A word is everything up to the spaces on
      either side of it: what somebody wants off a double click is the path or the identifier
      under it, and neither of those stops at a punctuation mark.
    """
    if chain >= _LINE:
        return 0, len(line)
    end = line.find(" ", at)
    return line.rfind(" ", 0, at) + 1, len(line) if end < 0 else end


def _took(widget: Widget, line: int, span: tuple[int, int]) -> None:
    """Selects part of one line of a widget, and says that a selection was made.

    Said again because the screen says it when the mouse is let go of, which is before the
    click that follows has been worked out to be a second or a third one -- and what is
    selected is copied by whoever is listening for that.

    Args:
      widget: What was clicked on.
      line: Which line of its text.
      span: Which characters of that line, as a start and an end.
    """
    start, end = span
    if start >= end:
        return  # a click on the spaces between two words, or on a line with nothing on it
    widget.screen.selections = {
        widget: Selection(Offset(start, line), Offset(end, line))
    }
    widget.post_message(events.TextSelected())
