---
pageClass: hmz-feature
---

# official/parallel_flame_chase

Seven agents, three lanes, one working directory. A coordinator plans the three lanes once and
does not come back; six actors alternate in fresh sessions and coordinate through durable
reports. **Lane 1 alone owns the original source** — lanes 2 and 3 work in private snapshots
and publish reconstructable artifacts rather than writing to your tree.

```sh
hmz exec -f official/parallel_flame_chase \
    -a codex/gpt-5.6-sol:max \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

<HmzFlowShape flow="parallel_flame_chase" />

## Seven agents, in this order

`-a` takes them in the order the flow names them, and the interface asks for them under these
names:

| | |
| --- | --- |
| `coordinator` | Plans the three lanes, once, and leaves the run |
| `lane_1_actor_a` · `lane_1_actor_b` | Lane 1, alternating — the only writers of the original source |
| `lane_2_actor_a` · `lane_2_actor_b` | Lane 2, alternating, in a snapshot of its own |
| `lane_3_actor_a` · `lane_3_actor_b` | Lane 3, alternating, in a snapshot of its own |

All seven open with the backend's [goal feature](/features/goals) turned off —
`AgentDefaults(goals=False)` beside each of them — because a lane's turn ends where the lane
protocol says it ends rather than where a model decides it has met the objective. That is what
the flow opens `/agents` on, not something it holds you to.

## One writer, and two that cannot write

The isolation is the point of the flow. A per-source advisory lock permits only one lane 1
owner; lanes 2 and 3 are confined to snapshots, and the runtime's control paths reject links
and replacements. What they produce reaches lane 1 as a **report** and a hashed,
reconstructable artifact package — never as a write into your tree — and reports are
redelivered until the receiving lane completes a valid turn and acknowledges them, so a lane
that fell over does not lose what it was told.

Durable data lives under `~/.humanize/parallel_flame_chase/<workspace-key>/<run-id>/`. The flow
coordinates local work only: there is no release, deployment, submission, messaging or purchase
executor in it.

## What it takes

```yaml
rest_seconds: 1.0      # what the single-writer scheduler rests between control passes
resume_mode: auto      # or `fresh`, to deliberately start another run
```

The [skill](/user/skills) it brings, `parallel-flame-chase`, is the actor, report, artifact,
checkpoint and resume protocol — mounted onto every session the flow opens.

## What it keeps

The plan, the snapshots, each lane's A/B alternation and its lane-local failure state. The same
substantive task resumes compatible state; a bare `continue` reads `TASK.md` when there is one,
and replans against a fresh source snapshot where the objective has changed. A different
substantive task starts a fresh run, and `resume_mode: fresh` starts one deliberately.

## See also

- [official/parallel_flame_chase_mission](/flows/parallel-flame-chase-mission) — the same lanes, audited
- [official/flame_chase](/flows/flame-chase) — one lane of this, and the flow it is named after
- [Worktrees](/weaver/worktrees) — humanize's own way of giving an agent a tree of its own
