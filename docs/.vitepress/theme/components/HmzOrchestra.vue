<script setup lang="ts">
// A run of a flow, drawn as it happens: one lane per agent, and every turn's tool calls
// landing on the trace strip underneath the way `hmz trace collect` lands them in Perfetto.
// The motion is a simulation of the shape of a run -- the real screens are in the gallery.
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'

type Kind = 'tool' | 'think' | 'say' | 'wait'

interface Agent {
  spec: string
  role: string
  human?: boolean
}

interface Slice {
  id: number
  lane: number
  label: string
  kind: Kind
  t0: number
  t1: number
}

const AGENTS: Agent[] = [
  { spec: 'claude/claude-opus-5:high', role: 'writes the kernel' },
  { spec: 'codex/gpt-5.6-sol:high', role: 'reads what landed' },
  { spec: 'dsh/deepseek-v4-pro:high', role: 'runs the benchmark' },
  { spec: 'kimi/kimi-code/k3:high', role: 'ports the module' },
  { spec: 'pi/openai-codex/gpt-5.5:high', role: 'reviews the diff' },
  { spec: 'human', role: 'answers when asked', human: true },
]

const TOOLS = ['Read', 'Bash', 'Edit', 'Grep', 'Write', 'Task', 'WebFetch', 'Glob']
const WINDOW = 22 // seconds of trace kept on screen
const COUNTS = [2, 4, 6]

const count = ref(4)
const running = ref(true)
const clock = ref(0)
const slices = shallowRef<Slice[]>([])
const hovered = ref<Slice | null>(null)
const focused = ref<number | null>(null)

const lanes = computed(() => AGENTS.slice(0, count.value))
const laneHeight = 26
const stripHeight = computed(() => lanes.value.length * laneHeight + 8)

let seed = 20260817
const rand = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)
const between = (lo: number, hi: number) => lo + rand() * (hi - lo)

interface Running {
  label: string
  kind: Kind
  t0: number
  t1: number
  tokens: number
  rate: number
}

const busy = ref<Running[]>([])
let counter = 0

function begin(lane: number, at: number): Running {
  const agent = AGENTS[lane]
  if (agent.human) {
    const asked = rand() < 0.35
    return {
      label: asked ? 'answers' : 'waiting to be asked',
      kind: asked ? 'say' : 'wait',
      t0: at,
      t1: at + (asked ? between(0.8, 1.6) : between(2.4, 5)),
      tokens: 0,
      rate: 0,
    }
  }
  const roll = rand()
  const kind: Kind = roll < 0.46 ? 'tool' : roll < 0.84 ? 'think' : 'say'
  const label =
    kind === 'tool'
      ? TOOLS[Math.floor(rand() * TOOLS.length)]
      : kind === 'think'
        ? 'thinking'
        : 'says'
  return {
    label,
    kind,
    t0: at,
    t1: at + (kind === 'tool' ? between(0.5, 2.8) : between(0.6, 2.2)),
    tokens: 0,
    rate: between(38, 190),
  }
}

function reset() {
  clock.value = 0
  counter = 0
  slices.value = []
  busy.value = lanes.value.map((_, lane) => begin(lane, between(0, 1.4)))
  // A run that has been going a while, so the strip is never a blank rectangle waiting to
  // be filled: what you scroll onto is a trace already being written.
  for (let i = 0; i < 640; i += 1) step(0.05)
}

function step(dt: number) {
  clock.value += dt
  const now = clock.value
  let landed = false
  const next = busy.value.slice()
  for (let lane = 0; lane < next.length; lane += 1) {
    const run = next[lane]
    run.tokens += run.rate * dt
    if (now >= run.t1) {
      slices.value = [
        ...slices.value,
        { id: (counter += 1), lane, label: run.label, kind: run.kind, t0: run.t0, t1: run.t1 },
      ]
      next[lane] = begin(lane, run.t1)
      landed = true
    }
  }
  busy.value = next
  const left = now - WINDOW
  if (landed && slices.value.length > 160) {
    slices.value = slices.value.filter((s) => s.t1 > left)
  }
}

let frame = 0
let last = 0
let idle = false

function loop(at: number) {
  frame = requestAnimationFrame(loop)
  const dt = Math.min((at - last) / 1000, 0.1)
  last = at
  if (running.value && !idle) step(dt * 1.35)
}

let observer: IntersectionObserver | undefined
const root = ref<HTMLElement | null>(null)

onMounted(() => {
  reset()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    running.value = false // the filled strip above is the whole of it: no animation
    return
  }
  observer = new IntersectionObserver((entries) => (idle = !entries[0].isIntersecting), {
    rootMargin: '120px',
  })
  if (root.value) observer.observe(root.value)
  last = performance.now()
  frame = requestAnimationFrame(loop)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})

function setCount(n: number) {
  count.value = n
  focused.value = null
  reset()
}

const left = computed(() => Math.max(0, clock.value - WINDOW))
const scale = 1000 / WINDOW
const x = (t: number) => (t - left.value) * scale
const drawn = computed(() =>
  slices.value
    .filter((s) => s.t1 > left.value)
    .map((s) => ({ slice: s, x: x(s.t0), w: Math.max(3, (s.t1 - s.t0) * scale) })),
)
const ticks = computed(() => {
  const first = Math.ceil(left.value / 4) * 4
  return Array.from({ length: 6 }, (_, i) => first + i * 4).filter((t) => t <= clock.value)
})
const caption = computed(() => {
  if (hovered.value) {
    const s = hovered.value
    const agent = AGENTS[s.lane]
    return `${s.label} · ${(s.t1 - s.t0).toFixed(1)}s · ${agent.spec}`
  }
  const n = drawn.value.length
  return `${lanes.value.length} agents · ${n} slice${n === 1 ? '' : 's'} on screen · one track per row of an agent's sessions`
})
</script>

<template>
  <div ref="root" class="orchestra hmz-panel">
    <div class="bar">
      <span class="live" :class="{ paused: !running }">
        <i />
        {{ running ? 'running' : 'paused' }}
      </span>
      <code class="flow">hmz exec -f official/flame_chase</code>
      <div class="spacer" />
      <div class="counts" role="group" aria-label="how many agents">
        <button
          v-for="n in COUNTS"
          :key="n"
          type="button"
          :class="{ on: count === n }"
          @click="setCount(n)"
        >
          {{ n }}
        </button>
      </div>
      <button class="toggle" type="button" @click="running = !running">
        {{ running ? '❙❙' : '▶' }}
      </button>
    </div>

    <div class="lanes">
      <div
        v-for="(agent, lane) in lanes"
        :key="agent.spec"
        class="lane"
        :class="{ dim: focused !== null && focused !== lane }"
        :style="{ '--tone': `var(--hmz-lane-${lane + 1})` }"
        @mouseenter="focused = lane"
        @mouseleave="focused = null"
      >
        <span class="dot" />
        <code class="spec">{{ agent.spec }}</code>
        <span class="role">{{ agent.role }}</span>
        <span class="doing" :class="busy[lane]?.kind">{{ busy[lane]?.label }}</span>
        <span class="tok">{{ Math.round(busy[lane]?.tokens ?? 0) }} tok</span>
      </div>
    </div>

    <div class="strip">
      <svg
        :viewBox="`0 0 1000 ${stripHeight}`"
        role="img"
        aria-label="a trace being written as the run happens"
      >
        <line
          v-for="t in ticks"
          :key="t"
          :x1="x(t)"
          :x2="x(t)"
          y1="0"
          :y2="stripHeight"
          class="tick"
        />
        <g v-for="item in drawn" :key="item.slice.id">
          <rect
            :x="item.x"
            :y="item.slice.lane * laneHeight + 6"
            :width="item.w"
            :height="laneHeight - 10"
            rx="3"
            class="slice"
            :class="[item.slice.kind, { dim: focused !== null && focused !== item.slice.lane }]"
            :style="{ '--tone': `var(--hmz-lane-${item.slice.lane + 1})` }"
            @mouseenter="hovered = item.slice"
            @mouseleave="hovered = null"
          />
          <text
            v-if="item.w > 52"
            :x="item.x + 7"
            :y="item.slice.lane * laneHeight + laneHeight / 2 + 2"
            class="label"
            :class="[item.slice.kind, { dim: focused !== null && focused !== item.slice.lane }]"
          >
            {{ item.slice.label }}
          </text>
        </g>
        <line x1="1000" x2="1000" y1="0" :y2="stripHeight" class="head" />
      </svg>
    </div>

    <p class="caption">{{ caption }}</p>
  </div>
</template>

<style scoped>
.orchestra {
  --tone: var(--hmz-lane-1);
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
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
}

.live i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--hmz-accent);
  box-shadow: 0 0 0 0 var(--hmz-accent);
  animation: pulse 2s ease-out infinite;
}

.live.paused i {
  background: var(--vp-c-text-3);
  animation: none;
}

@keyframes pulse {
  70% {
    box-shadow: 0 0 0 7px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}

.flow {
  color: var(--vp-c-text-3);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.spacer {
  flex: 1;
}

.counts {
  display: inline-flex;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  overflow: hidden;
}

.counts button,
.toggle {
  padding: 4px 10px;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.counts button.on {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.toggle {
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  min-width: 34px;
}

.counts button:hover,
.toggle:hover {
  color: var(--vp-c-brand-1);
}

.lanes {
  padding: 10px 14px 4px;
}

.lane {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 8px;
  border-radius: 8px;
  font-size: 12px;
  transition: background 0.2s, opacity 0.2s;
}

.lane:hover {
  background: var(--vp-c-default-soft);
}

.lane.dim {
  opacity: 0.34;
}

.dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: var(--tone);
  box-shadow: 0 0 8px var(--tone);
}

.spec {
  color: var(--vp-c-text-1);
  font-weight: 600;
  white-space: nowrap;
}

.role {
  color: var(--vp-c-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.doing {
  flex: none;
  min-width: 118px;
  text-align: right;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--tone);
}

.doing.think {
  color: var(--vp-c-text-3);
  font-style: italic;
}

.doing.wait {
  color: var(--vp-c-text-3);
}

.tok {
  flex: none;
  width: 74px;
  text-align: right;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
  font-variant-numeric: tabular-nums;
}

.strip {
  margin: 6px 14px 0;
  border-top: 1px solid var(--hmz-panel-border);
  background: linear-gradient(180deg, var(--vp-c-bg-alt), transparent);
}

svg {
  display: block;
  width: 100%;
  height: auto;
}

.tick {
  stroke: var(--hmz-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.slice {
  fill: var(--tone);
  opacity: 0.86;
  transition: opacity 0.2s;
}

.slice.think {
  opacity: 0.4;
}

.slice.wait {
  fill: var(--vp-c-text-3);
  opacity: 0.22;
}

.slice.dim {
  opacity: 0.12;
}

.slice:hover {
  opacity: 1;
}

.label {
  fill: var(--vp-c-bg);
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  pointer-events: none;
}

/* A thinking slice is drawn faint, so its label is read against the panel rather than
   against the slice. */
.label.think,
.label.wait {
  fill: var(--vp-c-text-2);
}

.label.dim {
  opacity: 0.15;
}

.head {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  filter: drop-shadow(0 0 4px var(--hmz-accent));
}

.caption {
  margin: 0;
  padding: 8px 16px 12px;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

@media (prefers-reduced-motion: reduce) {
  .live i {
    animation: none;
  }
}

@media (max-width: 720px) {
  .role,
  .tok {
    display: none;
  }

  .spec {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Narrow enough that scaling the strip to fit would make every label a smudge, so it
     keeps its size and scrolls instead -- starting at the right, where the newest is. */
  .strip {
    overflow-x: auto;
    direction: rtl;
  }

  .strip svg {
    width: 680px;
    direction: ltr;
  }
}

@media (max-width: 560px) {
  .flow {
    display: none;
  }
}
</style>
