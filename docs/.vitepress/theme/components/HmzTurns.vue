<script setup lang="ts">
// Turns are only sequential inside one session. Move the slider: the same twelve prompts,
// scheduled across as many conversations as you allow, and the wall clock is what changes.
// The one rule that trips people is the switch: two turns on one session are two turns, one
// after the other, however they are awaited.
import { computed, ref } from 'vue'

// Fixed, so the picture is the same every time it is read: a turn is not the same length as
// the turn beside it, and a schedule drawn on equal blocks would be a schedule that lies.
const MINUTES = [3.1, 1.4, 4.2, 2.0, 1.1, 3.6, 2.7, 1.8, 5.0, 2.3, 1.6, 3.3]
const FILES = [
  'parser.py',
  'printer.py',
  'cli.py',
  'pay.py',
  'retry.py',
  'store.py',
  'verses.py',
  'skills.py',
  'runner.py',
  'epic.py',
  'kept.py',
  'models.py',
]

interface Where {
  key: string
  said: string
  about: string
}

const WHERE: Where[] = [
  {
    key: 'here',
    said: 'this machine',
    about: 'Every session is rooted at the directory the flow runs in, which is where they all worked before there was anywhere else to put one.',
  },
  {
    key: 'worktrees',
    said: 'a worktree apiece',
    about: 'A conversation is rooted at a directory and every turn of it runs there — so a worktree per task is a session per task, and one agent works in all of them at once.',
  },
  {
    key: 'containers',
    said: 'a container apiece',
    about: 'What is isolated is the tools a command finds, not the work: the agent goes on running here, with its own credentials and its own trajectory, and only what it does reaches the container.',
  },
  {
    key: 'target',
    said: 'an ssh target',
    about: 'The agent stays here and its commands land there — one build box, as many conversations as you like against it.',
  },
]

const width = ref(4)
const shared = ref(false)
const where = ref(0)

interface Block {
  file: string
  lane: number
  t0: number
  t1: number
}

const schedule = computed(() => {
  const lanes = shared.value ? 1 : Math.max(1, width.value)
  const free = Array.from({ length: lanes }, () => 0)
  const blocks: Block[] = []
  MINUTES.forEach((minutes, i) => {
    let lane = 0
    for (let j = 1; j < free.length; j += 1) if (free[j] < free[lane]) lane = j
    const t0 = free[lane]
    free[lane] = t0 + minutes
    blocks.push({ file: FILES[i], lane, t0, t1: free[lane] })
  })
  return blocks
})

const serial = MINUTES.reduce((sum, one) => sum + one, 0)
const makespan = computed(() => Math.max(...schedule.value.map((one) => one.t1)))
const lanes = computed(() => Math.max(...schedule.value.map((one) => one.lane)) + 1)
const scale = computed(() => 1000 / serial)
const height = computed(() => lanes.value * 22 + 8)
</script>

<template>
  <div class="turns hmz-panel">
    <div class="bar">
      <label class="slider">
        <span>conversations at once</span>
        <input v-model.number="width" type="range" min="1" max="12" step="1" :disabled="shared" />
        <b>{{ shared ? 1 : width }}</b>
      </label>
      <label class="sw">
        <input v-model="shared" type="checkbox" />
        all of them on one session
      </label>
      <div class="spacer" />
      <span class="clock">
        <b>{{ makespan.toFixed(1) }}</b> minutes of wall clock ·
        <em>{{ serial.toFixed(1) }} of model time</em>
      </span>
    </div>

    <div class="chart">
      <svg :viewBox="`0 0 1000 ${height}`" role="img" aria-label="twelve prompts, scheduled">
        <rect
          v-for="(one, i) in schedule"
          :key="i"
          :x="one.t0 * scale"
          :y="one.lane * 22 + 4"
          :width="Math.max(4, (one.t1 - one.t0) * scale - 3)"
          height="16"
          rx="4"
          class="block"
          :style="{ '--tone': `var(--hmz-lane-${(one.lane % 6) + 1})` }"
        />
        <text
          v-for="(one, i) in schedule"
          :key="`t${i}`"
          :x="one.t0 * scale + 6"
          :y="one.lane * 22 + 16"
          class="who"
        >
          {{ (one.t1 - one.t0) * scale > 62 ? one.file : '' }}
        </text>
        <line
          :x1="makespan * scale"
          :x2="makespan * scale"
          y1="0"
          :y2="height"
          class="edge"
        />
      </svg>
      <p class="axis">
        <span>0</span>
        <span class="end">{{ serial.toFixed(0) }} minutes, if they went one after another</span>
      </p>
    </div>

    <div class="where">
      <div class="chips">
        <button
          v-for="(one, i) in WHERE"
          :key="one.key"
          type="button"
          :class="{ on: where === i }"
          @click="where = i"
        >
          {{ one.said }}
        </button>
      </div>
      <p class="about">{{ WHERE[where].about }}</p>
    </div>

    <p class="note" :class="{ warn: shared }">
      <template v-if="shared">
        One session, and the width does nothing. A conversation is a conversation: two turns
        awaited on it run one after the other, exactly as two called on it do. Two turns at once
        means two <strong>sessions</strong>.
      </template>
      <template v-else>
        One agent — one set of settings, one id, one place in the trace — holding
        {{ lanes }} conversation{{ lanes === 1 ? '' : 's' }}. A session costs nothing until a
        turn lands in one, so ten thousand of them up front is a list, not a bill.
      </template>
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.slider,
.sw {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  cursor: pointer;
}

.slider input {
  width: 132px;
  accent-color: var(--vp-c-brand-1);
}

.sw input {
  accent-color: var(--vp-c-brand-1);
}

.slider b,
.clock b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
  font-variant-numeric: tabular-nums;
}

.clock em {
  font-style: normal;
  color: var(--vp-c-text-3);
}

.spacer {
  flex: 1;
}

.chart {
  padding: 14px 16px 0;
}

svg {
  display: block;
  width: 100%;
  height: auto;
}

.block {
  fill: var(--tone);
  opacity: 0.85;
  transition: x 0.35s ease, y 0.35s ease, width 0.35s ease;
}

.who {
  fill: var(--vp-c-bg);
  font-size: 9.5px;
  font-family: var(--vp-font-family-mono);
  pointer-events: none;
}

.edge {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  transition: x1 0.35s ease, x2 0.35s ease;
}

.axis {
  display: flex;
  justify-content: space-between;
  margin: 4px 0 0;
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.where {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 14px 16px 0;
  flex-wrap: wrap;
}

.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.chips button {
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  cursor: pointer;
}

.chips button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.where .about {
  flex: 1;
  min-width: 260px;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

.note {
  margin: 0;
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .clock {
    width: 100%;
  }
}
</style>
