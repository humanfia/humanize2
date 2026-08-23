---
pageClass: hmz-feature
---

# Capability map

This is a wayfinding map, not an exhaustive product contract. It groups related behavior by
the user problem it solves; one group may combine several implementations, and one feature may
support more than one group. Availability still depends on the backend, account, operating
system, and shape of the run.

Use the interactive map to choose an area, then follow **Learn** for the design, **Use** for a
task-oriented guide, or **Reference** for the complete interface and its limits.

<HmzMap />

## A. Flow system

Express work as ordinary Python or as an inspectable graph, then compose, schedule, and recover
it without hiding which execution model is in use.

### A1. Expression and compilation

**Outcome.** Choose unrestricted runtime behavior or a graph whose structure is settled before
the first agent turn.

- A regular flow is unrestricted Python; its next step is whatever its body decides at runtime.
- An atlas uses a restricted declarative body that compiles into a typed prophecy graph.
- Calls, shaped values, branches, loops, and returns become explicit nodes, edges, and exits.
- Canonical graph identities separate structural changes from formatting and node-body changes.
- Shipped graphs are checked for drift and rebuilt only from allowlisted prophecy types.

**Learn:** [Python becomes a prophecy](/features/prophecy) · **Use:**
[Writing a flow](/weaver/writing-a-flow), [Atlas](/weaver/atlas) · **Reference:**
[Flows](/reference/flows#an-atlas)

### A2. Static correctness and proving

**Outcome.** Find structural mistakes and exercise hostile paths before spending a real model
turn.

- Zero-execution checking reads flow structure without importing or running user code.
- Atlas checks cover edge shapes, bound values, recursion, returns, and loop progress.
- Ordinary flow checks catch selected liveness and shaped-answer mistakes without claiming to
  prove arbitrary Python.
- Nested flows and changed configuration schemas are validated before their work begins.
- Stand-in agents, adversarial scenarios, and virtual time can exercise execution without a
  real model.

**Learn:** [Python becomes a prophecy](/features/prophecy) · **Use:**
[Checking flows](/weaver/checking-flows), [Testing flows](/weaver/testing-flows) ·
**Reference:** [Flows](/reference/flows#checking-a-flow)

### A3. Composition and hot reload

**Outcome.** Reuse flows and their supporting assets while keeping each nested run visible and
independently scoped.

- A regular flow may load and call another flow while preserving nested run context.
- An atlas may contain another atlas as a typed supernode in the outer prophecy.
- Remote skill repositories are fetched and cached; selected flow skills are mounted for the
  scope that needs them and removed when it ends.
- Flow entry points and side modules are read again so current source is used for later work.
- Synchronous and asynchronous flows share the same runner and failure model.

**Learn:** [A flow is Python](/features/flows) · **Use:**
[Calling flows](/weaver/calling-flows), [Skills](/user/skills) · **Reference:**
[Flows](/reference/flows#a-flow-that-calls-another-flow)

### A4. Scheduling, state, and resumption

**Outcome.** Place and fan out work deliberately, then continue the workflow state that was
actually recorded.

- Flows declare agent roles, capabilities, and working locations without binding them to one
  backend implementation.
- Independent sessions may run concurrently; turns sharing one session remain sequential.
- Resumable regular flows keep an explicit state mapping and resume by running current flow
  code again.
- Atlases record completed node visits and resume the first unfinished visit under the same
  prophecy identity.
- Neither form restores a backend conversation; repositories and explicit flow state carry the
  work forward.

**Learn:** [Many turns at once](/features/concurrency),
[Picked up where it stopped](/features/resuming) · **Use:**
[Async flows](/weaver/async-flows), [Picking a run up](/user/resuming) · **Reference:**
[Flows](/reference/flows#a-flow-that-can-be-picked-up)

## B. Agent control plane

Drive different coding agents through one orchestration model while preserving their real
capabilities, identities, conversations, and ways of collaborating with a person.

### B1. Backend unification

**Outcome.** Configure one agent abstraction across different CLIs and protocols without
pretending every backend supports the same controls.

- Agent and session contracts normalize turns, events, answers, and lifecycle operations.
- Native app servers, streaming command-line adapters, and Agent Client Protocol (ACP) servers
  keep their own transport semantics behind that contract.
- A capability matrix exposes what each backend can do, so a flow can require capabilities and
  reject an incompatible backend.
- Model catalogues are usually discovered for the account that will run them; backends that
  cannot list models begin with a small advisory catalogue instead.
- Shaped answers are reconstructed into the same typed result where a backend supports them.

**Learn:** [Many backends, one agent](/features/backends),
[Answers in a shape](/features/shapes) · **Use:** [Providers](/user/providers),
[Efforts](/user/efforts) · **Reference:**
[Agents](/reference/agents#what-each-backend-can-do)

### B2. Turn and session control

**Outcome.** Keep live work steerable and make human collaboration part of the run rather than
an out-of-band interruption.

- Per-turn controls, lifecycle hooks, and typed failures give flows explicit decision points.
- Steering delivers an acknowledged instruction into a supported turn that is already running.
- Goals continue across controlled turns, while cloning creates a separate conversation branch.
- Side questions through /btw read a frozen conversation snapshot without changing the main
  session.
- Agent questions and the human agent share an answer path; away mode returns no answer instead
  of leaving a run blocked.
- The board carries non-blocking, durable lines between a person and a flow while both
  continue.

**Learn:** [A line typed mid-turn](/features/steering),
[It decides when it is done](/features/goals), [The moments of a turn](/features/hooks),
[You, as one of the agents](/features/human) · **Use:** [Questions](/user/questions),
[Side questions (/btw)](/user/btw), [Board](/user/board),
[Human agent](/weaver/human-agent), [Being away](/user/afk) · **Reference:**
[Agents](/reference/agents#turns), [Flows](/reference/flows#the-person-at-the-prompt)

### B3. Tools and skills

**Outcome.** Give each session only the reusable instructions and temporary callable tools its
role needs.

- Each session receives the flow-owned skills selected for its role and scope.
- Backends expose the native skills already installed where their own CLI reads them.
- Flow-owned skills are mounted for the session and removed when that scope ends.
- A flow callback can become a native tool from the next turn until it is withdrawn or the
  session ends, on a capable backend.

**Learn:** [Many backends, one agent](/features/backends) · **Use:**
[Skills](/user/skills), [Callbacks as tools](/weaver/tools) · **Reference:**
[Agents](/reference/agents#the-skills-an-agent-carries),
[Flows](/reference/flows#the-skills-a-flow-brings)

### B4. Failure recovery

**Outcome.** Respond to a failed turn according to what failed, while making conversation loss
an explicit boundary.

- Backends distinguish failures worth another attempt from explicitly unrecoverable ones;
  configured policy then retries, walks accounts, and finally walks places.
- Retries and waits are policy for a place, not an automatic response to every failure.
- An account chain stays inside one backend and may continue the same backend conversation.
- Cross-backend fallback opens a new session and carries compatible agent settings and the
  pending turn, but not the earlier conversation.
- Recovery stops on loops, missing destinations, unsupported capabilities, and failures another
  attempt cannot fix.

**Learn:** [Two accounts of one CLI](/features/accounts) · **Use:**
[Falling back](/user/fallback) · **Reference:**
[Account recovery](/reference/agents#when-an-account-goes-down),
[Cross-backend recovery](/reference/agents#when-the-place-has-nowhere-left-to-run)

### B5. Accounts and credentials

**Outcome.** Run the same CLI under separate identities without changing the agent's command or
leaking another account into the turn.

- Where a CLI provides a native login, capture lets it create and refresh credentials in its
  own format; other backends use their configured credential inputs.
- Credential paths and environment variables are redirected only for the account taking a turn.
- Ambient credential variables are removed so the shell cannot silently select another account.
- Compatible vendor credentials can be reused across CLI backends under each backend's
  spelling.
- Concurrent accounts keep private files, and updates to stored account state land atomically.
- The machine's existing login may start an account chain, but humanize does not own or copy
  it.

**Learn:** [Two accounts of one CLI](/features/accounts) · **Use:**
[Providers](/user/providers) · **Reference:** [Providers](/reference/providers)

## C. Execution fabric

Let a local coding agent operate another machine while keeping process behavior, workspace
movement, transport, and machine ownership explicit.

### C1. Transparent remote execution

**Outcome.** Keep the agent local while selected work behaves as though its processes and files
belong to the target machine.

- A supervisor decides selected system calls and can replay them remotely one at a time.
- Program launches, descendants, network access, paths, and executables follow explicit routes.
- Control files and backend state that should remain local stay on the local side.
- Remote results preserve target errors, exit status, and common signals; rarer or repeated
  signals have documented limits.
- The anchor is routing and transport, not a sandbox or an authorization boundary.

**Learn:** [The anchor](/features/anchor) · **Use:**
[Remote execution](/user/remote-execution), [Security](/user/security) · **Reference:**
[Remote execution](/reference/remote-execution)

### C2. Shadow workspace and consistent writes

**Outcome.** Make a remote workspace available quickly without exposing readers to partial file
updates.

- A sparse local shadow presents the target workspace before every file has crossed the wire.
- Missing files and virtual exports are materialized when the agent actually reaches them.
- Writes stream to the target and become visible atomically when the complete file arrives.

**Learn:** [The anchor](/features/anchor) · **Use:**
[Remote execution](/user/remote-execution) · **Reference:**
[What the agent observes](/reference/remote-execution#what-the-agent-observes)

### C3. Portable transport runtime

**Outcome.** Reach different targets through one session protocol without installing humanize
on the target first.

- A compact target runtime carries process, file, environment, and working-directory
  operations.
- One multiplexed connection can keep independent requests and streamed results in flight.
- Targets may use different transports while preserving the same remote-execution semantics.
- Local and target environments are composed deliberately rather than replacing each other.
- Each remote command uses the target-resolved counterpart of the tracee's current working
  directory.

**Learn:** [The anchor](/features/anchor) · **Use:**
[Remote execution](/user/remote-execution) · **Reference:**
[Targets](/reference/remote-execution#targets)

### C4. Machine lifecycle

**Outcome.** Give agents isolated or shared machines with a clear owner for startup, reuse, and
cleanup.

- An agent may receive a dedicated container whose lifetime follows that agent.
- A run may share one container when the participants need the same environment.
- Existing remote targets remain externally owned; managed targets are closed by the scope that
  created them.
- Workspace placement is declared separately from which backend performs the turn.

**Learn:** [The anchor](/features/anchor) · **Use:** [Containers](/user/containers) ·
**Reference:** [Machines](/reference/machines)

## D. Run continuity and observability

Keep long work reachable, leave a readable record after failure, reconstruct its timeline, and
separate local traces from optional outbound reporting.

### D1. Detached operation

**Outcome.** Let an interactive run survive terminal or SSH loss and reattach to its current
screen later.

- One workspace daemon owns the interface pseudoterminal (PTY) while terminals act as
  attachable readers.
- A new terminal receives a redraw of the live screen rather than a promised full transcript.
- Slow readers have independent buffers and cannot stall the run or other attached terminals.
- Detaching, cooperative stopping, and forced stopping remain distinct operations.
- Detachment does not survive host or daemon loss; persisted state can support a later run, not
  resurrect the old process.

**Learn:** [The terminal can leave](/features/daemon) · **Use:**
[Unattended runs](/user/unattended), [Stopping](/user/stopping) · **Reference:**
[Daemon](/reference/daemon)

### D2. Persistent state and layered logs

**Outcome.** Preserve enough structured evidence to inspect an abrupt stop and continue a flow
that explicitly supports it.

- Each run's epic record gains complete journal entries as events happen.
- Ordinary flow state is written through on assignment, with a final save for nested mutations.
- Atlas state records completed node visits under the prophecy identity and nesting path.
- Called flows keep layered journals and state beside the run without overwriting their caller.
- These records preserve workflow state, not the backend conversation or a terminal transcript.

**Learn:** [Picked up where it stopped](/features/resuming),
[The terminal can leave](/features/daemon) · **Use:**
[Picking a run up](/user/resuming), [History](/user/history) · **Reference:**
[Resumable flows](/reference/flows#a-flow-that-can-be-picked-up),
[Epic records](/reference/tracing#epics)

### D3. Trace reconstruction

**Outcome.** Rebuild agent activity and the programs it started onto one timeline that can be
inspected after the run.

- Backend session logs and profiled processes are combined without copying their source
  records.
- Process clocks are calibrated so agent events and operating-system activity can be compared.
- Epic records bound collection to the sessions opened by the run being inspected.
- Subagent relationships become explicit topology rather than anonymous extra sessions.
- Dense lane packing and lazy attachments keep large traces navigable without dropping detail.
- A trace is a local artifact; creating or opening it does not opt into outbound telemetry.

**Learn:** [One timeline](/features/tracing) · **Use:** [Tracing](/user/tracing) ·
**Reference:** [Tracing](/reference/tracing)

### D4. Telemetry privacy

**Outcome.** Send diagnostic reporting only after consent, with content limits enforced before
anything leaves the machine.

- Consent may remain unanswered, be enabled, or be disabled; unanswered machines send nothing.
- Data suppliers run only while a report is actually being assembled and provide names,
  counts, and configuration rather than prompts, transcripts, tool output, or file content.
- Final filters remove command lines, credentials, external paths, frame context, and logging
  breadcrumbs before an outbound report is sent.
- Local run journals, session logs, profiles, and traces are separate from optional reporting.

**Learn:** [One timeline](/features/tracing) · **Use:** [Reporting](/user/reporting),
[Tracing](/user/tracing) · **Reference:** [SDK](/reference/sdk),
[Tracing](/reference/tracing)

## E. Product surfaces

Discover, own, configure, and start the same flows through interfaces suited to interactive,
scripted, embedded, or detached work.

### E1. Discovery, forking, and configuration

**Outcome.** Find the nearest flow, make a safe local copy when it should become yours, and
configure it from the contract the flow declares.

- Built-in, fetched, project, and user flows participate in explicit catalogue and resolution
  precedence.
- Qualified names select a source directly; unqualified names prefer the nearest local version.
- Forking stages a complete copy and refuses to overwrite an existing local flow.
- A flow's pydantic model drives setup fields, validation, defaults, and grouped presentation.
- Remembered settings are revalidated against the model the flow declares now.

**Learn:** [One system, four ways in](/features/surfaces) · **Use:**
[Flowverses](/weaver/flowverses), [Flow settings](/weaver/flow-settings) · **Reference:**
[Flows](/reference/flows#flowverses)

### E2. Unified entry points

**Outcome.** Choose a terminal, command line, or Python entry point without creating a second
definition of what a flow or run means.

- The SDK, command line, and terminal interface share workspace stores, flow loading,
  validation, and the underlying runner where their responsibilities overlap.
- The daemon holds the terminal interface but does not interpret flows or become another
  engine.
- Each surface keeps its purpose: composable SDK, scriptable command line, conversational
  interface, and detached terminal continuity.
- A user-facing run is written as an epic record that history, state, and tracing can inspect.
- Shared semantics do not imply identical interaction or backend capability on every surface.

**Learn:** [One system, four ways in](/features/surfaces) · **Use:**
[Quickstart](/), [Status](/user/status) · **Reference:**
[SDK](/reference/sdk), [CLI](/reference/cli), [TUI](/reference/tui),
[Daemon](/reference/daemon)
