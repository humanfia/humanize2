<script setup lang="ts">
// How one syscall gets to where it is going. The filter is drawn the way
// `coganchor/linux/seccomp.py` builds it -- SECCOMP_RET_TRACE for the cold, path-bearing
// calls and SECCOMP_RET_ALLOW for everything else, so the hot ones never pay a ptrace stop --
// and the routing is `coganchor/policy.py`: paths, programs and redirects, three questions.
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Verdict = 'allow' | 'trace'
type Route = 'fast' | 'target' | 'here'

interface Call {
  call: string
  by: string
  verdict: Verdict
  route: Route
  lands: string
  note: string
}

const CALLS: Call[] = [
  {
    call: 'read(7)',
    by: 'the agent',
    verdict: 'allow',
    route: 'fast',
    lands: 'the kernel on this machine',
    note: 'It names no path, so the filter never asks the supervisor about it. A descriptor already decided is a descriptor the answer is known for — and this is the call a turn makes a million times.',
  },
  {
    call: 'openat("kernel.cu")',
    by: 'the agent',
    verdict: 'trace',
    route: 'target',
    lands: 'the workspace',
    note: 'Read out of the local mirror at local speed. The mirror and the target are kept in step, and inside the workspace the agent sees the target: the same names, contents, sizes, modes and timestamps, at the same paths.',
  },
  {
    call: 'write("kernel.cu")',
    by: 'the agent',
    verdict: 'trace',
    route: 'target',
    lands: 'the target',
    note: 'A file the agent modified is pushed in full before any command runs on the target, and again when the session ends. A whole file, both ways: there are no partial transfers to reason about.',
  },
  {
    call: 'renameat2(…)',
    by: 'the agent',
    verdict: 'trace',
    route: 'target',
    lands: 'the target',
    note: "Creating, removing, renaming, linking and changing permissions are replayed on the target first, so what the agent sees is the target's own error rather than a local approximation of one.",
  },
  {
    call: 'execve("pytest")',
    by: 'the agent',
    verdict: 'trace',
    route: 'target',
    lands: 'the target',
    note: "It runs in the target's copy of the working directory, and behaves like an ordinary local child: the same descriptors, the same output, the same exit status. Signals travel both ways.",
  },
  {
    call: 'connect("pypi.org")',
    by: 'pytest',
    verdict: 'trace',
    route: 'target',
    lands: 'the target',
    note: 'The filter is inherited by every descendant and every thread, so a command the agent spawned is supervised too — and reaches the network from the target.',
  },
  {
    call: 'connect(the provider)',
    by: 'the agent',
    verdict: 'trace',
    route: 'here',
    lands: 'this machine',
    note: "The agent's own connections stay here, so the credentials it runs on never leave this machine. It is the one program below the supervisor whose network is not the target's.",
  },
  {
    call: 'openat("~/.claude/…")',
    by: 'the agent',
    verdict: 'trace',
    route: 'here',
    lands: 'this machine',
    note: 'Its state directory is local, and so is anything a path is answered with: an agent running as somebody else’s account reads those credentials from here, and a refreshed token lands here.',
  },
]

const WIRE: Record<Route, string> = {
  fast: 'M 196 150 C 250 150 262 150 326 150 C 402 150 420 76 470 76',
  target:
    'M 196 150 C 250 150 262 150 326 150 C 404 150 424 214 500 214 L 676 214 C 728 214 740 196 782 196',
  here: 'M 196 150 C 250 150 262 150 326 150 C 404 150 424 214 500 214 L 676 214 C 722 214 720 288 738 288',
}

const picked = ref(1)
const running = ref(true)
const call = computed(() => CALLS[picked.value])

// The ratio is the point of the filter, so it is counted rather than asserted: the hot calls
// stream past while the trapped ones arrive at a walking pace.
const allowed = ref(1_284_910)
const trapped = ref(5_102)

const wire = ref<SVGPathElement | null>(null)
const at = ref({ x: 196, y: 150, shown: false })

let frame = 0
let travelled = 0
let last = 0
let counted = 0
let idle = false

function tick(now: number) {
  frame = requestAnimationFrame(tick)
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now
  if (!running.value || idle) return
  travelled = (travelled + dt * 0.46) % 1.3
  counted += dt
  if (counted > 0.08) {
    allowed.value += Math.round(counted * 21_000)
    trapped.value += Math.round(counted * 21)
    counted = 0
  }
  place()
}

function place() {
  const path = wire.value
  if (!path) return
  const t = Math.min(travelled, 1)
  const point = path.getPointAtLength(t * path.getTotalLength())
  at.value = { x: point.x, y: point.y, shown: travelled <= 1.02 }
}

function pick(i: number) {
  picked.value = i
  travelled = 0
  requestAnimationFrame(place)
}

const root = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    running.value = false
    travelled = 0.62
    requestAnimationFrame(place)
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

const said = (n: number) => n.toLocaleString('en-US')
const lit = (route: Route | 'super') =>
  route === 'super'
    ? call.value.verdict === 'trace'
      ? 'lit'
      : ''
    : call.value.route === route
      ? 'lit'
      : ''
</script>

<template>
  <div ref="root" class="calls hmz-panel">
    <div class="bar">
      <span class="tally">
        <b>{{ said(allowed) }}</b> allowed
      </span>
      <span class="tally trap">
        <b>{{ said(trapped) }}</b> trapped
      </span>
      <span class="hint">one ptrace stop each, and only for these</span>
      <div class="spacer" />
      <button class="toggle" type="button" @click="running = !running">
        {{ running ? '❙❙' : '▶' }}
      </button>
    </div>

    <svg viewBox="0 0 1000 330" role="img" aria-label="one syscall, from the agent to wherever it is answered">
      <defs>
        <linearGradient id="hmz-syscall-wire" x1="0" x2="1">
          <stop offset="0" stop-color="var(--vp-c-brand-3)" />
          <stop offset="1" stop-color="var(--hmz-accent)" />
        </linearGradient>
      </defs>

      <path :d="WIRE.fast" class="wire" :class="{ on: call.route === 'fast' }" />
      <path :d="WIRE.target" class="wire" :class="{ on: call.route === 'target' }" />
      <path :d="WIRE.here" class="wire warm" :class="{ on: call.route === 'here' }" />
      <path ref="wire" :d="WIRE[call.route]" class="hidden" />

      <rect x="24" y="118" width="172" height="64" rx="10" class="box" />
      <text x="110" y="144" class="title mid">the agent</text>
      <text x="110" y="162" class="sub mid">unchanged, and told none of it</text>

      <rect x="252" y="106" width="148" height="88" rx="10" class="box strong" />
      <text x="326" y="132" class="title mid">seccomp filter</text>
      <text x="326" y="150" class="sub mid">classic BPF · 35 traps</text>
      <text x="326" y="166" class="sub mid">installed before execve</text>
      <text x="326" y="182" class="sub mid">inherited by every child</text>

      <g :class="lit('fast')">
        <rect x="470" y="44" width="250" height="62" rx="10" class="box" />
        <text x="595" y="70" class="title mid">straight to the kernel</text>
        <text x="595" y="88" class="sub mid">SECCOMP_RET_ALLOW · no stop, no cost</text>
      </g>

      <g :class="lit('super')">
        <rect x="470" y="176" width="206" height="76" rx="10" class="box strong" />
        <text x="573" y="202" class="title mid">the supervisor</text>
        <text x="573" y="220" class="sub mid">SECCOMP_RET_TRACE · one stop</text>
        <text x="573" y="238" class="sub mid">paths · programs · redirects</text>
      </g>

      <g :class="lit('target')">
        <rect x="782" y="168" width="194" height="58" rx="10" class="box" />
        <text x="879" y="192" class="title mid">the target</text>
        <text x="879" y="210" class="sub mid">replayed, and its own errors come back</text>
      </g>

      <g :class="lit('here')">
        <rect x="738" y="262" width="238" height="52" rx="10" class="box" />
        <text x="857" y="284" class="title mid">answered here</text>
        <text x="857" y="301" class="sub mid">state · credentials · the provider</text>
      </g>

      <text x="404" y="112" class="tag">allow</text>
      <text x="410" y="246" class="tag trap">trace</text>

      <g v-show="at.shown" class="packet" :transform="`translate(${at.x} ${at.y})`">
        <rect :x="-Math.max(52, call.call.length * 3.6)" y="-13" :width="Math.max(104, call.call.length * 7.2)" height="26" rx="13" />
        <text y="4">{{ call.call }}</text>
      </g>
    </svg>

    <div class="picker">
      <button
        v-for="(one, i) in CALLS"
        :key="one.call"
        type="button"
        :class="{ on: picked === i, hot: one.verdict === 'allow', local: one.route === 'here' }"
        @click="pick(i)"
      >
        <code>{{ one.call }}</code>
        <span>{{ one.by }}</span>
      </button>
    </div>

    <p class="note">
      <strong>{{ call.verdict === 'allow' ? 'never asked' : call.lands }}</strong>
      {{ call.note }}
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
  color: var(--vp-c-text-3);
}

.tally b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-brand-1);
  font-variant-numeric: tabular-nums;
}

.tally.trap b {
  color: var(--hmz-warm);
}

.hint {
  color: var(--vp-c-text-3);
}

.spacer {
  flex: 1;
}

.toggle {
  min-width: 34px;
  padding: 3px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  cursor: pointer;
}

.toggle:hover {
  color: var(--vp-c-brand-1);
}

svg {
  display: block;
  width: 100%;
  height: auto;
  background:
    radial-gradient(56% 80% at 14% 50%, var(--vp-c-brand-soft), transparent 70%),
    radial-gradient(50% 80% at 88% 60%, rgba(20, 184, 166, 0.1), transparent 70%);
}

.box {
  fill: var(--vp-c-bg-soft);
  stroke: var(--hmz-panel-border);
  transition: stroke 0.3s, filter 0.3s, opacity 0.3s;
}

.box.strong {
  fill: var(--vp-c-bg-elv);
  stroke: var(--vp-c-brand-3);
}

g:not(.lit) > .box {
  opacity: 0.5;
}

g.lit > .box {
  stroke: var(--hmz-accent);
  filter: drop-shadow(0 0 9px var(--vp-c-brand-soft));
}

.title {
  fill: var(--vp-c-text-1);
  font-size: 13px;
  font-weight: 650;
}

.sub {
  fill: var(--vp-c-text-3);
  font-size: 10.5px;
}

.mid {
  text-anchor: middle;
}

.tag {
  fill: var(--vp-c-text-3);
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  letter-spacing: 0.08em;
}

.tag.trap {
  fill: var(--hmz-warm);
}

.wire {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 2;
  stroke-dasharray: 3 7;
  transition: stroke 0.3s, stroke-width 0.3s;
}

.wire.on {
  stroke: url(#hmz-syscall-wire);
  stroke-width: 2.5;
  animation: crawl 1.1s linear infinite;
}

.wire.warm.on {
  stroke: var(--hmz-warm);
}

.hidden {
  fill: none;
  stroke: none;
}

@keyframes crawl {
  to {
    stroke-dashoffset: -20;
  }
}

.packet rect {
  fill: var(--vp-c-text-1);
}

.packet text {
  fill: var(--vp-c-bg);
  font-size: 11px;
  font-weight: 650;
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
}

.picker {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 14px 16px 0;
}

.picker button {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, transform 0.2s;
}

.picker button:hover {
  transform: translateY(-1px);
  border-color: var(--vp-c-brand-1);
}

.picker button code {
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.picker button span {
  font-size: 10px;
  color: var(--vp-c-text-3);
}

.picker button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.picker button.on.local {
  border-color: var(--hmz-warm);
}

.picker button.hot code {
  color: var(--vp-c-text-3);
}

.note {
  margin: 0;
  padding: 12px 16px 15px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.note strong {
  margin-right: 8px;
  color: var(--vp-c-text-1);
}

@media (prefers-reduced-motion: reduce) {
  .wire.on {
    animation: none;
  }
}

@media (max-width: 900px) {
  .picker {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .hint {
    display: none;
  }

  .picker button span {
    display: none;
  }
}
</style>
