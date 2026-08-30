# Mock CLI performance evaluation — 2026-09-10

All twelve built-in CLI backends use immediate loopback model responses and dummy credentials, including Cursor's separately distributed official local runtime. The CLI still reads files, edits code, executes the unchanged checker and resumes its native conversation. No live-model samples enter these performance comparisons. The [September 9 real-provider report](RESULTS.md) remains a separate historical record.

## Confirmed concurrency

Each row passed five candidate repetitions against five fresh original serial controls. The ratio columns show the largest of cold/warm p50/p95 for that metric. All primary startup and fixed-work gates pass; the separate legacy verdict uses different event boundaries.

| CLI / profile | Sessions | Worst startup × | Worst fixed work × | Legacy strict | Evidence |
| --- | ---: | ---: | ---: | --- | --- |
| agy | 9 | 1.648 | 0.468 | Pass | [Data](evidence-2026-09-10/selected-stage6-summary.json) |
| claude | 2 | 0.951 | 0.839 | Pass | [Data](evidence-2026-09-10/selected-stage4-summary.json) |
| codex | 6 | — | — | — | [Data](evidence-2026-09-10/codex-complete-task-floor-summary.json) |
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

Codex's row is the exception and its ratio columns are empty on purpose: it is measured against the [complete-task floor](#codex-under-the-complete-task-floor) — cold and warm p50 and p95 of the whole turn, at most 2× a fresh original serial control — and against nothing else. Its startup and fixed-work columns were not measured for that row and the legacy verdict was not taken.

Exact ratios, original/candidate phase distributions, all repeat denominators and the selected source references are in [the machine-readable result](results-2026-09-10.json). The retained trial sequence follows; `P` is a primary pass, `T` a timing miss, and `E` an execution failure. An entry `6×5 P` means six concurrent sessions and five repetitions. Three-repeat passes remain exploratory.

| CLI / profile | Recorded candidate trials |
| --- | --- |
| agy | 2×3 P; 4×3 P; 8×3 P; 16×3 T; 12×3 T; 10×3 T; 9×5 P |
| claude | 2×3 P; 4×3 T; 3×3 P; 3×5 T; 2×5 P |
| codex | 4×3 P; 5×3 P; 6×3 P; 7×3 P; 8×3 P; 9×3 P; 10×3 T; 7×5 P; 7×5 T; 7×5 T; 7×5 P; 6×5 P; 6×5 P; 6×5 P; 6×5 P; 5×5 P; 5×5 P |
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

## Method

Each backend is measured alone inside a cgroup limited to four CPUs, 16 GiB memory and zero swap, with affinity to physical cores 8–11. The mock server runs on separate CPUs outside that scope; tests and audits use other CPUs. The [retained fixture launch observation](evidence-2026-09-10/diagnostics/fixture-launch-provenance.json) records the planned affinity override and observed separation. This is a shared 64-logical-CPU host with enforced limits, not a dedicated virtual machine. OS page caches remain warm between fresh sessions.

Every pair contains cold and warm turns. Each turn must perform the same three real shell tool calls and four successful workload requests, produce a fresh execution proof and preserve immutable task inputs. The warm answer must recall a conversation-only marker. Missing work, repeated workload requests, provider errors, provenance changes or surviving processes invalidate the case. Auxiliary calls and cancellations remain separately visible. Error coverage is fixture-only: every fixture workload and auxiliary HTTP failure is checked, while native auxiliary log coverage is incomplete. This does not establish that every CLI emitted no native error.

Startup runs from turn submission to the earliest correlated provider request, including auxiliary requests. Fixed-work time runs from that request to the hmz result; it includes native tool execution, adapter delivery and mock transport. Cold/warm p50 and nearest-rank p95 must each satisfy startup ≤2× and fixed work ≤1.10× against fresh original serial controls. The original first-event/post-first-tool harness verdict is retained separately; first-event time is not a startup measurement. Synthetic token counts do not establish model throughput.

Three-repeat ladder trials are exploratory. A chosen passing boundary requires five fresh original serial controls and five candidate groups. The observed passing boundary and failed neighboring trials do not prove a universal maximum: host scheduling and the unequal sample counts of serial and concurrent p95 estimates remain relevant. These trials do not measure mixed-backend concurrency.

## Configuration conditions

Original source is commit `3e0e6edf1d47ae27a70c1a334ee6cf364d05f59b`. Candidate snapshots, native executable hashes, fixture/harness revisions, per-turn distributions and proof checks are retained with the evidence. All configured model routes use literal `127.0.0.1` and complete child environments with dummy keys; no real-provider fallback is configured. Fixed JSON/SSE responses have no intentional delay. Fixture processing time and active handlers are retained to distinguish server contention from CLI overhead.

Cursor uses the unchanged official local distribution `2026.09.08-6caf4ff` with native authless mode and an OpenAI-compatible local endpoint. The original adapter's `fixture-model[fast=false]` and the candidate's `fixture-model` receive the same response policy. This validates the local distribution's coding tools and conversation resume; standard Cursor authentication and service RPC are outside this profile. Native update/command-discovery errors are separate from the configured model route and are retained where observable.

OpenCode's default shared SQLite database failed during the first two-session candidate repetition, before any model request. The controller stopped that case and retained its missing and undispatched work. A separate, optional native `OPENCODE_DB` launcher selects one persistent database per canonical task workspace for both original and candidate. Its interpreter startup and database initialization are included in timing. This condition changes benchmark configuration, not the production driver; it does not replace the failed default trial. The initial three-repeat isolated comparison passed all gates and verified nine distinct databases with cold/warm native conversation continuity; the later five-repeat confirmation also passed.

ZCode uses separate Agent instances. Codex no longer does: its complete-task-floor row is measured with multiple Sessions on one Agent, which is `run.py`'s default and the shape a flow actually runs. Other backends use multiple Sessions on one Agent. Antigravity receives the same explicit workspace argument in original and candidate; its first native formatting-only settings rewrite is retained as a stopped provenance trial and subsequent locks pin the rewritten bytes.

## Codex under the complete-task floor

Codex's row is measured against one requirement: complete-task p50 and p95, cold and warm, at most 2× a fresh original serial control — a run still at least half the speed it has with no concurrency. The startup and fixed-work gates the other rows report were not measured for it. All twelve confirmations below ran after the `hmzbench-run` occupancy guard was corrected, each in whichever measurement group was free and each with that group's four exclusive physical cores rather than the 8–11 the other rows used; every earlier codex figure in this file predates that correction and is superseded. Its original source is `48d1559805cbdb083958bf381a2ff57c183f96ab`, not the commit the other rows compare against, and every control below was run from that snapshot rather than reused. Every turn retained across every codex rung passed each item check: changed source with untouched fixture and checker, a fresh execution proof, the turn-two conversation marker, exactly one result, at least one tool, and no cleanup survivor in any rung.

The driver changed. `codex app-server` runs the turns of separate conversations at the same time, but the driver held its stdio stream for the whole of a turn, so every session of one agent queued behind the one in front. That is why the earlier codex rows were taken with `--instances separate` — one agent, and so one server, per session. Measured with the default `--instances shared`, which is what a flow with one agent and several sessions actually runs, the original driver **confirms at one session**: two sessions is 2.171× at five repetitions, and throughput stays at about one task per second from two sessions to seven. The driver now hands each message read off that stream to whoever it belongs to — the call that asked for it, or the turn of the thread it names — so turns of one server overlap. Codex will not pick a thread up on a second server while the first still holds its rollout open (`thread ... already has an active writer`, retained from the first pooling prototype), so a session keeps the server it was opened on for life and is opened on one no turn is running on; one more server is started, outside the agent's lock, only when every server it has is busy. A thread the server already holds at the rung the turn asks for is no longer picked up again.

| Profile | Source | Sessions | Worst complete-task × | Verdict |
| --- | --- | ---: | ---: | --- |
| shared (`run.py` default) | original | 2 | 2.171 | Fail |
| separate (earlier codex rows) | original | 7 | 1.992 | Pass |
| shared (`run.py` default) | candidate | 7 | 1.684 / 2.132 / 2.213 / 1.846 | Pass, fail, fail, pass |
| shared (`run.py` default) | candidate | 6 | 1.554 / 1.472 / 1.589 / 1.404 | Pass, pass, pass, pass |
| shared (`run.py` default) | candidate | 5 | 1.163 / 1.270 | Pass, pass |

Six is published: four five-repeat confirmations, all passing, none discarded. Seven is not: it passed twice and failed twice, and both failures are retained. The verdict at seven turns on the serial control rather than on the concurrent group — a five-observation nearest-rank p95 is the largest of five, and those five-sample cold controls ranged from 1.09 s to 1.94 s across the day while the concurrent groups pooled 35 turns apiece. The three-repeat ladder taken beside these confirmations passes as far as nine (1.986×) against its own faster control, which is the same variance read from the other side. The published boundary is what these repetitions support, not a maximum.

Where the remaining cold cost is: at eight sessions almost the whole complete-task penalty sits before the first event, which goes from 1.092 s serial to 2.161 s, while the interval from that event to the result goes only from 0.405 s to 0.498 s. Eight app servers booting at once cost 0.535 s against 0.271 s for one, and the credential supervisor's interpreter is 0.027 s of that, so roughly a quarter of the penalty is boots and the rest is eight first model round trips and eight per-conversation setups contending for four cores. Two mechanisms were measured and rejected. Teeing the live `item/agentMessage/delta` to stderr costs nothing detectable: 2.512 s cold p50 at eight sessions without it against 2.459 s with it, both inside the run-to-run spread. And one shared server with the stream demultiplexed but no second server is far worse than a server per busy conversation — 4.87× at eight sessions, 5.31 s cold p50 — because Codex opens and picks up threads one at a time however many turns it is running: four conversations opened at once on one server each waited 1.32 to 1.54 s for `thread/start` and finished staggered, while the four turns that followed overlapped and ended within 32 ms of each other. That is identical with and without the credential supervisor, so the serialization is inside the app server rather than in anything humanize wraps it in.

## Implementation and validation

Qwen and Antigravity reuse official streaming CLI processes for ordinary turns, resume finite structured-output turns and restart when native settings or skills change. Antigravity also keeps finite slash commands. Usage handling and native structured-result/workspace behavior retain dedicated regression coverage. The Linux supervisors remove temporary ctypes pointer cycles without changing the flow API.

Kimi wakes authoritative REST reads from official WebSocket notifications, answers native heartbeats and retains polling recovery. Mock profiling exposed a full receive queue delaying socket disposal by one second after a completed turn. The bounded receive queue stays unchanged; a 100 ms close grace removes approximately 900 ms from that wait. Separate instrumented before/after task probes verified cleanup and exact task proofs; those timings are diagnostic only and excluded from performance gates.

See [fixture reproduction](DETERMINISTIC.md), [the general runner](RUNNING.md) and [rejected process-reuse experiments](REJECTED.md). `uv run pytest` passed 2,239 tests with 77 skips and 41 warnings in 716.87 seconds, including the 58 benchmark tests. `uv run pre-commit run --all-files` also passed. Skips cover opt-in live-agent checks and unavailable Docker/localhost SSH; no live-agent tests were enabled for mock profiling. Native feature and flow contract checks from the earlier evaluation remain separately documented in [the historical report](RESULTS.md). The production flow implementation/API is unchanged.

## Remaining measured costs

The [CPU phase comparison](evidence-2026-09-10/diagnostics/cli-cpu-phases.json) and its [input provenance](evidence-2026-09-10/diagnostics/cli-cpu-phases-provenance.json) cover selected four/eight-session trials. At eight sessions, Qwen, Grok and Pi approach the four-core quota during portions of fixed work. Peak memory in these cases stays well below 16 GiB, with no recorded OOM events. Fixture processing remains a few milliseconds per turn. Shared process-tree samples overlap concurrent turns; they cannot attribute CPU to an individual session or prove which native function is expensive.

Lowering Grok's native worker count reduced threads but did not improve absolute task timing. MiMo's per-workspace database profile also missed the fixed-work gate. Both are retained as [rejected experiments](REJECTED.md), alongside OpenCode/MiMo server-reuse prototypes and the Cursor local persistence investigation. [MiMo's native phase diagnostic](evidence-2026-09-10/diagnostics/mimo-default-n2-native-phases.json) locates most of its two-session increase between tool requests; it does not establish SQLite contention as the cause. [Kimi's cleanup diagnostic](evidence-2026-09-10/diagnostics/kimi-notification-cleanup.json) isolates the adopted close-grace improvement.

These results establish observed concurrency for this fixed workload and the installed versions. They do not prove that no future native-runtime or adapter optimization is possible. Official CLI binaries remain unchanged; unsupported protocol substitutions and changes that regressed measured startup were not adopted.
