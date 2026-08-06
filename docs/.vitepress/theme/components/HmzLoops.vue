<script setup lang="ts">
// A flow is a Python function that drives agents. What differs between one loop and the next
// is where the turns go: a session apiece, one session held, two agents handing to each other,
// or two hundred at once -- and what runs between them is ordinary code.
import { computed, onMounted, onUnmounted, ref } from 'vue'

interface Beat {
  lane: number // -1 is the flow's own code, between the turns
  text: string
  fresh?: boolean
  shaped?: boolean
}

interface Shape {
  key: string
  name: string
  about: string
  lanes: string[]
  beats: Beat[]
  carries: string
}

const SHAPES: Shape[] = [
  {
    key: 'chat',
    name: 'a conversation',
    about:
      'The flow waits for the next thing to say and says it. Between two turns it is a Python function sitting on a call that has not returned yet.',
    lanes: ['one session, held'],
    carries: 'everything: one conversation, and every turn of it in context',
    beats: [
      { lane: -1, text: 'waits for the next thing to say' },
      { lane: 0, text: 'a turn' },
      { lane: -1, text: 'waits again' },
      { lane: 0, text: 'a turn' },
      { lane: -1, text: 'nothing more to say · the flow returns' },
    ],
  },
  {
    key: 'ralph',
    name: 'ralph',
    about:
      'A session of its own each round: the agent starts from the task and the repository with nothing of the last round in context. The repository is the memory.',
    lanes: ['a session per round'],
    carries: 'nothing in context — only which round it is on, written into the state',
    beats: [
      { lane: -1, text: 'rounds += 1 · written down as it is set' },
      { lane: 0, text: 'a turn on the task', fresh: true },
      { lane: -1, text: 'sleep 5' },
      { lane: 0, text: 'a turn on the task', fresh: true },
      { lane: -1, text: 'sleep 5' },
      { lane: 0, text: 'a turn on the task', fresh: true },
    ],
  },
  {
    key: 'stateful',
    name: 'stateful ralph',
    about:
      'One session, opened once and held for as long as the flow runs, re-sent the same task every round. The conversation is what the flow is.',
    lanes: ['one session, opened once'],
    carries: 'the whole conversation — and a run picked up again cannot have it back',
    beats: [
      { lane: -1, text: 'agent.new() · one session' },
      { lane: 0, text: 'the task' },
      { lane: 0, text: 'the task again' },
      { lane: 0, text: 'the task again' },
      { lane: -1, text: 'and on, until it is stopped' },
    ],
  },
  {
    key: 'reviewed',
    name: 'an actor and a reviewer',
    about:
      'Two agents. One works in a session it keeps; the other is asked, in a session of its own, for an answer in a shape — so the loop reads a field rather than searching a paragraph.',
    lanes: ['actor · one session', 'reviewer · a session per round'],
    carries: 'the actor’s conversation, and one field out of the reviewer’s',
    beats: [
      { lane: 0, text: 'builds' },
      { lane: 1, text: 'reads the diff → done: false', fresh: true, shaped: true },
      { lane: -1, text: 'if review.done: return' },
      { lane: 0, text: 'the notes, word for word' },
      { lane: 1, text: 'reads it again → done: true', fresh: true, shaped: true },
      { lane: -1, text: 'the reviewer says it is finished' },
    ],
  },
  {
    key: 'fanout',
    name: 'a fan-out',
    about:
      'One agent, a session per file, all of them going at once. Written as a coroutine, because the loop has to wait for more than one thing.',
    lanes: ['session · parser', 'session · printer', 'session · cli'],
    carries: 'one agent, one set of settings, one place in the trace — three conversations',
    beats: [
      { lane: -1, text: 'a worktree apiece' },
      { lane: 0, text: 'a turn', fresh: true },
      { lane: 1, text: 'a turn', fresh: true },
      { lane: 2, text: 'a turn', fresh: true },
      { lane: -1, text: 'gathered, in the order they were asked' },
    ],
  },
]

const shape = ref(1)
const at = ref(0)
const playing = ref(true)
const picked = computed(() => SHAPES[shape.value])

let timer = 0
let idle = false

function beat() {
  if (!playing.value || idle) return
  at.value = at.value + 1 > picked.value.beats.length ? 0 : at.value + 1
}

function pick(i: number) {
  shape.value = i
  at.value = 0
}

function step() {
  playing.value = false
  at.value = at.value + 1 > picked.value.beats.length ? 0 : at.value + 1
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    playing.value = false
    at.value = picked.value.beats.length
    return
  }
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  timer = window.setInterval(beat, 1100)
})

onUnmounted(() => {
  window.clearInterval(timer)
  observer?.disconnect()
})

const shown = computed(() => picked.value.beats.slice(0, at.value))
const turns = computed(() => shown.value.filter((one) => one.lane >= 0).length)
const opened = computed(
  () =>
    new Set(
      shown.value
        .filter((one) => one.lane >= 0)
        .map((one, i) => (one.fresh ? `${one.lane}:${i}` : `${one.lane}`)),
    ).size,
)
</script>

<template>
  <div ref="root" class="loops hmz-panel">
    <div class="bar">
      <div class="tabs" role="group" aria-label="which loop">
        <button
          v-for="(one, i) in SHAPES"
          :key="one.key"
          type="button"
          :class="{ on: shape === i }"
          @click="pick(i)"
        >
          {{ one.name }}
        </button>
      </div>
      <div class="spacer" />
      <button class="ctl" type="button" @click="step">step</button>
      <button class="ctl" type="button" @click="playing = !playing">
        {{ playing ? '❙❙' : '▶' }}
      </button>
    </div>

    <p class="about">{{ picked.about }}</p>

    <div class="stage">
      <div class="lanes">
        <div v-for="(lane, i) in picked.lanes" :key="lane" class="lane">
          <span class="tag" :style="{ '--tone': `var(--hmz-lane-${i + 1})` }">{{ lane }}</span>
          <div class="slots">
            <template v-for="(one, j) in shown" :key="j">
              <span
                v-if="one.lane === i"
                class="turn"
                :class="{ fresh: one.fresh, shaped: one.shaped }"
                :style="{ '--tone': `var(--hmz-lane-${i + 1})` }"
              >
                {{ one.text }}
              </span>
              <span v-else class="hole" />
            </template>
          </div>
        </div>

        <div class="lane code">
          <span class="tag py">the flow, between the turns</span>
          <div class="slots">
            <template v-for="(one, j) in shown" :key="j">
              <span v-if="one.lane === -1" class="py-beat">{{ one.text }}</span>
              <span v-else class="hole" />
            </template>
          </div>
        </div>
      </div>
    </div>

    <div class="foot">
      <span><b>{{ turns }}</b> turns</span>
      <span><b>{{ opened }}</b> sessions opened</span>
      <span class="carries">what the next turn starts from: {{ picked.carries }}</span>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tabs button {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.spacer {
  flex: 1;
}

.ctl {
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  cursor: pointer;
}

.ctl:hover {
  color: var(--vp-c-brand-1);
}

.about {
  margin: 0;
  padding: 12px 16px 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.stage {
  padding: 12px 16px 0;
  overflow-x: auto;
}

.lane {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
  min-width: 640px;
}

.tag {
  flex: none;
  width: 152px;
  font-size: 10.5px;
  line-height: 1.35;
  font-family: var(--vp-font-family-mono);
  color: var(--tone, var(--vp-c-text-3));
}

.tag.py {
  color: var(--vp-c-text-3);
  font-style: italic;
}

.slots {
  display: flex;
  gap: 8px;
  flex: 1;
}

.turn,
.py-beat,
.hole {
  flex: 1;
  min-width: 0;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  font-size: 11px;
  text-align: center;
  line-height: 1.25;
  animation: land 0.35s ease;
}

.turn {
  background: color-mix(in srgb, var(--tone) 18%, transparent);
  border: 1px solid var(--tone);
  color: var(--vp-c-text-1);
}

.turn.fresh {
  border-style: dashed;
}

.turn.shaped {
  box-shadow: inset 0 -3px 0 0 var(--hmz-accent);
}

.py-beat {
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
}

.hole {
  background: transparent;
  animation: none;
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(5px) scale(0.97);
  }
}

.foot {
  display: flex;
  align-items: baseline;
  gap: 18px;
  flex-wrap: wrap;
  padding: 14px 16px 16px;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.foot b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
  font-size: 13px;
}

.carries {
  flex: 1;
  min-width: 220px;
}

@media (prefers-reduced-motion: reduce) {
  .turn,
  .py-beat {
    animation: none;
  }
}
</style>
