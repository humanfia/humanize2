# Deterministic model fixture

The fixture measures time until the CLI makes its first provider request and the overhead of
executing a fixed tool sequence. Its responses are synthetic. It does not establish real
model throughput, remote-provider limits, reasoning quality or authentication behavior.
Use this fixture for adapter performance profiling with official CLI logic, tools and context
handling intact. Real endpoints described in [RUNNING.md](RUNNING.md) are optional, separate
integration verification; they are not required for these deterministic measurements.

The [twelve-backend mock evaluation](MOCK-RESULTS.md) records the measured configuration
conditions, concurrency confirmations, and retained failures.

Start the server outside the constrained benchmark scope:

```bash
uv run python bench/cli-concurrency/fixture_server.py \
  --port 18999 --log /tmp/fixture-requests.jsonl
```

It binds only `127.0.0.1`. The fixture accepts Anthropic Messages, OpenAI Responses and OpenAI
Chat Completions, plus Gemini `generateContent`/`streamGenerateContent`, in JSON and SSE. It also provides model-list, token-count, models.dev
registry and synthetic API-key-metadata routes. `--models` changes the comma-separated
advertised IDs. Responses continuation IDs retain the current task context in a bounded
4,096-entry cache. gzip and deflate requests are accepted. If a CLI sends zstd requests,
start with `uv run --with zstandard python ...` to supply that optional decoder.
The startup journal records the Python version and SHA256 of every fixture source file,
so a running server can be distinguished from later edits on disk. Restart after changing
fixture code and keep the same fixture revision for baseline and candidate measurements.
No authorization headers or full request bodies are logged. Request diagnostics retain only
message roles, task positions, explicit tool policy, token limits and fixed instruction-hint
matches. These help distinguish metadata traffic without retaining private prompt text.

The fixture can also answer every model request with a deliberate provider fault, so an
adapter's error handling can be exercised against the real CLI's own error path rather than a
mock of one. `--fault none|throttled|refused|retired|dropped` arms one at startup, and
`POST /fixture/fault {"fault": "..."}` arms one on a running fixture, so a single revision
walks the whole taxonomy without a restart changing the model map, the provider or anything
else under measurement. `throttled` answers HTTP 429 with `Retry-After: 1`, `refused` 401 and
`retired` 404, each in the envelope the protocol being spoken actually uses -- Anthropic's
`{"type":"error",...}`, Gemini's `RESOURCE_EXHAUSTED`/`UNAUTHENTICATED`/`NOT_FOUND`, OpenAI's
`{"error":{"type":...}}` -- and `dropped` sets `SO_LINGER` to zero and closes, so the CLI sees
a real RST rather than a clean shutdown. Faults are recorded in the request journal and are
never part of a measurement sample: a run with one armed is an error-path check, not a
throughput one.

Create isolated providers using only dummy keys; this step runs no agent CLI or model call:

```bash
uv run python bench/cli-concurrency/setup_fixture.py \
  --endpoint http://127.0.0.1:18999 --directory /tmp/cli-fixture-config
```

Setup uses `hmz.providers.add` and registered ways, writes its own `HUMANIZE_HOME` beneath
`/tmp`, and prints the model map and launch arguments. It refuses a non-loopback endpoint,
a non-temporary directory or an existing setup. Native user configuration is never edited.
The ten generated configurations are **unvalidated until their actual workloads pass**:

| Backend | Fixture routing |
| --- | --- |
| Antigravity | Built-in key way, Gemini API base URL and isolated official `--app_data_dir` |
| Claude | Built-in gateway, Anthropic base URL and dummy bearer token |
| Codex | Built-in gateway settings, `wire_api=responses` |
| Dsh | Required built-in `key` way, with an explicit `DEEPSEEK_BASE_URL` in that provider |
| Grok | Built-in xAI gateway |
| Kimi | Built-in model environment, upstream `fixture-model`, hmz alias `__kimi_env_model__` |
| Qwen | Built-in key way and explicit OpenAI-compatible base URL |
| Pi | Temporary documented `registerProvider` extension, passed through provider CLI args |
| OpenCode | Provider `OPENCODE_CONFIG_CONTENT` defining `@ai-sdk/openai-compatible` |
| MiMo | Provider `MIMOCODE_CONFIG_CONTENT` defining the same compatible model transport |

Dsh intentionally uses its `key` way: its driver rejects other authentication ways. The
base URL is stored explicitly beside that fake key so ambient-variable isolation retains
it. Pi's temporary extension registers a model using the official extension API; no
installed CLI code or native `models.json` is changed. Its extension file stays in `/tmp`.
OpenCode and MiMo may resolve their declared SDK package using their own package machinery.
Retain the resolved package versions and executable/source hashes with measurements.

OpenCode's default native SQLite database is shared across workspaces. Concurrent native
processes can fail with `database is locked` before any provider request; retain that default
configuration failure separately. For an **optional benchmark configuration**, OpenCode's
native `OPENCODE_DB` setting can select one persistent database per task workspace:

```bash
uv run python bench/cli-concurrency/setup_opencode_database.py \
  --directory /tmp/opencode-workspace-databases \
  --official /path/to/official/opencode
```

Prepend the emitted `bin` directory to the existing fixture `PATH` for both original and
candidate. Keep their provider, model map, native configuration and skills identical. The
temporary launcher derives an absolute SQLite filename from the canonical `--dir` or cwd,
sets only `OPENCODE_DB`, then executes the unchanged official binary with its original
arguments and standard streams. Cold and warm turns share that database; `:memory:` would
lose the session between finite CLI processes. Setup makes no native or model calls and
records launcher, interpreter and official-executable hashes.

Use fresh original serial controls with this same launcher. Its interpreter startup and
new-workspace database initialization remain inside measured startup. Results describe this
optional isolation profile and do not repair or replace the default shared-database trial.
Retain each database and its `-wal`/`-shm` companions with the workspace proofs when auditing
native conversation resume. This option does not change the production driver or general
fixture setup; it requires an official version that supports `OPENCODE_DB`.

Antigravity requires both `modelProvider: "gemini"` in settings and `GEMINI_API_KEY`.
Setup uses its official hidden `--app_data_dir` flag, which accepts a path relative to
`~/.gemini`, to place those synthetic settings, conversations and runtime data under `/tmp`.
`GOOGLE_GEMINI_BASE_URL` routes the key provider to this fixture. No launcher, official-binary
modification or native settings edit is needed. Gemini function responses are matched to
preceding calls; harmless command comments retain step identity if the CLI rewrites call IDs.
The official CLI also needs `--add-dir` with the absolute task workspace; its native default
project can otherwise run commands in its scratch directory despite the process working
directory. Use `run.py --agy-add-dir` for both original and candidate AgY measurements.
This explicit benchmark compatibility option adds the same per-session native argument
without changing the original source or shared provider. A candidate that already supplies
the argument receives no duplicate. Metadata and item records retain the option and path. Fixture revision `gemini-user-envelope-v4` recognizes the exact leading, closed
`<USER_REQUEST>` envelope emitted by the official Gemini transport. Quoted or incomplete
envelopes cannot start a task. Earlier `gemini-and-auxiliary-v3` Antigravity samples that
completed without tools are invalid and must be repeated; the other protocol planners are
unchanged. A successful text response alone never validates this fixture.

Cursor's standard endpoint targets Cursor service RPC, which this model fixture does not
implement. To include its separate official local distribution, supply its existing launcher
explicitly; setup checks the adjacent local-runtime package identity and executable:

```bash
uv run python bench/cli-concurrency/setup_fixture.py \
  --endpoint http://127.0.0.1:18999 --directory /tmp/cli-fixture-with-cursor \
  --cursor-local-official /path/to/official/cursor-agent-local
```

This adds an eleventh provider and a temporary `bin/cursor-agent` symlink. Use the emitted
`PATH` and `HUMANIZE_HOME` together. The provider selects native authless mode, one localhost
OpenAI-compatible endpoint, a dummy key and an isolated `CURSOR_CONFIG_DIR`; the installed
launcher and user settings are untouched. It runs `fixture-model` with no effort suffix.
The metadata records the launcher and package hashes. Package identity is not a download
signature; obtain the distribution from its official source and retain its provenance.

Keep original and candidate model spellings visible. An older adapter may send
`fixture-model[fast=false]` while the local-aware adapter sends `fixture-model`; the fixture
accepts both unchanged under the same response policy. No model-name rewrite or native shim
is needed. This validates the official local runtime, not standard Cursor authentication or
its service RPC. Its native debug sidecars are in the OS temporary directory under
`cursor-agent-logs-<uid>/session-<timestamp>-<pid>-<counter>.log`; retain the owned PID files
before pruning and avoid `latest.log` under concurrency. Native update or feedback traffic
is separate from the configured localhost model route.

Without `--cursor-local-official`, setup keeps the original ten providers and records Cursor
as unavailable to this fixture.

ZCode has a separate setup for an unchanged official `zcode.cjs` distribution. It creates a
custom OpenAI-compatible native model and a temporary launcher that applies fake provider
credentials and the isolated config in one supervisor. The model map uses the empty native
provider so the driver does not wrap that supervisor again:

```bash
uv run python bench/cli-concurrency/setup_zcode_fixture.py \
  --endpoint http://127.0.0.1:18999 --directory /tmp/zcode-fixture \
  --official /path/to/official/zcode.cjs
```

Use the emitted `HUMANIZE_HOME`, prepend its `bin` directory to `PATH`, and pass its
`models.json` with `--backends zcode` to the normal constrained harness. Keep the identical
launcher, official CJS hash and store for original and candidate. An official CLI loopback
probe completed both read/edit/check tasks and second-turn marker recall with the existing
Chat fixture protocol. Each measured run still needs its own successful validation. The
main process changes its name from `node` to `zcode-cli`; compare PID plus creation time
when proving persistence. The general ten-provider setup records ZCode separately because
its optional official CJS path and launcher must be supplied explicitly.

Run the normal harness with the generated model map. Choose four CPUs the host actually
allows; this host's verified example is `8-11`:

```bash
systemd-run --user --scope --quiet \
  -p CPUQuota=400% -p MemoryMax=16G -p MemorySwapMax=0 \
  taskset -c 8-11 env -i HOME="$HOME" PATH="$PATH" \
  HUMANIZE_HOME=/tmp/cli-fixture-config/humanize \
  uv run python bench/cli-concurrency/run.py \
  --config /tmp/cli-fixture-config/models.json \
  --backends agy,claude,codex,dsh,grok,kimi,qwen,pi,opencode,mimo \
  --concurrency 1,2,4,8 --repeats 3 --output /tmp/cli-fixture-baseline
```

Use a clean child environment as shown so ambient real API keys, provider overrides and
telemetry settings cannot enter the run. With Cursor enabled, replace `PATH` with the
setup's emitted value, which includes its temporary `bin` directory. Add `cursor` to
`--backends`; continue using the separate ZCode setup above for its native config mapping.

`AllowedCPUs` on a user scope can be silently ineffective when the cpuset controller is
not delegated. Keep `taskset` and the harness's exact affinity verification. A CPU quota
alone is insufficient. To benchmark a prior source snapshot, add `PYTHONPATH=/path/to/src`
to that `env` command; the worker records the actual loaded `hmz.__file__` and source hashes,
so the snapshot is distinguishable from the checkout's current Git HEAD.

For every task turn, the fixture chooses the CLI's declared command tool and asks it to:

1. Read the three seeded task files.
2. Replace the broken function with the correct implementation.
3. Execute the unchanged checker to produce its fresh proof artifact.

Responses have zero intentional delay: JSON or fixed SSE chunks are written immediately,
with no simulated reasoning or token cadence. Each workload response carries fixed synthetic
usage of 1,000 input and 40 output tokens. Rates computed from those counters measure this
fixture workload, not model generation speed. Compare startup and elapsed fixed-work time,
and retain auxiliary requests and fixture service time rather than inferring cloud capacity.

The next response finishes the turn and includes the conversation marker. Tool outputs are
counted only after the newest benchmark user task. Earlier cold-turn tool outputs cannot
cause the warm turn to skip its work. Unknown shell schemas produce an explicit error.
The same artifact, context, event and result checks used for real providers still apply.

Each provider request records its handler-arrival monotonic timestamp before body decoding,
the conversation marker, phase, completed tool-step count, service duration, active handler
count and cumulative fixture CPU/RSS. The harness records the matching marker and turn-start
monotonic timestamp. Join these on the same machine:

```bash
uv run python bench/cli-concurrency/fixture_metrics.py \
  --run /tmp/cli-fixture-baseline/results.jsonl \
  --requests /tmp/fixture-requests.jsonl --output /tmp/cli-fixture-baseline/startup.jsonl
```

Analysis revision `workload-and-auxiliary-v2` requires a correct task pair, exactly four
successful workload exchanges with completed steps `0,1,2,3`, and coherent timestamps.
Requests without a declared shell, with tools explicitly disabled, or with another tool
forced are classified separately as auxiliary traffic; arrival order alone never excludes
a request. This covers title, structured-metadata and token-count requests. A completion
review also counts separately, but only when the complete tool history and this fixture's
assistant completion marker precede an injected user message quoting the original task.
A direct repeated task still resets the sequence and fails validation. Task quotes do not
start a new workload turn. Counts, service
time, failures and cancellations remain visible. Cancelled auxiliary requests do not imply
failed work. Auxiliary HTTP errors invalidate the sample: historical runs where the older
fixture returned HTTP 400 to metadata calls must be repeated with the corrected fixture.

Time to the first provider request includes the earliest correlated auxiliary POST, even
if it precedes the first workload call. Uncorrelated discovery traffic is outside that
metric. Fixed-work overhead after that request and total fixture processing time are
reported separately for cold and warm. Missing work, repeated workload requests, workload
provider failures, timeouts and cleanup survivors cannot become valid startup samples. `--baseline /tmp/previous/startup.jsonl` compares cold/warm p50 and
p95 startup to the earlier serial baseline with an explicit 2x limit and identical settings.
Real-model work-speed verification remains false in these synthetic comparison records.

Provider arrival includes loopback transport and fixture scheduling. Run the fixture on
otherwise available host CPUs, inspect its CPU and processing-time records, and repeat or
scale the fixture if it becomes a bottleneck. A saturated fixture does not establish a CLI
concurrency ceiling. Historical journals without `sampler_revision` captured CPU counters after the sample
timestamp and can overstate the first instantaneous peak. Preserve those raw baselines,
use their cumulative cgroup CPU averages, and omit the invalid instantaneous peak. Revision
`counter-before-timestamp-v2` timestamps after counter reads and retains each sample's raw
CPU counter, so its rate can be recomputed exactly. It also records the harness source
hashes. Repeat any ceiling conclusion that depended on the historical instantaneous peak.
