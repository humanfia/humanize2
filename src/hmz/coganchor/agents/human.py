"""The person at the prompt, driven as an agent -- which is what they are to a flow.

A flow that is a conversation has two sides, and only one of them was a thing a flow could
name. What the other side said arrived through a hook hung off whichever agent happened to be
talking, which is a way of asking the person something without ever saying that is what is
happening. Here they are an agent: it is said to, and it answers, and the answer is what was
typed. `agents.human(said)` reads as what it does.

Asked for a shape, they are asked a question per field: the description the flow wrote where it
declared the field, the answers it will take where those are a fixed few, and what is typed
read back through the model. Which is the same thing a coding agent's own `AskUserQuestion`
does, put where a flow can reach it -- and more than that one does, since the flow says the
shape of the whole answer rather than one multiple choice at a time, and says it in the model
it is going to use.

Not a coding agent. It runs no model, spends nothing, and takes no turn that anyone is
watching -- the transcript already has what was typed, behind the `❯` it was typed at. Which
is why it is not among the agents a flow is configured with: nobody chooses what the person
runs, so a flow that names one is handed one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, get_args, get_origin

from .base import AgentBase, SessionBase
from .board import Board
from .config import AgentConfig
from .event import Event, Question

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

    from pydantic import BaseModel
    from pydantic.fields import FieldInfo

    from .hooks import Moment

__all__ = ["HumanAgent", "HumanSession"]

#: How many times a field is put again once what was typed is not what it takes. The first
#: ask and two corrections: somebody told twice what is wrong who types a third wrong thing
#: is somebody who is not going to fill this in, and a flow must not wait on them forever.
_TRIES = 3

#: What a switch is offered as. Both are words pydantic reads back as a boolean, so what is
#: shown is also what is answered -- there is no second spelling of `yes` for this to get
#: wrong.
_YES, _NO = "yes", "no"

#: What is typed to leave a field at what the flow declared it as. A word rather than an empty
#: answer, because an empty answer is how every prompt here says nobody answered -- and a dash
#: is short, is on every keyboard, and is nobody's idea of a value.
_LEAVE = "-"

#: What is said about a field the model will take more than one of, and about one that takes
#: a number, where the options do not already say. A field with options needs neither.
_SEVERAL = " (several, separated by commas)"
_NUMBER = " (a number)"


def _says(value: object) -> str:
    """One default, as a person is told it.

    Args:
      value: What the field falls back to.

    Returns:
      A switch as `yes` or `no`, and anything empty as the word for it: a default shown as
      `''` is a default nobody knows how to type.
    """
    if isinstance(value, bool):
        return _YES if value else _NO
    return "nothing" if value in ("", None) else str(value)


def _listed(kind: object) -> bool:
    """Whether a field takes several answers rather than one.

    Args:
      kind: What the field was annotated with.

    Returns:
      True for a list, a tuple or a set of things -- including one written as `list[str] |
      None`, which is the same question with a way of not answering it.
    """
    for said in (kind, *get_args(kind)):
        if get_origin(said) in (list, tuple, set, frozenset):
            return True
    return False


def _options(field: FieldInfo) -> tuple[str, ...]:
    """The answers a field will take, where they are a fixed few.

    Args:
      field: The field, as the model declared it.

    Returns:
      The words of a literal in the order the flow wrote them, `yes` and `no` for a switch,
      and nothing at all for a field that is written rather than chosen.
    """
    kind = field.annotation
    # `Literal["a", "b"] | None` and `Literal["a", "b"]` offer the same few answers, so the
    # union is unwrapped before the literal is read off it.
    for said in (kind, *get_args(kind)):
        if get_origin(said) is Literal:
            return tuple(str(one) for one in get_args(said))
    if kind is bool:
        return (_YES, _NO)
    return ()


def _asking(name: str, field: FieldInfo, about: str = "") -> Question:
    """One field, as the question a person is put.

    Args:
      name: What the field is called, which is what it is asked as where the flow wrote no
        description: a field is named for what it holds, and an underscore is a space.
      field: The field, as the model declared it.
      about: What to say above it -- what the flow is asking about on the first question, and
        what the model said was wrong with the last answer on a second go at one.

    Returns:
      The question, with whatever answers the field will take.
    """
    said = field.description or name.replace("_", " ")
    offered = _options(field)
    hint = ""
    if not offered:
        if _listed(field.annotation):
            hint = _SEVERAL
        elif field.annotation in (int, float):
            hint = _NUMBER
    if not field.is_required():
        said_default = _says(field.get_default(call_default_factory=True))
        hint += f" -- or `{_LEAVE}` for {said_default}"
    return Question(
        text=f"{about}\n\n{said}{hint}" if about else said + hint, options=offered
    )


def _read(schema: type[BaseModel], answers: dict[str, str]) -> dict[str, Any]:
    """What was typed, as the fields the model is to read.

    Every answer is held as it was typed and handed to the model to read back, so a field is
    only ever wrong in one place: pydantic coerces `yes`, `42` and `discussion` into the bool,
    the int and the literal the flow declared. A field that takes several is the one thing
    that has to be cut up first -- a line of them is how a person writes a list.

    Args:
      schema: The model being filled in.
      answers: What was typed, field by field.

    Returns:
      The fields, ready for the model.
    """
    read: dict[str, Any] = {}
    for name, said in answers.items():
        field = schema.model_fields[name]
        read[name] = (
            [one.strip() for one in said.split(",") if one.strip()]
            if _listed(field.annotation)
            else said
        )
    return read


class HumanSession(SessionBase):
    """One conversation with the person: said to, and answered when they answer."""

    def stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Says something to the person and waits for what they say back.

        Overridden rather than implemented through `_stream`, so that this is not bracketed
        by the `begins` and `ends` that say whose turn it is: the person's turn is not one
        being watched. Counting it would put them in the graph of who handed to whom and spin
        a clock at them while they thought, which is a run of a flow saying that the flow is
        working when the flow is waiting.

        Args:
          prompt: What to say to them, which they have already read -- it is what the agent
            just said, and the transcript is where they read it. Where a shape is asked for
            it is said again above the first question, since a questionnaire that opened on
            its first field would be a form with no title.
          schema: The shape to fill in, or None to take whatever they type. A person is never
            shown a schema: they are asked a question per field and it is built out of the
            answers, which is :meth:`_filled`.

        Yields:
          One `result`: what they said back, the shape they filled in as its own JSON, or ""
          once there will be nothing more -- which is how a flow that is a conversation learns
          the conversation is over, and how one that asked for a shape learns nobody answered.
        """
        if schema is None:
            yield Event(kind="result", text=self._agent.prompted() or "")
            return
        yield Event(kind="result", text=self._filled(prompt, schema))

    def _filled(self, prompt: str, schema: type[BaseModel]) -> str:
        """Puts the model to the person a field at a time, and builds it out of the answers.

        Each field is one question, put through the same road a coding agent's own question
        takes: whatever is driving this agent shows it and answers it. What the model refuses
        is put back to them, on the field it was refused for and in the model's own words,
        because the flow that declared the field is the only thing that knows what it will
        take -- and this is the moment there is somebody there to be told.

        Args:
          prompt: What the flow is asking about, said above the first question.
          schema: The shape to fill in.

        Returns:
          The filled-in model as JSON, or "" for a questionnaire nobody was there to answer,
          one they walked away from, or one that was still wrong after being put back.
        """
        from pydantic import ValidationError

        answers: dict[str, str] = {}
        about = prompt
        for name, field in schema.model_fields.items():
            said = self._agent.asked(_asking(name, field, about))
            if said is None:
                return (
                    ""  # nobody there, or they have gone: there is no answer to build
                )
            about = ""
            self._answered(schema, answers, name, said)
        for _ in range(_TRIES):
            try:
                return schema.model_validate(_read(schema, answers)).model_dump_json()
            except ValidationError as refused:
                for wrong in refused.errors():
                    where = wrong.get("loc") or ()
                    named = str(where[0]) if where else ""
                    if named not in schema.model_fields:
                        # The model refused the answers together rather than one of them --
                        # a rule of the flow's own. There is no field to put back.
                        return ""
                    said = self._agent.asked(
                        _asking(named, schema.model_fields[named], str(wrong["msg"]))
                    )
                    if said is None:
                        return ""
                    self._answered(schema, answers, named, said)
        return ""

    @staticmethod
    def _answered(
        schema: type[BaseModel], answers: dict[str, str], name: str, said: str
    ) -> None:
        """Writes one answer down, or leaves the field to the model's own default.

        A dash at a field that has a default is that default: the field is left out, and the
        model fills it in as it would for anything nobody was asked about. Which holds on a
        field put back as much as on one first asked -- what a person types means the same
        thing the second time they are asked it.

        Args:
          schema: The shape being filled in.
          answers: What has been typed so far, written into.
          name: The field.
          said: What they typed at it.
        """
        if said.strip() == _LEAVE and not schema.model_fields[name].is_required():
            answers.pop(name, None)
            return
        answers[name] = said.strip()

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Never called: `stream` is what a turn of this goes through.

        Args:
          prompt: What to say to them.
          schema: The shape to fill in.

        Yields:
          Nothing.
        """
        yield from self.stream(prompt, schema=schema)


class HumanAgent(AgentBase):
    """Whoever is at the prompt, said to as an agent and answering as one.

    Made by whatever is driving the flow rather than by the flow: the person is reached
    through the interface they are sitting at, and a flow only says that it is talking to
    them. Run from a command line, where nobody is at a prompt, they answer "" the first time
    they are asked -- so a flow that is a conversation does the one thing it was given and
    returns, rather than waiting on somebody who is not there.
    """

    #: None. A moment is a point in a turn of a model, and the person takes no such turn:
    #: there is no tool to be told about, nothing to send them on from, and a prompt that
    #: refused them would be an interface refusing what was typed at it.
    moments: ClassVar[frozenset[Moment]] = frozenset()

    def __init__(self, *, name: str = "human") -> None:
        """Initializes the person as an agent.

        Args:
          name: What to call them, which a flow that names its agents overrides as it does
            for any other.
        """
        super().__init__(AgentConfig(model="human", effort=""), name=name)
        #: The board this person and the flow both write on, which is the other half of
        #: talking to them: a question stops the turn until it is answered, and this stops
        #: nothing at all. Theirs rather than the flow's because the flow is a function that
        #: returns and the board outlives any one turn of it.
        self._board = Board()

    @property
    def board(self) -> Board:
        """What the flow and the person both write on, and neither waits at.

        A handful of named lines kept beside the run and shown where the run is shown: what
        there is to do, how far through it is, what somebody thought of while it was
        running. The flow reads and writes it whenever it likes and the person changes it
        whenever they like, so neither is ever held up by the other -- which is what makes it
        the place a run's work queue goes, and `asked` the place a question goes.
        """
        return self._board

    def _remade(self, config: AgentConfig, name: str | None) -> HumanAgent:  # noqa: ARG002
        """Another person, which is the same person: they are made rather than configured.

        Args:
          config: What they run at, which is nothing: a person runs no model.
          name: What to call them, or None for the name a person is made under.

        Returns:
          The new agent. It is another person and so another board: what was on the first is
          that run's, and a copy of it moving under both would be two boards saying one thing.
        """
        return type(self)(name=name or "human")

    def new(self, cwd: str | os.PathLike[str] | None = None) -> HumanSession:
        """Opens a conversation with them.

        Returns:
          The session. There is nothing to open: the person is already there, or is not.
        """
        return HumanSession(self, cwd)
