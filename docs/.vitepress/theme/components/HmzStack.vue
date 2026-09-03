<script setup lang="ts">
// The package, drawn from the table `tests/test_layering.py` enforces: every layer, and
// everything it is allowed to name. It is a DAG -- everything points downward, nothing points
// both ways -- and hovering a layer lights up exactly what it is built on.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

interface Node {
  id: string
  x: number
  y: number
  blurb: string
  href: string
}

const W = 132
const H = 40

const NODES: Node[] = [
  { id: 'tui', x: 190, y: 42, blurb: 'the terminal interface', href: '/reference/tui' },
  { id: 'daemon', x: 450, y: 42, blurb: 'a run held where a terminal closing cannot end it', href: '/reference/daemon' },
  { id: 'cli', x: 730, y: 42, blurb: 'one command line, over layers that have none', href: '/reference/cli' },
  { id: 'proctitle', x: 590, y: 116, blurb: 'what `hmz exec` is called to every other process: the command, not the task', href: '/reference/cli#hmz-exec' },
  { id: 'sdk', x: 380, y: 116, blurb: 'humanize as one object, which every way in goes through', href: '/reference/sdk' },
  { id: 'runner', x: 300, y: 190, blurb: 'finds a flow, checks it, names the agents, drives it', href: '/reference/flows' },
  { id: 'epic', x: 452, y: 264, blurb: 'one run of one flow, written down as it happens', href: '/reference/tracing' },
  { id: 'flows', x: 120, y: 338, blurb: 'what a flow is, where it is found, what it brings', href: '/reference/flows' },
  { id: 'tracing', x: 770, y: 338, blurb: "the backends' own logs, read back as one Chrome trace", href: '/reference/tracing' },
  { id: 'agents', x: 300, y: 412, blurb: 'the contract a flow is written against, and a driver per backend', href: '/reference/agents' },
  { id: 'models', x: 770, y: 412, blurb: 'what each backend runs, asked of it the way it offers being asked', href: '/reference/providers' },
  { id: 'machines', x: 120, y: 486, blurb: "where an agent's turns land: a container, a host, here", href: '/reference/machines' },
  { id: 'providers', x: 560, y: 486, blurb: 'which account an agent runs as, kept apart from which CLI it is', href: '/reference/providers' },
  { id: 'coganchor', x: 120, y: 560, blurb: 'syscall interposition: a supervisor here, a server there', href: '/reference/remote-execution' },
  { id: 'backends', x: 660, y: 560, blurb: 'every fact about a coding agent CLI that is not code', href: '/guide/concepts' },
]

const EDGES: [string, string][] = [
  ['tui', 'sdk'],
  ['tui', 'runner'],
  ['tui', 'epic'],
  ['tui', 'flows'],
  ['tui', 'tracing'],
  ['tui', 'agents'],
  ['tui', 'models'],
  ['tui', 'providers'],
  ['tui', 'backends'],
  ['cli', 'sdk'],
  ['cli', 'daemon'],
  ['cli', 'proctitle'],
  ['cli', 'runner'],
  ['cli', 'tracing'],
  ['cli', 'epic'],
  ['cli', 'models'],
  ['sdk', 'runner'],
  ['sdk', 'epic'],
  ['sdk', 'flows'],
  ['sdk', 'tracing'],
  ['sdk', 'agents'],
  ['sdk', 'models'],
  ['sdk', 'providers'],
  ['sdk', 'backends'],
  ['runner', 'epic'],
  ['runner', 'flows'],
  ['runner', 'agents'],
  ['runner', 'backends'],
  ['epic', 'agents'],
  ['epic', 'tracing'],
  ['flows', 'agents'],
  ['flows', 'backends'],
  ['tracing', 'backends'],
  ['agents', 'machines'],
  ['agents', 'providers'],
  ['agents', 'backends'],
  ['agents', 'coganchor'],
  ['models', 'providers'],
  ['models', 'backends'],
  ['machines', 'coganchor'],
  ['providers', 'backends'],
  ['providers', 'coganchor'],
]

const at = Object.fromEntries(NODES.map((n) => [n.id, n])) as Record<string, Node>

const wires = EDGES.map(([from, to]) => {
  const a = at[from]
  const b = at[to]
  const y0 = a.y + H / 2
  const y1 = b.y - H / 2
  const bend = Math.max(24, (y1 - y0) * 0.45)
  return {
    from,
    to,
    d: `M ${a.x} ${y0} C ${a.x} ${y0 + bend}, ${b.x} ${y1 - bend}, ${b.x} ${y1}`,
  }
})

const active = ref('agents')
const touched = ref(false)
const node = computed(() => at[active.value])
const beneath = computed(() => new Set(EDGES.filter(([f]) => f === active.value).map(([, t]) => t)))
const above = computed(() => new Set(EDGES.filter(([, t]) => t === active.value).map(([f]) => f)))

let tour: ReturnType<typeof setInterval> | undefined
const ORDER = ['agents', 'coganchor', 'sdk', 'tracing', 'tui', 'flows']

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  let i = 0
  tour = setInterval(() => {
    if (touched.value) return clearInterval(tour)
    i = (i + 1) % ORDER.length
    active.value = ORDER[i]
  }, 3800)
})

onUnmounted(() => clearInterval(tour))

function hold(id: string) {
  touched.value = true
  active.value = id
}
</script>

<template>
  <div class="stack hmz-panel">
    <svg viewBox="0 0 900 604" role="img" aria-label="the layers of humanize, and what each may name">
      <g class="wires">
        <path
          v-for="wire in wires"
          :key="`${wire.from}-${wire.to}`"
          :d="wire.d"
          class="wire"
          :class="{
            on: wire.from === active,
            up: wire.to === active,
          }"
        />
      </g>
      <g
        v-for="item in NODES"
        :key="item.id"
        class="node"
        :class="{
          on: item.id === active,
          under: beneath.has(item.id),
          over: above.has(item.id),
        }"
        @mouseenter="hold(item.id)"
        @focusin="hold(item.id)"
      >
        <rect :x="item.x - W / 2" :y="item.y - H / 2" :width="W" :height="H" rx="9" />
        <text :x="item.x" :y="item.y + 5">{{ item.id }}</text>
      </g>
    </svg>

    <div class="read">
      <div class="who">
        <code>hmz.{{ node.id }}</code>
        <a :href="withBase(node.href)">read it →</a>
      </div>
      <p>{{ node.blurb }}</p>
      <p class="deps">
        <span v-if="beneath.size">
          built on
          <em v-for="id in beneath" :key="id">{{ id }}</em>
        </span>
        <span v-else>names nothing — a leaf, and the DAG is wider for it</span>
      </p>
      <p v-if="above.size" class="deps named">
        named by
        <em v-for="id in above" :key="id">{{ id }}</em>
      </p>
      <p class="hint">hover a layer</p>
      <p class="rule">
        The table is <code>tests/test_layering.py</code>, and it fails a build that bends this.
      </p>
    </div>
  </div>
</template>

<style scoped>
.stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 264px;
}

svg {
  display: block;
  width: 100%;
  height: auto;
  padding: 8px;
}

.wire {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 1.4;
  stroke-dasharray: 2 6;
  animation: crawl 5s linear infinite;
  transition: stroke 0.35s, stroke-width 0.35s, opacity 0.35s;
  opacity: 0.7;
}

.wire.on {
  stroke: var(--vp-c-brand-1);
  stroke-width: 2.2;
  stroke-dasharray: 8 8;
  opacity: 1;
  animation: crawl 0.9s linear infinite;
}

.wire.up {
  stroke: var(--hmz-accent);
  stroke-width: 1.8;
  opacity: 0.9;
}

@keyframes crawl {
  to {
    stroke-dashoffset: -32;
  }
}

.node rect {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-divider);
  transition: fill 0.3s, stroke 0.3s, filter 0.3s;
}

.node text {
  fill: var(--vp-c-text-2);
  font-size: 13px;
  font-weight: 600;
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
  transition: fill 0.3s;
  pointer-events: none;
}

.node {
  cursor: pointer;
}

.node.on rect {
  fill: var(--vp-c-brand-1);
  stroke: var(--vp-c-brand-1);
  filter: drop-shadow(0 3px 14px var(--vp-c-brand-soft));
}

.node.on text {
  fill: var(--vp-c-bg);
}

.node.under rect {
  stroke: var(--vp-c-brand-1);
  fill: var(--vp-c-brand-soft);
}

.node.under text {
  fill: var(--vp-c-brand-1);
}

.node.over rect {
  stroke: var(--hmz-accent);
}

.read {
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--hmz-panel-border);
  padding: 22px 20px;
  background: var(--vp-c-bg);
}

.who {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.who code {
  font-size: 14px;
  font-weight: 700;
  color: var(--vp-c-text-1);
}

.who a {
  font-size: 12px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  white-space: nowrap;
}

.read p {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.deps {
  color: var(--vp-c-text-3) !important;
  font-size: 12px !important;
}

.deps em {
  display: inline-block;
  margin: 4px 4px 0 0;
  padding: 2px 7px;
  border-radius: 6px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-family: var(--vp-font-family-mono);
  font-style: normal;
  font-size: 11px;
}

.deps.named em {
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
}

.hint {
  margin-top: 18px !important;
  font-size: 11px !important;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--vp-c-text-3) !important;
}

.rule {
  margin-top: auto !important;
  padding-top: 18px;
  font-size: 12px !important;
  color: var(--vp-c-text-3) !important;
}

.rule code {
  font-size: 11px;
}

@media (prefers-reduced-motion: reduce) {
  .wire {
    animation: none;
  }

  .node rect,
  .node text {
    transition: none;
  }
}

@media (max-width: 860px) {
  .stack {
    grid-template-columns: minmax(0, 1fr);
  }

  .read {
    border-left: 0;
    border-top: 1px solid var(--hmz-panel-border);
  }
}
</style>
