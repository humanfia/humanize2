"""The structural rules of the package tree, in one table.

Two things nothing else can check. The layers keep the dependencies the merged projects had:
`agents` names the machine its turns land on, so it reads `machines`, and a machine hands back
an anchor, so `machines` reads `coganchor`. A flow is written against `flows` and names nothing
else, which is what makes `flows` the layer that names the agents rather than the flow doing
it; `runner` is what reads a command line into one and writes the run down as `cycle`.
`tracing` reads the logs back afterwards and needs only where they are. Nothing points both
ways, which is checked here too.

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
        # A turn that has walked its accounts to the end asks where the agent itself falls
        # back to, and builds the agent that is named. It names only `backends`, so this
        # widens the DAG without bending it.
        "hmz.fallbacks",
        "hmz.machines",
        # Which account a turn runs as is a setting of the agent, so driving one reads the
        # providers. They name nothing above themselves, so this widens the DAG without
        # bending it -- as `backends` does below.
        "hmz.providers",
        # A skill a flow brought that a session will not read because something of that name
        # is already there is noticed here and nowhere else. The reporter names nothing above
        # itself, so this widens the DAG without bending it.
        "hmz.telemetry",
    },
    "hmz.backends": set(),
    "hmz.coganchor": set(),
    # Where a turn goes when the agent taking it cannot take it at all, which is written
    # between two agents. An agent is named the way a command line names one, so this reads
    # `backends` to read one -- the leaf those facts are written down in, which names nothing
    # itself and so widens the DAG without bending it. It names no agent and no account: what
    # is written down is two lines of text, and whoever walks the chain builds what it names.
    "hmz.fallbacks": {"hmz.backends"},
    "hmz.coganchor.serve": {"hmz.coganchor", "hmz.coganchor.proto"},
    # A run writes down which sessions its agents opened, and points a link at each of the
    # logs the backend is writing them to. Where those logs are is a fact about the CLI, and
    # `backends` is the leaf those are written down in: it names nothing, so this widens the
    # DAG without bending it. And a run that is being profiled samples the programs its
    # agents start, which is `tracing`: what a run left behind, read back.
    "hmz.cycle": {"hmz.agents", "hmz.backends", "hmz.tracing"},
    # What a flow is written against, which is why it is also the one import a flow needs:
    # the agents it drives, and the facts a loop steers by. A flow that has to know where
    # its own agent keeps its tasks, or what models that account runs, is reading a fact
    # rather than a log -- `backends` is the leaf those are written down in and `models` is
    # what asks a CLI, and neither names anything above itself, so both widen the DAG
    # without bending it. The run one flow makes when it calls another is written into the
    # cycle of the run that called it, and a failure in any of them is reported by the one
    # reporter every layer may reach for.
    "hmz.flows": {
        "hmz.agents",
        "hmz.backends",
        "hmz.cycle",
        # Where a flow says one of its agents works, which is a container of the flow's own
        # naming. It names only the anchor under it, so this widens the DAG without bending
        # it.
        "hmz.machines",
        "hmz.models",
        "hmz.telemetry",
    },
    # What an agent is written down as, which is a shape and a file and nothing else: the
    # interface keeps them and a command line reads the same ones, so it sits under both.
    "hmz.kept": set(),
    # What humanize remembers: what each workspace was set up to run, and the handful of
    # settings that are not a workspace's. A leaf for the reason `kept` is one -- the
    # interface writes them and a command line has to be able to read them without loading
    # the interface to do it -- and it names `kept` because an agent is written down the
    # same way wherever it is written down.
    "hmz.settings": {"hmz.kept"},
    # What humanize reports about itself, which every layer may do and none of them may be
    # reached into to do: what goes with a report is handed over as a callable by whoever
    # knows it. So this names only the setting that says whether to report at all.
    "hmz.telemetry": {"hmz.settings"},
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
        # Whether a run here is profiled as well as traced, which is a workspace's own
        # setting. A leaf, like the agents kept under a name beside it.
        "hmz.settings",
        # What a run is, said where a report of a failure in one can reach it. The reporter
        # names nothing above itself, so this widens the DAG without bending it.
        "hmz.telemetry",
    },
    # A provider is credentials for one backend, kept apart from that backend's own, and it
    # is run under the same interception a session on another machine is: the facts about the
    # CLI, and the ptrace layer that answers a path. Neither of those names it back.
    "hmz.providers": {"hmz.backends", "hmz.coganchor"},
    "hmz.tracing": {"hmz.backends"},
    # humanize as one object, which is what the command line, the daemon and the interface
    # all hold. It is above the layers and below the four ways in, so it may name any of
    # them and none of them may name it -- which is what keeps `hmz exec` from paying for a
    # tracer: everything here is reached from inside the call that needs it.
    "hmz.sdk": {
        "hmz.agents",
        "hmz.backends",
        "hmz.cycle",
        "hmz.fallbacks",
        "hmz.flows",
        "hmz.kept",
        "hmz.models",
        "hmz.providers",
        "hmz.runner",
        "hmz.settings",
        "hmz.telemetry",
        "hmz.tracing",
    },
    # The run held where a terminal closing cannot end it, which knows nothing of what a run
    # is: it is handed something that opens one and returns when it is over. A leaf, so that
    # the half of humanize which is a process and a socket can be read without any of the
    # half that drives coding agents.
    "hmz.daemon": set(),
    # What this process is called to every other process. A leaf: it names nothing, and
    # only `hmz exec` names it -- the one line that carries a task, which is what the
    # rename keeps off the command line.
    "hmz.proctitle": set(),
    "hmz.tui": {
        "hmz.agents",
        "hmz.backends",
        # The runs of this directory, which `/cycles` lists and picks one up from. It names
        # the agents and the facts about them, both of which are under the interface too.
        "hmz.cycle",
        # `/fallback` is where it is said what a turn does when the agent taking it cannot,
        # which is the other half of what `/providers` says about an account. It names only
        # `backends`, so this widens the DAG without bending it.
        "hmz.fallbacks",
        "hmz.flows",
        # The agents written down under a name, which `/agents` walks and `hmz agents` says
        # from a command line. It names nothing, so this widens the DAG without bending it.
        "hmz.kept",
        # `/providers` is where an account is made and `/agents` is where one is given to an
        # agent, so the interface reads the same leaf the agents do. It names nothing above
        # itself, so this widens the DAG without bending it.
        "hmz.providers",
        # humanize as one object, which is what starts a flow, gathers a trace of one that
        # has ended, and walks every store the sheets show. Everything the interface does
        # rather than draws is asked of it -- which is why the runner, what humanize
        # remembers and what each CLI runs are not named here: the sheets reach all three
        # through this and nothing here may reach past it to them.
        "hmz.sdk",
        # The interface is where humanize's own failures are answered for -- it is the one
        # thing here with somebody to ask -- and where what it does that nobody meant is
        # noticed. The reporter names nothing above itself.
        "hmz.telemetry",
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
