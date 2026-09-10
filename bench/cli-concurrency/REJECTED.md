# Rejected CLI performance experiments

The experimental official `serve` plus `run --attach` transports were removed. Both
backends retain their original standalone `run` command per turn. Although retained
servers reduced later-turn startup, they reduced the concurrency that satisfied the
startup requirement. The Qwen, Antigravity and Kimi changes are evaluated separately.

## Controlled fixture results

These measurements used the installed official CLIs, the deterministic tool workload,
three repeats, four CPU cores, 16 GiB memory and zero swap. Startup is turn start to the
first provider request. Ratios compare each rung with the original serial baseline of
that backend, using the same settings. Both cold and warm p50/p95 must remain at most 2x.
With three serial controls, nearest-rank p95 is the largest observation; larger concurrent
pools use their own 95th-percentile rank and have different tail-estimate uncertainty.

| Backend | Sessions | Cold p50 ratio | Cold p95 ratio | Warm p50 ratio | Warm p95 ratio | Startup gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| OpenCode | 1 | 1.686 | 1.839 | 0.527 | 0.532 | Pass |
| OpenCode | 2 | 2.084 | 2.157 | 0.537 | 0.560 | Fail |
| OpenCode | 4 | 2.590 | 3.467 | 0.737 | 0.800 | Fail |
| OpenCode | 8 | 3.898 | 6.905 | 1.329 | 1.737 | Fail |
| MiMo | 1 | 2.266 | 2.086 | 0.705 | 0.703 | Fail |
| MiMo | 2 | 2.430 | 2.202 | 0.731 | 0.727 | Fail |
| MiMo | 4 | 3.189 | 3.088 | 0.929 | 1.043 | Fail |
| MiMo | 8 | 4.290 | 6.485 | 1.568 | 1.987 | Fail |

All these task pairs passed their functional checks. Resource records verified server
reuse; the MiMo results include the fix for its scheduler files invalidating a retained
server. They also include cheaper executable identity checks. Startup failures therefore
remain after those fixes. Canned fixture tokens are not evidence of real-model throughput.

Raw evidence remains in the original run directories, including `startup.jsonl`,
`results.jsonl`, `audit.json`, event transcripts and resource samples:

- `/tmp/hmz-opencode-priority-n1-fixture-v4`
- `/tmp/hmz-opencode-priority-n2-4-8-fixture-v4`
- `/tmp/hmz-mimo-priority-n1-fixture-v4`
- `/tmp/hmz-mimo-priority-n2-4-8-fixture-v4`

## Delaying the server until a resumed turn

A separate prototype kept the first turn standalone and started a server for the second.
At four concurrent sessions, first-request p50 was 3.129 seconds cold and 5.055 seconds on
the second turn for OpenCode, and 3.888/5.355 seconds for MiMo. All 24 initial probe turns
preserved conversation IDs, recalled the marker, completed fresh read/edit/execute work,
and reaped their servers. A second OpenCode probe reproduced the original native
`database is locked` failure on a first standalone turn; no retry was added.

These prototype probes had CPU affinity 24–27 but lacked the benchmark's cgroup limits.
They are diagnostic evidence, not additional passing benchmark samples. They did not
justify replacing the original transports. Their scripts and results remain under
`/tmp/hmz-feature-audit/`: `mimo-lazy.py`/`.jsonl`,
`om-lazy-concurrent.py`/`.jsonl`, and `om-lazy-profile.py`/`.jsonl`/`.stderr`.


## MiMo per-workspace databases

A later mock-only trial kept the standalone driver and used the official `MIMOCODE_DB`
setting to select one persistent database per canonical workspace. Both original serial
controls and the two-session candidate used the same launcher and fresh databases. All
nine pairs completed their cold/warm tools, checker proofs and conversation recall.

Warm fixed-work p50/p95 ratios were 1.332/1.147, exceeding the 1.10 gate. The default
serial five-repeat comparison passes independently; the isolated profile does not justify
recommending two sessions. The [rejected comparison](evidence-2026-09-10/rejected-optional-mimo-db-n2/index.json)
retains the exact condition and its separate strict failure. Queries restricted to the
nine trial-owned session IDs confirm that each database contains its own trial session
and none of the other eight. An initial assumption that each database contained only one
total session was false and is retained as an audit correction; unrelated history is not
published. Database contention was not established as the cause of the default slowdown.

## Grok worker count

The installed official Rust executable reads `GROK_WORKER_THREADS` and passes the parsed,
bounded value to its runtime builder. An optional profile set it to `2` for both fresh
original serial controls and a six-session candidate, keeping all other inputs unchanged.
All 21 task pairs completed correctly. The [retained comparison](evidence-2026-09-10/rejected-optional-grok-pool2-n6/index.json)
and [phase diagnostic](evidence-2026-09-10/diagnostics/grok-worker-pool.json) keep this condition
separate from default-profile results.

Relative to the earlier default six-session trial, peak threads fell from 338 to 326,
but candidate cold/warm fixed-work p50 increased by 3.6%/5.6%; both p95 values increased
too. The optional profile still fails cold fixed-work p50/p95 and warm fixed-work p95.
Its serial control also changed, so a better ratio alone would not establish an absolute
improvement. This setting is not adopted as a production default or recommended tuning.
The thread reduction is consistent with two fewer workers per process; individual thread
ownership and per-thread CPU time were not sampled.

## Cursor local runtime reuse

Cursor documents a persistent [`agent acp` transport](https://cursor.com/docs/cli/acp)
with Cursor login/API-key authentication. Inspection of the installed official local
package shows that this path does not select the local OpenAI-compatible runtime used by
the mock profile. The interactive persistence route requires a terminal; its print route
collects a piped prompt until EOF rather than accepting a sequence of structured turns.
These routes do not provide a validated replacement for local print-and-resume work.
The benchmark therefore retains the official local print command per turn, including
its measured startup overhead. Standard Cursor service authentication is evaluated
separately from the local model fixture.

### What else was tried against the speed floor

The per-turn cost is the official CLI's, not the adapter's. Timing the driver's own work
for one turn -- local-runtime detection, the environment a turn is run with, the command
it builds and the supervisor wrapper -- totals 0.22 ms against the 5.46 s serial turn the
confirmed rungs are measured against, so no adapter change can move the complete-turn
ratio.

The CLI's own `startup.metrics` sidecar says what does move. A serial turn spends 472 ms
loading the 9.6 MB bundle and 3,569 ms inside `computeGlobalCache`'s `codebaseRef`, which
is an idle wait rather than work. At sixteen sessions `codebaseRef` is unchanged at
3,684 ms while bundle load reaches 2,227 ms, 4.7x its serial cost: sixteen Node processes
compiling the same bundle on four cores is the whole of the degradation. The wait is in
the serial control too, so it divides out of the ratio, and it is why this backend
tolerates concurrency that others cannot. Removing it would make every turn faster and
the measured ratio worse.

Node's compile cache is therefore not an available win here: the official launcher already
points `NODE_COMPILE_CACHE` at the user's cache directory whenever `HOME` is set, and the
472 ms is the cached cost. What that cache is worth was measured rather than assumed, by
pointing the variable at a path Node cannot use as a cache directory for both the serial
controls and the candidate. Bundle load at one session rose from 472 ms to 654 ms, and the
worst complete-turn ratio at twelve sessions -- the rung that decides this ceiling -- rose
from 2.014 to 2.234, with the serial control itself 6% slower. So a warm compile cache is
worth roughly a tenth of the ratio where it matters most, which is more than a low-
concurrency probe would suggest and still not a ceiling-mover. Any Node CLI whose launcher
does not set it is leaving that much on the table.

Reducing Node's pools -- `NODE_OPTIONS=--v8-pool-size=2` with `UV_THREADPOOL_SIZE=2`, for
both fresh serial controls and the candidate -- cut peak threads at one session from 72 to
55 and did not help: sixteen sessions measured a worst complete-turn ratio of 2.601 against
2.389 for the default profile in the neighbouring trial. Not adopted, as a default or as a
tuning suggestion.

Pacing the driver's own process starts, so that a fan-out's bundle-load burst is spread
rather than simultaneous, was not attempted. `_at_once` states this library's position on
it: "a flow that asks for a thousand answers has asked for a thousand turns, and pacing
them behind a number nobody chose would be this library deciding how wide a fan-out may
be." A driver that throttled a caller's fan-out to flatter this benchmark would contradict
that, and the throttled turns would pay the wait anyway.
