"""Older AgY workspace compatibility keeps session commands isolated and idempotent."""

# ruff: noqa: INP001, S101, SLF001 -- standalone benchmark compatibility checks

from pathlib import Path
from types import SimpleNamespace

from run import _agy_workspace


def test_native_workspace_args_remain_per_session_and_preserve_conversation(
    tmp_path: Path,
) -> None:
    """Parallel conversations must not inherit each other's workspace or native args."""
    original = ["agy", "--conversation", "existing-conversation", "--print", "task"]
    sessions = [
        SimpleNamespace(
            cwd=tmp_path / str(index), _turn=lambda _: (list(original), None)
        )
        for index in range(2)
    ]
    for session in sessions:
        _agy_workspace(session)
    for session in sessions:
        argv, stdin = session._turn("task")
        assert argv == [original[0], "--add-dir", str(session.cwd), *original[1:]]
        assert stdin is None
        _agy_workspace(session)
        assert session._turn("task")[0] == argv
    assert original == [
        "agy",
        "--conversation",
        "existing-conversation",
        "--print",
        "task",
    ]


def test_native_workspace_wrapper_preserves_persistent_print_suffix(
    tmp_path: Path,
) -> None:
    """The real streaming adapter removes the trailing --print pair to form its command."""
    from hmz.agents import AntigravityCLIAgent, AntigravityCLIAgentConfig

    session = AntigravityCLIAgent(
        AntigravityCLIAgentConfig(model="gemini-3.7-flash-low", effort="low")
    ).new(cwd=tmp_path)
    _agy_workspace(session)
    finite, _ = session._turn("task")
    assert finite[-2:] == ["--print", "task"]
    streaming = session._command()
    assert "--print" not in streaming
    assert streaming.count("--add-dir") == 1
    assert streaming[streaming.index("--add-dir") + 1] == str(tmp_path)
