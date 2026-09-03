# Claude and Codex Session Fork Plan

**Status:** proposed

**Scope:** add context-preserving fork support for `claude` and `codex` only. Other
backends remain unsupported until they expose an equivalent native operation.

## Goal

Allow a flow to branch an already-open conversation into an independent research
conversation:

```python
# Called between completed parent turns.
research = parent.fork()
findings = await research.aturn("Collect read-only evidence for this question.")
```

The fork must preserve the parent conversation through one completed history
boundary, leave the parent usable and unchanged, and let the child run
independently. By default the child inherits the parent's effective backend,
model, provider, permissions, skills, tools, effort, machine and workspace. Any
override must be explicit and must state whether it invalidates cache equivalence.

Forking must use the backend's native history operation. Replaying the transcript
into a new session is not an acceptable fallback: it changes the prompt shape and
does not preserve the prefix-cache condition.

Two rules make the boundary unambiguous:

1. `Session.fork()` performs the native fork eagerly, without sending a user
   prompt. The returned child already has its backend id.
2. A fork is allowed only while the parent is idle and its selected boundary is
   completed. A call while a parent turn is running raises a clear error. A flow
   that needs a child during a later parent turn must prepare it before starting
   that turn; a tool callback must never create its own fork while the parent is
   waiting for that callback.

## Phase 0: Native Prerequisites

No flowverse implementation is started until these backend facts are verified in
the exact CLI versions supported by the release.

### Claude probe

- Verify that `--resume <parent> --fork-session --session-id <child>` creates and
  persists the child without a user prompt. If Claude requires a prompt to create
  the branch, Claude cannot satisfy the eager boundary contract in this release
  and its fork capability remains disabled.
- Verify the child id, transcript isolation, effective model/effort/permission,
  MCP configuration and behavior when the parent continues immediately after the
  fork.
- Record the minimum Claude version that supports this operation. Older versions
  must report an unavailable capability rather than fail after a flow has started.

### Codex probe

- Verify `thread/fork` and `lastTurnId` against the app-server schema, including a
  fork from the latest completed turn and from an earlier completed turn.
- Verify that a second app-server process, using the same Codex home, provider
  environment, machine and workspace, can load the parent thread by id and fork
  it. It must not create a second container or remote mirror for the same child.
- Verify that the child server can run while the parent server is in a turn. A
  single server remains serialized; the fork runtime must own a separate server
  when overlap is requested.
- Record the minimum Codex version. A server without `thread/fork` must produce a
  capability error, not a transcript replay.

### Failure and retry probe

Test a native operation whose response is lost after the backend creates a child.
The driver must not blindly retry and create an unknown number of branches. It
must either reconcile the child id from the backend or surface an explicit
unreconciled-fork error and record the orphan in telemetry.

## Phase 1: Core Fork Contract

This phase adds the flow-facing primitive and the internal fork context. It must
land before any flowverse helper.

### Public contract

```python
class Session(Protocol):
    forks: ClassVar[bool]

    @property
    def last_turn_id(self) -> str | None: ...

    def fork(
        self,
        *,
        last_turn_id: str | None = None,
        permission: str | None = None,
    ) -> Session: ...
```

The semantics are fixed:

- `fork()` takes no prompt and performs the native operation before returning.
- The parent must be opened, idle and not closed. An unopened parent, an active
  parent turn, a non-completed `last_turn_id`, or a session already moved to a
  different backend raises a clear error before a child is exposed.
- With `last_turn_id=None`, the child is forked through the parent's latest
  completed turn. Codex also accepts an earlier completed turn. Claude forks the
  complete conversation and raises `NotImplementedError` for a non-None boundary
  instead of silently ignoring it.
- `last_turn_id` is inclusive. It is exposed as the latest completed backend turn
  id where the backend provides one; Claude returns `None` because its native
  operation has no intermediate boundary argument. A flow does not need private
  driver state to name an intermediate Codex boundary.
- The child has a new backend id, lock, meter, steering state and lifecycle. Its
  `last_turn_id` starts empty and its parent metadata is immutable.
- The fork context snapshots the effective model, provider/account, permission,
  service tier, effort, environment, machine, workspace, selected skills and
  offered tools at the boundary. Later parent reconfiguration, fallback or skill
  changes do not change the child.
- `permission` is the only v1 fork override. `None` inherits the parent's
  effective permission; an explicit value is passed through the native operation,
  recorded in telemetry and sets `cache_equivalent=false` when it differs from the
  parent. It must be one of the common permission values and must be rejected
  before the native call when the backend cannot express it. Model, provider,
  effort and workspace overrides are deferred.
- Pending parent steering, waiting prompts, interactive answers and flow-owned
  prompting state are not copied. Hooks, watchers and the cycle are shared as
  routing facilities and receive the child session; they are not copied as a
  second mutable lifecycle.
- Error precedence is stable: an unopened/active/closed parent or invalid
  boundary is a `RuntimeError`, an unsupported capability is a
  `NotImplementedError`, and a native backend failure keeps the existing
  `CalledProcessError` diagnostic. These errors are never hidden by `suppress`.
- A forked child never uses the normal cross-account or cross-backend fallback
  path. Native fork errors and child turn errors are surfaced explicitly. The
  parent retains its existing fallback behavior.
- Backends without native support expose `forks = False` and raise
  `NotImplementedError` without creating a child. The capability may still be
  disabled at runtime when the installed CLI fails the Phase 0 probe.

### Flow checker and capability model

- Add a flow-facing `Forks` marker, analogous to `Goal`, so a flow that forks
  declares `Annotated[Agent, Forks]`. The runner rejects a selected backend
  without `Session.forks` before the first turn.
- Add `forks` to the capability catalogue. The catalogue is descriptive; the
  annotation and runtime check are what enforce the requirement.
- Add `fork` to the checker's session-returning call set (`new`, `clone`, `fork`)
  so turns on a forked child remain tracked. A normal Python flow can use it;
  atlas bodies still have no `Session` and cannot express a fork node.
- `Session.fork` is present in the structural Protocol for every backend, so the
  API is not literally "visible only where forks is true". The contract is that
  only capable backends pass the declared check and successfully execute it.
- Keep `hmz.flows.fork(name, into)` documented as the flow-directory copy
  operation; it is unrelated to `Session.fork()`.

### Lifecycle and telemetry contract

Add a fork-specific journal event rather than overloading `cycle.opened`:

```json
{
  "event": "forked",
  "agent": "actor",
  "backend": "codex",
  "provider": "local",
  "parent_session_id": "parent-thread",
  "session_id": "child-thread",
  "parent_key": "actor-codex@local-parent-thread",
  "session_key": "actor-codex@local-child-thread",
  "last_turn_id": "turn-7"
}
```

The cycle must register and link the child as soon as the native response gives
its id, even if the first child turn later fails. The `*_session_id` fields are
backend ids for diagnostics; the `*_key` fields are the cycle's fully qualified
relation keys. Usage is recorded on child turn completion in numeric fields only;
no prompt, transcript or file content is written. Existing readers ignore the new
event, while tracing maps the child session's `parent` to `parent_key`.

The implementation must update the journal protocol, cycle reader/linker,
tracing collector/renderers and tests together. A single unspecified "telemetry
field" is not sufficient because fork creation, child failure and per-turn cache
usage happen at different times.

## Phase 2: Backend Drivers

### Claude implementation

The ordinary command paths remain:

```text
new:     --session-id <id>
resume:  --resume <existing-id>
```

The one-time native fork path is:

```text
--resume <parent-id> --fork-session --session-id <child-id>
```

The driver must perform this operation eagerly, adopt the child id before any
child prompt, and then use ordinary `--resume <child-id>` commands. The fork
branch must never use `--session-id` with the parent or resume the parent without
`--fork-session`.

The command builder uses the immutable fork context, not the agent's later mutable
config, for model, effort, permission mode, service tier, provider environment,
skills and MCP configuration. A child process has its own process and session
lock, so parent and child may overlap. Closing the child kills only its process.

Required changes include `ClaudeCodeSession._command()`, an eager native-fork
operation, fork-context storage, child adoption before the first turn and the
forked journal event. Tests must cover a parent that continues immediately after
the fork and a child whose first turn fails.

### Codex implementation

Codex uses app-server JSON-RPC rather than spawning `codex fork`:

```json
{
  "method": "thread/fork",
  "params": {
    "threadId": "<parent-thread-id>",
    "lastTurnId": "<optional-inclusive-boundary>"
  }
}
```

The child is created eagerly on a dedicated app-server process that shares the
parent's backend home, provider environment, machine, workspace and reference-
counted MCP bridge. It is not made through the public `AgentBase.clone()` path,
which intentionally drops hooks, tools and cycle state and may create a second
machine. The fork runtime forwards child events to the parent agent's watchers
and journal while keeping child locks, server stop and meter state independent.

The response's `thread.id` is adopted immediately. The first child prompt then
uses the existing `turn/start` path with the child thread id. The child server is
never the parent's server for an overlapping child turn. If the configured
machine cannot provide two app-server processes over the same backend home, the
fork fails explicitly rather than creating a different context.

`thread/fork` parameters omit inherited model/provider/service tier and permission
values. An explicit v1 `permission` override is sent using Codex's sandbox and
approval fields. The first child `turn/start` must use the effective values
returned by the fork response, rather than silently re-reading a parent agent
that may have been reconfigured.

The app-server layer needs a request/notification router that can wait for a
thread-specific asynchronous operation without dropping unrelated notifications.
This is required for fork recovery and any later compaction capability; changes
are not limited to `CodexSession._thread()`.

## Phase 3: Flow-Side Research Helper

This phase adds a convenient delegation workflow on top of the core primitive. It
does not implement native fork logic in `humanfia/flowverse`.

### Prepared child model

A tool callback runs while the parent turn is active and therefore cannot call
`parent.fork()`. The flowverse helper must prepare a child between parent turns:

```python
slot = ResearchFork.prepare(
    parent, permission="read-only", timeout=60, max_output_chars=32000
)
parent.offers([slot.tool])
try:
    answer = await parent.aturn("Use the research tool if evidence is needed.")
finally:
    slot.close()  # also unregisters the helper from the parent
```

`prepare()` performs the eager native fork and captures the completed boundary.
The callback only sends the child-specific research prompt to the already-created
child, waits for it, validates the result and returns a digest through the
existing MCP bridge. Before exposing the slot, the helper replaces the forked
child's inherited tool list with the explicit read-only allowlist (empty by
default). It is one-shot by default; a flow explicitly prepares a new slot for
another parent turn. The child does not offer the research tool itself, so
recursive delegation is bounded.

The helper accepts only Claude and Codex sessions with `forks=True`. It refuses
to prepare a child from an unopened, active, moved or unsupported parent. The
parent's transcript, id, pending turn and future prompts are never used as the
child's mutable state.

### Read-only policy

`Session.fork()` v1 inherits the parent's effective permission by default. The
research helper explicitly requests `permission="read-only"`, so it can be used
with a bypass parent without weakening the parent's own session. This explicit
override invalidates the default cache-equivalence guarantee and is recorded as
such.

Flow-owned callbacks execute in the flow process, outside the backend sandbox.
The helper therefore offers no parent tools by default. If a flow supplies tools,
it must pass an explicit read-only allowlist; names or prompt instructions are not
treated as proof that a callback has no side effects. The parent and child may
share the MCP socket, but only those allowlisted callbacks are advertised to the
child.

### Deadline, result and cleanup rules

- The helper has a monotonic deadline covering child turn execution and result
  validation, plus a small cleanup grace period. `asyncio.wait_for()` alone is
  insufficient because the current awaited-turn worker continues after task
  cancellation.
- Claude cancellation closes and joins the child process. Codex cancellation
  stops only the child fork runtime and its dedicated app server; it must never
  call `parent_agent.stop()`.
- A timeout, native error, child failure, malformed result or cleanup failure is
  returned as an MCP tool error with a stable error code and diagnostic. It is
  never converted to an empty finding.
- The child result has a typed flowverse schema with a maximum serialized size.
  Oversized or schema-invalid output is an error, not an unbounded digest passed
  into the parent context.

The helper continues to use the normal MCP tool-call loop. `Verdict(adds=...)` is
a hook channel and is not a substitute for a tool result.

### Flowverse coordination

The core humanize2 change and the flowverse change are released together. The
flowverse pins or declares the minimum humanize2 version that provides
`Session.fork`, `Forks` and the prepared-child behavior. Its tests use the public
flow interfaces and fake native drivers; they do not import `hmz.agents` or call
private driver methods.

## Cache-Preserving Requirements

The default fork must preserve the provider-visible common prefix:

- fork only at a completed boundary captured eagerly;
- use the same backend, effective model, provider/account, service tier,
  permissions, system/developer instructions, tool definitions and workspace;
- send only the child-specific prompt after the native fork;
- never replay the parent transcript in a newly constructed prompt;
- never use cross-backend fallback for a forked conversation.

The provider still decides whether a request hits its cache. Tests assert the
invariants and retain reported usage; they do not claim that every provider must
return a hit.

Claude already reports cache-read/cache-write usage. Codex's token usage contains
separate cached and non-cached input fields. Before implementation, define one
non-double-counting mapping into the common usage model, for example:

```text
input       = net-new input tokens
cache_read  = cached input tokens
cache_write = cache-write input tokens
output      = output tokens
```

The chosen mapping must be documented, tested against `Usage.total`, and written
to child telemetry. The phrase "map them if needed" is not sufficient for the
cache acceptance condition.

## Fork Then Compact (Deferred Follow-up)

Compaction is intentionally outside the current fork v1. Keep it as a separate
follow-up after fork lifecycle and usage accounting are stable:

```python
child.compact()
```

The child must be forked and idle; compaction never touches the parent. Add a
`compacts: ClassVar[bool]` capability and reject unsupported backends explicitly.

- **Claude:** send `/compact` as a child-only operation over the stream-json
  protocol. An empty successful result and `system/compact_boundary` are success;
  `--autocompact` is not a force operation.
- **Codex:** call `thread/compact/start` on the child server and wait for a
  thread-specific completion. Accept both the legacy `thread/compacted`
  notification and the current `contextCompaction` item delivered through
  `item/completed`; the app-server router must not discard either form.

Compaction is one summarization pass with its own reported usage. Later child
turns use the smaller summary prefix. A parent may be compacted before preparing
many children only through an explicit parent operation, since that changes the
parent's own context.

## Non-Supported Backends

`agy`, `cursor`, `dsh`, `grok`, `kimi`, `pi`, `qwen`, `opencode`, `mimo` and
`zcode` do not receive fork support in this plan. The ACP bridge and
`HumanSession` also expose `forks = False`. They retain their current session,
batch and native-subagent behavior. A request to fork one of them fails before a
child is created; there is no transcript-replay fallback.

## Specification and Documentation Gate

This plan does not edit any `SPEC.md`. Under the repository instructions, a
separate explicit request is required before `src/hmz/agents/SPEC.md` or
`src/hmz/flows/SPEC.md` is changed. Until that approval exists, the implementation
must be labelled experimental and the public reference docs must not describe
forking as part of the normative interface. Once approved, update the reference
interfaces, checker docs, tracing docs and flowverse documentation in the same
release.

## Acceptance Matrix

| Area | Acceptance condition |
| --- | --- |
| Native prerequisites | Supported CLI versions prove eager native fork, shared backend state and response-loss behavior. |
| API | `fork()` is eager, prompt-free, idle-only, returns a child id and honors the completed boundary contract. |
| Capability | `Annotated[Agent, Forks]` rejects a backend without native fork before its first turn. |
| Claude | Native `--resume + --fork-session + --session-id` creates an isolated child and later child turns resume that id. |
| Codex | Native `thread/fork` creates the child, honors inclusive `lastTurnId`, and uses a dedicated overlapping server. |
| Snapshot | Parent effective configuration and selected session state are frozen at the boundary; explicit permission overrides set `cache_equivalent=false`. |
| Isolation | Parent id, transcript, pending turn and future prompts are unchanged; parent may continue immediately. |
| Prepared helper | The MCP callback consumes a pre-created child and never forks while the parent turn is waiting. |
| Tools | Only explicitly allowlisted read-only flow callbacks are offered to a research child. |
| Concurrency | Claude child processes overlap; Codex child and parent overlap only on separate servers and otherwise serialize per server. |
| Timeout | Deadline cancellation stops and joins only the child runtime; no worker, process or server is left behind. |
| Errors | Unopened/active parent, invalid boundary, unsupported native operation, timeout, malformed result and unreconciled fork are explicit. |
| Fallback | A forked child never moves to another account or backend implicitly. |
| Cache | Prefix invariants hold and Claude/Codex cache fields use a tested, non-double-counting mapping. |
| Telemetry | Fork creation, parent relation, boundary, child failure and per-turn usage are linkable in cycle/tracing output. |
| Compact (follow-up) | Deferred from fork v1; when implemented, child-only compaction must work with current and legacy Codex completion signals while the parent remains unchanged. |
| Compatibility | Unsupported backends and old CLI versions reject fork without creating a child. |
| Integration | humanize2 tests, docs and the pinned `humanfia/flowverse` tests agree on the experimental or approved contract. |

## Required Tests

- fake Claude CLI: eager no-prompt fork, exact flags, parent continuation, child
  resume and child failure;
- fake Codex app server: `thread/fork`, inclusive boundary, separate-server
  overlap, notification routing and response-loss recovery;
- fork rejection for unopened, active, closed, moved and unsupported sessions;
- parent config/state mutation after fork does not change child behavior;
- fallback is disabled for forked children while parent fallback remains intact;
- prepared MCP helper returns a typed digest and never forks from inside the
  active parent callback;
- timeout, cancellation, process/server reaping, malformed output, size limit,
  recursion limit and deterministic MCP error responses;
- read-only parent/tool allowlist enforcement, including a callback that would
  mutate state if it were incorrectly advertised;
- cycle/tracing relation and cache usage records for successful and failed child
  turns;
- Codex cache field mapping and `Usage.total` accounting;
- follow-up only: optional Claude and Codex compaction, including
  `contextCompaction` and legacy `thread/compacted` signals;
- flow checker capability declaration and all non-Claude/Codex compatibility
  cases;
- the humanize2 suite and the flowverse suite against the released interface.
