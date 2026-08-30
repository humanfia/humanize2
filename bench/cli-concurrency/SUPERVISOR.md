# What a turn under an account pays before it is a turn

A turn under a provider is not spawned as the CLI. It is spawned as `hmz cred --map=... --`
and the CLI underneath it: a seccomp filter over every syscall that can name a path, and a
supervisor that answers the two to four naming a credential. Everything else the CLI names —
its own startup, the project it reads, the shells it runs and the interpreters those start —
stops too, and is let through.

This measures what those stops cost, what is left of them, and what changing that did to the
one requirement: at least half the speed of no concurrency at all.

All of it uses the [deterministic loopback fixture](DETERMINISTIC.md) with dummy credentials.
Canned responses are not model throughput. The machine-readable result is
[`results-credential-supervisor.json`](results-credential-supervisor.json).

## How many stops there are

Counted with a temporary counter in the supervisor, over one cold and one warm turn of the
benchmark workload:

| Backend | Path syscalls stopped | Naming an absolute path |
| --- | ---: | ---: |
| qwen | 77,790 per session | 99.35% |
| grok | 19,935 and 20,722 (one per turn) | 99.90% |
| claude | 10,445 per session | 96.76% |
| codex | 9,118 per session | — |
| opencode | 1,412 and 1,412 (one per turn) | — |

Two to four of those name a credential. The rest are the program's own, and nearly all of
them are already absolute and already tidy — which is to say, already the path the kernel
will resolve.

## What the stops cost

The same conversations with the redirect table emptied. That is a diagnostic and not a
configuration anybody may use: it removes the supervisor and nothing else. Serial, five
repeats, median. Codex is left out because its per-agent app server means removing the swaps
does not isolate the supervisor.

| Backend | Cold turn, no supervisor | Original | This change | Supervisor's share |
| --- | ---: | ---: | ---: | --- |
| qwen | 2.73 s | 7.67 s | 5.96 s | 4.94 s → 3.23 s |
| claude | 0.60 s | 1.57 s | 1.33 s | 0.97 s → 0.73 s |
| opencode | 2.10 s | 2.28 s | 2.33 s | 0.18 s → 0.23 s |

OpenCode's difference is inside its own run-to-run spread; it makes 1,412 stops a turn, and
there is nothing there to win.

## Where one stop goes

One tracee making 20,000 `stat` calls on absolute paths that are none of the provider's,
watched by the real supervisor and by one cut down to the stop alone. Minimum of fifteen:

| | Total per stop | Of which the handler |
| --- | ---: | ---: |
| Original | 44.65 µs | 27.00 µs |
| This change | 25.68 µs | 4.06 µs |

The rest is the stop itself — a `waitpid`, a `PTRACE_CONT` and the two context switches
between them — which is the kernel's and is not touched. The handler is what was left, and
it was three things: a register set allocated per stop, a page-sized buffer allocated per
path read, and every path decoded and normalised before being held against the table. Now
the register set and the buffer belong to the supervisor and are read over, and a path that
is absolute, holds no `.`, `..` or doubled separator, and does not begin with anything the
table could answer is dropped without being decoded at all. What is answered is unchanged,
and a path spelled the long way round still resolves — there is a test that spells one.

## The comparison

One cell at a time. For each backend and each concurrency, the original source snapshot and
the candidate alternate with the order flipped every other pair — three repeats a side, six
pairs. The ratio is formed inside a pair and the median taken.

A full ladder round was tried first and thrown away: it put the two sides of a ratio five
minutes apart, and on this host that is long enough for drift to land on one of them. Its
claude cells read 1.00 and 1.13 where six tight pairs of the same cell read 0.948 and 0.969,
with the candidate faster in seven of seven clean pairs. A cell puts the two sides under a
minute apart.

Complete-task time, candidate over original at the same number of sessions — below one is
faster:

| Backend | Sessions | Cold p50 | Cold p95 | Warm p50 | Warm p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| claude | 1 | 0.932 | 0.846 | 0.883 | 0.892 |
| claude | 2 | 0.941 | 0.952 | 0.889 | 0.896 |
| claude | 4 | 0.882 | 0.948 | 1.175 | 1.182 |
| claude | 8 | 0.948 | 0.969 | 0.950 | 1.009 |
| codex | 1 | 0.991 | 0.966 | 0.991 | 0.984 |
| codex | 2 | 1.058 | 0.976 | 1.004 | 1.061 |
| codex | 4 | 1.006 | 1.044 | 0.742 | 0.889 |
| codex | 8 | 0.968 | 0.963 | 0.918 | 0.829 |
| qwen | 1 | 0.907 | 0.880 | 1.003 | 0.930 |
| qwen | 2 | 0.925 | 0.949 | 0.952 | 1.063 |
| qwen | 4 | 0.910 | 0.917 | 0.920 | 0.976 |
| qwen | 8 | 0.884 | 0.894 | 0.921 | 0.939 |
| opencode | 1 | 0.995 | 1.006 | 0.990 | 0.995 |
| opencode | 2 | 1.004 | 1.003 | 1.001 | 0.995 |
| opencode | 4 | 0.989 | 0.986 | 0.987 | 0.996 |
| opencode | 8 | 0.985 | 0.983 | 0.985 | 0.994 |

Qwen is the clear one: 0.88 to 1.00, and it is the backend that stops 77,790 times.
Claude is 0.85 to 0.97 in fifteen of sixteen cells. OpenCode is flat within 1.6% either way,
which is what 1,412 stops a turn predicts. Codex's cells are mostly below one and two are
just above; its numbers are about one app server per agent with calls serialized behind it,
not about the supervisor.

The exception is claude's warm turn at four sessions: 1.175 and 1.182, and reproducible —
five of six pairs, an absolute 40 ms on a 230 ms turn. Claude's warm turns at one, two and
eight sessions are 0.883, 0.889 and 0.950, so it is not the change scaling badly. It is
recorded as measured and unexplained.

## Against the requirement

The requirement is complete-task time at N sessions no worse than 2.0× the original serial
control of that backend — half the speed of no concurrency at all — cold and warm, p50 and
p95, with every validity check intact: all items passing, artifacts verified, the checker's
own proof, turn two recalling a marker given only in conversation, exactly one result, no
cleanup survivors.

| Backend | Sessions | Original: worst | This change: worst | Verdict |
| --- | ---: | ---: | ---: | --- |
| claude | 2 | 1.621 | 1.508 | both pass |
| claude | 4 | 1.139 | 1.078 | both pass |
| claude | 8 | 4.186 | 2.710 | both fail |
| codex | 2 | 2.738 | 3.122 | both fail |
| codex | 4 | 6.937 | 6.083 | both fail |
| codex | 8 | 15.363 | 13.486 | both fail |
| qwen | 2 | 1.331 | 1.437 | both pass |
| qwen | 4 | 2.371 | 2.314 | both fail |
| qwen | 8 | 5.669 | 5.029 | both fail |
| opencode | 2 | 1.058 | 1.065 | both pass |
| opencode | 4 | 1.426 | 1.417 | both pass |
| opencode | 8 | 3.162 | 3.097 | both fail |

**No verdict moves.** The change lowers absolute time nearly everywhere and lowers the
distance to the floor in most cells, but it does not carry any backend across it. Claude at
eight sessions is the largest single move — 4.186 to 2.710 — and is still well outside.
Where a backend fails, what it is failing on is its own: codex serializes behind one app
server, qwen's warm turns are 0.2 s serial and any queueing dominates them, and opencode
shares one SQLite database.

An earlier run of this comparison, taken while three units were unknowingly sharing one quad
of CPUs, reported claude at eight sessions crossing from 2.185 to 1.972 — from outside the
floor to inside it. That reading did not survive being re-measured on a dedicated quad and
is withdrawn.

## What was measured and left alone

The brief for this work named several places humanize might be recomputing per session.
Measured on this machine, with the fixture providers:

| | Per turn |
| --- | ---: |
| `AgentBase.spawned` — `PATH` lookup, provider args, swaps | 0.13–0.38 ms |
| `SessionBase._environ` — the environment a process is started with | 0.05 ms |
| `AgentBase.hushed` — the variables a provider's turn runs without | 0.024 ms |
| `SessionBase._mounts` for a flow that brings no skills | 0.000 ms |
| Constructing an agent | 0.010 ms |
| `agent.new()` | 0.004 ms |
| `AgentBase.node()` / `walks()` — already held per agent | ≤ 0.001 ms |
| `qwen._settings()`, including its fingerprint | 0.46 ms |
| `agy._settings()`, including its fingerprint | 1.19 ms |

Against turns of 0.2 to 8 seconds that is between 0.02% and 0.2%, and caching any of it
would not have been measurable. `hmz.agents.skills.skills()` is not on the session path at
all — it is read by the terminal interface, not by a turn — and `hmz.models` and
`hmz.tui.discover` are not imported by an agent or a session. None of it was changed.

The fingerprint was, in one respect: `hmz.agents._inputs.snapshot` read and hashed every file
under every watched root, whatever its size, once a turn per session. It now reads up to a
mebibyte of a file and takes anything larger on its stat identity. Over 200 files of 4 MiB
that is 661.64 ms → 1.69 ms. It does not help a tree of many small files: 2,000 files of
4 KiB cost about 46 ms either way, because that cost is the opens and not the bytes.

The supervisor's own interpreter start — `python -m hmz cred`, once per spawned CLI process —
measures about 70 ms against 14 ms for a bare interpreter. Making `hmz.coganchor`'s package
import lazy, which is where most of it looked like it was, saved 4 ms. That was reverted and
is not adopted.

Process lifetime, transports, the set of trapped syscalls and what the table answers are all
unchanged.

## Conditions

Four CPUs, 16 GiB, no swap, in a dedicated `systemd-run --user --scope`, with `taskset -c
4-7` — socket-0 physical cores, this unit's own quad. `AllowedCPUs` on a user scope is
silently ineffective on this host, which is why the affinity is set with `taskset` and
verified by the harness; every rung records `allowed_cpus: [4, 5, 6, 7]`.

This is a shared 64-CPU host and not a dedicated machine. Three performance units were
briefly measuring on one shared quad; every figure above was taken after that was corrected,
and the figures taken before it are not published here. OpenCode's `database is locked`
failures are its default shared SQLite database, the condition
[`DETERMINISTIC.md`](DETERMINISTIC.md) records; they hit both sides, and the cells carry
their failed item counts.
