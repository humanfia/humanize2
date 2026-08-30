"""Route an unchanged official ZCode CJS through one isolated dummy-provider supervisor."""

# ruff: noqa: INP001 -- standalone optional official-package setup

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from setup_fixture import FAKE_KEY, PROVIDER


def setup(directory: Path, endpoint: str, official: Path) -> dict[str, object]:
    """Create a temporary native config and launcher without executing the official CLI."""
    directory = directory.resolve()
    official = official.resolve(strict=True)
    endpoint = endpoint.rstrip("/")
    url = urlsplit(endpoint)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("The deterministic provider must be loopback HTTP")
    if not directory.is_relative_to(Path("/tmp")) or directory.exists():  # noqa: S108
        raise ValueError("Choose a new directory under /tmp")
    node = shutil.which("node")
    if node is None:
        raise ValueError("Official ZCode CJS needs node")
    directory.mkdir(mode=0o700)
    native = directory / "native"
    native.mkdir(mode=0o700)
    binary = directory / "bin"
    binary.mkdir(mode=0o700)
    home = directory / "humanize"
    os.environ["HUMANIZE_HOME"] = str(home)
    from hmz import providers

    providers.add(
        "zcode",
        PROVIDER,
        "gateway",
        {
            "ZCODE_BASE_URL": endpoint,
            "ZCODE_API_KEY": FAKE_KEY,
            "OPENAI_API_KEY": FAKE_KEY,
        },
    )
    config = native / "config.json"
    model = "fixture/fixture-model"
    config.write_text(
        json.dumps(
            {
                "model": {"main": model, "lite": model},
                "provider": {
                    "fixture": {
                        "kind": "openai-compatible",
                        "options": {"baseURL": endpoint + "/v1", "apiKey": FAKE_KEY},
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    launcher = binary / "zcode"
    native_path = str(Path.home() / ".zcode/cli/config.json")
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "from hmz import backends\n"
        "from hmz.providers import find\n"
        "from hmz.providers.redirect import command\n"
        f"os.environ['HUMANIZE_HOME'] = {str(home)!r}\n"
        f"provider = find('zcode', {PROVIDER!r})\n"
        "assert provider is not None\n"
        "profile = backends.named('zcode')\n"
        "assert profile is not None\n"
        "env = {key: value for key, value in os.environ.items() "
        "if key not in profile.hushes()} | dict(provider.env)\n"
        f"swaps = (*provider.swaps(), ({native_path!r}, {str(config)!r}))\n"
        f"argv = command(swaps, [{node!r}, {str(official)!r}, *sys.argv[1:]])\n"
        "os.execve(argv[0], argv, env)\n",
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    models = directory / "models.json"
    models.write_text(
        json.dumps({"zcode": {"model": model, "effort": "low", "provider": ""}}),
        encoding="utf-8",
    )
    result = {
        "environment": {
            "HUMANIZE_HOME": str(home),
            "PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""),
        },
        "models": str(models),
        "launcher": str(launcher),
        "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
        "native_config": str(config),
        "native_config_mapping": native_path,
        "official_executable": str(official),
        "official_sha256": hashlib.sha256(official.read_bytes()).hexdigest(),
        "synthetic_model": True,
        "provider_selection": (
            "Empty native provider; launcher applies dummy account and config in one supervisor"
        ),
        "validation": "Unvalidated until actual read/edit/check/context workload passes",
    }
    (directory / "setup.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    """Write and print the reproducible launcher configuration; never call the model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--official", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(setup(args.directory, args.endpoint, args.official), indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
