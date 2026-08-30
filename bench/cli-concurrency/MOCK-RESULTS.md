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
| kimi | 2 | 1.573 | 0.317 | Fail | **4** | [Data](evidence-2026-09-10/kimi-fixed-state/ladders.json) |
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
| kimi / speed floor | 7×5 P; 8×5 P (drifting state) |
| kimi / speed floor, fixed state | 2×5 P; 3×5 P ×2; 4×5 P ×5; 5×5 T ×4 and P ×1; 6×5 T ×2; 8×5 T ×2 |
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
| kimi | 4 | 1.827 | — | — | 200/200 |
| mimo | 8 | 1.932 | 1.730 | 3.117 | 80/80 |
| opencode | 6 | 1.860 | 2.146 | 2.023 | 60/60 |

The startup and fixed-work columns are those same rungs under the old gates, kept so the two can be read against each other: every one of these rungs fails the old fixed-work tolerance, and every one of them runs at better than half serial speed. That is the whole of the difference between one to three sessions and six to twelve. Nothing in these CLIs became faster. Exact per-phase distributions, denominators and settings are in [the retained evidence](evidence-2026-09-10/speed-floor-five-backends-summary.json).

Three of the five are boundaries: the width above was tried at five repetitions and missed — claude 8 (2.055) and 10 (2.368), dsh 16 (2.224), kimi 5 (2.785, 2.222, 2.127, 2.080, and one draw at 1.907). **Mimo and opencode are confirmed widths rather than boundaries.** Each cleared the top of its ladder and the width above was never tried: the run that would have tried mimo 9 and opencode 7 was stopped mid-flight when this unit was asked to hand over. Their real ceilings are higher than what is written down.

**Kimi's row moved down, and it moved down because the baseline it was measured against was not standing still.** Its 8 was five candidate repetitions against five serial controls whose cold turn was fifty-six seconds of `kimi web` boot and one second of work; every session of a rung waits on the same boot, so that dilution is most of what made 1.824 out of it. Re-run with a pristine kimi state directory before every repeat — the same daemon boot on both sides, and a boot of a second and a half rather than a minute — kimi's own numbers say **4**, at a worst of 1.827 across five ladders that ran it, and five sessions is the boundary: 2.785, 2.222, 1.907, 2.127, 2.080, one reading below the line out of five, which is a draw rather than a confirmation. Nothing about the CLI changed between the two readings and neither figure is wrong: they are answers to different questions, and the one with a controlled baseline is the one that says what concurrency costs. Its startup and fixed-work columns are left empty because those gates were derived against the drifting baseline and were not re-derived here. Kimi's row is also the only one in this table not taken in `u16`: its ladders ran in whichever `hmzbench` group was free, after the wrapper's occupancy guard was fixed — `cgroup.procs` is a kernfs file that `stat`s as empty however many PIDs it lists, so the guard had been letting two units share one quad. `hmzbench-status` and the state's size and file count are recorded beside every rung. [Seven ladders, twenty-four rungs, 440 task pairs and 880 turns, every one of them correct, with no cleanup survivor and no watchdog kill](evidence-2026-09-10/kimi-fixed-state/ladders.json).

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

**kimi** shares one `kimi web` daemon across every session of its agent, and that daemon was the whole of its cold cost: a serial cold turn was almost a minute of daemon boot and about a second of work, and because every session of a rung waits on the same boot, kimi's cold ratio stayed between 1.16 and 1.45 at every width from two to eight while only its warm turns really moved. That boot is the one number here that did not hold still — 17.7, 28.1, 38.4, 43.1, 55.1 seconds across five trials, and 16 to 127 seconds across everything measured since, while the CLI's own home grew past 440 MB and 5,200 files.

**The cause is now established.** `~/.kimi-code/cache/query-store` is an append-only write-ahead log across sixteen shards, and `kimi web` replays the whole of it on every start: decode each CRC-checked record, insert it into a skip list, rebuild the secondary indexes. A CPU profile of one 32-second boot spends 20 of its 33 sampled seconds in exactly those four functions. The log had reached 183 MB and grows by roughly a megabyte and a half per session created. It is not truncated by a clean shutdown, and the shutdown is clean: SIGTERM was answered in 1.1 to 3.0 seconds every time, well inside the driver's five-second grace. **Bundle compilation is 0.28 s of that 33-second boot**, so `NODE_COMPILE_CACHE` is not worth setting for kimi — and cannot become worth setting at width, because kimi compiles its bundle once per agent rather than once per session. [The decomposition](evidence-2026-09-10/kimi-fixed-state/daemon-boot.json), six conditions and a profile.

Nothing in the driver can fix that, and nothing in the driver may try: the store is the CLI's own and humanize does not prune, redirect or disable what a CLI keeps. The one lever is how many of those boots there are, and the driver already takes it — one daemon per agent, started only when a turn first needs one, shared by every session. A server per session would multiply a 16-to-127-second boot by N. What the measurement can do is hold the state still, and [kimi's fixed-state ladders](evidence-2026-09-10/kimi-fixed-state/ladders.json) do: a pristine kimi state directory before every repeat, which puts the boot at 1.46 s on both sides and leaves the ratio measuring concurrency instead of history. Those ladders were taken after the `hmzbench-run` occupancy guard was fixed, in whichever group was free, with `hmzbench-status` and the state's size and file count recorded beside every rung.

**opencode** and **mimo** run a fresh CLI process for every turn, and it is 2.4 to 3.8 seconds of native startup each time — three to five times what either of them then spends doing the work. That is the largest fixed cost in this matrix and it is paid per turn rather than once per session. It is also, notably, *not* what caps them: both reach six and eight sessions anyway, because a cost every session pays alike divides out of the ratio. The [rejected server-reuse prototypes](REJECTED.md) remain the record of what was tried.

### opencode's shared database, and why the driver leaves it alone

The `database is locked` failure [DETERMINISTIC.md](DETERMINISTIC.md) records was reproduced here: one item of a five-session exploratory trial failed with `Unexpected error database is locked` after 0.99 s, before any provider request and before the session had an id. It is the only failed item in **297** opencode items this unit ran, across one, two, four, five, six, seven and eight sessions — and a later fifty-item trial at that same five sessions had no failure at all. So it is probabilistic rather than a ceiling. Nothing below five concurrent cold starts produced it, and nothing about the width above five made it more likely.

humanize does not set `OPENCODE_DB` itself, and the reason is not performance. That database is where opencode keeps the **conversation**, not a credential, and `backends.py` says what a turn under a provider may move: "the sessions, the settings and the skills are the same ones the CLI already has." A per-workspace database would put every conversation humanize opened somewhere the user's own `opencode` cannot find it, and would charge a fresh database initialization to the first turn in every new directory — for a failure that appears above four concurrent cold starts. The measurement does not argue for it either: the [optional per-workspace profile](evidence-2026-09-10/selected-stage3-summary.json) is not faster than the default. It stays what it is, a benchmark configuration and an operator's lever, and `setup_opencode_database.py` remains the way to apply it.

No retry was added either, for the reason [REJECTED.md](REJECTED.md) already records against the same failure.

### The driver changes these trials justify

Kimi's reader took four authoritative REST readings — pending questions, session status, session spending, session messages — on every notification the daemon woke it with. One daemon serves every session of its agent, so at eight sessions that is the shared daemon answering, several times a second, questions it has just said the answer to. The notification stream now says which of those readings is due, and only one of them is worth bringing forward: **a question, because a question is the only thing a turn stops on**. What a turn has spent is a meter and is read a second apart whatever the daemon says. Status and messages are read every round, which is also what paces the round — a version that put status on the second's cadence too was measured and [reverted](REJECTED.md), because the round then had nothing left to wait for and spun on the history instead: 27 history reads per warm rung became 88, and the warm turn at eight sessions went from 0.73 s to 1.03 s. The settings a session runs at are posted once rather than before every turn, since a second turn at the same settings is a session that already has them — except a goal, which is set going rather than held, and so is asked for again every time it is asked for.

At eight sessions the warm phase of a rung now costs the shared daemon 8 pending-question reads instead of 27, 16 spending reads instead of 35, and no profile writes instead of 8. **It is not worth a measurable amount of the complete-turn ratio, and it is reported as such**: with the reads and without them, against its own five fresh serial controls each time, four sessions read 1.744 and 1.827, six read 2.441 and 2.406, eight read 3.131 and 3.037. Two to three per cent in one direction at two widths and the other direction at the third is this host's noise, not a result. What it buys is not speed, it is a shared daemon doing less work that nothing was waiting on. Where kimi's warm turn actually goes at eight sessions is measured: 0.63 s of a 0.73 s turn is time blocked on daemon calls, and 2.6 s of that 5.0 s across the rung is the history reads the turn needs to be watchable at all.

Frames the daemon streams a chunk at a time — a running command's output, a tool call's arguments — are coalesced into at most one reading per second rather than woken for one by one. A first version of this change woke for each of them instead, which on a shell-heavy turn would have cost more than it saved. It was found in review after its own five-repeat trial had already run; that trial is retained beside the others as `kimi-superseded-candidate-n7-contended-cpuset`, and the reported candidate is the coalescing one.

Two correctness bugs in the same machinery were found by review and fixed here. Both predate the commit they were attributed to: the pending filter arrives in the commit before it, and the early return out of a settled wait was already there too. A turn could return an **empty answer**: `wait(settled=True)` returned on the first frame the daemon sent, so a session read as not busy in the window between the prompt landing and the turn starting was read back before it had said anything. The grace is restored — only `turn.ended` cuts it short now, because only `turn.ended` says the words are written down — and a turn ends on two consecutive readings of a session that has stopped, not one, and not before something of the turn has been seen — the session working, the daemon saying it ended, or a word of it written down — since the daemon takes a prompt before it runs it. And the pending-question read is spelled `?status=pending` because this daemon's querystring schema is `object({ status: literal("pending") })` and it refuses the bare path; a daemon that has never had that filter refuses the other, so both are asked, and whichever answered is kept only where the refusal carried a status of its own, since a dropped connection says nothing about a querystring and a session moved onto the unfiltered list by one hiccup would put an answered question again every second. One refusal is carried on from; a daemon that has refused for a whole recovery interval is a failed turn rather than a turn that polls a permanently busy session forever. Four tests pin them, each failing on the code before it: three answer with nothing where the turn's own words should be, and one hangs until pytest is killed, which is the turn polling a permanently busy session forever. Neither fix costs anything measurable: the grace is free whenever the daemon says `turn.ended`, and a serial warm turn is a quarter of a second — less than the grace itself, which is the evidence that it is not being paid.

**What none of this established.** On the superseded contended cpuset, three five-repeat trials at seven sessions sat side by side: the original misses the floor at 2.088, the superseded candidate passes at 1.966 and the shipped candidate passes at 1.556, each against its own five fresh serial controls. Read as a progression that is exactly wrong, because the serial controls underneath them are not the same: their cold p50 is 18.4 s, 29.0 s and 39.5 s, and their warm p50 is 0.752 s, 0.881 s and 1.093 s. In absolute seconds the seven-session warm p50 barely moved — 1.570 s, 1.717 s, 1.604 s — while every denominator grew. **No timing improvement is claimed for this change.** What is measured is the call count: 79 daemon calls per cold/warm task pair before, 43 after. What the trials show is that the change cost nothing, and that eight sessions clears the floor **against a serial control whose cold turn is fifty-six seconds of daemon boot** — the shipped candidate's own eight-session confirmation in the isolated group is 1.824, with 80 of 80 turns correct. Held against a fixed kimi state that reading does not survive: at eight sessions it is 3.037, and the width kimi holds is 4. Both readings are in [the retained evidence](evidence-2026-09-10/kimi-fixed-state/ladders.json); the difference between them is the baseline, not the CLI.

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

See [fixture reproduction](DETERMINISTIC.md), [the general runner](RUNNING.md) and [rejected process-reuse experiments](REJECTED.md). `uv run pytest` passed 2,248 tests with 77 skips and 41 warnings in 721.78 seconds, including the 58 benchmark tests. `uv run pre-commit run --all-files` also passed. Skips cover opt-in live-agent checks and unavailable Docker/localhost SSH; no live-agent tests were enabled for mock profiling. Native feature and flow contract checks from the earlier evaluation remain separately documented in [the historical report](RESULTS.md). The production flow implementation/API is unchanged.

## Remaining measured costs

The [CPU phase comparison](evidence-2026-09-10/diagnostics/cli-cpu-phases.json) and its [input provenance](evidence-2026-09-10/diagnostics/cli-cpu-phases-provenance.json) cover selected four/eight-session trials. At eight sessions, Qwen, Grok and Pi approach the four-core quota during portions of fixed work. Peak memory in these cases stays well below 16 GiB, with no recorded OOM events. Fixture processing remains a few milliseconds per turn. Shared process-tree samples overlap concurrent turns; they cannot attribute CPU to an individual session or prove which native function is expensive.

Lowering Grok's native worker count reduced threads but did not improve absolute task timing. MiMo's per-workspace database profile also missed the fixed-work gate. Both are retained as [rejected experiments](REJECTED.md), alongside OpenCode/MiMo server-reuse prototypes and the Cursor local persistence investigation. [MiMo's native phase diagnostic](evidence-2026-09-10/diagnostics/mimo-default-n2-native-phases.json) locates most of its two-session increase between tool requests; it does not establish SQLite contention as the cause. [Kimi's cleanup diagnostic](evidence-2026-09-10/diagnostics/kimi-notification-cleanup.json) isolates the adopted close-grace improvement.

These results establish observed concurrency for this fixed workload and the installed versions. They do not prove that no future native-runtime or adapter optimization is possible. Official CLI binaries remain unchanged; unsupported protocol substitutions and changes that regressed measured startup were not adopted.
