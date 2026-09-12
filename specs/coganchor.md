# coganchor SPEC

What you are entitled to when you run an agent under coganchor, and what you
are deliberately not.

## The model

There are two arrangements, and which one a session uses is a setting of the
session rather than a fact about the target. They are opposites, and everything
below that is not marked otherwise is about the first.

**Supervised.** An agent runs on this machine, unchanged. Everything it *does* —
reading and writing project files, running commands, reaching the network from
those commands — happens on the target.

The workspace the agent works in is a local mirror of the target's copy. It
reads and writes the mirror at local speed; coganchor keeps the two in step.
The agent is told none of this and cooperates in none of it.

**Native CLI.** The CLI already installed on the target is the one that runs,
and it runs there. Nothing is mirrored, nothing is traced, and nothing of
coganchor is below the agent: this machine starts the CLI on the target in the
target's own copy of the workspace, carries its three streams byte for byte,
sends it the signals aimed here, and exits with its own status. Which is what
makes running a turn elsewhere an argument change for a backend that already
speaks a framed protocol to a process humanize spawns — the frames cross a
machine boundary and neither end is told.

Nothing below Requirements applies to it. It asks nothing of this machine's
kernel: no ptrace, no seccomp, no register map, no architecture it has to be
one of. A machine that could not supervise a turn can still take one this way,
and it MUST be able to — so nothing that needs any of those may be reached on
the road to starting one.

It MUST be asked for. A session says which arrangement it is, and says so under
`anchor:` and the name of the way: `anchor:supervised` for the first,
`anchor:native-cli` for the second. A flow needing one asks for it by that name
rather than inferring it from a target.

A native session MUST refuse to start a CLI the target has not got, before it
has put anything on that machine, saying what is missing and the line that
installs it there.

Three things do not follow the CLI across on their own, and each MUST be
carried deliberately:

- **The account.** What a provider sets reaches the turn, because the turn is
  the thing being run as that account. What a provider *hushes* is taken off on
  the target, where the environment is composed — a variable merely left out of
  what is sent survives in the target's own shell profile, and a turn billed to
  that key would have nothing about it looking wrong.
- **Its credential files.** Projected, as below.
- **The skills the flow carries.** Put into the target's copy of the workspace
  for the length of the turn and taken out again. Nothing already there is
  written over, and only what was made is removed.

And one thing MUST NOT: the flow's own callbacks. The bridge that carries them
is a program on this machine speaking to a socket in this process, and the CLI
that would start it is on the target. A turn offering them is refused rather
than taken without them.

## What the agent observes

It starts in the workspace, or in whichever directory inside it the session was
opened at — named as the target names it, and reached through this machine's
mirror of it.

Inside the workspace it sees the target: the same file names, contents, sizes,
modes and timestamps, at the same paths. A failure answers with the target's
own error, not a local approximation of it.

Where the target spells a path more than one way, every spelling of it reaches
the same file. A Mac reaches `/tmp`, `/var` and `/etc` through `/private`, and
ignores case unless it was formatted not to, so the paths a command there hands
back are not always the paths the workspace was named with. A path outside the
workspace is untouched by this: it belongs to this machine, and is answered as
this machine answers it.

Except where a path is answered with another: a credential the agent names is
the one it is given instead, and a syscall that cannot be given it fails rather
than reading the one it named.

Every program it spawns behaves like an ordinary local child — the same
descriptors, the same output, the same exit status — and its parent is released
as soon as it starts, so commands run concurrently and a long-lived one can be
talked to while it runs. Signals travel both ways: one aimed at a running
command reaches the real process on the target, and a command killed there
kills its local counterpart the same way.

A command never reports a success it did not achieve: one that cannot be
started, or that coganchor loses track of, fails visibly. What a command
changes on the target becomes visible to the agent once it exits, and when
coganchor exits nothing it started is left running.

## What reaches the target

- **File contents.** A file the agent modifies is pushed in full before any
  command runs on the target, and again when the session ends.
- **Structural changes.** Creating, removing, renaming, linking and changing
  permissions are replayed on the target first, so the target's error is what
  the agent sees.
- **Commands.** Everything the agent spawns, including helpers bundled with the
  agent itself, in the target's copy of the working directory.
- **Network.** Whatever those commands reach.

## What stays on this machine

Under a supervised session:

- the agent's own executable and its re-execs
- its state directory — claude, codex and kimi are known by name; any other
  agent keeping state inside the workspace must be named explicitly
- anything a path is answered with, and the paths that answer it: an agent run
  as an account of somebody else's reads its credentials from here, and what it
  writes when a token is refreshed lands here
- any variable named as the agent's own, so that a credential it was given to
  reach its model provider is not handed to every command it runs there
- anything else named as a local path or a local program
- the agent's own network connections, unless asked otherwise, so that it can
  still reach its model provider

Under a native session, none of it does, and that is the trade the arrangement
is: the CLI is on the target, so its executable, its state, its account and its
connections are the target's. In particular the account **leaves this machine**,
which a supervised session is built to prevent. What it is held to instead:

- What a provider sets is sent as the turn's environment and MUST NOT be written
  into a command line, where another user's `ps` would read it.
- What a provider keeps as files is projected: written into a directory on the
  target that only the target's own user may enter, each file unreadable by
  anyone else from the instant it exists, and named to the CLI by the variable
  that moves the directory it belongs in — never by a path in a command line.
- The projection lasts the turn and no longer. It MUST be removed when the
  turn is over, whatever became of the turn.
- A credential the CLI reads out of the user's own home MUST NOT be projected.
  Nothing but `HOME` points a CLI at one, and a replaced home is not a projected
  account: the target's git identity, its ssh keys and the CLI's own transcripts
  live under that name, and the next turn of a conversation would find nothing
  to resume. So it stays here and the account reaches the turn by whatever else
  carries it — unless nothing else does, which MUST be refused rather than
  skipped: the CLI would read the one copy left on the target, and the turn
  would run as whoever that machine is signed in as.

So the target is trusted with the account for as long as a turn lasts. A machine
that should not be is a machine to reach the other way, where the account never
goes near it.

Two more things follow from there being no supervisor, and both look like
defects if you meet them cold:

- **The agent's own connections are the target's.** Nothing here keeps them
  local, so a provider pointed at an endpoint on *this* machine — `127.0.0.1`,
  `localhost` — is a turn dialling the target's loopback and reaching that
  machine's service or none. A gateway a native turn is to use must be reachable
  under a name the target can resolve.
- **Everything crosses every turn.** The credentials and the skills are written
  again each time, because each turn is a process of its own and nothing outlives
  it to know they are already there.

## What is not guaranteed

Each of these is deliberate, and each looks like a defect if you meet it cold.

- **Serving is not a sandbox.** An export bounds which files a request may
  name. It does not confine the commands that request can run, and it does not
  stop a symlink pointing out of the tree from being followed. A listening port
  is equivalent to a shell on that machine.
- **Mirrored directories are the mirror's, not the target's.** A directory in
  the mirror carries this machine's permissions and the time the mirror was
  made.
- **Only file contents are pushed.** A permission change made through an
  already-open descriptor never reaches the target, and ownership, device nodes
  and extended attributes never leave the mirror.
- **A request that goes unanswered is abandoned here, not there.** It may still
  take effect on the target after the agent has been told it failed.
- **Losing the connection does not stop the agent.** Work needing the target
  fails, already-mirrored files still read, and the agent exits with its own
  status.
- **Only the common signals are reproduced faithfully.** A repeat of a signal
  already delivered, and the rarer signals, do not reach the command.
- **The mirror is authoritative.** Anything in it the target does not have is
  deleted. coganchor refuses a mirror directory holding unrelated files, or one
  last used against a different target, unless told to proceed.

## Requirements

Running an agent needs Linux on x86-64 or aarch64 and a recent Python; any
other architecture is refused at start-up, and told where it can run instead.
Serving needs only a POSIX system with a Python of the same vintage — no root,
no compiler, no kernel module, nothing installed. A macOS target serves as
readily as a Linux one, on either architecture: macOS ships no `python3` on the
`PATH` a remote command is given, so the interpreter is looked for where a Mac
keeps one — Homebrew's, or the framework the installer from python.org writes —
and a target holding none is told what was looked for. The same program serves
both ends, and the two refuse to run against each other if their versions
disagree.

## Limits

- **Whole files.** A file crosses in full, in both directions.
- **One writer.** The target's workspace must not be edited by anyone else at
  the same time.
- **No privilege escalation.** `sudo` does not work below the agent on this
  machine. Commands run on the target, where it is unaffected.
- **No crossing.** Renaming or linking between the workspace and a path kept on
  this machine fails.
- **64-bit only.** A 32-bit process below the agent is not intercepted and runs
  against the mirror with nothing replayed.
- **Names resolve here** and are dialled from the target, so split-horizon DNS
  can disagree.
