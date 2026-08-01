# humanize

## File Structure

```
.
├── __init__.py
├── __main__.py
├── agents
├── backends.py
├── cli
├── coganchor
├── cycle.py
├── flows
├── machines
├── models.py
├── providers
├── runner.py
├── tracing
└── tui
```

Each subdirectory is a library and has a SPEC of its own; the modules beside them are
specified here. None of them MUST have a command line: `cli` is the whole of it, one module
per command that takes a parser of its own, and it MUST reach a layer only from inside the
command carried out in it, so that a command pays for no layer but its own -- and so that the
same package serves as the target half of a session, where it is the only one installed.

No two layers MUST name each other. A pair that does is two things put in one place, not one
thing above another, and is what `tests/test_layering.py` refuses.

Every module MUST be named for what it holds. `coganchor` alone is a name of its own, being a
program that ships to a target and could be lifted out whole.

## `__init__.py`

Expose `home`, and nothing else. A caller names the layer it wants.

## `backends.py`

Every fact about a coding agent CLI that is not code: what it is called, what a command line
may call it, how hard it can be asked to think, where it keeps its home, which files under it
a session is logged to, and which files under it and under a workspace are the skills it would
load.

- It MUST be the only place any of those is written down, and MUST import nothing but the
  standard library, so that reading a fact costs nothing of the layer the fact is about.
- Code that acts on a fact MUST live where its purpose does: driving a backend in `agents`,
  reading its logs back in `tracing`.
- A model id MUST NOT be written down here, nor anywhere else in this package. What a CLI
  runs is not a fact that keeps: it ships models without asking anybody, and which of them an
  account may name is that account's. `models.py` is what asks.
- The efforts MUST be written down, being that backend's own vocabulary rather than a
  catalogue of things that come and go. A rung the backend takes without documenting MUST be
  written down as one, since no listing of the backend's own will ever name it.

## `models.py`

```python
def where(cli: str, provider: str = "") -> Path: ...
def offered(cli: str, provider: str = "") -> tuple[Model, ...]: ...
def asked(cli: str, provider: str = "") -> str: ...
def ask(
    cli: str, provider: str = "", seconds: float = WAITING
) -> tuple[Model, ...]: ...
```

What each backend runs, asked of that backend and kept until it is asked again.

- What a backend runs MUST be got from that backend itself, by whatever mechanism that
  backend offers for being asked -- its own control request, its own catalogue command, its
  own dump of what it is configured with. It MUST NOT be a list written down here: a list is
  wrong the day the CLI ships a model, and says nothing about which of them this account may
  actually name.
- It MUST be asked as the account whose it would be: under that provider's own credential
  paths and variables, and without the ones its backend would take another account from --
  which is how a turn of that account is run. What is kept MUST be kept per account, two
  accounts of one CLI being two catalogues.
- What is kept for a provider MUST be kept with that provider, so that taking the account
  away takes its catalogue with it. The account nobody chose keeps its own under humanize's
  home.
- Asking MUST NOT happen at a prompt: it is a coding agent starting up. Reading what was kept
  MUST cost one file read.
- An account MUST be asked as soon as it is made, since that is the first moment there is
  anything to ask. A backend that would not answer MUST leave the account made: an account
  whose models are not known yet is one to ask again, not one that failed.
- A model's efforts MUST be its backend's ladder narrowed to the rungs that backend said that
  model takes, in the ladder's own order, and MUST be the whole ladder where it said nothing
  of that model -- a model it says nothing about is one it will take any of them for.
- A catalogue that has never been asked for MUST be empty rather than guessed at.

## `cycle.py`

What one run of one flow was, written down as it happens: which flow, on what, by which
agents, and which sessions each of them opened. Not what the sessions said -- the backend's
own log is the turn-by-turn record and this MUST NOT be a second copy of it.

- One cycle MUST be one run. It opens when the flow starts and closes when the flow stops,
  however it stops -- finished, failed, or interrupted. A closed cycle MUST NOT be reopened.

## `runner.py`

```python
class NotAFlow(ValueError): ...


def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]:
    """What the flow calls each agent it drives, in the order it takes them."""


def flow_and_agents(argv: list[str]) -> tuple[str, list[AgentBase], str]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, and the task."""


class Runner:
    def __init__(self, flow: str | os.PathLike[str], agents: Sequence[AgentBase]): ...

    def run(self, task: str) -> None:
        """Runs the flow, until it returns.

        Args:
            task: What the flow is to have its agents do.
        """
```

- A flow MUST be a Python file holding a function marked with `hmz.flows.flow` and taking
  `(agents: tuple[...], task: str)`. Nothing else MUST be one: which of a file's functions is a
  flow is the file's to say and not a name to guess at. That tuple MUST be of a fixed length,
  which is how many agents the flow drives: it is the one thing about a flow a command line
  running it cannot otherwise know. It MUST be readable where the flow runs rather than only
  where a type checker looks, since a count nothing can read back is not one a command line can
  be held to.
- One file MAY hold several flows: the one marked `@flow` is the flow the file holds under its
  own name, and each marked `@flow(name=...)` is addressed as `<flow>:<name>`. Which one was
  asked for MUST be read before the name is resolved to a file, and a name no flow in the file
  answers to MUST be reported as a usage error saying which ones it holds -- a file of three
  asked for by its own name is a colon away from what was meant.
- A `NamedTuple` of agents MUST be accepted in its place, and MUST additionally say what the
  flow calls each of them. `drives` MUST report those names, so that whatever asks for the
  agents asks for them by what they are for rather than by their place in a line; a plain
  tuple MUST report a name apiece that is empty, having said nothing but how many.
- `__init__` MUST load the flow and MUST raise `NotAFlow` unless the file is there and has
  such an entry point, declaring as many agents as it was given, so that a flow started with
  the wrong number of them fails before its first turn rather than partway through a loop.
- An agent that was not named where it was made MUST take the name the flow gives it, before
  anything is written down about the run: a name is what a trace groups an agent's sessions
  under, and `builder` says what a hex tail does not. One named already MUST keep that name.
- Whatever the flow itself raises as it is loaded MUST be left alone, so that a flow whose own
  setup fails is not answered with a command line to correct.
- `run` MUST call the entry point with the agents as the tuple the flow declared -- the named
  one where it named them -- in the order they were given, and the task.
- `flow_and_agents` MUST read the same `hmz exec` line the command takes, and MUST be here
  rather than in `cli`: the terminal interface starts a flow from that line and then keeps the
  agents, and a reader that lived in the command line would be one the interface reached up
  into.

## Commands

```shell
hmz [<command> [<args>...]]
```

- A line naming no command at all MUST open the terminal interface, which is every command at
  one prompt. There MUST be no command that opens it too: one way in is one way in. A line
  naming something that is not a command MUST be a usage error listing the commands there
  are. Everything after the command name MUST reach that command untouched, `--help`
  included, so that each answers for its own arguments.
- `__main__.py` MUST run this same command line, so that `python -m hmz` is `hmz`.

## `hmz exec`

```shell
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...] <task>
```

Runs a flow in the current directory, on the agents it is given.

Args:

- `-f`, `--flow <flow>[:<name>]`: The flow: one of the ones humanize ships or a flowverse holds,
  by name, or a file of your own, by path. Required. A file that holds several flows MUST be
  said which, after a colon; a flowverse's own MAY be said which, `<flowverse>/<flow>`.
- `-a`, `--agent <cli>[@<provider>]/<model>:<effort>`: One agent to drive the flow with. Repeated once for
  each agent the flow drives, in the order it takes them -- which for a flow that drives none,
  because the only side it talks to is the person at the prompt, is not at all: the person is
  handed over rather than chosen. A line short of an agent the flow does drive is caught as
  every other miscount is, against what the flow declares. It MUST also be
  accepted written out as `cli=<cli>,model=<model>,effort=<effort>`, in any order, since a
  model or an effort that holds the punctuation the short form separates on has nowhere else
  to go. One `-a` MUST be one agent: a list in a single `-a` MUST NOT be split into several.
- `<task>`: What the flow is to have the agents do, as the text itself.

- `<cli>` MUST be one of `claude`, `codex` and `kimi`, each of which MUST also answer to the
  longer name it is installed under, and `<model>` and `<effort>` MUST be what that CLI is
  asked for. A model MAY hold slashes of its own -- Kimi Code's and opencode's are written
  `provider/id` -- so the CLI MUST be read from the front and the effort from after the last
  colon.
- The CLI MAY be followed by `@<provider>`, which is the account that agent's turns run as: a
  CLI is never spelled with an `@` in it, so the two are told apart wherever an agent is
  written. `provider=` MUST say the same thing written out, and an `@` naming nothing MUST be
  a line to correct rather than a line saying nothing.
- Two agents of one spelling MUST be two agents, so that a flow of an actor and a reviewer at
  one configuration is what it says it is.
- A flow that is not there, has no entry point, does not say how many agents it drives, or
  drives a different number than were given MUST be reported as a usage error, before any
  agent has run. Whatever else a flow does as it is imported is the flow's own, and MUST fail
  as it would anywhere.

## `hmz collect`

```shell
hmz collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects and aggregates agent trajectories and generates Chrome JSON trace files for visualization.

Args:

- `<workspace>`: The path to the workspace directory to generate traces for. If not provided, the current working directory is used, unless sessions are named.
- `--session <session>[,<session>]...`: The sessions to generate traces for, comma separated and repeatable. A session is named by its whole id, by the key the trace shows it under, or by a leading part of either, and the sub-agents it started are collected with it. If not provided, every session of the workspace is included. Named sessions are collected wherever they were recorded, and are cut down to the workspace when one is provided.
- `--output <output>`: The path to the output file where the aggregated trace will be saved. Its directory is created if it does not exist. If not provided, the trace is saved as `.humanize/<datetime>.trace.json` in the current working directory, where `<datetime>` is the UTC moment it was collected, so that collecting twice keeps both traces.
- `--start <start>`: The start time for filtering the session logs, in any wording dateparser understands. If not provided, up to earliest logs are included.
- `--end <end>`: The end time for filtering the session logs, in any wording dateparser understands. If not provided, up to latest logs are included.

Prints the output path with the number of sessions and slices it holds.

Environment Variables:

- `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME`: The path to agent home directories for discovering session logs. If not set, use the default paths of each agent. A home directory that does not exist is skipped.

## `hmz providers`

```shell
hmz providers [list [<cli>] | ways <cli> | add <cli>/<name> [-w <way>] [-s VAR=VALUE]... [--no-login] | login <cli>/<name> [-s VAR=VALUE]... | show <cli>/<name> | remove <cli>/<name>]
```

The accounts an agent may be run as: what there is, how a backend can be signed into, and the
three things that can happen to one -- made, signed in again, taken away.

- It MUST be the same store the interface's own `/providers` walks: one place a thing is kept
  is one place it is kept, whichever way somebody reached it.
- Whatever a way asks that the line did not answer MUST be asked at the terminal, and a secret
  MUST NOT be echoed. A line run where nobody is at a terminal MUST answer everything itself:
  a question with no answer and no default MUST be reported rather than waited on.
- Nothing MUST print a secret. What one holds MUST be shown as the names of the variables it
  sets and never their values.
- An account that has just been made or signed in again MUST have its CLI asked what it runs
  as that account, and what it said MUST be reported. A CLI that would not answer MUST NOT
  make the line fail: the account was made, which is what the line was for. `--no-login` MUST
  ask nothing either -- a line that says not to run the backend does not run it.

## `hmz cred`

```shell
hmz cred --map <from>=<to> [--map ...] -- <command> [<args>...]
```

Runs a program with some of its paths answered by others, and exits with its status. What a
turn under a provider is spawned as, and what a login run for one is spawned as.

- It MUST be a command of its own rather than something the driver does in this process, for
  the reason `hmz anchor` is: the supervisor forks the program and takes the process's signal
  handling with it, which a flow pumping turns from threads of its own cannot lend it.
- A line naming nothing to answer MUST be a usage error: a run with nothing to redirect is a
  supervisor started for no reason.
