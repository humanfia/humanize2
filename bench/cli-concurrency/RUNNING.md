# Official CLI concurrency benchmark

This harness drives every backend in `hmz.backends.PROFILES` through its normal hmz driver
and the externally installed CLI or official SDK. For CLI performance profiling, use the
[deterministic loopback fixture](DETERMINISTIC.md) with dummy credentials to exclude model
latency and remote rate limits. The same runner can use real endpoints for separate model
integration checks. It does not patch installed CLIs or automatically download a missing
CLI. No real credentials belong in benchmark JSON files.
`--list` reports all supported backends, resolved executables and their SHA256 hashes.
For SDK backends, an absent executable does not by itself mean the backend is unavailable.

The [2026-09-10 mock evaluation](MOCK-RESULTS.md) records confirmed concurrency, all
trial outcomes and fixture evidence. The [2026-09-09 real-provider evaluation](RESULTS.md)
retains its historical timing data and provider/access gaps separately.

## Run

Install the repository development environment with `uv sync` and the official CLIs to be
measured. The fixture setup supplies isolated dummy providers for profiling. For a separate
real-endpoint check, authenticate the CLIs and create a model configuration outside the
repository:

```json
{
  "codex": {"model": "your-codex-model", "effort": "low"},
  "claude": {"model": "your-claude-model", "provider": "your-hmz-provider", "effort": "low"}
}
```

Every registered backend is selected by default. Supply its actual model in the config;
missing configurations are recorded as unavailable and make the run fail. `--backends`
selects a subset for investigation. `--model` and `--provider` supply optional defaults.
Omitting `provider` uses the CLI's existing login and environment. Prefer explicitly pinned
model IDs and explicit efforts; the fallback effort is the backend's lowest registered rung.
The config can also contain other fields of that backend's existing hmz agent configuration.
Model requests incur the account's normal usage charges.

Choose four CPUs actually allowed by the host, then run in a dedicated cgroup v2 scope:

```bash
systemd-run --user --scope \
  -p CPUQuota=400% -p AllowedCPUs=0-3 \
  -p MemoryMax=16G -p MemorySwapMax=0 \
  taskset -c 0-3 uv run python bench/cli-concurrency/run.py \
  --config /tmp/cli-models.json --concurrency 1,2,4,8 \
  --repeats 3 --output /tmp/cli-baseline
```

The strict check is on by default. It records every ancestor's cgroup limits, verifies the
effective CPU quota equals four, checks affinity contains exactly four logical CPUs, and
requires 16 GiB memory with zero swap. Replace `0-3` if those CPUs are unavailable. A quota
alone is insufficient: many CLI runtimes size thread pools from the available CPUs.
`--allow-unconstrained` is for functional diagnostics only and records invalid sizing limits.

All rungs run serially. Each rung uses one fresh Python worker with N concurrent sessions
and a fresh workspace per session. `--instances shared` (the default) opens all sessions on
one agent; `--instances separate` constructs one agent per session in that same worker.
Both preserve the CLI's existing transport and process lifetime. Cold means a newly opened
session/agent, with the OS page cache retained. Warm means a second turn of that session.

Each turn independently reads three task files, fixes a function, and executes a Python
checker that produces a fresh execution artifact. Cold and warm tasks have identical input
sizes and algorithms. The harness verifies changed source, untouched fixture and checker,
correct proof, tool events, and exactly one result. Turn two must also recall a random
marker given only in the preceding conversation. An item counts as successful only when
both turns pass. This is a coding workload benchmark, not a complete backend feature test.

`--timeout` bounds both turns of each item (240 seconds by default). Timed-out sessions
receive `close()`, and `--grace` bounds waiting for cancellation. A parent watchdog bounds
worker failures. The supervisor adopts orphaned CLI descendants, tracks PID creation times,
and terminates every process belonging to the rung, including detached CLI servers. Worker
completion deliberately holds the worker alive until the parent has sampled its remaining
children. Cleanup survivors make the run fail; artifacts are retained for diagnosis.

An explicit HTTP/status 429 or rate-limit error in an item stops the run after that rung
finishes and cleanup completes. No later repeat, concurrency level or backend is dispatched,
and the harness does not retry the prompt. The completed rung, turn and item evidence stays
intact. Its aggregate records the actual `repeats`, `requested_repeats`, whether it is
`partial`, and `stopped_reason: "provider_rate_limit"`; the process exits with failure.
A bare task number or memory marker containing `429` does not trigger this stop.
The stop guard can only classify errors exposed in item records. A native CLI may hide
HTTP 429 behind a generic exit error and retain the status only in its private log; inspect
those logs after an unexplained failure before starting another provider trial.

## Evidence and comparison

`results.jsonl` contains invocation metadata, per-rung summaries and repeated aggregates.
Each rung directory contains the exact nonsecret settings, complete task workspaces,
`items.jsonl` with turn and item results, event transcripts, resource samples and worker logs.
Keep these directories private: they contain ordinary CLI transcripts and model outputs.
CLI identity hashes and the repository commit are recorded; retain the matching lockfile
and official package versions with a published report. Executable hashes identify launchers;
they do not prove the provenance of every file in an installed CLI package.

Resource measurements include process RSS sums, process/thread/FD peaks, sampled charged
cgroup memory, cgroup task count, cumulative CPU seconds and sampled CPU utilization in
cores. RSS sums can double-count shared pages; cgroup memory is the enforced memory measure.
`memory.peak` in raw cgroup counters is the scope lifetime peak, while `resources_peak` is
sampled separately for each rung. Peaks shorter than `--sample-every` (default 0.2 seconds)
can be missed. Cgroup counters include benchmark overhead and kernel page cache. Use an
otherwise idle dedicated scope, and never run another benchmark alongside this one.
Each resource sample also records its monotonic timestamp and `process_records`: PID,
executable name and process creation time. Compare PID plus creation time across cold and
warm turns to establish process reuse; names alone cannot establish identity. The sampler
reuses its existing process scan and never records command lines or environment variables.
Cleanup revision `pidfd-portable-wait-v2` falls back to bounded `waitpid`/process-status
polling if a kernel rejects psutil's pidfd wait. Each rung records the fallback count and
any surviving PIDs. Permission-denied process status remains potentially live.

Latency distributions count only fully correct task pairs, while failed items remain an
explicit count. Nearest-rank p95 retains the slowest observation in small samples. Record:

- `first_event_seconds`: elapsed time to the first hmz event, including network/model delay.
- `first_tool_seconds`: elapsed time to the first tool event.
- `result_seconds`: elapsed time to the result.
- `work_seconds`: elapsed time from the first tool event to the end of the stream.
- `output_tokens_per_second`: reported output tokens divided by the complete turn duration;
  absent when the CLI does not report output tokens. Revision `output-key-aliases-v2`
  accepts normalized `Usage["output"]` and the `output_tokens` name retained by Qwen/Grok,
  prefers the normalized field if both exist, and counts a reported zero as zero.
  This is a rate across the full tool-using turn, not model decoding throughput.

First-event latency is **not pure startup latency**. Comparison records explicitly retain
`startup_verified: false`; measure time to the first provider request separately before
claiming the user's startup requirement is met.

A serial rung is the baseline for later rungs of that backend. Default comparison gates
require all items to pass, both p50 and p95 first-event latency at most 2x baseline, and both
p50 and p95 work/result latency at most 1.10x baseline, for both cold and warm turns. The 10%
tolerance is explicit and can be changed with `--work-tolerance`. These are operational
gates, not a statistical significance test. Three repeats are a starting point; repeat more
at the apparent concurrency boundary and inspect provider load, task/tool counts and tails.
The process exit code reports functional/cleanup failure; inspect comparison `passes` for
performance failures. Never promote a rung with failed items or unverified startup.

To compare an optimized revision against the original serial baseline, keep model/provider/
effort settings identical and supply the original journal:

```bash
# Run inside the same dedicated limits as above.
uv run python bench/cli-concurrency/run.py \
  --config /tmp/cli-models.json --concurrency 1,4,8 --repeats 5 \
  --baseline /tmp/cli-baseline/results.jsonl --output /tmp/cli-candidate
```

The harness requires an exact backend/settings match for external baselines. It does not
silently treat a different model or account as the reference. Before changing code, retain
a baseline; after optimization, run the full repository gates and the backend feature tests
in addition to this workload. A successful task pair does not establish hooks, steering,
schema, cancellation, permission or provider isolation behavior on its own.


Recover historical token rates into a separate artifact without changing raw evidence:

```bash
uv run python bench/cli-concurrency/recover_usage.py \
  --run /tmp/cli-baseline/results.jsonl \
  --output /tmp/cli-baseline/usage-corrected.jsonl
```

Analysis revision `retained-usage-rates-v1` includes source-file SHA256 hashes, original
rates, the selected token field and corrected turn/aggregate rates. New measurements save
`turn_seconds` explicitly. Older valid turns reconstruct that same stream duration from
`first_tool_seconds + work_seconds`; they do not substitute the earlier result event.
Missing usage or duration stays absent, and failed task pairs stay out of distributions.
Only completed rungs in the source journal are summarized; orphaned artifacts from an
interrupted rung remain incomplete evidence. The correction command refuses an existing
output path. Preserve historical JSONL files and their hashes.

The credential and coganchor supervisors pass the addresses of locally owned ctypes
buffers directly to synchronous memory and register operations. This avoids temporary
pointer objects that retain their source buffers until cyclic garbage collection; the
syscall filters and credential mappings are unchanged. A diagnostic with installed Qwen
0.23.1, four CPUs, a local canned model response, and three alternating pairs measured
median completion time of 9.59 s before this allocation change and 6.78 s afterward.
All six runs completed successfully. This isolates supervisor overhead; it does not
measure remote model throughput or establish a concurrency limit. Full comparisons
must retain the same credential isolation and official CLI workloads.
