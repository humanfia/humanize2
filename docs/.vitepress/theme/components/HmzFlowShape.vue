<script setup lang="ts">
// A run of one flow, played. One lane per agent, one box per turn, and a head that walks the
// rounds at the speed of about a second each.
//
// The thing the diagram is for is the distinction the flows differ by and prose keeps losing:
// which turns opened a session and which took another turn of the one they had. A `new` box
// carries a filled pip; a `held` box is joined to the turn before it by a bar. Everything else
// on it -- what a turn hands the next one, what the arc at the end goes back to, what the run
// is spending -- is read off `theme/flows.ts`, which is read off the flows themselves.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { SHAPES, type Shape, type Step } from '../flows'

const props = defineProps<{
  /** The shape to play, by its key in SHAPES. */
  flow?: string
  /** Several of them, as a comma-separated list, with a strip to pick between. */
  pick?: string
}>()

const offered = computed(() =>
  (props.pick ?? props.flow ?? '')
    .split(',')
    .map((one) => one.trim())
    .filter((one) => one in SHAPES),
)

const at = ref(0)
const shape = computed<Shape>(() => SHAPES[offered.value[at.value]] ?? SHAPES.ralph_loop)

/* The geometry. One viewBox, 760 wide, however many lanes the flow has -- narrow rather than
   wide because the drawing scales to the column it is in, and a 1000-unit box in a 780-pixel
   column renders every label a fifth smaller than it was written. */
const WIDE = 760
const LABEL = 150
const RIGHT = 18
const LANE_H = 62
const BOX_H = 34
const TOP = 16
const ARC = 30 // the band under the lanes the arc back is drawn in, where there is one
const METER = 42 // and the one under that, where something other than the flow stops it
const GAUGE = 64 // which the governed loop's bar chart wants more of than the budget's bar
const TAIL = 1.1 // columns of time the head parks at the end, while the arc goes back

const cols = computed(() => Math.max(...shape.value.steps.map((s) => s.col + (s.span ?? 1))))
const colw = computed(() => (WIDE - LABEL - RIGHT) / cols.value)
const floor = computed(() => TOP + shape.value.lanes.length * LANE_H)
const under = computed(() => floor.value + (shape.value.loop ? ARC : 6))
const deep = computed(() =>
  !shape.value.meter ? 6 : shape.value.meter.kind === 'juice' ? GAUGE : METER,
)
const height = computed(() => under.value + deep.value)

const laneAt = (id: string) => shape.value.lanes.findIndex((lane) => lane.id === id)
/** The colour a lane takes. Named where two lanes are two halves of one thing. */
const toneOf = (id: string) => {
  const lane = shape.value.lanes[laneAt(id)]
  return `var(--hmz-lane-${((lane?.tone ?? laneAt(id) + 1) - 1) % 6 + 1})`
}
const laneY = (id: string) => TOP + laneAt(id) * LANE_H
const boxY = (id: string) => laneY(id) + 11
const midY = (id: string) => boxY(id) + BOX_H / 2
const x0 = (step: Step) => LABEL + step.col * colw.value + 5
const x1 = (step: Step) => LABEL + (step.col + (step.span ?? 1)) * colw.value - 5

/* The clock. One column a beat, then a beat at the end for the arc back. */
const BEAT = 1.05 // seconds a column takes
const t = ref(0)
const pass = ref(0)
const running = ref(true)
const onScreen = ref(true)
const still = ref(false) // reduced motion: drawn once, at rest, finished
const held = ref<Step | null>(null)

const backTo = computed(() => {
  const loop = shape.value.loop
  if (!loop) return 0
  return shape.value.steps.find((s) => s.id === loop.to)?.col ?? 0
})

function restart() {
  // Under reduced motion the diagram is the whole run at rest, so picking another flow shows
  // that flow finished rather than that flow never started.
  t.value = still.value ? cols.value + TAIL : 0
  pass.value = still.value ? 1 : 0
}

watch(shape, restart)

let frame = 0
let last = 0

function tick(now: number) {
  frame = requestAnimationFrame(tick)
  const dt = Math.min((now - last) / 1000, 0.12)
  last = now
  if (!running.value || !onScreen.value || still.value) return
  t.value += dt / BEAT
  if (t.value >= cols.value + TAIL) {
    // Back to where the loop says it goes, and not to the beginning: what happened before the
    // loop -- a coordinator that planned once, an idea that was drafted -- happened once.
    t.value = shape.value.loop ? backTo.value : 0
    pass.value += 1
  }
}

const root = ref<HTMLElement | null>(null)
let watcher: IntersectionObserver | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    // Everything landed, nothing moving: a diagram of the whole run rather than of a moment.
    still.value = true
    t.value = cols.value + TAIL
    pass.value = 1
    return
  }
  watcher = new IntersectionObserver((seen) => (onScreen.value = seen[0].isIntersecting), {
    rootMargin: '140px',
  })
  if (root.value) watcher.observe(root.value)
  last = performance.now()
  frame = requestAnimationFrame(tick)
})

onUnmounted(() => {
  cancelAnimationFrame(frame)
  watcher?.disconnect()
})

/* What each step is doing at time t. */
type State = 'waiting' | 'running' | 'landed'

function state(step: Step): State {
  const ends = step.col + (step.span ?? 1)
  if (t.value >= ends) return 'landed'
  if (t.value >= step.col) return 'running'
  // A step before the point the loop goes back to has already happened, once.
  return pass.value > 0 && step.col < backTo.value ? 'landed' : 'waiting'
}

/** How far through its own turn a running box is, 0 to 1. */
function through(step: Step) {
  const span = step.span ?? 1
  return Math.min(1, Math.max(0, (t.value - step.col) / span))
}

const byId = computed(() => new Map(shape.value.steps.map((s) => [s.id, s])))

interface Wire {
  key: string
  d: string
  said: string
  live: boolean
  /** Where the thing being handed over has got to. */
  bead: { x: number; y: number }
  /** Where the label goes, which is the middle of the curve. */
  mid: { x: number; y: number }
  tone: string
}

/** A point on the cubic the wire is drawn as -- the bead has to sit on the line it follows. */
const cubic = (a: number, b: number, c: number, d: number, p: number) => {
  const q = 1 - p
  return q * q * q * a + 3 * q * q * p * b + 3 * q * p * p * c + p * p * p * d
}

const wires = computed<Wire[]>(() => {
  const out: Wire[] = []
  for (const step of shape.value.steps) {
    for (const carry of step.carry ?? []) {
      const to = byId.value.get(carry.to)
      if (!to) continue
      const ends = step.col + (step.span ?? 1)
      const over = Math.max(0.6, to.col - ends)
      const p = Math.min(1, Math.max(0, (t.value - ends) / over))
      const ax = x1(step)
      const ay = midY(step.lane)
      const bx = x0(to)
      const by = midY(to.lane)
      // Clamped so the handles never cross: two boxes a few pixels apart on different lanes
      // want a near-vertical hop, not a loop back on itself.
      const bend = Math.min(40, Math.max(0, (bx - ax) / 2))
      const [c1x, c1y, c2x, c2y] =
        ay === by ? [ax, ay, bx, by] : [ax + bend, ay, bx - bend, by]
      const on = (q: number) => ({
        x: cubic(ax, c1x, c2x, bx, q),
        y: cubic(ay, c1y, c2y, by, q),
      })
      out.push({
        key: `${step.id}-${carry.to}`,
        d: `M ${ax} ${ay} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${bx} ${by}`,
        said: carry.said,
        live: p > 0 && p < 1,
        bead: on(p),
        // A wire between two lanes has a gap of its own to put the label in; one along a lane
        // has only the lane, so its label goes above the line rather than on it.
        mid: { x: on(0.5).x, y: ay === by ? ay - 9 : on(0.5).y + 3 },
        tone: toneOf(step.lane),
      })
    }
  }
  return out
})

/** The bar that joins a held turn to the one it is continuing. */
const bands = computed(() => {
  const out: { key: string; x: number; w: number; y: number; tone: string; on: boolean }[] = []
  const seen = new Map<string, Step>()
  for (const step of [...shape.value.steps].sort((a, b) => a.col - b.col)) {
    const before = seen.get(step.lane)
    if (step.session === 'held' && before) {
      out.push({
        key: `${before.id}-${step.id}`,
        x: x1(before),
        w: Math.max(0, x0(step) - x1(before)),
        y: midY(step.lane) - 1.5,
        tone: toneOf(step.lane),
        on: state(step) !== 'waiting',
      })
    }
    if (step.session !== 'none') seen.set(step.lane, step)
  }
  return out
})

/** The arc back to the round's beginning. */
const arc = computed(() => {
  const loop = shape.value.loop
  if (!loop) return null
  const from = byId.value.get(loop.from)
  const to = byId.value.get(loop.to)
  if (!from || !to) return null
  const ax = x1(from)
  const bx = x0(to)
  const low = floor.value + 12
  return {
    d: `M ${ax} ${midY(from.lane)} C ${ax + 40} ${low}, ${bx - 40} ${low}, ${bx} ${midY(to.lane)}`,
    said: loop.said,
    live: t.value >= cols.value,
    x: (ax + bx) / 2,
    y: low + 12,
  }
})

/* The bar underneath, for the flows that something other than the flow stops. */
const meterY = computed(() => under.value + 8)

/** Millions of output tokens the loop has spent, of the ten it comes with. */
const spent = computed(() =>
  Math.min(9.4, (pass.value * cols.value + Math.min(t.value, cols.value)) * 0.42),
)

//: What four rounds of a governed loop measured, in output tokens an average turn came out
//: with. The target is 2000, and the point of the picture is that the loop walks onto it.
const JUICE = [1180, 1590, 2080, 1960, 2030]

/** The floor the bars of a governed loop stand on. */
const base = computed(() => meterY.value + 34)

/** Where the top of a bar of that many output tokens goes. */
const tall = (juice: number) => base.value - Math.max(3, (juice - 700) / 60)

const head = computed(() => LABEL + Math.min(t.value, cols.value) * colw.value)

const caption = computed(() => {
  const step = held.value
  if (!step) return shape.value.caption
  const said =
    step.session === 'new'
      ? 'a session opened for this turn'
      : step.session === 'held'
        ? 'another turn of the session above'
        : 'no turn of a model at all'
  const lane = shape.value.lanes[laneAt(step.lane)]
  return `${lane?.name ?? step.lane} — ${step.label} · ${said}`
})

/** A label that fits the box it is in, over one line or two. */
function lines(label: string, width: number) {
  const room = Math.max(6, Math.floor(width / 6.3))
  if (label.length <= room) return [label]
  const words = label.split(' ')
  const one: string[] = []
  while (words.length && [...one, words[0]].join(' ').length <= room) one.push(words.shift()!)
  const two = words.join(' ')
  if (!one.length) return [label.slice(0, room - 1) + '…']
  return [one.join(' '), two.length > room ? two.slice(0, room - 1) + '…' : two]
}

/** The same, worked out once per step rather than once per line of one. */
const written = computed(
  () => new Map(shape.value.steps.map((s) => [s.id, lines(s.label, x1(s) - x0(s) - 20)])),
)
const said = (step: Step) => written.value.get(step.id) ?? [step.label]
</script>

<template>
  <div ref="root" class="shape hmz-panel">
    <div class="bar">
      <div v-if="offered.length > 1" class="tabs" role="group" aria-label="which flow">
        <button
          v-for="(one, i) in offered"
          :key="one"
          type="button"
          :class="{ on: i === at }"
          @click="at = i"
        >
          {{ SHAPES[one].of }}
        </button>
      </div>
      <code v-else class="only">{{ shape.of }}</code>
      <div class="spacer" />
      <button
        v-if="!still"
        class="toggle"
        type="button"
        :aria-label="running ? 'pause' : 'play'"
        @click="running = !running"
      >
        {{ running ? '❙❙' : '▶' }}
      </button>
    </div>

    <svg :viewBox="`0 0 ${WIDE} ${height}`" role="img" :aria-label="`the shape of ${shape.of}`">
      <!-- the lanes -->
      <g class="rails">
        <g v-for="(lane, i) in shape.lanes" :key="lane.id" :style="{ '--tone': toneOf(lane.id) }">
          <line :x1="LABEL" :x2="WIDE - RIGHT" :y1="midY(lane.id)" :y2="midY(lane.id)" class="rail" />
          <circle :cx="LABEL - 10" :cy="midY(lane.id)" r="3.5" class="pin" />
          <text :x="LABEL - 20" :y="midY(lane.id) - 2" class="lane-name">{{ lane.name }}</text>
          <text :x="LABEL - 20" :y="midY(lane.id) + 11" class="lane-note">{{ lane.note }}</text>
        </g>
      </g>

      <!-- one session, held across turns -->
      <rect
        v-for="band in bands"
        :key="band.key"
        class="band"
        :class="{ on: band.on }"
        :x="band.x"
        :y="band.y"
        :width="band.w"
        height="3"
        rx="1.5"
        :style="{ '--tone': band.tone }"
      />

      <!-- what a turn hands the next one -->
      <g class="wires">
        <g
          v-for="wire in wires"
          :key="wire.key"
          :style="{ '--tone': wire.tone }"
        >
          <path :d="wire.d" class="wire" :class="{ live: wire.live }" />
          <template v-if="wire.live">
            <text class="said" :x="wire.mid.x" :y="wire.mid.y">{{ wire.said }}</text>
            <circle class="bead" :cx="wire.bead.x" :cy="wire.bead.y" r="3.5" />
          </template>
        </g>
      </g>

      <!-- the turns -->
      <g class="steps">
        <g
          v-for="step in shape.steps"
          :key="step.id"
          :class="[state(step), step.tone ?? 'work', step.session ?? 'new']"
          :style="{ '--tone': toneOf(step.lane) }"
          @mouseenter="held = step"
          @mouseleave="held = null"
        >
          <rect
            class="box"
            :x="x0(step)"
            :y="boxY(step.lane)"
            :width="x1(step) - x0(step)"
            :height="BOX_H"
            rx="7"
          />
          <rect
            v-if="state(step) === 'running'"
            class="fill"
            :x="x0(step)"
            :y="boxY(step.lane)"
            :width="(x1(step) - x0(step)) * through(step)"
            :height="BOX_H"
            rx="7"
          />
          <circle
            v-if="step.session === 'new'"
            class="opened"
            :cx="x0(step)"
            :cy="midY(step.lane)"
            r="3.5"
          />
          <g v-if="step.inside" class="inside">
            <rect
              v-for="n in step.inside"
              :key="n"
              :x="(x0(step) + x1(step)) / 2 + (n - 1 - (step.inside - 1) / 2) * 16 - 5"
              :y="boxY(step.lane) + BOX_H - 8"
              width="10"
              height="3"
              rx="1.5"
              :class="{ on: through(step) * step.inside >= n - 0.5 || state(step) === 'landed' }"
            />
          </g>
          <text
            v-for="(line, n) in said(step)"
            :key="n"
            class="label"
            :x="(x0(step) + x1(step)) / 2"
            :y="midY(step.lane) + (said(step).length === 1 ? 4 : n * 12 - 2) - (step.inside ? 3 : 0)"
          >
            {{ line }}
          </text>
        </g>
      </g>

      <!-- what a round ends on, and what it starts again at -->
      <g v-if="arc" class="arc" :class="{ live: arc.live }">
        <path :d="arc.d" />
        <text :x="arc.x" :y="arc.y">{{ arc.said }}</text>
      </g>

      <!-- what the run is spending, where that is what stops it -->
      <g v-if="shape.meter" class="meter">
        <template v-if="shape.meter.kind === 'budget'">
          <rect :x="LABEL" :y="meterY" :width="WIDE - LABEL - RIGHT" height="7" rx="3.5" class="trough" />
          <rect
            :x="LABEL"
            :y="meterY"
            :width="((WIDE - LABEL - RIGHT) * spent) / 10"
            height="7"
            rx="3.5"
            class="poured"
          />
          <text :x="LABEL - 20" :y="meterY + 7" class="meter-name">budget</text>
          <text :x="WIDE - RIGHT" :y="meterY + 24" class="meter-said">
            {{ spent.toFixed(2) }}M of 10M output tokens
          </text>
        </template>
        <template v-else>
          <!-- The bars stand on a floor and the dashed line is the target, so a round that
               came out under it is a bar that stops short of it and one over it is a bar that
               goes past. A line the bars merely sit on would say nothing. -->
          <line :x1="LABEL" :x2="WIDE - RIGHT" :y1="tall(2000)" :y2="tall(2000)" class="target" />
          <g v-for="(step, i) in shape.steps" :key="step.id">
            <rect
              v-if="state(step) !== 'waiting'"
              :x="x0(step)"
              :y="tall(JUICE[i] ?? 2000)"
              :width="Math.min(46, x1(step) - x0(step))"
              :height="base - tall(JUICE[i] ?? 2000)"
              class="juice"
            />
            <text
              v-if="state(step) !== 'waiting'"
              class="gauge-said"
              :x="x0(step)"
              :y="tall(JUICE[i] ?? 2000) - 4"
            >
              {{ JUICE[i] ?? 2000 }}
            </text>
          </g>
          <text :x="LABEL - 20" :y="base - 2" class="meter-name">juice</text>
          <text :x="WIDE - RIGHT" :y="base + 16" class="meter-said">
            held to 2000 output tokens a turn of the model
          </text>
        </template>
      </g>

      <!-- where the run is -->
      <line :x1="head" :x2="head" y1="6" :y2="floor - 4" class="head" />
    </svg>

    <p class="caption">{{ caption }}</p>
  </div>
</template>

<style scoped>
.shape {
  --tone: var(--hmz-lane-1);
}

.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tabs button {
  padding: 4px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 20px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, background 0.2s;
}

.tabs button:hover {
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.only {
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
}

.spacer {
  flex: 1;
}

.toggle {
  min-width: 34px;
  padding: 4px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11px;
  cursor: pointer;
}

.toggle:hover {
  color: var(--vp-c-brand-1);
}

svg {
  display: block;
  width: 100%;
  height: auto;
  padding: 4px 0 0;
}

.rail {
  stroke: var(--hmz-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.pin {
  fill: var(--tone);
}

.lane-name {
  fill: var(--vp-c-text-1);
  font-size: 11.5px;
  font-weight: 600;
  text-anchor: end;
}

.lane-note {
  fill: var(--vp-c-text-3);
  font-size: 9px;
  text-anchor: end;
}

.band {
  fill: var(--tone);
  opacity: 0.16;
  transition: opacity 0.3s;
}

.band.on {
  opacity: 0.55;
}

.wire {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 1.3;
  stroke-dasharray: 3 4;
  vector-effect: non-scaling-stroke;
}

.wire.live {
  stroke: var(--tone);
  stroke-dasharray: none;
}

.said {
  fill: var(--tone);
  font-size: 9.5px;
  text-anchor: middle;
  pointer-events: none;
}

.bead {
  fill: var(--tone);
  filter: drop-shadow(0 0 4px var(--tone));
}

.steps g {
  transition: opacity 0.35s;
}

.steps g.waiting {
  opacity: 0.16;
}

.steps g.running {
  opacity: 1;
}

.steps g.landed {
  opacity: 0.92;
}

.box {
  fill: var(--vp-c-bg);
  stroke: var(--tone);
  stroke-width: 1.4;
  vector-effect: non-scaling-stroke;
}

.read .box {
  stroke-dasharray: 5 3;
}

.none .box,
.ask .box {
  stroke: var(--vp-c-text-3);
  stroke-dasharray: 2 3;
}

.stop .box {
  stroke: var(--vp-c-text-3);
}

.fill {
  fill: var(--tone);
  opacity: 0.18;
}

.opened {
  fill: var(--tone);
}

.label {
  fill: var(--vp-c-text-2);
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  text-anchor: middle;
  pointer-events: none;
}

.landed .label,
.running .label {
  fill: var(--vp-c-text-1);
}

.inside rect {
  fill: var(--vp-c-text-3);
  opacity: 0.25;
}

.inside rect.on {
  fill: var(--tone);
  opacity: 0.95;
}

.arc path {
  fill: none;
  stroke: var(--vp-c-text-3);
  stroke-width: 1.2;
  stroke-dasharray: 4 4;
  opacity: 0.5;
  vector-effect: non-scaling-stroke;
  transition: stroke 0.3s, opacity 0.3s;
}

.arc text {
  fill: var(--vp-c-text-3);
  font-size: 9.5px;
  text-anchor: middle;
  transition: fill 0.3s;
}

.arc.live path {
  stroke: var(--hmz-accent);
  opacity: 1;
}

.arc.live text {
  fill: var(--hmz-accent);
}

.trough {
  fill: var(--vp-c-default-soft);
}

.poured {
  fill: var(--vp-c-brand-1);
  opacity: 0.8;
}

.target {
  stroke: var(--hmz-accent);
  stroke-width: 1.2;
  stroke-dasharray: 4 4;
  vector-effect: non-scaling-stroke;
}

.juice {
  fill: var(--hmz-lane-1);
  opacity: 0.75;
}

.meter-name {
  fill: var(--vp-c-text-3);
  font-size: 10px;
  font-weight: 600;
  text-anchor: end;
}

.meter-said {
  fill: var(--vp-c-text-3);
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  text-anchor: end;
}

.gauge-said {
  fill: var(--vp-c-text-3);
  font-size: 9px;
  font-family: var(--vp-font-family-mono);
  text-anchor: start;
}

.head {
  stroke: var(--hmz-accent);
  stroke-width: 1.6;
  opacity: 0.75;
  vector-effect: non-scaling-stroke;
}

.caption {
  margin: 0;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--hmz-panel-border);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
  min-height: 46px;
}

@media (max-width: 760px) {
  /* Narrow enough that the lane column would take half the picture, so the whole thing keeps
     its size and scrolls instead. */
  .shape svg {
    min-width: 700px;
  }

  .shape {
    overflow-x: auto;
  }
}
</style>
