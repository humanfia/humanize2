# coganchor SPEC

What you are entitled to when you run an agent under coganchor, and what you
are deliberately not.

## The model

An agent runs on this machine, unchanged. Everything it *does* — reading and
writing project files, running commands, reaching the network from those
commands — happens on the target.

The workspace the agent works in is a local mirror of the target's copy. It
reads and writes the mirror at local speed; coganchor keeps the two in step.
The agent is told none of this and cooperates in none of it.

## What the agent observes

Inside the workspace it sees the target: the same file names, contents, sizes,
modes and timestamps, at the same paths. A failure answers with the target's
own error, not a local approximation of it.

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

- the agent's own executable and its re-execs
- its state directory — claude, codex and kimi are known by name; any other
  agent keeping state inside the workspace must be named explicitly
- anything else named as a local path or a local program
- the agent's own network connections, unless asked otherwise, so that it can
  still reach its model provider

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

Running an agent needs Linux on x86-64 and a recent Python; any other
architecture is refused at start-up. Serving needs only a POSIX system with a
Python of the same vintage — no root, no compiler, no kernel module, nothing
installed. The same program serves both ends, and the two refuse to run against
each other if their versions disagree.

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
