"""What the socket between a run and the terminals reading it carries.

A frame is a kind and some bytes, and there are six kinds. Five of them are a terminal: the
one that says a terminal has arrived and how big it is, the two that carry the keys one way
and the screen the other, the one that says it has been resized, and the one that says the
run has let go. The sixth is a line asking the run a question about itself, which is what
`hmz daemon` sends and closes.

Framed rather than a raw pipe both ways, because the two directions are not only bytes: a
terminal that has been resized has to say so, and a run that is letting go has to say that
rather than closing a socket a terminal would read as the machine going down.
"""

from __future__ import annotations

import json
import struct
from typing import Any, cast

__all__ = [
    "CONTROL",
    "GONE",
    "HELLO",
    "INPUT",
    "OUTPUT",
    "RESIZE",
    "Frames",
    "asked",
    "frame",
    "spoken",
]

#: A terminal has arrived, and how many columns and rows it has.
HELLO = b"H"
#: What was typed at a terminal, on its way to the run.
INPUT = b"I"
#: What the run has drawn, on its way to every terminal reading it.
OUTPUT = b"O"
#: A terminal has been resized, and is these many columns and rows now.
RESIZE = b"R"
#: The run has let go of this terminal, and why.
GONE = b"X"
#: A question about the run rather than a terminal reading it, answered with one of the same.
CONTROL = b"C"

#: How long a frame may be. A screen is kilobytes and a paste is not much more; a length
#: longer than this is a socket that is not carrying this protocol.
_LONGEST = 1 << 22

#: The kind, and then the length: one byte and four, which is what every frame begins with.
_HEAD = struct.Struct(">cI")


def frame(kind: bytes, payload: bytes = b"") -> bytes:
    """One frame, ready to be written.

    Args:
      kind: Which of the six it is.
      payload: What it carries.

    Returns:
      The bytes.
    """
    return _HEAD.pack(kind, len(payload)) + payload


def spoken(kind: bytes, said: dict[str, Any]) -> bytes:
    """One frame carrying a mapping, which is how a question and its answer are written."""
    return frame(kind, json.dumps(said).encode())


def asked(payload: bytes) -> dict[str, Any]:
    """What one such frame said, and nothing at all for one that is not a mapping."""
    try:
        held: object = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError):
        return {}
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}


class Frames:
    """A socket read a piece at a time, and the whole frames that came out of it.

    A stream socket hands back whatever has arrived, which is half a frame as often as it is
    two: what is read is fed in here and what has been completed comes back out.
    """

    def __init__(self) -> None:
        #: What has arrived and is not a whole frame yet, which is nothing most of the time:
        #: a read is usually one whole frame, being a screen on its way to a terminal or a
        #: keystroke on its way back.
        self._held = b""

    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]:
        """Takes what was read, and gives back every whole frame in it.

        Answered whole rather than a frame at a time. What is read is taken out of the buffer
        before any of it is handed over, so that a caller which stops reading partway -- a
        terminal that has just been told the run is over -- cannot leave a frame that has
        been handed out sitting in the buffer to be handed out again.

        Args:
          data: What came off the socket.

        Returns:
          The kind and the payload of each frame that is now complete, in the order they
          arrived, and nothing at all where none is.

        Raises:
          ValueError: If a length arrives that no frame of this protocol has, which is a
            socket carrying something else.
        """
        held = self._held + data if self._held else data
        at = 0
        whole: list[tuple[bytes, bytes]] = []
        while len(held) - at >= _HEAD.size:
            kind, length = _HEAD.unpack_from(held, at)
            if length > _LONGEST:
                self._held = b""
                raise ValueError(f"a frame of {length} bytes is not one of these")
            if len(held) - at < _HEAD.size + length:
                break
            begins = at + _HEAD.size
            at = begins + length
            whole.append((kind, held[begins:at]))
        self._held = held[at:] if at else held
        return whole
