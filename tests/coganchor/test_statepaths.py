from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.coganchor.statepaths import profile_for, resolve

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def executable(path: Path, content: bytes = b"\x7fELF") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o755)
    return path


def test_the_bundled_dsh_runtime_keeps_dsh_state_local() -> None:
    profile = profile_for(
        "/opt/deepseek_harness_runtime/runtime/dsh-jsonrpc-agent-pkg-linux-x64"
    )

    assert profile.name == "dsh"
    assert profile.state_paths == ("~/.dsh",)


def test_codex_standalone_keeps_its_code_mode_host_local(tmp_path: Path) -> None:
    codex = executable(tmp_path / "release" / "bin" / "codex")
    host = executable(codex.with_name("codex-code-mode-host"))
    work_helper = executable(tmp_path / "release" / "codex-path" / "rg")

    resolved = resolve([str(codex)])

    assert str(codex) in resolved.local_programs
    assert str(host) in resolved.local_programs
    assert str(work_helper) not in resolved.local_programs


def test_codex_node_package_keeps_its_whole_runtime_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = executable(tmp_path / "node-bin" / "node")
    monkeypatch.setenv("PATH", str(node.parent))

    package = tmp_path / "node_modules" / "@openai" / "codex"
    script = executable(package / "bin" / "codex.js", b"#!/usr/bin/env node\n")
    launcher = tmp_path / "bin" / "codex"
    launcher.parent.mkdir()
    launcher.symlink_to(script)
    vendor = (
        package
        / "node_modules"
        / "@openai"
        / "codex-linux-x64"
        / "vendor"
        / "x86_64-unknown-linux-musl"
    )
    native = executable(vendor / "bin" / "codex")
    host = executable(native.with_name("codex-code-mode-host"))
    work_helper = executable(vendor / "codex-path" / "rg")

    resolved = resolve([str(launcher)])

    assert resolved.program == str(script)
    assert str(node) in resolved.local_programs
    assert str(native) in resolved.local_programs
    assert str(host) in resolved.local_programs
    assert str(work_helper) not in resolved.local_programs
    assert str(launcher) in resolved.local_programs
