# Mock CLI performance evaluation — 2026-09-10

All twelve built-in CLI backends use immediate loopback model responses and dummy credentials, including Cursor's separately distributed official local runtime. The CLI still reads files, edits code, executes the unchanged checker and resumes its native conversation. No live-model samples enter these performance comparisons. The [September 9 real-provider report](RESULTS.md) remains a separate historical record.

## Confirmed concurrency

Each row passed five candidate repetitions against five fresh original serial controls. The ratio columns show the largest of cold/warm p50/p95 for that metric. All primary startup and fixed-work gates pass; the separate legacy verdict uses different event boundaries.

| CLI / profile | Sessions | Worst startup × | Worst fixed work × | Legacy strict | Evidence |
| --- | ---: | ---: | ---: | --- | --- |
| agy | 9 | 1.648 | 0.468 | Pass | [Data](evidence-2026-09-10/selected-stage6-summary.json) |
| claude | 2 | 0.951 | 0.839 | Pass | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| codex | 5 | 1.637 | 0.940 | Fail | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| cursor local | 4 | 1.055 | 1.082 | Pass | [Data](evidence-2026-09-10/selected-stage5-summary.json) |
| dsh | 3 | 1.217 | 0.881 | Pass | [Data](evidence-2026-09-10/selected-stage3-summary.json) |
| grok | 5 | 1.156 | 1.077 | Pass | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| kimi | 2 | 1.573 | 0.317 | Fail | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| mimo | 1 | 1.018 | 1.023 | Pass | [Data](evidence-2026-09-10/mimo-serial-confirmation-summary.json) |
| opencode | 1 | 0.998 | 1.068 | Fail | [Data](evidence-2026-09-10/opencode-default-serial-confirmation-summary.json) |
| pi | 7 | 1.695 | 0.902 | Fail | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| qwen | 6 | 0.938 | 0.998 | Pass | [Data](evidence-2026-09-10/selected-stage5-summary.json) |
| zcode | 4 | 1.279 | 0.936 | Fail | [Data](evidence-2026-09-10/selected-stage5-summary.json) |
| opencode / optional workspace DB | 2 | 1.095 | 0.985 | Pass | [Data](evidence-2026-09-10/selected-stage3-summary.json) |

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
| qwen / speed floor, `48d1559` unchanged | 2×5 P P P; 3×5 P P P P T T T T T T; 4×5 P P P T T; 5×5 T T; 6×5 T |
| qwen / speed floor, headless defaults and compile cache | 2×5 P P; 3×5 P P P P P P P P T T T T; 4×5 P P P P T T T; 5×5 P T T; 6×5 T T; 7×5 T |

The initial [twelve-backend protocol smokes](evidence-2026-09-10/smokes/index.json) and [optional OpenCode two-session exploration](evidence-2026-09-10/optional-opencode-db-n2/index.json) precede this matrix and are retained separately. No failed or interrupted sample was turned into a passing result.

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

## Qwen at the speed floor

The requirement above is no longer startup ≤2× and fixed work ≤1.10×. It is a complete turn at no worse than 2× the serial control — half the speed of no concurrency at all — cold and warm, p50 and p95, with every correctness check kept. Read that way, **Qwen's six is not six**. Its denominator in the matrix above is commit `3e0e6ed`, which started a CLI per turn: that control answers a warm turn in 11.0 s, where today's `origin/main`, which holds the process open, answers one in 0.21 s. Against a fresh serial control of its own source, unchanged `origin/main` **confirms two**.

The candidate writes Qwen's own lowest settings layer — the system defaults, beside the generated effort file, which a person's own settings still outrank — saying that a turn hmz drives defaults to `general.preventSystemSleep: false` and `general.enableAutoUpdate: false`, and it points Node's `NODE_COMPILE_CACHE` at `~/.cache/humanize/qwen-code` unless the environment names one. It **confirms four**. Every rung of both sources is fully correct: all items passing, fresh execution proofs, immutable fixture and checker, the turn-two conversation-only marker recalled, exactly one result, no cleanup survivors.

| Sessions | Original: trials | Original: median worst × | Candidate: trials | Candidate: median worst × |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 3/3 | 1.336 | 2/2 | 1.265 |
| 3 | 4/10 | **2.109** | 8/12 | 1.854 |
| 4 | 3/5 | 1.824 | 4/7 | 1.800 |
| 5 | 0/2 | **2.334** | 1/3 | **2.758** |
| 6 | 0/1 | **2.620** | 0/2 | **2.712** |
| 7 | — | — | 0/1 | **3.979** |

Each trial is five repetitions against the five fresh serial controls of the same run and the same source. One trial decides nothing here: the serial control's own warm p95 moves by about a third with load outside the cgroup, and the floor divides by it — so widths are read on the median of their trials, and every trial is retained. The original passes four and misses three; the candidate passes two, three and four alike, which is why four is the width published for it and two for the original. The candidate's column pools its trials from before and after the format-version stamp, which removed a file rewrite and can only have helped; the retained record separates them, and the last four of its trials are the committed source run back to back against the original in the same measurement group.

That the original misses three and passes four is the estimator, not the CLI. Nearest-rank p95 of *k* observations is the ⌈0.95*k*⌉-th: a five-repeat serial control has *k*=5 and its p95 is its maximum; a three-session rung has *k*=15 and its p95 is *also* its maximum; four sessions has *k*=20 and excludes the maximum, five has *k*=25 and excludes one. Three sessions is the harshest rung on this ladder, and the ladder is not monotone. That asymmetry is retained here rather than corrected. In every individual miss the rung's p50 passes and its p95 is set by one repeat whose sessions all ran slow together — the signature of load outside the cgroup, on the measurement group's unallocated SMT siblings, rather than of anything the CLI did.

| | Cold turn | Cold CPU | Warm turn | Warm CPU | Cores per warm turn |
| --- | ---: | ---: | ---: | ---: | ---: |
| original `48d1559`, quiet host | 6.678 s | 9.306 | 0.241 s | 0.608 | 2.52 |
| candidate, quiet host | 5.722 s | 8.185 | 0.210 s | 0.486 | 2.31 |
| original `48d1559`, busy host | 7.111 s | 10.217 | 0.278 s | 0.667 | 2.40 |
| candidate, busy host | 7.023 s | 10.098 | 0.270 s | 0.625 | 2.31 |
| candidate, credential supervisor removed (diagnostic) | 2.025 s | 4.000 | 0.158 s | 0.415 | 2.63 |

One session alone in the same four cores, eight cold/warm pairs, cgroup CPU seconds charged to each turn, taken as two back-to-back pairs an hour apart. The absolute saving is 14% of a cold turn's wall and 20% of a warm turn's CPU on a quiet host, and 1% and 6% of the same on a busy one — contention compresses the difference. The last column, which is the one the floor is about, reads 2.31 either way.

**What caps Qwen is the fourth column against the third, not the first.** A warm turn spends about half a CPU-second in a fifth of a second of wall — 2.3 cores at once — so on four cores the arithmetic ceiling is 4/2.31 × 2 ≈ 3.5 sessions however fast the turn is made: a saving that shortens the turn shortens the serial control with it and divides out. Only the part that lowers cores per turn moves the width, which is why 20% off the CPU buys one session rather than four.

The last row is a diagnostic and not a configuration anybody may use: it removes credential isolation and nothing else. It shows the supervisor is **51% of a cold turn's CPU** and 15% of a warm turn's — by far Qwen's largest single cost, and the reason its absolute times are what they are — but removing it *raises* cores per warm turn to 2.63, because ptrace stops serialize the tracee against its tracer. Faster stops would buy Qwen a great deal of wall time and almost no concurrency.

Measured against the same warm CPU and not adopted: `--v8-pool-size=1` (0.520) and `=0` (0.742), `UV_THREADPOOL_SIZE=1` (0.560), `--max-semi-space-size=64` (0.521), `--max-old-space-size=512` (0.524), `tools.shell.enableInteractiveShell: false` (0.515), and a wider headless block turning off `privacy.usageStatisticsEnabled` and the `ui.*` defaults (0.552) — against 0.512 for the settings change alone at the time each was taken. Exact per-round ratios, distributions, denominators and conditions are in [the retained record](evidence-2026-09-10/qwen-speed-floor-summary.json). With this change, `uv run pytest` passed 2,244 tests with 77 skips and 41 warnings, and `uv run pre-commit run --all-files` passed.
