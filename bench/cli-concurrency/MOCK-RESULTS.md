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
| cursor local / speed floor | 8×3 P; 16×3 T; 10×3 T; 12×3 T; 9×3 P; 10×3 P; 11×3 P; 12×3 T; 14×3 T; 12×3 T; 16×3 T; 20×3 T; 12×5 T; 12×5 T; 11×5 T; 11×5 T; 11×5 P; 11×5 P |
| cursor local / rejected optional reduced native thread pools | 16×3 T |
| cursor local / rejected optional defeated Node compile cache | 12×3 T |

The initial [twelve-backend protocol smokes](evidence-2026-09-10/smokes/index.json) and [optional OpenCode two-session exploration](evidence-2026-09-10/optional-opencode-db-n2/index.json) precede this matrix and are retained separately. No failed or interrupted sample was turned into a passing result.

## Cursor at the speed floor

Cursor's separately distributed official local runtime holds **eleven** concurrent sessions at better than half its serial speed. The four in the matrix above is where the deleted fixed-work tolerance stopped it, not where the CLI stopped. Almost none of the difference is code: the candidate changes only which environment variables a cursor turn is run without, and the whole of the driver's own per-turn Python work — local-runtime detection, the environment a turn is run with, the command it builds, the supervisor wrapper — measures 0.22 ms against a 5.46 s serial turn. The `cursor local / speed floor` row in the trial table above is scored against this floor rather than the deleted primary gates, and against `48d1559` rather than this report's earlier original.

| Profile | Sessions | Worst complete-turn × | cold p50 | cold p95 | warm p50 | warm p95 | Correct pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cursor local | 11 | 1.997 | 1.507 | 1.864 | 1.510 | 1.997 | 55/55 |
| cursor local, repeated | 11 | 1.729 | 1.589 | 1.720 | 1.622 | 1.729 | 55/55 |
| cursor local, the rung above | 12 | 2.044 | 1.806 | 2.044 | 1.817 | 1.963 | 60/60 |

Each row is five candidate repetitions against five fresh original serial controls of `48d1559`, run adjacent to it in the same measurement group, and followed by a second set of serial controls so a rung taken while the host was busy can be told from one taken while it was not. Eleven is confirmed twice because its first confirmation left only 0.003 of margin. Twelve is a boundary rather than a near miss: it was tried five times — 2.625, 2.091, 2.014 at three repeats and 2.085, 2.044 at five — and missed on a tail every time while both p50s passed. Read the way this document's other ratio columns are, as the largest of cold/warm p50/p95, the same eleven-session rung has a startup ratio of 1.637 and a fixed-work ratio of 4.502; twelve has 1.637 and 5.382. That is what the deleted gates were rejecting, and none of those turns is slower than half serial speed. Exact distributions, denominators, limits and source hashes for every trial named here are in [the retained record](evidence-2026-09-10/cursor-speed-floor-summary.json).

**Where a cursor turn's time goes, and why the ratio holds so far.** The CLI's own `startup.metrics` sidecar says a serial turn spends 472 ms loading its 9.6 MB bundle and 3,569 ms inside `computeGlobalCache`'s `codebaseRef`, which is an idle wait rather than work. At sixteen sessions `codebaseRef` is unchanged at 3,684 ms while bundle load reaches 2,227 ms, 4.7× its serial cost: sixteen Node processes compiling the same bundle on four cores is the whole of the degradation. The wait is in the serial control too, so it divides out of the ratio, and it is why this backend tolerates concurrency others cannot — removing it would make every turn faster and this number worse. What was tried against the bundle-load cost, and why none of it was adopted, is in [the rejected experiments](REJECTED.md).

**Conditions, and three retained failures.** Every figure here was taken at four logical CPUs with a 400% quota, 16 GiB and zero swap, one `run.py` at a time, against the same fixture revision and the same official local distribution. The exploratory ladder was climbed twice, before and after the `hmzbench-run` occupancy guard was fixed — `[[ -s cgroup.procs ]]` is always false on a kernfs file, so the wrapper had been joining groups that already held another unit's run — and the two ladders agree within noise at both widths they share (2.091 against 2.014 at twelve, 2.389 against 2.594 at sixteen), so that bug cost this backend nothing measurable. Three samples are retained as failures rather than results. A ten-session trial reported 3.627, worse than sixteen sessions in the same ladder, because two of this unit's own benchmarks were in flight at once; the twelve-session rung of that same ladder, 2.625, shares the condition. Two five-repeat attempts at eleven sessions reported 3.197 and 2.921 on cpus 4-7 while a sibling unit's `systemd-run --user --scope` benchmark was scheduled on those same cores: the groups are `cpuset.cpus.partition=member` with no `cpuset.cpus.exclusive`, so they confine what is inside them and reserve nothing against what is not, and `cpu_busy_cores` peaked at 3.52 against a 4.0 quota while those pairs' own serial controls stayed normal. The published rungs were screened by sampling `/proc` for running tasks on the measurement CPUs outside the `hmzbench` cgroup; only Kubernetes and host daemons appeared.

**What this does not establish.** It validates the official local distribution's coding tools and conversation resume under concurrency. It says nothing about standard Cursor authentication or its service RPC, which this fixture does not implement and which still answers `Authentication required` on this host exactly as [the September 9 report](RESULTS.md) records.

## Method

Each backend is measured alone inside a cgroup limited to four CPUs, 16 GiB memory and zero swap, with affinity to physical cores 8–11. The mock server runs on separate CPUs outside that scope; tests and audits use other CPUs. The [retained fixture launch observation](evidence-2026-09-10/diagnostics/fixture-launch-provenance.json) records the planned affinity override and observed separation. This is a shared 64-logical-CPU host with enforced limits, not a dedicated virtual machine. OS page caches remain warm between fresh sessions.

Every pair contains cold and warm turns. Each turn must perform the same three real shell tool calls and four successful workload requests, produce a fresh execution proof and preserve immutable task inputs. The warm answer must recall a conversation-only marker. Missing work, repeated workload requests, provider errors, provenance changes or surviving processes invalidate the case. Auxiliary calls and cancellations remain separately visible. Error coverage is fixture-only: every fixture workload and auxiliary HTTP failure is checked, while native auxiliary log coverage is incomplete. This does not establish that every CLI emitted no native error.

Startup runs from turn submission to the earliest correlated provider request, including auxiliary requests. Fixed-work time runs from that request to the hmz result; it includes native tool execution, adapter delivery and mock transport. Cold/warm p50 and nearest-rank p95 must each satisfy startup ≤2× and fixed work ≤1.10× against fresh original serial controls. The original first-event/post-first-tool harness verdict is retained separately; first-event time is not a startup measurement. Synthetic token counts do not establish model throughput.

Three-repeat ladder trials are exploratory. A chosen passing boundary requires five fresh original serial controls and five candidate groups. The observed passing boundary and failed neighboring trials do not prove a universal maximum: host scheduling and the unequal sample counts of serial and concurrent p95 estimates remain relevant. These trials do not measure mixed-backend concurrency.

## Configuration conditions

Original source is commit `3e0e6edf1d47ae27a70c1a334ee6cf364d05f59b`. Candidate snapshots, native executable hashes, fixture/harness revisions, per-turn distributions and proof checks are retained with the evidence. All configured model routes use literal `127.0.0.1` and complete child environments with dummy keys; no real-provider fallback is configured. Fixed JSON/SSE responses have no intentional delay. Fixture processing time and active handlers are retained to distinguish server contention from CLI overhead.

Cursor uses the unchanged official local distribution `2026.09.08-6caf4ff` with native authless mode and an OpenAI-compatible local endpoint. The original adapter's `fixture-model[fast=false]` and the candidate's `fixture-model` receive the same response policy. This validates the local distribution's coding tools and conversation resume; standard Cursor authentication and service RPC are outside this profile. Native update/command-discovery errors are separate from the configured model route and are retained where observable. The speed-floor rungs above reuse this same distribution and launcher, by the executable and package hashes retained beside them; the only difference between original and candidate on a cursor turn is which environment variables the turn is run without, since the CLI reads its local runtime's endpoint and key from `CURSOR_LOCAL_AGENT_BASE_URL` and `CURSOR_LOCAL_AGENT_API_KEY` whoever exported them.

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
