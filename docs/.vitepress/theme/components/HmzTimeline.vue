<script setup lang="ts">
// What `hmz trace collect` hands Perfetto: a process per agent, a track per row of its
// sessions, a slice per thing it did -- and, for a profiled run, the programs those turns
// ran drawn the same way underneath. The two switches are the two things that are easy to
// get wrong: leaving the programs out, and timing them against the wrong clock.
import { computed, ref } from 'vue'

type Kind = 'tool' | 'think' | 'say' | 'prog'

interface Slice {
  t0: number
  t1: number
  label: string
  kind: Kind
  args: string
}

interface Row {
  head: string
  sub: string
  lane: number
  slices: Slice[]
  program?: boolean
}

const SPAN = 36

const AGENTS: Row[] = [
  {
    head: 'actor · claude-opus-5 · max',
    sub: 'main',
    lane: 1,
    slices: [
      { t0: 0, t1: 1.6, label: 'thinking', kind: 'think', args: 'reasoning · 412 tokens' },
      { t0: 1.6, t1: 2.4, label: 'Read', kind: 'tool', args: 'src/pay.py · 214 lines' },
      { t0: 2.4, t1: 3.1, label: 'Grep', kind: 'tool', args: 'pattern: def charge' },
      { t0: 3.1, t1: 5.2, label: 'thinking', kind: 'think', args: 'reasoning · 1,180 tokens' },
      { t0: 5.2, t1: 6.0, label: 'Edit', kind: 'tool', args: 'src/pay.py · 1 hunk' },
      { t0: 6.0, t1: 14.8, label: 'Bash', kind: 'tool', args: 'pytest -q · exit 1 · 8.8s' },
      { t0: 14.8, t1: 16.0, label: 'thinking', kind: 'think', args: 'reasoning · 903 tokens' },
      { t0: 16.0, t1: 17.2, label: 'Task', kind: 'tool', args: 'explore · where is the retry?' },
      { t0: 17.2, t1: 19.0, label: 'says', kind: 'say', args: 'the failure is in the retry path' },
      { t0: 22.0, t1: 23.4, label: 'Read', kind: 'tool', args: 'tests/test_pay.py' },
      { t0: 23.4, t1: 27.0, label: 'Bash', kind: 'tool', args: 'ruff check --fix · exit 0' },
      { t0: 27.0, t1: 28.2, label: 'says', kind: 'say', args: 'green, and the diff is small' },
    ],
  },
  {
    head: '',
    sub: 'subagent · explore',
    lane: 1,
    slices: [
      { t0: 16.2, t1: 17.4, label: 'Glob', kind: 'tool', args: '**/retry*.py' },
      { t0: 17.4, t1: 19.8, label: 'Read', kind: 'tool', args: 'src/retry.py' },
      { t0: 19.8, t1: 21.6, label: 'says', kind: 'say', args: 'four call sites, one of them bare' },
    ],
  },
  {
    head: 'reviewer · gpt-5.6-sol · high',
    sub: 'main',
    lane: 2,
    slices: [
      { t0: 19.0, t1: 20.4, label: 'thinking', kind: 'think', args: 'reasoning · 640 tokens' },
      { t0: 20.4, t1: 21.8, label: 'Read', kind: 'tool', args: 'the diff' },
      { t0: 28.4, t1: 31.0, label: 'thinking', kind: 'think', args: 'reasoning · 1,502 tokens' },
      { t0: 31.0, t1: 33.2, label: 'says', kind: 'say', args: 'done: false · notes: name the case' },
    ],
  },
]

const PROGRAMS: Row[] = [
  {
    head: 'pytest · 48219',
    sub: 'main',
    lane: 4,
    program: true,
    slices: [{ t0: 6.05, t1: 14.72, label: 'pytest -q', kind: 'prog', args: 'started by the Bash above' }],
  },
  {
    head: '',
    sub: 'worker-1',
    lane: 4,
    program: true,
    slices: [{ t0: 6.6, t1: 11.9, label: 'python', kind: 'prog', args: 'one of pytest’s own threads' }],
  },
  {
    head: '',
    sub: 'worker-2',
    lane: 4,
    program: true,
    slices: [{ t0: 6.6, t1: 13.9, label: 'python', kind: 'prog', args: 'the one the run waited on' }],
  },
  {
    head: 'rg · 48602',
    sub: 'main',
    lane: 3,
    program: true,
    slices: [{ t0: 17.5, t1: 17.9, label: 'rg', kind: 'prog', args: 'the sub-agent’s Glob' }],
  },
  {
    head: 'ruff · 48533',
    sub: 'main',
    lane: 5,
    program: true,
    slices: [
      { t0: 23.44, t1: 26.9, label: 'ruff', kind: 'prog', args: 'ruff check --fix · 312 files' },
    ],
  },
]

const profiled = ref(true)
const corrected = ref(true)
const hovered = ref<{ slice: Slice; row: Row } | null>(null)

// What the operating system reports a start as is worked out from an estimate of when the
// machine booted, which is half a second out on an ordinary one. The number is the offset the
// profile measures away again.
const SKEW = 0.52

const rows = computed(() => (profiled.value ? [...AGENTS, ...PROGRAMS] : AGENTS))
const shift = (row: Row) => (row.program && !corrected.value ? SKEW : 0)

// Drawn as rows rather than as one scaled drawing, so that a label on the left is beside the
// track it names at every width -- a viewBox would scale the rows out from under them.
const across = (t: number) => `${(t / SPAN) * 100}%`

const caption = computed(() => {
  if (hovered.value) {
    const { slice, row } = hovered.value
    return `${slice.label} · ${(slice.t1 - slice.t0).toFixed(2)}s · ${slice.args} · ${row.sub}`
  }
  const n = rows.value.reduce((sum, row) => sum + row.slices.length, 0)
  const tracks = rows.value.length
  return `${tracks} tracks · ${n} slices · hover one`
})
</script>

<template>
  <div class="trace hmz-panel">
    <div class="bar">
      <span class="what">one run, as one document</span>
      <div class="spacer" />
      <label class="sw">
        <input v-model="profiled" type="checkbox" />
        the programs the turns ran
      </label>
      <label class="sw" :class="{ off: !profiled }">
        <input v-model="corrected" type="checkbox" :disabled="!profiled" />
        timed against the trace's own clock
      </label>
    </div>

    <div class="board">
      <div v-for="(row, i) in rows" :key="i" class="row" :class="{ program: row.program }">
        <div class="label">
          <strong v-if="row.head">{{ row.head }}</strong>
          <span>{{ row.sub }}</span>
        </div>
        <div class="track">
          <!-- Where it really started, kept on screen while the drift is on: half a second is
               eight pixels here, and eight pixels of shift with nothing to measure it against
               is a difference nobody can see. -->
          <span
            v-for="(slice, j) in shift(row) ? row.slices : []"
            :key="`g${j}`"
            class="ghost"
            :style="{ left: across(slice.t0), width: across(slice.t1 - slice.t0) }"
          />
          <span
            v-for="(slice, j) in row.slices"
            :key="j"
            class="slice"
            :class="[slice.kind, { drifted: row.program && !corrected }]"
            :style="{
              left: across(slice.t0 + shift(row)),
              width: across(slice.t1 - slice.t0),
              '--tone': `var(--hmz-lane-${row.lane})`,
            }"
            @mouseenter="hovered = { slice, row }"
            @mouseleave="hovered = null"
          >
            {{ slice.t1 - slice.t0 >= 1.7 ? slice.label : '' }}
          </span>
        </div>
      </div>
    </div>

    <p class="caption">{{ caption }}</p>

    <p class="verdict" :class="{ warn: profiled && !corrected }">
      <template v-if="!profiled">
        Without the programs, the long <code>Bash</code> is a rectangle that says only that
        something took eight seconds. A turn is mostly other programs, and a timeline that stops
        at the tool call stops exactly where the time went.
      </template>
      <template v-else-if="!corrected">
        Half a second out, and <code>pytest</code> now starts after the tool call that ran it and
        outlives it. That is what the operating system's own answer looks like on a timeline
        where a tool call is timed to the millisecond — so the offset is measured from the
        profile instead, off the smallest gap anywhere between when a program was reported to
        have started and when it was first seen.
      </template>
      <template v-else>
        Every program sits inside the tool call that started it, because both are timed against
        one clock. Now the eight seconds have a shape: two workers, one of which the run waited
        on.
      </template>
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.spacer {
  flex: 1;
}

.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  color: var(--vp-c-text-2);
}

.sw.off {
  opacity: 0.4;
  cursor: default;
}

.sw input {
  accent-color: var(--vp-c-brand-1);
}

.board {
  padding: 12px 16px 0;
}

.row {
  display: flex;
  align-items: stretch;
  gap: 10px;
  min-height: 26px;
}

.label {
  flex: none;
  width: 214px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  line-height: 1.15;
}

.label strong {
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  font-weight: 650;
}

.label span {
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.row.program .label span {
  color: var(--hmz-warm);
}

/* One line every four seconds, so the drift is read against something. */
.track {
  position: relative;
  flex: 1;
  min-width: 0;
  background-image: linear-gradient(90deg, var(--hmz-grid) 0 1px, transparent 1px 100%);
  background-size: 11.111% 100%;
}

.slice {
  position: absolute;
  top: 50%;
  height: 16px;
  transform: translateY(-50%);
  min-width: 3px;
  border-radius: 3px;
  padding: 0 5px;
  display: flex;
  align-items: center;
  overflow: hidden;
  white-space: nowrap;
  background: var(--tone);
  color: var(--vp-c-bg);
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  opacity: 0.86;
  cursor: default;
  transition: opacity 0.2s, left 0.4s ease;
}

.slice.think {
  opacity: 0.38;
  color: var(--vp-c-text-1);
}

.slice.prog {
  opacity: 0.72;
}

.slice.drifted {
  box-shadow: 0 0 0 1.5px var(--hmz-warm);
}

.ghost {
  position: absolute;
  top: 50%;
  height: 18px;
  transform: translateY(-50%);
  border: 1px dashed var(--hmz-warm);
  border-radius: 3px;
  opacity: 0.55;
}

.slice:hover {
  opacity: 1;
}

.caption {
  margin: 0;
  padding: 10px 16px 0;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.verdict {
  margin: 0;
  padding: 10px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.verdict.warn {
  color: var(--vp-c-text-2);
}

.verdict code {
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 5px;
  background: var(--vp-c-default-soft);
}

@media (max-width: 760px) {
  .label {
    width: 128px;
  }

  .label strong {
    font-size: 10.5px;
  }
}
</style>
