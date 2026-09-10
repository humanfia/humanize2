# Mock CLI performance evaluation — 2026-09-10

All twelve built-in CLI backends use immediate loopback model responses and dummy credentials, including Cursor's separately distributed official local runtime. The CLI still reads files, edits code, executes the unchanged checker and resumes its native conversation. No live-model samples enter these performance comparisons. The [September 9 real-provider report](RESULTS.md) remains a separate historical record.

## Confirmed concurrency

Each row passed five candidate repetitions against five fresh original serial controls. The ratio columns show the largest of cold/warm p50/p95 for that metric. All primary startup and fixed-work gates pass; the separate legacy verdict uses different event boundaries.

Antigravity's row was re-taken against [the speed floor](#antigravity-at-the-speed-floor), which is the requirement now: a complete turn at most 2× the serial control. The startup and fixed-work gates it was first climbed under are not reported for it, so its ratio columns are empty rather than carrying numbers from a gate that no longer decides anything.

| CLI / profile | Sessions | Worst startup × | Worst fixed work × | Legacy strict | Evidence |
| --- | ---: | ---: | ---: | --- | --- |
| agy | 10 | — | — | — | [Data](evidence-2026-09-10/agy-speed-floor-summary.json) |
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
| agy | 2×3 P; 4×3 P; 8×3 P; 16×3 T; 12×3 T; 10×3 T; 9×5 P — then, at the speed floor: 8×3 P; 9×5 P ×4; 10×5 P ×10, T ×1; 11×5 P ×4, T ×5; 12×5 T ×2 |
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

The initial [twelve-backend protocol smokes](evidence-2026-09-10/smokes/index.json) and [optional OpenCode two-session exploration](evidence-2026-09-10/optional-opencode-db-n2/index.json) precede this matrix and are retained separately. No failed or interrupted sample was turned into a passing result.

## Antigravity at the speed floor

The requirement is one number: a complete turn — submission to the hmz result — at most **2× the serial control**, cold and warm, p50 and p95, which is at least half the speed the same work has with no concurrency at all. Every check that is not about speed is unchanged: all items correct, the fixture's own four workload exchanges with completed steps `0,1,2,3` and no auxiliary failure, a fresh execution proof over untouched task inputs, the turn-two marker recalled from the conversation alone, exactly one result, and no cleanup survivor. Twenty-six rounds were taken, each five fresh serial controls plus five repetitions at each width, alternating `origin/main` and candidate. [The record](evidence-2026-09-10/agy-speed-floor-summary.json) carries every round, contaminated ones included.

| Sessions | `origin/main` 48d1559 | candidate | worst ratio seen passing |
| ---: | ---: | ---: | ---: |
| 9 | 3 of 3 | 4 of 4 | 1.863 |
| 10 | 4 of 7 | **10 of 11** | 2.008 missed; 1.997 passed |
| 11 | 0 of 6 | 4 of 9 | 1.988 |
| 12 | 0 of 1 | 0 of 2 | — |

So **ten** is the confirmed width, and it is the candidate's: `origin/main` clears ten in four rounds of seven, which is a coin toss rather than a confirmation. Nine is the width neither source ever missed. Eleven is refused: the candidate takes it in four rounds of nine and `origin/main` in none of six, which is a rung to retry rather than a result.

**The earlier re-derivation of this backend's floor used a denominator `origin/main` had already beaten.** The retained original serial controls of this evaluation are commit `3e0e6ed`, which ran one CLI process per turn: cold complete-turn p50 1.504 s and warm 1.538 s. Commit `48d1559` holds that process open, and a fresh serial control on it is cold 0.75–0.89 s and warm 0.27–0.37 s — 2× and 4.6× faster. Against the older control this backend clears the floor at sixteen sessions; against a fresh one, sixteen is **3.26× cold p50** and nowhere near it. The same correction applies to Qwen, whose driver changed in the same commit, and to nothing else: every other backend's original controls are unchanged.

**What sets the width is the official binary starting, not the adapter.** A cold-and-warm task pair costs about 0.8 CPU seconds, and the rungs saturate their four cores exactly. Of that pair, the Antigravity executable's own boot is 0.33–0.47 CPU seconds, its credential supervisor is 0.07 to start plus its per-syscall share, and **the hmz driver is 0.014 for the whole pair** — under two per cent. The cold turn is where a boot lands, and it is the gate that binds: time to first provider request rises 0.10 s per added session, which is four cores' worth of exactly that boot. Antigravity is a Go executable with no JavaScript bundle, so there is no compile cache to warm; no launch flag makes it boot for less; and no per-session state accumulates to make it worse — see [the rejected experiments](REJECTED.md). A driver change cannot move a ratio whose numerator it contributes two per cent of, and the measured difference between the two sources here is inside the round-to-round spread of the five-sample serial control: median cold p50 at ten sessions is 1.507 s for `origin/main` and 1.449 s for the candidate, against serial controls of 0.776 s and 0.814 s.

**Eight of the twenty-six rounds are retained as contaminated rather than published.** Six ran in a group that never reached its own 400% quota — peak busy cores 1.35–3.28 where a clean rung of the same shape reads 3.98–4.01 — while `pids.current` in the cgroup stayed at 3 throughout, so nothing foreign was ever *in* the cgroup. Their CPU seconds per rung matched their clean neighbours and their wall times were two to four times longer, which is what a stolen SMT sibling looks like: the sibling thread of a measured core is in a different cgroup and a different cpuset, so the task census cannot see it. Two more ran while the parent cgroup's cpuset was being changed underneath them and their group briefly resolved to 24 cores instead of four; those read flatteringly, which is the more dangerous direction. **Peak `cpu_busy_cores` against the quota is the screen**: a rung that cannot reach 4.00 was not measured on four cores.

Three methodology corrections landed during these rounds and are recorded rather than quietly applied. The group wrapper's occupancy guard tested `[[ -s cgroup.procs ]]`, and `stat` reports size 0 for a kernfs file however many PIDs it lists, so a run could join a group that already held one; it reads the file now. The measurement groups then held only the first thread of each of their four physical cores, leaving the sibling threads to the rest of the machine, which is what starved the six rounds above; every non-measurement process is now pinned onto the siblings of two groups and those two are avoided here. The thirteen rounds taken before those corrections — every round labelled `A`, `B`, `R`, `F` or `G` in [the record](evidence-2026-09-10/agy-speed-floor-summary.json) — are retained and counted, because the screen above clears them: each reached 3.98–4.00 busy cores with three or four processes in its cgroup before every rung. The five taken after them agree with them. The last two candidate rounds ran the exact source that is committed; the other nine ran it without the three fixes a review added afterwards, none of which touch a path this workload takes.

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

Qwen and Antigravity reuse official streaming CLI processes for ordinary turns, resume finite structured-output turns and restart when native settings or skills change. Antigravity also keeps finite slash commands. Usage handling and native structured-result/workspace behavior retain dedicated regression coverage. The Antigravity candidate additionally stops five latent faults from ending a held process or mis-billing a turn: a command is now a whole first word, so a task naming a path keeps the process warm; a provider credential refreshing on its own schedule no longer counts as a changed process input; a native-home flag naming nothing no longer collapses onto the whole Gemini home; a cumulative counter that started again is charged in full rather than clamped to zero; and the workspace pinned with `--add-dir` is the one the CLI finds it at, which for an anchored turn is the mirror. Each has a regression test that fails on the original source. The Linux supervisors remove temporary ctypes pointer cycles without changing the flow API.

Kimi wakes authoritative REST reads from official WebSocket notifications, answers native heartbeats and retains polling recovery. Mock profiling exposed a full receive queue delaying socket disposal by one second after a completed turn. The bounded receive queue stays unchanged; a 100 ms close grace removes approximately 900 ms from that wait. Separate instrumented before/after task probes verified cleanup and exact task proofs; those timings are diagnostic only and excluded from performance gates.

See [fixture reproduction](DETERMINISTIC.md), [the general runner](RUNNING.md) and [rejected process-reuse experiments](REJECTED.md). `uv run pytest` passed 2,245 tests with 77 skips and 40 warnings in 674.79 seconds, including the 58 benchmark tests. `uv run pre-commit run --all-files` also passed. Skips cover opt-in live-agent checks and unavailable Docker/localhost SSH; no live-agent tests were enabled for mock profiling. Native feature and flow contract checks from the earlier evaluation remain separately documented in [the historical report](RESULTS.md). The production flow implementation/API is unchanged.

## Remaining measured costs

The [CPU phase comparison](evidence-2026-09-10/diagnostics/cli-cpu-phases.json) and its [input provenance](evidence-2026-09-10/diagnostics/cli-cpu-phases-provenance.json) cover selected four/eight-session trials. At eight sessions, Qwen, Grok and Pi approach the four-core quota during portions of fixed work. Peak memory in these cases stays well below 16 GiB, with no recorded OOM events. Fixture processing remains a few milliseconds per turn. Shared process-tree samples overlap concurrent turns; they cannot attribute CPU to an individual session or prove which native function is expensive.

Lowering Grok's native worker count reduced threads but did not improve absolute task timing. MiMo's per-workspace database profile also missed the fixed-work gate. Both are retained as [rejected experiments](REJECTED.md), alongside OpenCode/MiMo server-reuse prototypes and the Cursor local persistence investigation. [MiMo's native phase diagnostic](evidence-2026-09-10/diagnostics/mimo-default-n2-native-phases.json) locates most of its two-session increase between tool requests; it does not establish SQLite contention as the cause. [Kimi's cleanup diagnostic](evidence-2026-09-10/diagnostics/kimi-notification-cleanup.json) isolates the adopted close-grace improvement.

These results establish observed concurrency for this fixed workload and the installed versions. They do not prove that no future native-runtime or adapter optimization is possible. Official CLI binaries remain unchanged; unsupported protocol substitutions and changes that regressed measured startup were not adopted.
