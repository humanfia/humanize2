from __future__ import annotations

from hmz.coganchor.statepaths import profile_for


def test_the_bundled_dsh_runtime_keeps_dsh_state_local() -> None:
    profile = profile_for(
        "/opt/deepseek_harness_runtime/runtime/dsh-jsonrpc-agent-pkg-linux-x64"
    )

    assert profile.name == "dsh"
    assert profile.state_paths == ("~/.dsh",)
