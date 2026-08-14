---
pageClass: hmz-feature
---

# The anchor

An agent runs on this machine, unchanged. Everything it *does* — reading and writing project
files, running commands, reaching the network from those commands — happens on another machine.
The agent is told none of this and cooperates in none of it: there is no plugin, no
configuration, no flag, and nothing in its own settings that says where it is.

<HmzSyscalls />

## The one idea

A coding agent is a program, and a program's contact with the world is a few dozen system
calls. Take those, one at a time, and you have taken everything it does without touching
anything it is.

So the agent is forked and told to be traced, a filter is installed on it, and it is replaced
by the CLI. From then on every call it makes that names a path, spawns a process or opens a
socket stops on its way into the kernel, and a supervisor beside it decides what happens: this
one is replayed on the target, that one is answered here, and the argument of this third one is
rewritten before it goes through.

## Why it is not slow

A filter that trapped everything would be a filter you could feel. This one is a flat
classic-BPF program — one comparison per trapped call, and there are thirty-five of them —
installed once in the forked child between `PTRACE_TRACEME` and `execve`, and inherited by
every descendant process and every thread of them.

It answers `SECCOMP_RET_TRACE` for the cold, path-bearing calls the supervisor cares about, and
`SECCOMP_RET_ALLOW` for everything else. A `read` on a descriptor already decided, a `futex`, a
`clock_gettime` — the calls a turn makes hundreds of thousands of times — never pay a ptrace
stop at all. The counter above the diagram is the whole argument: the ratio between the two
columns is why this is a way of working rather than a demonstration.

An architecture the filter does not recognise is allowed through untouched. coganchor is a
redirector rather than a sandbox, so failing open keeps an unexpected personality working
instead of killing the agent — which is also why a 32-bit process below the agent is not
intercepted and runs against the mirror with nothing replayed.

## Three questions, answered separately

Every trapped call is one of three questions, and the router answers them independently.

| | |
| --- | --- |
| **Paths** | A directory on this machine — the mirror — stands for a path on the target. By default the two are spelled identically, so the agent genuinely believes it is working on the target. |
| **Programs** | Everything the agent spawns runs on the target, except the agent's own runtime: its launcher, interpreter, native binary, runtime helpers and re-execs stay here. |
| **Redirects** | A path the agent names may be answered with another one — the credentials of the [account](/features/accounts) a turn runs as, rather than whichever account this machine is signed into. What it is answered with is local, so it never reaches the target either. |

## The mirror, and why writes are whole files

Inside the workspace the agent sees the target: the same file names, contents, sizes, modes and
timestamps, at the same paths. It reads and writes a local mirror of them at local speed, and
coganchor keeps the two in step.

- **A file the agent modifies is pushed in full** before any command runs on the target, and
  again when the session ends. A file crosses whole, in both directions; there are no partial
  writes to reason about, and no moment where the target holds half an edit.
- **Structural changes go the other way first.** Creating, removing, renaming, linking and
  changing permissions are replayed on the target *before* the mirror is touched, so what the
  agent gets back is the target's own error rather than a local approximation of one.
- **The mirror is authoritative.** Anything in it the target does not have is deleted, and
  coganchor refuses a mirror directory holding unrelated files, or one last used against a
  different target, unless it is told to go ahead.

A command the agent spawns behaves like an ordinary local child: the same descriptors, the same
output, the same exit status. Its parent is released as soon as it starts, so commands run
concurrently and a long-lived one can be talked to while it runs. Signals travel both ways —
one aimed at a running command reaches the real process on the target, and a command killed
there kills its local counterpart the same way.

## What never leaves this machine

- the agent's own runtime executables and re-execs — for an npm-installed Codex, that includes
  Node, the native CLI and its code-mode host
- its state directory — the known CLIs are known by name, and any other agent keeping state
  inside the workspace has to be named
- anything a path is answered with, and the paths that answer it: an agent run as somebody
  else's account reads those credentials from here, and a refreshed token lands here
- any variable named as the agent's own, so that a credential it was given to reach its model
  provider is not handed to every command it runs on the target
- the agent's own network connections, unless asked otherwise, so it can still reach its model
  provider

That last pair is the arrangement in one line: **the work is over there and the account is over
here.**

## The turn is also where the session ends

An anchored session ends its process with each turn rather than holding one open across them.
That is not an implementation detail: coganchor pushes what the agent wrote when the session
ends, so a process held open past the turn would leave that turn's work on this machine while
the turn said it had landed. Such a session resumes rather than reopens on the turn after, and
between two turns there is nothing there to be [talked to](/features/steering).

## What it is deliberately not

Each of these is a decision, and each looks like a defect if you meet it cold.

- **Serving is not a sandbox.** An export bounds which files a request may name. It does not
  confine the commands that request can run, and it does not stop a symlink pointing out of the
  tree from being followed. **A listening port is equivalent to a shell on that machine.**
- **Mirrored directories are the mirror's.** A directory in the mirror carries this machine's
  permissions and the time the mirror was made.
- **Only file contents are pushed.** A permission change made through an already-open
  descriptor never reaches the target, and ownership, device nodes and extended attributes
  never leave the mirror.
- **A request that goes unanswered is abandoned here, not there.** It may still take effect on
  the target after the agent has been told it failed.
- **Losing the connection does not stop the agent.** Work needing the target fails,
  already-mirrored files still read, and the agent exits with its own status.
- **One writer.** The target's workspace must not be edited by anybody else at the same time.
- **No crossing.** Renaming or linking between the workspace and a path kept on this machine
  fails, and `sudo` does not work below the agent on this machine — commands run on the target,
  where it is unaffected.
- **Names resolve here** and are dialled from the target, so split-horizon DNS can disagree.

## What it needs installed

Running an agent under it needs Linux on x86-64 and a recent Python. **Serving needs only a
POSIX system and a Python of the same vintage** — no root, no compiler, no kernel module,
nothing installed. The same program is both ends, and the two refuse to run against each other
if their versions disagree.

## Where the detail is

- [Remote execution](/guide/remote-execution) — how to point an agent at one
- [Remote execution reference](/reference/remote-execution) — what you are entitled to, exactly
- [Security](/guide/security) — read this first
- [Two accounts of one CLI](/features/accounts) — the same technique, aimed at credentials
