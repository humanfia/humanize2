# Agents

## File Structure

```
.
├── __init__.py
├── base.py
├── claude.py
├── codex.py
└── kimi.py
```

## `__init__.py`

Expose AgentBase, SessionBase, and all agent and session classes.

## `agents/base.py`

The docstrings below are summaries; `base.py` carries the full Args/Returns/Raises.

```python
class SessionBase(ABC):
    agent: AgentBase
    session_id: str | None  # the backend's id, None until the first turn lands

    def __init__(self, agent: AgentBase):
        """Initializes an unopened session on the given agent."""
        ...

    def run(self, prompt: str) -> str:
        """Sends one turn, opening the session on the first call and resuming it after.

        Raises subprocess.CalledProcessError if the agent CLI exits nonzero.
        """
        ...

    @abstractmethod
    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the command for one turn, and the text to write to its stdin.

        stdin is None when the prompt is already inside the command. The command opens a new
        session while `session_id` is None, and resumes that session once it is set.
        """
        ...

    @abstractmethod
    def _read_session_id(self, transcript: str) -> str:
        """Reads the backend's session id out of everything the opening turn printed."""
        ...


class AgentBase(ABC):
    model: str
    effort: str

    def __init__(self, *, model: str, effort: str):
        """Initializes the agent with the given model and effort level."""
        ...

    @abstractmethod
    def start(self) -> SessionBase:
        """Creates a new session, which stays unopened until its first turn."""
        ...

    def run(self, prompt: str) -> str:
        """Runs one turn in a throwaway session, so nothing carries over to the next call."""
        ...
```

- All concrete agents MUST derive from `AgentBase`.
- All concrete agents MUST accept `model` and `effort` parameters in their constructors.
- All concrete agents MUST hold no conversation state; a session MUST own it.
- All concrete sessions MUST derive from `SessionBase`.
- Every agent MUST have exactly one session class, which `start` returns.
- A session's turns after the first MUST resume the session the first turn opened.
- `session_id` MUST identify that session for as long as the session lives, so
  `_read_session_id` MUST be called only for the turn that opened it.
- A session MUST NOT resume a session that a failed turn may not have opened.
- `_read_session_id` MUST raise if the backend gave it no id to return.
