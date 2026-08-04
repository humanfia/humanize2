"""The structural rules of the package tree, in one table.

Two things nothing else can check. The layers keep the dependencies the merged projects had:
`agents` names the machine its turns land on, so it reads `machines`, and a machine hands back
an anchor, so `machines` reads `coganchor`. A flow is written against the agents it is handed
and names nothing else; `runner` is what finds one by the name a command line gave it, and
writes the run down as `cycle`. `tracing` reads the logs back afterwards and needs only where
they are. Nothing points both ways, which is checked here too.

And the target half runs on the target, which may be any architecture, while
:mod:`hmz.coganchor.linux` picks a register map at import time and refuses anything but
x86-64 -- so the serving half must not reach the agent half, nor may anything a caller imports
to configure one.

The rules are on the layers alone. Above them sits the command line, which joins them and so
may name any of them -- and which is checked instead by what a run of it actually loads.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

from hmz.coganchor.transport import build_bundle

SRC = Path(__file__).resolve().parent.parent / "src"

#: What each layer may import besides its own subtree and :mod:`hmz` itself. Longest
#: matching layer wins, and a layer it may name covers the modules inside that layer.
ALLOWED: dict[str, set[str]] = {
    # Driving a backend is acting on the facts about it -- where it keeps the skills it
    # would load, so that an agent given some can be told about the rest -- and `backends`
    # is the leaf those are written down in. It names nothing itself, so this widens the DAG
    # without bending it, exactly as it does for a flow below.
    "hmz.agents": {
        "hmz.backends",
        "hmz.coganchor",
        "hmz.machines",
        # Which account a turn runs as is a setting of the agent, so driving one reads the
        # providers. They name nothing above themselves, so this widens the DAG without
        # bending it -- as `backends` does below.
        "hmz.providers",
    },
    "hmz.backends": set(),
    "hmz.coganchor": set(),
    "hmz.coganchor.serve": {"hmz.coganchor", "hmz.coganchor.proto"},
    "hmz.cycle": {"hmz.agents"},
    # A flow drives agents, and one that has to know where its own agent keeps its tasks
    # is reading a fact rather than a log: `backends` is the leaf that exists so a fact of
    # that kind is written once, and it names nothing, so this widens the DAG without
    # bending it.
    "hmz.flows": {"hmz.agents", "hmz.backends"},
    # What an agent is written down as, which is a shape and a file and nothing else: the
    # interface keeps them and a command line reads the same ones, so it sits under both.
    "hmz.kept": set(),
    "hmz.machines": {"hmz.coganchor"},
    # What a backend runs is asked of that backend as the account whose it would be, so the
    # asking reads the facts about the CLI and the providers it could be run as. Neither
    # names it back, so this widens the DAG without bending it.
    "hmz.models": {"hmz.backends", "hmz.providers"},
    "hmz.runner": {
        "hmz.agents",
        "hmz.backends",
        "hmz.cycle",
        "hmz.flows",
    },
    # A provider is credentials for one backend, kept apart from that backend's own, and it
    # is run under the same interception a session on another machine is: the facts about the
    # CLI, and the ptrace layer that answers a path. Neither of those names it back.
    "hmz.providers": {"hmz.backends", "hmz.coganchor"},
    "hmz.tracing": {"hmz.backends"},
    "hmz.tui": {
        "hmz.agents",
        "hmz.backends",
        "hmz.flows",
        # The agents written down under a name, which `/agents` walks and `hmz agents` says
        # from a command line. It names nothing, so this widens the DAG without bending it.
        "hmz.kept",
        # What each CLI runs, which the sheets offer and the key on them fills again.
        "hmz.models",
        # `/providers` is where an account is made and `/agents` is where one is given to an
        # agent, so the interface reads the same leaf the agents do. It names nothing above
        # itself, so this widens the DAG without bending it.
        "hmz.providers",
        "hmz.runner",
    },
}

#: What reaching the target half costs besides: the two modules of the command line that route
#: to it, and the settings module that coganchor's own `__init__` names on the way past. All
#: are held to the same bar as the package itself and import their machinery only when it is
#: used. Loaded rather than imported, so this widens what a run may load and not what the
#: serving half may name.
STARTUP = {
    "hmz",
    "hmz.cli",
    "hmz.cli.anchor",
    "hmz.coganchor.anchor",
}


def _module_name(source: Path) -> str:
    """The dotted name a file under ``src/`` is imported as."""
    parts = source.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(source: Path) -> set[str]:
    """Every module of this package a file names in an import.

    Relative spellings are resolved rather than skipped: ``from ..supervisor import Supervisor``
    inside ``serve/`` reaches the agent half just as surely as the absolute spelling, and is the
    form a refactoring tool would write. ``from hmz.coganchor import supervisor`` names that
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
    return {name for name in named if name.split(".")[0] == "hmz" and _is_module(name)}


def _is_module(dotted: str) -> bool:
    """Whether a dotted name is a file or package under ``src/``, rather than a name inside one."""
    path = SRC.joinpath(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _covers(layer: str, name: str) -> bool:
    """Whether naming `layer` is leave to name `name`, which is it or anything inside it."""
    return name == layer or name.startswith(f"{layer}.")


def test_the_package_is_marked_as_typed() -> None:
    """Without the marker, type checking humanize -- here or downstream -- checks nothing."""
    assert (SRC / "hmz" / "py.typed").is_file()


def test_every_layer_imports_only_what_it_may() -> None:
    offenders: dict[str, set[str]] = {}
    for source in sorted(SRC.rglob("*.py")):
        module = _module_name(source)
        layer = max(
            (name for name in ALLOWED if _covers(name, module)), key=len, default=""
        )
        if not layer:
            continue
        bad = {
            name
            for name in _imports(source)
            # `hmz` itself, which is where `home()` is, is every layer's to name. It is
            # answered here rather than written into the table: its name is the prefix of
            # every other, so an entry saying it would silently say all of them.
            if name != "hmz"
            and not any(_covers(allowed, name) for allowed in (layer, *ALLOWED[layer]))
        }
        if bad:
            offenders[module] = bad
    assert not offenders, f"these modules import outside their layer: {offenders}"


def test_no_two_layers_name_each_other() -> None:
    """A table meant to read as a DAG is one: a pair pointing both ways is a packaging error.

    It is what tells a layer that is genuinely below another from two that were put in one
    place and are now holding each other up.
    """
    both = {
        (one, other)
        for one, may in ALLOWED.items()
        for other in may
        if any(_covers(other, named) for named in ALLOWED.get(one, set()))
        and any(_covers(one, named) for named in ALLOWED.get(other, set()))
    }
    assert not both, f"these layers name each other: {both}"


def test_every_module_at_the_top_is_a_layer_the_table_governs() -> None:
    """One left out is unchecked, and reads from here exactly like one deliberately exempt."""
    named = {
        f"hmz.{path.stem}"
        for path in (SRC / "hmz").iterdir()
        if not path.name.startswith("_")
        and (path.suffix == ".py" or (path / "__init__.py").is_file())
    }
    # The command line joins the layers and so may name any of them.
    assert named - {"hmz.cli"} <= set(ALLOWED)


def test_serving_loads_only_the_permitted_modules(tmp_path: Path) -> None:
    """The static rule again, but against what a real target half actually loads."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    probe = (
        "import contextlib, io, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from hmz import cli\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        # A line it reads all the way through rather than `--help`, which now exits before the
        # serving half is reached at all: what is checked is what a run of it loads. The line
        # is refused for its port, which is a return rather than an exit.
        "    cli.main(['anchor', 'serve', '--export', '/project:/tmp',\n"
        "              '--listen', 'not-a-port'])\n"
        "print('\\n'.join(m for m in sys.modules if m.split('.')[0] == 'hmz'))\n"
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
    serve = "hmz.coganchor.serve"
    assert f"{serve}.server" in loaded, "the target half did not actually run"
    assert loaded <= ALLOWED[serve] | STARTUP | {
        name for name in loaded if name.startswith(serve)
    }
