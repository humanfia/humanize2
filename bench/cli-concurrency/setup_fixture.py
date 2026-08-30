"""Create isolated hmz providers that point supported official CLIs at a local fixture."""

# ruff: noqa: INP001 -- standalone benchmark setup, not installed runtime code

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

FAKE_KEY = "fixture-not-a-real-credential"
PROVIDER = "cli-fixture"


def _way(
    cli: str, way_name: str, environment: dict[str, str], args: tuple[str, ...] = ()
) -> None:
    from hmz import providers

    way = next(way for way in providers.ways(cli) if way.name == way_name)
    if way.argv:
        raise ValueError("Fixture setup never executes login commands")
    values = {**dict(way.sets), **environment}
    rendered = tuple(providers.filled(argument, values) for argument in way.args)
    providers.add(cli, PROVIDER, way.name, values, (*rendered, *args))


def _opencode(endpoint: str) -> str:
    return json.dumps(
        {
            "enabled_providers": ["fixture"],
            "provider": {
                "fixture": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Deterministic local fixture",
                    "options": {"baseURL": endpoint + "/v1", "apiKey": FAKE_KEY},
                    "models": {
                        "fixture-model": {
                            "name": "Fixture model",
                            "limit": {"context": 200000, "output": 32000},
                        }
                    },
                },
            },
        }
    )


def _agy_settings(native: Path) -> dict[str, Any]:
    """Use Antigravity's official hidden app-data flag, relative to its ~/.gemini root."""
    directory = native / "agy"
    directory.mkdir()
    settings = directory / "settings.json"
    settings.write_text(json.dumps({"modelProvider": "gemini"}), encoding="utf-8")
    found = shutil.which("agy")
    official = Path(found).resolve() if found else None
    return {
        "official_executable": str(official) if official else None,
        "official_executable_sha256": (
            hashlib.sha256(official.read_bytes()).hexdigest() if official else None
        ),
        "settings": str(settings),
        "arguments": [
            "--app_data_dir",
            os.path.relpath(directory, Path.home() / ".gemini"),
        ],
    }


def _cursor_local(official: Path) -> Path:
    """Validate the explicitly supplied local-runtime package without invoking it."""
    official = official.expanduser().resolve()
    try:
        package = json.loads(
            (official.parent / "package.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(
            "Cursor local launcher needs its official package.json"
        ) from exc
    if (
        not official.is_file()
        or not os.access(official, os.X_OK)
        or official.name != "cursor-agent-local"
        or not isinstance(package, dict)
        or package.get("name") != "@anysphere/agent-cli-local-runtime"
    ):
        raise ValueError(
            "Expected the official executable Cursor local-runtime package"
        )
    return official


def setup(
    directory: Path, endpoint: str, *, cursor_local_official: Path | None = None
) -> dict[str, Any]:
    """Write only new /tmp provider stores and native extension files, using fake keys."""
    directory = directory.resolve()
    if not directory.is_relative_to(Path("/tmp")):  # noqa: S108 -- boundary check only
        raise ValueError("Fixture setup must be placed below /tmp")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in ("127.0.0.1", "localhost")
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
    ):
        raise ValueError(
            "Fixture endpoint must be an unauthenticated loopback HTTP origin"
        )
    cursor = _cursor_local(cursor_local_official) if cursor_local_official else None
    endpoint = endpoint.rstrip("/")
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "setup.json").exists() or (directory / "humanize").exists():
        raise ValueError("Choose a fresh fixture setup directory")
    humanize = directory / "humanize"
    native = directory / "native"
    native.mkdir()
    extension = native / "pi-fixture.mjs"
    extension.write_text(
        "export default function(pi) {\n  pi.registerProvider('fixture', "
        + json.dumps(
            {
                "name": "Deterministic local fixture",
                "baseUrl": endpoint + "/v1",
                "apiKey": "$FIXTURE_API_KEY",
                "api": "openai-completions",
                "models": [
                    {
                        "id": "fixture-model",
                        "name": "Fixture model",
                        "reasoning": False,
                        "input": ["text"],
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                        },
                        "contextWindow": 200000,
                        "maxTokens": 32000,
                    }
                ],
            }
        )
        + ");\n}\n",
        encoding="utf-8",
    )
    entries = {
        "claude": (
            "gateway",
            {"ANTHROPIC_BASE_URL": endpoint, "ANTHROPIC_AUTH_TOKEN": FAKE_KEY},
            "claude-sonnet-4-5",
            "low",
        ),
        "codex": (
            "gateway",
            {"CODEX_PROVIDER_URL": endpoint + "/v1", "CODEX_PROVIDER_KEY": FAKE_KEY},
            "gpt-5-codex",
            "low",
        ),
        "dsh": (
            "key",
            {"DEEPSEEK_API_KEY": FAKE_KEY, "DEEPSEEK_BASE_URL": endpoint + "/v1"},
            "deepseek-chat",
            "off",
        ),
        "grok": (
            "gateway",
            {"GROK_XAI_API_BASE_URL": endpoint + "/v1", "XAI_API_KEY": FAKE_KEY},
            "fixture-model",
            "low",
        ),
        "kimi": (
            "model",
            {
                "KIMI_MODEL_NAME": "fixture-model",
                "KIMI_MODEL_API_KEY": FAKE_KEY,
                "KIMI_MODEL_BASE_URL": endpoint + "/v1",
                "KIMI_MODEL_PROVIDER_TYPE": "openai",
            },
            "__kimi_env_model__",
            "low",
        ),
        "qwen": (
            "key",
            {"OPENAI_API_KEY": FAKE_KEY, "OPENAI_BASE_URL": endpoint + "/v1"},
            "fixture-model",
            "none",
        ),
        "pi": ("env", {"FIXTURE_API_KEY": FAKE_KEY}, "fixture/fixture-model", "off"),
        "opencode": (
            "env",
            {"OPENCODE_CONFIG_CONTENT": _opencode(endpoint)},
            "fixture/fixture-model",
            "minimal",
        ),
        "mimo": (
            "env",
            {"MIMOCODE_CONFIG_CONTENT": _opencode(endpoint)},
            "fixture/fixture-model",
            "minimal",
        ),
    }
    agy = _agy_settings(native)
    entries["agy"] = (
        "key",
        {"GEMINI_API_KEY": FAKE_KEY, "GOOGLE_GEMINI_BASE_URL": endpoint},
        "gemini-3.7-flash-low",
        "low",
    )
    cursor_fixture: dict[str, Any] = {}
    if cursor is not None:
        local = native / "cursor"
        local.mkdir()
        (local / "cli-config.json").write_text("{}\n", encoding="utf-8")
        binary = directory / "bin"
        binary.mkdir()
        (binary / "cursor-agent").symlink_to(cursor)
        entries["cursor"] = (
            "env",
            {
                "CURSOR_ENABLE_AUTHLESS": "1",
                "CURSOR_LOCAL_AGENT_BASE_URL": endpoint + "/v1",
                "CURSOR_LOCAL_AGENT_API_KEY": FAKE_KEY,
                "CURSOR_CONFIG_DIR": str(local),
            },
            "fixture-model",
            "",
        )
        cursor_fixture = {
            "official_executable": str(cursor),
            "official_executable_sha256": hashlib.sha256(
                cursor.read_bytes()
            ).hexdigest(),
            "official_package_sha256": hashlib.sha256(
                (cursor.parent / "package.json").read_bytes()
            ).hexdigest(),
            "launcher": str(binary / "cursor-agent"),
            "settings": str(local / "cli-config.json"),
            "standard_cursor_service_auth_covered": False,
        }
    previous = os.environ.get("HUMANIZE_HOME")
    os.environ["HUMANIZE_HOME"] = str(humanize)
    try:
        for cli, (way, environment, _, _) in entries.items():
            extra = ("--extension", str(extension)) if cli == "pi" else ()
            if cli == "agy":
                extra = tuple(agy["arguments"])
            _way(cli, way, environment, extra)
    finally:
        if previous is None:
            os.environ.pop("HUMANIZE_HOME", None)
        else:
            os.environ["HUMANIZE_HOME"] = previous
    models = {
        cli: {
            "model": model,
            "effort": effort,
            "provider": PROVIDER,
        }
        for cli, (_, _, model, effort) in entries.items()
    }
    model_path = directory / "models.json"
    model_path.write_text(json.dumps(models, indent=2) + "\n", encoding="utf-8")
    unsupported = {
        "cursor": (
            "CURSOR_API_ENDPOINT addresses Cursor's service; this fixture implements "
            "model APIs, not Cursor's service RPC."
        ),
        "zcode": (
            "Use setup_zcode_fixture.py with an explicit unchanged official zcode.cjs; "
            "its temporary native-model config and single-supervisor launcher are separate."
        ),
    }
    environment = {"HUMANIZE_HOME": str(humanize)}
    if cursor is not None:
        unsupported.pop("cursor")
        environment["PATH"] = (
            str(directory / "bin") + os.pathsep + os.environ.get("PATH", os.defpath)
        )
    record = {
        "synthetic_model": True,
        "agy_fixture": agy,
        **({"cursor_fixture": cursor_fixture} if cursor is not None else {}),
        "endpoint": endpoint,
        "environment": environment,
        "models": str(model_path),
        "configured_unvalidated": list(entries),
        "unsupported_or_unverified": {
            cli: {
                "reason": reason,
                "executable": shutil.which("cursor-agent" if cli == "cursor" else cli),
            }
            for cli, reason in unsupported.items()
        },
        "launch_prefix": shlex.join(
            ["env", *(f"{key}={value}" for key, value in environment.items())]
        ),
        "harness_arguments": shlex.join(
            ["--config", str(model_path), "--backends", ",".join(entries)]
        ),
    }
    (directory / "setup.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main() -> None:
    """Print the isolated provider configuration and its nonsecret launch arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--directory", type=Path)
    parser.add_argument(
        "--cursor-local-official",
        type=Path,
        help="Optional official cursor-agent-local launcher beside its package.json",
    )
    args = parser.parse_args()
    directory = args.directory or Path(tempfile.mkdtemp(prefix="hmz-cli-fixture-"))
    print(  # noqa: T201 -- setup output
        json.dumps(
            setup(
                directory,
                args.endpoint,
                cursor_local_official=args.cursor_local_official,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
