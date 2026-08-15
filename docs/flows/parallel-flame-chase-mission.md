---
pageClass: hmz-feature
---

# official/parallel_flame_chase_mission

The same three isolated lanes as
[`official/parallel_flame_chase`](/flows/parallel-flame-chase), with a coordinator that comes
back. A **fresh** coordinator adjudicates terminal outcomes, deadlines, stalls, failures,
objective revisions, external review requests and periodic portfolio audits — and accepted
private-lane artifacts enter lane 1's durable integration queue.

```sh
hmz exec -f official/parallel_flame_chase_mission \
    -a codex/gpt-5.6-sol:max \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

<HmzFlowShape flow="parallel_flame_chase_mission" />

## A separate flow, not a flag

It has its own configuration, its own mounted mission skill and its own resumable state. The
two share only a hidden runtime implementation, so their common isolation and recovery
semantics cannot drift apart — which is the reason they are two public flows rather than one
with a switch.

Reach for the base flow when durable peer coordination is enough. Reach for this one when
something has to decide, mid-run, that a lane is finished, stuck, or working on the wrong
thing.

## Fresh, every audit

The coordinator that audits is a new session. What it adjudicates is the evidence in front of
it — reports, artifacts, the state of the lanes — rather than the run it planned six hours ago
and would otherwise be defending.

## What it takes

Everything the base flow takes, and:

```yaml
global_audit_hours: 6.0          # between global portfolio audits; null disables them
mission_deadline_hours: 6.0      # for coordinator missions that omit a usable value
max_turns_without_outcome: 6     # progress turns before a targeted audit
interrupt_grace_seconds: 60      # after an interjection, before the target session is closed
external_events: null            # an adapter-owned version-1 JSONL evidence stream
```

An interruption closes **only the target session**, after its grace period. The other lanes
carry on.

## What it keeps

The missions, the audits and their outcomes, and everything the base flow keeps: the plan, the
snapshots, each lane's alternation and failure state.

## See also

- [official/parallel_flame_chase](/flows/parallel-flame-chase) — the same lanes, unaudited
- [Many turns at once](/features/concurrency) — why seven agents are not seven queues
- [Hooks](/guide/hooks) — the moments an interruption is allowed to land on
