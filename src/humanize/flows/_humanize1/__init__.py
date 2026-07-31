"""PolyArch/humanize, as the parts a flow drives it with.

Ported from `PolyArch/humanize` 1.16.0, at 0ec921a: its three commands, its four subagents,
its six hooks and its forty prompt templates. The prompts here are that version's, word for
word, so a diff against `prompt-template/` in a later one shows what has moved.

Beside `humanize1.py` rather than in it because there is a lot of it, and the flow itself is
only the order it all happens in. Underscored, so that nothing looks for a flow in here.

- :mod:`planning` is what either agent is told while the idea is opened and the plan written.
- :mod:`prompts` is every word the loop itself says, kept as the plugin writes them.
- :mod:`blocks` is what the builder is told instead of being let go of.
- :mod:`loop` is the state the RLCR loop keeps and the gate a round has to pass.
- :mod:`guards` is what the builder may not do while the loop is running.
"""

from __future__ import annotations

from . import blocks, guards, loop, planning, prompts

__all__ = ["blocks", "guards", "loop", "planning", "prompts"]
