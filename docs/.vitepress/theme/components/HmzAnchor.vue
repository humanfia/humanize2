<script setup lang="ts">
// The anchor, drawn as what it is: a router. The agent runs here and is told none of this;
// every syscall it makes is taken by the supervisor and either replayed on the target or
// answered on this machine. Pick a call and watch which way it goes.
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Route = 'target' | 'here'
type Where = 'files' | 'processes' | 'network' | 'local'

interface Call {
  call: string
  by: string
  route: Route
  where: Where
  note: string
}

const CALLS: Call[] = [
  {
    call: 'openat("kernel.cu")',
    by: 'the agent',
    route: 'target',
    where: 'files',
    note: 'Read out of the local mirror at local speed. The mirror and the target are kept in step.',
  },
  {
    call: 'write("kernel.cu")',
    by: 'the agent',
    route: 'target',
    where: 'files',
    note: 'Pushed in full before any command runs on the target, and again when the session ends.',
  },
  {
    call: 'execve("pytest")',
    by: 'the agent',
    route: 'target',
    where: 'processes',
    note: "Runs in the target's copy of the working directory. Its exit status is the target's own.",
  },
  {
    call: 'connect("pypi.org")',
    by: 'pytest',
    route: 'target',
    where: 'network',
    note: 'A command the agent spawned always reaches the network from the target.',
  },
  {
    call: 'connect(the model provider)',
    by: 'the agent',
    route: 'here',
    where: 'local',
    note: "The agent's own connections stay here, so the credentials it runs on never leave this machine.",
  },
  {
    call: 'openat("~/.claude/…")',
    by: 'the agent',
    route: 'here',
    where: 'local',
    note: 'Its state directory stays here. All ten known CLIs are known by name.',
  },
]

const TO_TARGET = 'M 268 168 C 420 168 460 132 660 132'
const TO_HERE = 'M 268 168 C 330 168 340 236 300 250 L 250 250'

const picked = ref(0)
const call = computed(() => CALLS[picked.value])

const wireTarget = ref<SVGPathElement | null>(null)
const wireHere = ref<SVGPathElement | null>(null)
const at = ref({ x: 268, y: 168, shown: false })

let frame = 0
let travelled = 0
let last = 0

function tick(now: number) {
  frame = requestAnimationFrame(tick)
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now
  travelled = (travelled + dt * 0.42) % 1.35
  const wire = call.value.route === 'target' ? wireTarget.value : wireHere.value
  if (!wire) return
  const t = Math.min(travelled, 1)
  const point = wire.getPointAtLength(t * wire.getTotalLength())
  at.value = { x: point.x, y: point.y, shown: travelled <= 1.02 }
}

function pick(i: number) {
  picked.value = i
  travelled = 0
}

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    travelled = 0.55
    tick(performance.now())
    cancelAnimationFrame(frame)
    return
  }
  last = performance.now()
  frame = requestAnimationFrame(tick)
})

onUnmounted(() => cancelAnimationFrame(frame))

const lit = (where: Where) => (call.value.where === where ? 'lit' : '')
</script>

<template>
  <div class="anchor hmz-panel">
    <svg viewBox="0 0 1000 300" role="img" aria-label="an agent here, its work landing there">
      <defs>
        <linearGradient id="hmz-wire" x1="0" x2="1">
          <stop offset="0" stop-color="var(--vp-c-brand-3)" />
          <stop offset="1" stop-color="var(--hmz-accent)" />
        </linearGradient>
      </defs>

      <text x="24" y="26" class="side">this machine</text>
      <text x="976" y="26" class="side end">the target</text>
      <rect x="16" y="38" width="300" height="240" rx="14" class="zone" />
      <rect x="656" y="38" width="328" height="240" rx="14" class="zone remote" />

      <rect x="44" y="56" width="224" height="46" rx="9" class="box" />
      <text x="156" y="79" class="title mid">claude · codex · dsh · …</text>
      <text x="156" y="94" class="sub mid">unchanged, and told none of this</text>

      <path d="M 156 104 L 156 128" class="feed" />
      <text x="164" y="122" class="sub">syscalls</text>

      <rect x="44" y="132" width="224" height="72" rx="9" class="box strong" />
      <text x="156" y="156" class="title mid">supervisor</text>
      <text x="156" y="174" class="sub mid">seccomp filter · ptrace</text>
      <text x="156" y="192" class="sub mid">every call decided one at a time</text>

      <rect x="44" y="228" width="206" height="44" rx="9" class="box" :class="lit('local')" />
      <text x="147" y="248" class="title mid">answered here</text>
      <text x="147" y="264" class="sub mid">credentials · state · the model provider</text>

      <path ref="wireHere" :d="TO_HERE" class="wire local" :class="{ on: call.route === 'here' }" />
      <path
        ref="wireTarget"
        :d="TO_TARGET"
        class="wire"
        :class="{ on: call.route === 'target' }"
      />
      <text x="452" y="118" class="sub mid">ssh · docker · tcp · a pipe</text>

      <rect x="676" y="56" width="288" height="40" rx="9" class="box strong" />
      <text x="820" y="81" class="title mid">hmz anchor serve</text>

      <g class="dest" :class="lit('files')">
        <rect x="676" y="112" width="288" height="46" rx="9" class="box" />
        <text x="700" y="132" class="title">files</text>
        <text x="700" y="149" class="sub">contents, renames, modes — the target's own errors</text>
      </g>
      <g class="dest" :class="lit('processes')">
        <rect x="676" y="166" width="288" height="46" rx="9" class="box" />
        <text x="700" y="186" class="title">processes</text>
        <text x="700" y="203" class="sub">everything the agent spawns, in the target's cwd</text>
      </g>
      <g class="dest" :class="lit('network')">
        <rect x="676" y="220" width="288" height="46" rx="9" class="box" />
        <text x="700" y="240" class="title">the network</text>
        <text x="700" y="257" class="sub">whatever those commands reach</text>
      </g>

      <g v-show="at.shown" class="packet" :transform="`translate(${at.x} ${at.y})`">
        <rect x="-64" y="-13" width="128" height="26" rx="13" />
        <text y="4">{{ call.route === 'target' ? 'replayed' : 'answered here' }}</text>
      </g>
    </svg>

    <div class="calls">
      <button
        v-for="(item, i) in CALLS"
        :key="item.call"
        type="button"
        :class="{ on: picked === i, here: item.route === 'here' }"
        @click="pick(i)"
      >
        <code>{{ item.call }}</code>
        <span>{{ item.by }}</span>
      </button>
    </div>
    <p class="note">
      <strong>{{ call.route === 'target' ? 'lands on the target' : 'stays on this machine' }}</strong>
      {{ call.note }}
    </p>
  </div>
</template>

<style scoped>
svg {
  display: block;
  width: 100%;
  height: auto;
  background:
    radial-gradient(60% 90% at 12% 50%, var(--vp-c-brand-soft), transparent 70%),
    radial-gradient(60% 90% at 88% 50%, rgba(20, 184, 166, 0.1), transparent 70%);
}

.side {
  fill: var(--vp-c-text-3);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-weight: 700;
}

.end {
  text-anchor: end;
}

.zone {
  fill: var(--vp-c-bg);
  stroke: var(--hmz-panel-border);
  stroke-dasharray: 4 5;
}

.box {
  fill: var(--vp-c-bg-soft);
  stroke: var(--hmz-panel-border);
  transition: stroke 0.3s, fill 0.3s, filter 0.3s;
}

.box.strong {
  stroke: var(--vp-c-brand-3);
  fill: var(--vp-c-bg-elv);
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

.feed {
  stroke: var(--vp-c-divider);
  stroke-width: 1.5;
  fill: none;
}

.wire {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 2;
  stroke-dasharray: 3 7;
  transition: stroke 0.3s, stroke-width 0.3s;
}

.wire.on {
  stroke: url(#hmz-wire);
  stroke-width: 2.5;
  animation: crawl 1.1s linear infinite;
}

.wire.local.on {
  stroke: var(--hmz-warm);
}

@keyframes crawl {
  to {
    stroke-dashoffset: -20;
  }
}

.dest .box,
.box.lit {
  opacity: 1;
}

.dest:not(.lit) .box {
  opacity: 0.55;
}

.dest.lit .box,
.box.lit {
  stroke: var(--hmz-accent);
  filter: drop-shadow(0 0 8px var(--vp-c-brand-soft));
}

.box.lit {
  stroke: var(--hmz-warm);
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

.calls {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 14px 16px 0;
}

.calls button {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, transform 0.2s;
}

.calls button:hover {
  transform: translateY(-1px);
  border-color: var(--vp-c-brand-1);
}

.calls button code {
  font-size: 12px;
  color: var(--vp-c-text-1);
}

.calls button span {
  font-size: 10px;
  color: var(--vp-c-text-3);
}

.calls button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.calls button.on.here {
  border-color: var(--hmz-warm);
}

.note {
  margin: 0;
  padding: 12px 16px 14px;
  font-size: 13px;
  line-height: 1.6;
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

@media (max-width: 860px) {
  .calls {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .calls button span {
    display: none;
  }
}
</style>
