# Specification

flowjanus is a minimal library that hides which coding-agent CLI actually runs behind a uniform
interface. No CLI, no runtime, no orchestration — just classes.

## Structure

```
flowjanus/
├── base.py     # AgentBase (abstract) + AgentError
├── claude.py   # ClaudeCodeAgent
├── codex.py    # CodexAgent
└── kimi.py     # KimiCodeCLIAgent
```

## AgentBase

```python
class AgentBase(ABC):
    def __init__(self, *, model=None, effort=None, timeout=None, cwd=None): ...

    @abstractmethod
    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        """(argv, stdin). stdin=None means the prompt is already inside argv."""

    def run(self, prompt: str) -> str:
        """Run one turn via subprocess; return stripped stdout; raise AgentError on nonzero exit."""
```

`run` is the only method a caller uses, so the concrete backend is fully hidden. A subclass only
implements `_command`.

## Backends

Each concrete agent maps `(model, effort, prompt)` to its CLI invocation:

| Agent | Command | Prompt via | Effort |
|---|---|---|---|
| `ClaudeCodeAgent` | `claude --print --dangerously-skip-permissions [--model M] [--effort E]` | stdin | `--effort E` |
| `CodexAgent` | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check [--model M] [-c model_reasoning_effort="E"] -c service_tier="default"` | stdin | `-c model_reasoning_effort` |
| `KimiCodeCLIAgent` | `kimi --prompt PROMPT [--model M]` | argument | (ignored) |

## Adding an agent

Subclass `AgentBase` and implement `_command`; no registration or configuration is involved. See the
`AcmeAgent` example in [README.md](README.md).
