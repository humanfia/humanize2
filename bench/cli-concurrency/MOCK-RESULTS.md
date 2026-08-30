# Mock CLI performance evaluation — 2026-09-10

All twelve built-in CLI backends use immediate loopback model responses and dummy credentials, including Cursor's separately distributed official local runtime. The CLI still reads files, edits code, executes the unchanged checker and resumes its native conversation. No live-model samples enter these performance comparisons. The [September 9 real-provider report](RESULTS.md) remains a separate historical record.

## Confirmed concurrency

Each row passed five candidate repetitions against five fresh original serial controls. The ratio columns show the largest of cold/warm p50/p95 for that metric.

**The startup and fixed-work columns are no longer the requirement.** They were the gate this matrix was climbed under — startup at most 2× and fixed work at most 1.10× — and the requirement is now the single floor described [below](#concurrency-at-the-floor-the-requirement-names): a complete turn at most 2× the serial control, cold and warm, p50 and p95, which is at least half the speed the same work has with no concurrency at all. Every check that is not about speed still holds: all items correct, fresh execution proofs, immutable inputs, the turn-two marker recalled from the conversation alone, exactly one result, no cleanup survivors. The `Sessions` column is retained because it is what these trials were selected on, and because the columns beside it only mean anything against it.

| CLI / profile | Sessions | Worst startup × | Worst fixed work × | Legacy strict | [At the floor](#concurrency-at-the-floor-the-requirement-names) | Evidence |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| agy | 9 | 1.648 | 0.468 | Pass | ≥9 | [Data](evidence-2026-09-10/selected-stage6-summary.json) |
| claude | 2 | 0.951 | 0.839 | Pass | **7** | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| codex | 5 | 1.637 | 0.940 | Fail | ≥5 | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| cursor local | 4 | 1.055 | 1.082 | Pass | ≥5 | [Data](evidence-2026-09-10/selected-stage5-summary.json) |
| dsh | 3 | 1.217 | 0.881 | Pass | **12** | [Data](evidence-2026-09-10/selected-stage3-summary.json) |
| grok | 5 | 1.156 | 1.077 | Pass | ≥5 | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| kimi | 2 | 1.573 | 0.317 | Fail | **≥8** | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| mimo | 1 | 1.018 | 1.023 | Pass | **≥8** | [Data](evidence-2026-09-10/mimo-serial-confirmation-summary.json) |
| opencode | 1 | 0.998 | 1.068 | Fail | **≥6** | [Data](evidence-2026-09-10/opencode-default-serial-confirmation-summary.json) |
| pi | 7 | 1.695 | 0.902 | Fail | ≥7 | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| qwen | 6 | 0.938 | 0.998 | Pass | ≥7 | [Data](evidence-2026-09-10/selected-stage5-summary.json) |
| zcode | 4 | 1.279 | 0.936 | Fail | ≥5 | [Data](evidence-2026-09-10/selected-stage5-summary.json) |
| opencode / optional workspace DB | 2 | 1.095 | 0.985 | Pass | ≥2 | [Data](evidence-2026-09-10/selected-stage3-summary.json) |

A **bold** figure in the last column was measured for it: five fresh repetitions at that width against five fresh serial controls, inside four exclusive cores. Where it also carries `≥`, the width above was never tried, so it is a confirmed width rather than a ceiling. A plain figure, not in bold, was **re-derived arithmetically** from these same trials' retained complete-turn distributions rather than measured again — this ladder stopped climbing the moment a rung missed the old fixed-work gate, so its highest recorded rung is a floor and not a ceiling. The re-derivation is in [its own record](evidence-2026-09-10/speed-floor-rederived-summary.json); it shows every retained default-profile rung of this evaluation clearing the floor except codex at eight (2.020) and zcode at eight (2.565), and agy still clearing it at sixteen (1.978).

Exact ratios, original/candidate phase distributions, all repeat denominators and the selected source references are in [the machine-readable result](results-2026-09-10.json). The retained trial sequence follows; `P` is a primary pass, `T` a timing miss, and `E` an execution failure. An entry `6×5 P` means six concurrent sessions and five repetitions. Three-repeat passes remain exploratory.

| CLI / profile | Recorded candidate trials |
| --- | --- |
| agy | 2×3 P; 4×3 P; 8×3 P; 16×3 T; 12×3 T; 10×3 T; 9×5 P |
| claude | 2×3 P; 4×3 T; 3×3 P; 3×5 T; 2×5 P |
| codex | 2×3 P; 4×3 P; 8×3 T; 6×3 T; 5×5 P |
| cursor | 2×3 P; 4×3 P; 8×3 T; 6×3 T; 5×5 T; 4×5 P |
| dsh | 2×3 P; 4×3 T; 3×3 P; 3×5 P |
| grok | 2×3 P; 4×3 P; 8×3 T; 6×3 T; 5×5 P |
| kimi | 2×3 P; 4×3 T; 3×3 P; 3×5 T; 2×5 P |
| mimo | 2×3 T; 1×5 P |
| opencode | 2×3 E; 1×5 P |
| pi | 2×3 P; 4×3 P; 8×3 T; 6×3 P; 7×5 P |
| qwen | 2×3 P; 4×3 P; 8×3 T; 6×3 P; 7×5 T; 6×5 P |
| zcode | 2×3 P; 4×3 P; 8×3 T; 6×3 T; 5×5 T; 4×5 P |
| grok / rejected optional native worker pool size 2 | 6×3 T |
| mimo / rejected optional per workspace native database | 2×3 T |
| opencode / optional per workspace native database | 4×3 T; 3×3 T; 2×5 P |
| claude / speed floor | 7×5 P; 8×5 T; 10×5 T |
| dsh / speed floor | 10×5 P; 12×5 P; 16×5 T |
| kimi / speed floor | 7×5 P; 8×5 P |
| mimo / speed floor | 7×5 P; 8×5 P |
| opencode / speed floor | 4×5 P; 5×5 P; 6×5 P |

The initial [twelve-backend protocol smokes](evidence-2026-09-10/smokes/index.json) and [optional OpenCode two-session exploration](evidence-2026-09-10/optional-opencode-db-n2/index.json) precede this matrix and are retained separately. No failed or interrupted sample was turned into a passing result.

## Concurrency at the floor the requirement names

The requirement is **at least half the speed the same work has with no concurrency at all**. Read per turn that is complete-turn latency, from turn submission to the result and startup included, at most 2× the serial control, for cold and warm p50 and p95 alike. Throughput is not the reading: N sessions always finish more work than one, so a throughput floor would be met by every rung ever recorded here. Nothing else moved: a rung with a failed item, a missing execution proof, a marker the second turn could not recall, more than one result, or a surviving process is not a result at any speed.

Under the old gate five backends stopped at one to three sessions. None of them stops there under this one, and only one of the five had a line of its driver changed at all: the numbers below are the same CLIs doing the same work, asked the question the person asking it actually named. Each row is five candidate repetitions against five fresh serial controls of the same source, on the same fixture, the same four-CPU/16 GiB/zero-swap cgroup, the same workload and the same cold/warm task pair with its conversation-only marker.

| CLI | Sessions | Worst complete-turn × | Same rung, startup × | Same rung, fixed work × | Correct turns |
| --- | ---: | ---: | ---: | ---: | ---: |
| claude | 7 | 1.648 | 1.732 | 2.046 | 70/70 |
| dsh | 12 | 1.847 | 1.664 | 2.061 | 120/120 |
| kimi | 8 | 1.824 | 2.290 | 2.241 | 80/80 |
| mimo | 8 | 1.932 | 1.730 | 3.117 | 80/80 |
| opencode | 6 | 1.860 | 2.146 | 2.023 | 60/60 |

The startup and fixed-work columns are those same rungs under the old gates, kept so the two can be read against each other: every one of these rungs fails the old fixed-work tolerance, and every one of them runs at better than half serial speed. That is the whole of the difference between one to three sessions and six to twelve. Nothing in these CLIs became faster. Exact per-phase distributions, denominators and settings are in [the retained evidence](evidence-2026-09-10/speed-floor-five-backends-summary.json).

Two of the five are boundaries: the width above was tried at five repetitions and missed — claude 8 (2.055) and 10 (2.368), dsh 16 (2.224). **Kimi, mimo and opencode are confirmed widths rather than boundaries.** Each cleared the top of its ladder and the width above was never tried: the run that would have tried mimo 9 and opencode 7 was stopped mid-flight when this unit was asked to hand over, and kimi's rungs run over a minute each here. Their real ceilings are higher than what is written down.

**Conditions, and which figures predate the fix.** Every figure in this table was measured inside `/sys/fs/cgroup/hmzbench/u16` — four *exclusive* physical cores enforced by cgroup v2 `cpuset` rather than task affinity, `cpu.max` 400%, 16 GiB, zero swap — with one `run.py` at a time and the boundary and the width above it sharing one serial control. Earlier figures from this unit, taken on cpuset `0-3` while other units' benchmarks ran on neighbouring quads, are **superseded and not reported here**; they were systematically pessimistic, and every backend cleared a higher width once the cores were exclusive: claude 6→7, dsh 8→12, mimo 5→8, opencode 4→6. Two orphaned processes of this unit's own — survivors of a batch killed when the fixture server died — sat in scopes pinned to `0-3` for about eighty minutes and were reaped before the final runs. No retained rung recorded a watchdog kill, a cleanup survivor, a turn without a result, or a `--grace` above the harness's 45-second watchdog margin.

### What actually stops each of them

Measured serially, in seconds, in the same group (p50):

| CLI | Cold startup | Warm startup | Cold fixed work | Warm fixed work |
| --- | ---: | ---: | ---: | ---: |
| claude | 0.83 | 0.03 | 0.36 | 0.30 |
| dsh | 2.12 | 0.02 | 0.22 | 0.20 |
| kimi | 55.05 | 0.25 | 0.89 | 0.97 |
| mimo | 4.02 | 3.83 | 0.52 | 0.70 |
| opencode | 1.95 | 2.37 | 1.07 | 0.65 |

**claude** and **dsh** hold a process per session, so a warm turn starts in twenty to thirty milliseconds and the whole turn is a third of a second. Nothing in either driver is the limit; the four-core quota is, and both saturate it. Their old ceilings of two and three were a ratio against a fixed-work baseline of a fifth of a second, where a forty-millisecond tail is a failed gate.

**kimi** shares one `kimi web` daemon across every session of its agent, and that daemon is the whole of its cold cost: a serial cold turn is almost a minute of daemon boot and about a second of work. Because every session of a rung waits on the same boot, kimi's cold startup ratio stays between 1.16 and 1.45 at every width from two sessions to eight, and only its warm turns really move. That boot is also the one number here that did not hold still: across five kimi trials on this host the serial cold-startup control rose monotonically — 17.7, 28.1, 38.4, 43.1, 55.1 seconds — while the CLI's own home grew past 265 MB and 3,900 files. No cause was established and the correlation is not one, but somebody should establish it: a coding agent whose daemon takes a minute to start because of history it will never read is worth a look. What follows for these numbers is only that kimi rungs are comparable to the serial controls taken beside them and to nothing else.

**opencode** and **mimo** run a fresh CLI process for every turn, and it is 2.4 to 3.8 seconds of native startup each time — three to five times what either of them then spends doing the work. That is the largest fixed cost in this matrix and it is paid per turn rather than once per session. It is also, notably, *not* what caps them: both reach six and eight sessions anyway, because a cost every session pays alike divides out of the ratio. The [rejected server-reuse prototypes](REJECTED.md) remain the record of what was tried.

### opencode's shared database, and why the driver leaves it alone

The `database is locked` failure [DETERMINISTIC.md](DETERMINISTIC.md) records was reproduced here: one item of a five-session exploratory trial failed with `Unexpected error database is locked` after 0.99 s, before any provider request and before the session had an id. It is the only failed item in **297** opencode items this unit ran, across one, two, four, five, six, seven and eight sessions — and a later fifty-item trial at that same five sessions had no failure at all. So it is probabilistic rather than a ceiling. Nothing below five concurrent cold starts produced it, and nothing about the width above five made it more likely.

humanize does not set `OPENCODE_DB` itself, and the reason is not performance. That database is where opencode keeps the **conversation**, not a credential, and `backends.py` says what a turn under a provider may move: "the sessions, the settings and the skills are the same ones the CLI already has." A per-workspace database would put every conversation humanize opened somewhere the user's own `opencode` cannot find it, and would charge a fresh database initialization to the first turn in every new directory — for a failure that appears above four concurrent cold starts. The measurement does not argue for it either: the [optional per-workspace profile](evidence-2026-09-10/selected-stage3-summary.json) is not faster than the default. It stays what it is, a benchmark configuration and an operator's lever, and `setup_opencode_database.py` remains the way to apply it.

No retry was added either, for the reason [REJECTED.md](REJECTED.md) already records against the same failure.

### The one driver change these trials justify

Kimi's reader took four authoritative REST readings — pending questions, session status, session spending, session messages — on every notification the daemon woke it with. One daemon serves every session of its agent, so at eight sessions that is the shared daemon answering, several times a second, questions it has just said the answer to. The notification stream now says which of those readings is due: questions when the daemon has raised one, spending when a step has landed, and both when the listener is carrying nothing or is told something it does not recognize. Status and messages are read every round as before, and each of the two is read at least once a second regardless of what the daemon says, so nothing can be missed for longer than it could before there were notifications at all. An instrumented probe of one cold/warm task pair counted 79 daemon calls before the change and 43 after.

Frames the daemon streams a chunk at a time — a running command's output, a tool call's arguments — are coalesced into at most one reading per second rather than woken for one by one. A first version of this change woke for each of them instead, which on a shell-heavy turn would have cost more than it saved. It was found in review after its own five-repeat trial had already run; that trial is retained beside the others as `kimi-superseded-candidate-n7-contended-cpuset`, and the reported candidate is the coalescing one.

**What none of this established.** On the superseded contended cpuset, three five-repeat trials at seven sessions sat side by side: the original misses the floor at 2.088, the superseded candidate passes at 1.966 and the shipped candidate passes at 1.556, each against its own five fresh serial controls. Read as a progression that is exactly wrong, because the serial controls underneath them are not the same: their cold p50 is 18.4 s, 29.0 s and 39.5 s, and their warm p50 is 0.752 s, 0.881 s and 1.093 s. In absolute seconds the seven-session warm p50 barely moved — 1.570 s, 1.717 s, 1.604 s — while every denominator grew. **No timing improvement is claimed for this change.** What is measured is the call count: 79 daemon calls per cold/warm task pair before, 43 after. What the trials show is that the change cost nothing, and that eight sessions clears the floor for the code being shipped — the shipped candidate's own eight-session confirmation in the isolated group is 1.824, with 80 of 80 turns correct.

## Method

Each backend is measured alone inside a cgroup limited to four CPUs, 16 GiB memory and zero swap, with affinity to physical cores 8–11. The mock server runs on separate CPUs outside that scope; tests and audits use other CPUs. The [retained fixture launch observation](evidence-2026-09-10/diagnostics/fixture-launch-provenance.json) records the planned affinity override and observed separation. This is a shared 64-logical-CPU host with enforced limits, not a dedicated virtual machine. OS page caches remain warm between fresh sessions.

Every pair contains cold and warm turns. Each turn must perform the same three real shell tool calls and four successful workload requests, produce a fresh execution proof and preserve immutable task inputs. The warm answer must recall a conversation-only marker. Missing work, repeated workload requests, provider errors, provenance changes or surviving processes invalidate the case. Auxiliary calls and cancellations remain separately visible. Error coverage is fixture-only: every fixture workload and auxiliary HTTP failure is checked, while native auxiliary log coverage is incomplete. This does not establish that every CLI emitted no native error.

Startup runs from turn submission to the earliest correlated provider request, including auxiliary requests. Fixed-work time runs from that request to the hmz result; it includes native tool execution, adapter delivery and mock transport. Cold/warm p50 and nearest-rank p95 must each satisfy startup ≤2× and fixed work ≤1.10× against fresh original serial controls. The original first-event/post-first-tool harness verdict is retained separately; first-event time is not a startup measurement. Synthetic token counts do not establish model throughput.

Three-repeat ladder trials are exploratory. A chosen passing boundary requires five fresh original serial controls and five candidate groups. The observed passing boundary and failed neighboring trials do not prove a universal maximum: host scheduling and the unequal sample counts of serial and concurrent p95 estimates remain relevant. These trials do not measure mixed-backend concurrency.

## Configuration conditions

Original source is commit `3e0e6edf1d47ae27a70c1a334ee6cf364d05f59b`. Candidate snapshots, native executable hashes, fixture/harness revisions, per-turn distributions and proof checks are retained with the evidence. All configured model routes use literal `127.0.0.1` and complete child environments with dummy keys; no real-provider fallback is configured. Fixed JSON/SSE responses have no intentional delay. Fixture processing time and active handlers are retained to distinguish server contention from CLI overhead.

Cursor uses the unchanged official local distribution `2026.09.08-6caf4ff` with native authless mode and an OpenAI-compatible local endpoint. The original adapter's `fixture-model[fast=false]` and the candidate's `fixture-model` receive the same response policy. This validates the local distribution's coding tools and conversation resume; standard Cursor authentication and service RPC are outside this profile. Native update/command-discovery errors are separate from the configured model route and are retained where observable.

OpenCode's default shared SQLite database failed during the first two-session candidate repetition, before any model request. The controller stopped that case and retained its missing and undispatched work. A separate, optional native `OPENCODE_DB` launcher selects one persistent database per canonical task workspace for both original and candidate. Its interpreter startup and database initialization are included in timing. This condition changes benchmark configuration, not the production driver; it does not replace the failed default trial. The initial three-repeat isolated comparison passed all gates and verified nine distinct databases with cold/warm native conversation continuity; the later five-repeat confirmation also passed.

Codex and ZCode use separate Agent instances. Other backends use multiple Sessions on one Agent. Antigravity receives the same explicit workspace argument in original and candidate; its first native formatting-only settings rewrite is retained as a stopped provenance trial and subsequent locks pin the rewritten bytes.

## Implementation and validation

Qwen and Antigravity reuse official streaming CLI processes for ordinary turns, resume finite structured-output turns and restart when native settings or skills change. Antigravity also keeps finite slash commands. Usage handling and native structured-result/workspace behavior retain dedicated regression coverage. The Linux supervisors remove temporary ctypes pointer cycles without changing the flow API.

Kimi wakes authoritative REST reads from official WebSocket notifications, answers native heartbeats and retains polling recovery. Mock profiling exposed a full receive queue delaying socket disposal by one second after a completed turn. The bounded receive queue stays unchanged; a 100 ms close grace removes approximately 900 ms from that wait. Separate instrumented before/after task probes verified cleanup and exact task proofs; those timings are diagnostic only and excluded from performance gates.

See [fixture reproduction](DETERMINISTIC.md), [the general runner](RUNNING.md) and [rejected process-reuse experiments](REJECTED.md). `uv run pytest` passed 2,239 tests with 77 skips and 41 warnings in 716.87 seconds, including the 58 benchmark tests. `uv run pre-commit run --all-files` also passed. Skips cover opt-in live-agent checks and unavailable Docker/localhost SSH; no live-agent tests were enabled for mock profiling. Native feature and flow contract checks from the earlier evaluation remain separately documented in [the historical report](RESULTS.md). The production flow implementation/API is unchanged.

## Remaining measured costs

The [CPU phase comparison](evidence-2026-09-10/diagnostics/cli-cpu-phases.json) and its [input provenance](evidence-2026-09-10/diagnostics/cli-cpu-phases-provenance.json) cover selected four/eight-session trials. At eight sessions, Qwen, Grok and Pi approach the four-core quota during portions of fixed work. Peak memory in these cases stays well below 16 GiB, with no recorded OOM events. Fixture processing remains a few milliseconds per turn. Shared process-tree samples overlap concurrent turns; they cannot attribute CPU to an individual session or prove which native function is expensive.

Lowering Grok's native worker count reduced threads but did not improve absolute task timing. MiMo's per-workspace database profile also missed the fixed-work gate. Both are retained as [rejected experiments](REJECTED.md), alongside OpenCode/MiMo server-reuse prototypes and the Cursor local persistence investigation. [MiMo's native phase diagnostic](evidence-2026-09-10/diagnostics/mimo-default-n2-native-phases.json) locates most of its two-session increase between tool requests; it does not establish SQLite contention as the cause. [Kimi's cleanup diagnostic](evidence-2026-09-10/diagnostics/kimi-notification-cleanup.json) isolates the adopted close-grace improvement.

These results establish observed concurrency for this fixed workload and the installed versions. They do not prove that no future native-runtime or adapter optimization is possible. Official CLI binaries remain unchanged; unsupported protocol substitutions and changes that regressed measured startup were not adopted.
