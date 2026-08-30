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
| pi | 9 | not measured | not measured | not measured | [Data](evidence-2026-09-10/pi-speed-floor.json) |
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
| pi | Speed floor, candidate, sole occupant of the host: 8×5 P; 8×5 P; 8×5 P; 8×5 P; 9×5 P; 9×5 T; 9×5 P; 9×5 P; 9×5 P; 10×5 T; 10×5 T. Speed floor, unchanged original, same: 8×3 P; 8×5 P; 9×5 T; 9×5 T; 9×5 T. Eighteen further pairings that shared the host with a second pairing are retained in the evidence and excluded here. Under the deleted gates: 2×3 P; 4×3 P; 8×3 T; 6×3 P; 7×5 P |
| qwen | 2×3 P; 4×3 P; 8×3 T; 6×3 P; 7×5 T; 6×5 P |
| zcode | 2×3 P; 4×3 P; 8×3 T; 6×3 T; 5×5 T; 4×5 P |
| grok / rejected optional native worker pool size 2 | 6×3 T |
| mimo / rejected optional per workspace native database | 2×3 T |
| opencode / optional per workspace native database | 4×3 T; 3×3 T; 2×5 P |

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

## Pi at the 0.5× speed floor

Pi's row above is measured against a different requirement from the rest of this report: a run is acceptable while it is still at least half the speed it has with no concurrency, which is complete-task `result_seconds` p50 and p95 within 2.0× of the serial control, cold and warm. The startup and fixed-work gates are not measured for Pi and its cells say so. Every other validity check is unchanged: all items correct, changed source with untouched fixture inputs and checker, a fresh execution proof per turn, the second turn recalling a conversation-only marker, exactly one result, and no surviving process. Every item of every trial below was correct and no rung left a process behind.

**Nine concurrent sessions.** Five five-repeat pairings against five fresh `origin/main` serial controls, each pairing taken adjacently inside one exclusive four-core measurement group with no other pairing on the host: four pass at 1.646, 1.669, 1.847 and 1.814, and one misses at 2.038. Eight passes all four of its pairings, worst 1.881. Ten misses both of its, 2.162 and 2.164. Unchanged `origin/main` passes both of its eight-session pairings, worst 1.985, and misses all three of its nine-session ones at 2.134, 2.024 and 2.472. So the requirement's change takes Pi from the seven confirmed under the deleted gates to eight, and the adapter change adds the ninth. Every pairing is in [the retained record](evidence-2026-09-10/pi-speed-floor.json), passing or not.

The serial control is the noisy term: its cold p50 ranged 0.62 s to 0.89 s across batches, a spread wider than the distance between rungs, which is why a single pairing decides so little and why one nine-session pairing misses. Pooling all 78 correct control turns from those sole-occupant pairings and every pairing's candidate turns reads them together: candidate 8 at 1.613, candidate 9 at 1.813, candidate 10 at 2.063; unchanged `origin/main` 8 at 1.828 and 9 at 2.086. Both readings put the unchanged adapter at eight and this one at nine.

Two conditions are recorded rather than hidden. Every figure here was taken after the measurement groups' occupancy guard was corrected; readings from earlier in this investigation shared CPUs with other work and are discarded rather than published. And eighteen further pairings ran while a second pairing of this investigation held another group: the cpusets are exclusive so no core is shared, but memory bandwidth is, and the concurrent side of a pairing feels that more than its one-session control does. Those pairings are retained in the evidence and excluded from the counts and the pooled estimate above; read alone they would have put Pi a rung lower.

**What the rung costs is the process start.** At one session a cold turn is 0.77 s of which 0.47 s precedes the first provider request, and a warm turn is 0.27 s; the warm turn barely degrades at the rung, because the process is already there. All four cores are saturated from the moment the sessions start until the last result, so the ceiling is CPU per item and nothing else. A profile of one Pi start puts about a quarter of its main-thread time in `compileSourceTextModule`: V8 compiling the CLI's own bundle, which is the same bundle every session compiles again. Pointing Node's own `NODE_COMPILE_CACHE` at a directory under humanize's home removes 76 ms of that per start, 338 ms of main-thread time down to 258 ms. Measured alone that is 4% of one item's CPU; at nine concurrent sessions, where the compiling contends for the same four cores, the rung's cost falls from 0.91 CPU-seconds per item to 0.80. The cache is Node's, keyed on the file and on the runtime reading it, so an upgraded Pi or Node compiles once more; a cache the provider or the environment already names is left alone, and an anchored turn is given none, its path naming a directory on the wrong machine.

**The largest remaining cost is not Pi's.** One whole item costs 0.77 CPU-seconds run directly and 1.00 under the credential supervisor a provider's turn is wrapped in — 23% of the item. Its shape is specific: Pi checks whether its auth store has changed before nearly every credential it resolves, 614 `statx` of `~/.pi/agent/auth.json` for a built-in model and 823 with the fixture's extension provider, which is more than half of every path syscall a Pi start makes and lands on exactly the path a provider rewrites. That is a measurement for whoever owns the supervisor; it is not addressable from the adapter.

**The 143-second warm turn does not reproduce on this fixture**, which returns no transient errors — but its mechanism is identified. Pi retries transient failures itself, three attempts on a doubling delay, reporting `auto_retry_start` and `auto_retry_end` and saying nothing else in between. Against a loopback endpoint that answers only HTTP 429, one turn takes 16.4 seconds of which 14 are Pi waiting, and the driver reports the final 429 correctly once Pi gives up — `origin/main` and the candidate behave identically, so no change was made for it. With a real endpoint's round trips and `Retry-After` delays this is the shape of an unexplained multi-minute turn, and it matches the `fresh` batch's explicit 429 failures. What a flow cannot see is the waiting itself: humanize's event vocabulary has no word for a backend pausing, so a retrying turn is silent until it lands or fails.

Considered and rejected for Pi: the package's own `./rpc-entry` export, which imports exactly the same chunks as the `pi` command and saves nothing; `PI_OFFLINE` and `PI_SKIP_VERSION_CHECK`, which change no measured cost and no syscall — a Pi RPC turn makes exactly one outbound connection, to the configured endpoint; disabling theme, prompt-template, skill and context-file discovery, worth about 6% of path syscalls and no measurable CPU, at the price of features a user configured; `NODE_OPTIONS` V8 tuning, which every process the agent then spawns would inherit; pre-warming processes before a session names its workspace, which Pi's RPC mode cannot use because a session's directory is fixed at start; and hosting several sessions in one process through the package's SDK, which is a different program from the installed CLI.
