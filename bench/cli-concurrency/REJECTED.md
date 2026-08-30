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

## Codex on one app server per agent

Making the shared app server's stream safe for concurrent readers is adopted; keeping one
server per agent alongside it is not. Codex opens and picks a thread up one at a time
whatever else it is running, so every conversation after the first waits out the ones ahead
of it before it can say its first word. Four conversations opened at once on one server each
waited 1.32 to 1.54 seconds for `thread/start` and finished staggered, while the four turns
that followed overlapped and ended within 32 milliseconds of each other. The same shape holds
with and without the credential supervisor in front of the server, so the serialization is
inside the app server rather than in anything humanize wraps it in.

| Sessions | Worst complete-task ratio | Cold p50 |
| ---: | ---: | ---: |
| 2 | 1.384 | 1.508 s |
| 3 | 2.034 | 2.207 s |
| 4 | 2.716 | 2.946 s |
| 6 | 4.064 | 4.400 s |
| 8 | 4.872 | 5.308 s |

All these task pairs passed their functional checks. The adopted driver starts one more
server when every server the agent has is running a turn, which is a server per conversation
worked at once and exactly one for a flow that takes its turns in sequence. A first prototype
that also let a conversation move to whichever server was free failed instead of queueing:
Codex refuses `thread/resume` on a second server with `thread ... already has an active
writer` while the first still holds that rollout open. Five of sixteen items failed that way
before a session was pinned to the server it was opened on.

Removing the live `item/agentMessage/delta` tee was measured as a separate candidate and
rejected as immaterial: 2.512 s cold p50 at eight sessions without it against 2.459 s with
it, both inside the run-to-run spread of the serial control. It is retained for the reason it
was written. Raw evidence is in the [complete-task floor
summary](evidence-2026-09-10/codex-complete-task-floor-summary.json), under
`exploratory_ladders`, with the journal hash of each run directory.
