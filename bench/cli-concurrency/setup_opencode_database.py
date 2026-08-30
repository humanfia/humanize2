"""Prepare an optional per-workspace OpenCode database launcher for benchmarks."""

# ruff: noqa: INP001 -- standalone optional benchmark setup

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

LAUNCHER = """import hashlib
import os
import sys

NATIVE = {native!r}
DATABASE_ROOT = {databases!r}


def database_for(arguments, cwd):
    workspace = cwd
    arguments = iter(arguments)
    for argument in arguments:
        if argument == "--":
            break
        if argument == "--dir":
            workspace = next(arguments, None)
            if not workspace:
                raise ValueError("--dir requires a task workspace")
        elif argument.startswith("--dir="):
            workspace = argument.partition("=")[2]
            if not workspace:
                raise ValueError("--dir requires a task workspace")
    if not os.path.isabs(workspace):
        workspace = os.path.join(cwd, workspace)
    identity = hashlib.sha256(os.fsencode(os.path.realpath(workspace))).hexdigest()
    return os.path.join(DATABASE_ROOT, identity + ".sqlite3")


def main():
    environment = dict(os.environ)
    environment["OPENCODE_DB"] = database_for(sys.argv[1:], os.getcwd())
    os.execve(NATIVE, [NATIVE, *sys.argv[1:]], environment)


if __name__ == "__main__":
    main()
"""


def setup(directory: Path, official: Path) -> dict[str, object]:
    """Write a fresh launcher without invoking OpenCode or changing its configuration."""
    directory = directory.expanduser().resolve()
    official = official.expanduser().resolve(strict=True)
    if not directory.is_relative_to(Path("/tmp")) or directory.exists():  # noqa: S108
        raise ValueError("Choose a new directory under /tmp")
    if not official.is_file() or not os.access(official, os.X_OK):
        raise ValueError("Supply the existing official OpenCode executable")
    directory.mkdir(mode=0o700)
    binary = directory / "bin"
    databases = directory / "databases"
    binary.mkdir(mode=0o700)
    databases.mkdir(mode=0o700)
    launcher = binary / "opencode"
    launcher.write_text(
        f"#!{sys.executable}\n"
        + LAUNCHER.format(native=str(official), databases=str(databases)),
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    result = {
        "configuration": "optional-opencode-per-workspace-database",
        "environment": {
            "PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""),
        },
        "database_directory": str(databases),
        "database_policy": "Absolute SQLite file per canonical --dir or cwd, retained across turns",
        "launcher": str(launcher),
        "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
        "official_executable": str(official),
        "official_sha256": hashlib.sha256(official.read_bytes()).hexdigest(),
        "interpreter": sys.executable,
        "interpreter_sha256": hashlib.sha256(
            Path(sys.executable).read_bytes()
        ).hexdigest(),
        "native_setting": "OPENCODE_DB",
        "default_shared_database_behavior_changed": False,
        "validation": "Unvalidated until read/edit/check/context workloads pass",
    }
    (directory / "setup.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    """Print the optional launcher environment; no CLI or model is called."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--official", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(setup(args.directory, args.official), indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
