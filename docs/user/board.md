# The mission board

Asking somebody something **stops the turn**: the agent says what it wants, and nothing happens
until an answer comes back. That is right for a question and wrong for everything else a run
needs from you — what there is to do next, how far through it is, the thing you thought of
while it was running.

The board is the other shape. A handful of named lines, kept beside the run and shown on
[`/monitor`](/user/monitor). The flow reads and writes it whenever it likes, you change it
whenever you like, and **neither waits on the other** — an issue list without being one.

## Try it

```python
# .humanize/flows/board_loop/__init__.py
"""Work through whatever is on the board, and say how far through it is."""

from typing import NamedTuple

from hmz.flows import Agent, Person, flow


class Agents(NamedTuple):
    builder: Agent
    you: Person


@flow
def run(agents: Agents, task: str) -> None:
    board = agents.you.board
    board.put("todo", task, about="one thing a line; add more whenever you like")
    board.put("doing", "nothing yet", about="what it is on now", whose="flow")

    while waiting := [one for one in board.get("todo").splitlines() if one.strip()]:
        one, rest = waiting[0], waiting[1:]
        board.put("doing", one)
        agents.builder(one, suppress=True)
        board.put("todo", "\n".join(rest))
    board.put("doing", "nothing left")
```

```sh
hmz
```

Then name the flow on the line you were going to type anyway:

```
$board_loop write the parser
```

`board_loop` is this project's own flow, so it sits under **local** in
[`/flow`](/reference/tui#choosing-a-flow) — and since nothing here has run it before, naming it
on the line opens that menu with the cursor on it. Say what the one agent runs,
`claude/claude-opus-5:max` or whatever you have, and save: the line you already typed is what
it starts on.

Press **esc** for `/monitor`. Under the diagram is the board. Add a second line to `todo` while
the loop is working through the first, and it is picked up on the next round — nothing was
interrupted and nothing waited.

## From the prompt

It is drawn beside how far through the run is, rather than behind a command of its own: a board
you have to go and open is a board nobody reads.

```
  Board · what you and the flow both write on
    ◈ todo          write the parser
    ◈ doing         write the parser · flow's

      add           a line
```

| key | |
| --- | --- |
| `a` | put a line up: type a name, enter, then what it says. The `add` row below the lines does the same |
| enter | change the line under the cursor |
| `d` twice | take it off the board |

The board is the one place taking something away is still a key pressed twice. Everywhere else
in the interface a row opens onto a menu about itself, and being rid of it is a row in there;
enter on a line of the board opens the words of that line, which has no room for one. And it
lands the moment it is pressed — there is no menu to save and no walk out to change your mind on
— so the first press says what the second will do, and moving the cursor puts it down again.

## Whose each line is

A flow writing down how far through it is does not want that edited underneath it, and a list
of what you want next does not want rewriting by the thing that is meant to be reading it. So a
line says whose it is:

| `whose` | |
| --- | --- |
| `"both"` | either side writes it. The ordinary one — how the two hand something back and forth, and what a queue both of you add to and take from wants to be |
| `"user"` | yours. The flow reads it and is refused if it writes |
| `"flow"` | the flow's. You read it, and `/monitor` says so rather than opening an editor |

The other side is **refused where it writes**, with a `Refused` — a write that quietly did
nothing would be a flow that quietly does not do what it says.

## It is not a question

| | [`/questions`](/user/questions) | the board |
| --- | --- | --- |
| The turn | stops until it is answered | goes on |
| Who starts it | the agent | either of you |
| Where it is | in the transcript, once | on `/monitor`, until it changes |
| What it is for | one thing the agent cannot decide | what there is to do, and how far through it is |

A flow that has to have an answer asks. A flow that wants to *know whether* there is more to do
reads the board.

## From a flow

The other side of these keys is Python, and this is what the
[weaver](/weaver/human-agent#the-board-the-half-that-does-not-wait) puts on the board while you
are reading it:

```python
board = person.board

board.put("todo", "fix the build")           # write one, making it if it is not there
board.put("notes", "", about="what to know", whose="flow")
board.get("todo")                            # what it says now, or ""
board.get("nothing", "-")                    # what to answer when there is no such line
board.held("todo")                           # the whole Item, or None
board.items()                                # every line, in the order they went up
board.drop("todo")                           # take one off
board.moves("todo", to="done")               # rename it, keeping everything else
board.watch(lambda one: ...)                 # told whenever a line moves
```

An `Item` is `key`, `value`, `about`, `whose`, `at` — a monotonic moment, so a flow can tell a
line that moved from one that came back the same — and `by`, which is the side that wrote what
it says now. Writing a value keeps what the line is *for*: `about` is said once.

Everything is under one lock and what is read out is a copy, so a flow reading the board while
somebody types on it reads one moment of it rather than four moments of four lines.

The board is the person's, and a flow declares a person by taking one:
`agents: tuple[Agent, Person]`. Run from a command line, where nobody is there, the board is
still a board — the flow writes it and reads it — and nothing changes it from outside. A flow
built on somebody adding work will find nothing added, which is the same thing as an empty
queue.

## See also

- [Watching a run](/user/monitor) — where the board is drawn
- [Questions](/user/questions) — the half that does stop the turn
- [The person as an agent](/weaver/human-agent)
- [Callbacks as tools](/weaver/tools) — the other thing that does not stop a turn
