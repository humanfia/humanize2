<script setup lang="ts">
// Type something while the turn is running. On one side the words reach the turn that is
// already going; on the other they wait for it to end and start another. The queue rule, the
// pin and the "never quietly counted as said" ending are the ones `user/steering` describes.
import { computed, onMounted, onUnmounted, ref } from 'vue'

interface Line {
  id: number
  text: string
  state: 'pinned' | 'held' | 'taken' | 'late'
  said: number
}

interface Said {
  id: number
  text: string
  kind: 'tool' | 'you' | 'say' | 'edge'
}

const STEPS: { at: number; text: string; kind: 'tool' | 'say' }[] = [
  { at: 0.06, text: 'Read src/pay.py', kind: 'tool' },
  { at: 0.24, text: 'Grep "def charge"', kind: 'tool' },
  { at: 0.42, text: 'Edit src/pay.py', kind: 'tool' },
  { at: 0.62, text: 'Bash pytest -q', kind: 'tool' },
  { at: 0.88, text: 'says: the retry path was the one', kind: 'say' },
]

const SUGGESTED = ['actually, use pathlib', 'and fix the tests too', 'stop touching the CLI']

const TURN = 11 // seconds a turn takes here
const GAP = 2.6 // and the pause between two of them

const clock = ref(0)
const typed = ref('')
const lines = ref<Line[]>([])
const into = ref<Said[]>([])
const after = ref<Said[]>([])
const running = ref(true)

let frame = 0
let last = 0
let idle = false
let counter = 0
let epic = 0
let step = 0

const progress = computed(() => Math.min(1, clock.value / TURN))
const open = computed(() => clock.value < TURN)

function say(where: 'into' | 'after', text: string, kind: Said['kind']) {
  const said = { id: (counter += 1), text, kind }
  const list = where === 'into' ? into : after
  list.value = [...list.value.slice(-7), said]
}

function submit() {
  const text = typed.value.trim()
  if (!text) return
  typed.value = ''
  hand(text)
}

function hand(text: string) {
  lines.value = [
    ...lines.value,
    {
      id: (counter += 1),
      text,
      state: open.value ? 'pinned' : 'held',
      said: clock.value,
    },
  ]
}

function tick(now: number) {
  frame = requestAnimationFrame(tick)
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now
  if (!running.value || idle) return
  clock.value += dt

  // The turn says what it is doing as it does it, on both sides: the difference is not what
  // the agent does, it is when your line reaches it.
  while (step < STEPS.length && progress.value >= STEPS[step].at) {
    say('into', STEPS[step].text, STEPS[step].kind)
    say('after', STEPS[step].text, STEPS[step].kind)
    step += 1
  }

  // One at a time, in order: the next line goes only once the turn has said it has the one
  // before it, which here is a moment after it was typed.
  const waiting = lines.value.find((one) => one.state === 'pinned' || one.state === 'held')
  if (waiting) {
    if (waiting.state === 'held' && open.value) {
      waiting.state = 'pinned'
      waiting.said = clock.value
    } else if (waiting.state === 'pinned' && open.value && clock.value - waiting.said > 0.9) {
      waiting.state = 'taken'
      say('into', waiting.text, 'you')
      say('into', 'takes it into account', 'edge')
    }
  }

  if (clock.value >= TURN + GAP) {
    // The turn ended. Whatever was still waiting on the other side is a turn of its own now.
    const stale = lines.value.filter((one) => one.state === 'taken' || one.state === 'late')
    for (const one of stale) {
      if (one.state === 'taken') {
        one.state = 'late'
        say('after', one.text, 'you')
        say('after', `a turn of its own, ${Math.round(TURN - one.said)}s late`, 'edge')
      }
    }
    clock.value = 0
    step = 0
    epic += 1
    if (epic % 2 === 0) {
      into.value = []
      after.value = []
      lines.value = []
    }
  }
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    running.value = false
    clock.value = TURN * 0.5
    say('into', 'Read src/pay.py', 'tool')
    say('after', 'Read src/pay.py', 'tool')
    return
  }
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  last = performance.now()
  frame = requestAnimationFrame(tick)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})

const pinned = computed(() => lines.value.filter((one) => one.state !== 'late'))
</script>

<template>
  <div ref="root" class="steer hmz-panel">
    <div class="bar">
      <span class="live" :class="{ paused: !open || !running }">
        <i />
        {{ running ? (open ? 'a turn is running' : 'between turns') : 'paused' }}
      </span>
      <div class="track">
        <span class="fill" :style="{ width: `${progress * 100}%` }" />
      </div>
      <button class="toggle" type="button" @click="running = !running">
        {{ running ? '❙❙' : '▶' }}
      </button>
    </div>

    <div class="lanes">
      <section class="lane">
        <header>
          <strong>into the turn</strong>
          <span>humanize</span>
        </header>
        <ul>
          <li v-for="one in into" :key="one.id" :class="one.kind">
            <span class="mark">{{ one.kind === 'you' ? '❯' : one.kind === 'edge' ? '·' : '▸' }}</span>
            {{ one.text }}
          </li>
        </ul>
      </section>

      <section class="lane plain">
        <header>
          <strong>queued behind it</strong>
          <span>a prompt per turn</span>
        </header>
        <ul>
          <li v-for="one in after" :key="one.id" :class="one.kind">
            <span class="mark">{{ one.kind === 'you' ? '❯' : one.kind === 'edge' ? '·' : '▸' }}</span>
            {{ one.text }}
          </li>
        </ul>
        <p v-if="pinned.length" class="waiting">
          <span v-for="one in pinned" :key="one.id">❯ {{ one.text }}</span>
          <em>waiting for the turn to end</em>
        </p>
      </section>
    </div>

    <div class="editor">
      <div class="pins">
        <p v-for="one in pinned" :key="one.id" class="pin" :class="one.state">
          <span>❯</span> {{ one.text }}
          <em v-if="one.state === 'pinned'">· with claude#3a15</em>
          <em v-else-if="one.state === 'held'">· held for the next turn</em>
          <em v-else>· the words are in front of it</em>
        </p>
      </div>
      <form @submit.prevent="submit">
        <span class="caret">❯</span>
        <input
          v-model="typed"
          type="text"
          placeholder="say something to the turn that is running…"
          aria-label="a line typed mid-turn"
        />
        <button type="submit">enter</button>
      </form>
      <div class="chips">
        <button v-for="one in SUGGESTED" :key="one" type="button" @click="hand(one)">
          {{ one }}
        </button>
      </div>
    </div>

    <p class="note">
      There is no separate mode and no separate key: the editor means both things at once. A
      line joins one queue and leaves it a line at a time — the next goes only once the turn has
      said it has the one before it. A turn that ends without ever saying so puts the line back
      into the transcript <strong>as never sent</strong>.
    </p>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
}

.live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-2);
  font-weight: 600;
  white-space: nowrap;
}

.live i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--hmz-accent);
}

.live.paused i {
  background: var(--vp-c-text-3);
}

.track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--vp-c-default-soft);
  overflow: hidden;
}

.fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--vp-c-brand-1), var(--hmz-accent));
}

.toggle {
  min-width: 34px;
  padding: 3px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  cursor: pointer;
  font-size: 12px;
}

.lanes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 16px 0;
}

.lane {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.lane header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
}

.lane header strong {
  font-size: 12.5px;
  color: var(--vp-c-brand-1);
}

.lane.plain header strong {
  color: var(--vp-c-text-3);
}

.lane header span {
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.lane ul {
  list-style: none;
  margin: 0;
  padding: 10px 12px;
  min-height: 168px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.9;
  color: var(--vp-c-text-2);
}

.lane li {
  display: flex;
  gap: 8px;
  animation: land 0.35s ease;
}

.lane li .mark {
  color: var(--vp-c-text-3);
}

.lane li.you {
  color: var(--hmz-accent);
  font-weight: 600;
}

.lane li.edge {
  color: var(--vp-c-text-3);
  font-style: italic;
}

.lane li.say {
  color: var(--vp-c-text-1);
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

.waiting {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 8px 12px 10px;
  border-top: 1px dashed var(--vp-c-divider);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--hmz-warm);
}

.waiting em {
  font-style: normal;
  font-family: var(--vp-font-family-base);
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.editor {
  padding: 14px 16px 0;
}

.pins {
  min-height: 22px;
}

.pin {
  margin: 0 0 4px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-3);
}

.pin span {
  color: var(--vp-c-brand-1);
}

.pin.taken {
  color: var(--hmz-accent);
}

.pin em {
  font-style: normal;
  opacity: 0.7;
}

form {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
}

.caret {
  color: var(--vp-c-brand-1);
  font-family: var(--vp-font-family-mono);
}

form input {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-1);
  font-size: 13px;
  outline: none;
}

form button {
  padding: 3px 12px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
}

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 0 0;
}

.chips button {
  padding: 4px 11px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  cursor: pointer;
}

.chips button:hover {
  border-style: solid;
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.note {
  margin: 0;
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

@media (max-width: 720px) {
  .lanes {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
