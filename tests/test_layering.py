"""The structural rules of the package tree, in one table.

Two things nothing else can check. The subpackages are merged projects that keep their own
dependencies: janus names the machine its agents act on, so it reads coganchor's settings and
talanton's, and talanton hands back an anchor, so it reads coganchor's too. Nothing else
crosses -- oronyx stays alone, and none of them may reach back up into janus. And the target
half runs on the target, which may be any architecture, while :mod:`humanize.coganchor.linux`
picks a register map at import time and refuses anything but x86-64 -- so the serving half must
not reach the agent half, nor may anything a caller imports to configure one. All were package
boundaries before the merge; now they are rules, so they are checked here.

The rules are on the subpackages alone. Above them sits the command line, which joins them
and so may name any of them -- and which is checked instead by what a run of it actually loads.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

from humanize.coganchor.transport import build_bundle

SRC = Path(__file__).resolve().parent.parent / "src"

#: What each layer may import besides its own subtree. Longest matching layer wins.
ALLOWED = {
    "humanize.janus": {"humanize", "humanize.coganchor", "humanize.talanton"},
    "humanize.talanton": {"humanize", "humanize.coganchor"},
    "humanize.oronyx": {"humanize"},
    "humanize.jetflow": {"humanize"},
    # The interface is a second way in to the commands rather than a second copy of them, so
    # it alone among the subpackages names the command line.
    "humanize.tui": {"humanize", "humanize.cli", "humanize.janus"},
    "humanize.coganchor": {"humanize"},
    "humanize.coganchor.serve": {
        "humanize",
        "humanize.coganchor",
        "humanize.coganchor.proto",
    },
}

#: What reaching the target half costs besides: the one command line, and the settings module
#: that coganchor's own `__init__` names on the way past. Both are held to the same bar as the
#: package itself and import their machinery only when it is used. Loaded rather than imported,
#: so this widens what a run may load and not what the serving half may name.
STARTUP = {"humanize.cli", "humanize.coganchor.anchor"}


def _module_name(source: Path) -> str:
    """The dotted name a file under ``src/`` is imported as."""
    parts = source.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(source: Path) -> set[str]:
    """Every module of this package a file names in an import.

    Relative spellings are resolved rather than skipped: ``from ..supervisor import Supervisor``
    inside ``serve/`` reaches the agent half just as surely as the absolute spelling, and is the
    form a refactoring tool would write. ``from humanize.coganchor import supervisor`` names that
    module too, so a from-import that resolves to a file on disk counts as naming it.
    """
    package = _module_name(source)
    if source.name != "__init__.py":
        package = package.rpartition(".")[0]

    named: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            named.add(module)
            named.update(f"{module}.{alias.name}" for alias in node.names)
    # A from-import names a module only when one exists on disk; the rest are the objects in it.
    return {
        name for name in named if name.split(".")[0] == "humanize" and _is_module(name)
    }


def _is_module(dotted: str) -> bool:
    """Whether a dotted name is a file or package under ``src/``, rather than a name inside one."""
    path = SRC.joinpath(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def test_the_package_is_marked_as_typed() -> None:
    """Without the marker, type checking humanize -- here or downstream -- silently checks nothing."""
    assert (SRC / "humanize" / "py.typed").is_file()


def test_every_layer_imports_only_what_it_may() -> None:
    offenders: dict[str, set[str]] = {}
    for source in sorted(SRC.rglob("*.py")):
        module = _module_name(source)
        layer = max(
            (name for name in ALLOWED if module.startswith(name)), key=len, default=""
        )
        if not layer:
            continue
        # A layer it may name covers the modules inside it: naming `humanize.janus` is
        # leave to reach janus, and janus is what is inside it.
        bad = {
            name
            for name in _imports(source)
            if not any(
                name == allowed or name.startswith(f"{allowed}.")
                for allowed in (layer, *ALLOWED[layer])
            )
        }
        if bad:
            offenders[module] = bad
    assert not offenders, f"these modules import outside their layer: {offenders}"


def test_every_subpackage_is_a_layer_the_table_governs() -> None:
    """One left out is unchecked, and reads from here exactly like one deliberately exempt."""
    subpackages = {
        f"humanize.{path.name}"
        for path in (SRC / "humanize").iterdir()
        if (path / "__init__.py").is_file()
    }
    assert subpackages <= set(ALLOWED)


def test_serving_loads_only_the_permitted_modules(tmp_path: Path) -> None:
    """The static rule again, but against what a real target half actually loads."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    probe = (
        "import contextlib, io, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from humanize import cli\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        # A line it reads all the way through rather than `--help`, which now exits before the
        # serving half is reached at all: what is checked is what a run of it loads. The line
        # is refused for its port, which is a return rather than an exit.
        "    cli.main(['anchor', 'serve', '--export', '/project:/tmp',\n"
        "              '--listen', 'not-a-port'])\n"
        "print('\\n'.join(m for m in sys.modules if m.split('.')[0] == 'humanize'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, str(bundle)],
        capture_output=True,
        text=True,
        # An empty PYTHONPATH proves it all came out of the bundle.
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        cwd="/",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = set(result.stdout.split())
    serve = "humanize.coganchor.serve"
    assert f"{serve}.server" in loaded, "the target half did not actually run"
    assert loaded <= ALLOWED[serve] | STARTUP | {
        name for name in loaded if name.startswith(serve)
    }
