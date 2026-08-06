<script setup lang="ts">
// Two halves of one idea: a CLI told nothing runs as an account it was never signed into
// (`providers/redirect.py`), and the turn that fails walks the chain that account names
// (`providers/store.py`), waiting the way `providers/retry.py` says to wait.
import { computed, onUnmounted, ref } from 'vue'

type View = 'swap' | 'chain'

interface Shape {
  named: string
  answered: string
  about: string
}

// The three shapes a redirect answers, as `redirect.py` answers them.
const SHAPES: Shape[] = [
  {
    named: '~/.claude/.credentials.json',
    answered: '~/.humanize/providers/claude/work/home/.credentials.json',
    about:
      'The file itself. The CLI opens the path it has always opened; the syscall is given another one.',
  },
  {
    named: '~/.kimi-code/oauth/…',
    answered: '~/.humanize/providers/kimi/night/home/oauth/…',
    about:
      'A directory, and so everything under it — a backend that keeps one file per endpoint it has signed into keeps them all over there.',
  },
  {
    named: '~/.claude/.credentials.json.tmp',
    answered: '~/.humanize/providers/claude/work/home/.credentials.json.tmp',
    about:
      'Anything beside it under the same name and another suffix. Not a nicety: these CLIs rotate a token by writing `.tmp` and renaming it over, and an unanswered temp file writes the new token into the store you were redirecting away from.',
  },
]

interface Account {
  name: string
  kind: string
  about: string
  fails: boolean
  why: string
}

const ACCOUNTS = ref<Account[]>([
  {
    name: 'claude@work',
    kind: 'a subscription, signed in',
    about: "the CLI's own login wrote it",
    fails: true,
    why: '429 · too many requests',
  },
  {
    name: 'claude@key',
    kind: 'an API key',
    about: 'a variable, and nothing on disk',
    fails: true,
    why: '402 · the credit ran out',
  },
  {
    name: 'claude@gateway',
    kind: 'an endpoint of somebody else’s',
    about: 'speaking the same protocol',
    fails: false,
    why: '',
  },
])

const POLICIES = [
  { name: 'none', about: 'try again at once, with no wait at all' },
  { name: 'constant', about: 'the same wait every time' },
  { name: 'linear', about: 'one second longer each time' },
  { name: 'exponential', about: 'twice as long each time' },
  { name: 'exponential-jitter', about: 'exponential, each wait anywhere up to it' },
  { name: 'fibonacci', about: '1s, 1s, 2s, 3s, 5s' },
]

const CEILING = 60

function fib(n: number): number {
  let before = 0
  let held = 1
  for (let i = 0; i < n - 1; i += 1) [before, held] = [held, before + held]
  return held
}

// The same waits `retry.py` computes, with the jitter drawn as the band it is drawn from
// rather than as one roll of it: a bar that moved every render would say the wrong thing.
function waits(policy: string, attempt: number): number {
  const over = Math.max(attempt - 1, 0)
  if (!over) return 0
  if (policy === 'none') return 0
  if (policy === 'constant') return 1
  if (policy === 'linear') return over
  if (policy === 'fibonacci') return Math.min(fib(over), CEILING)
  return Math.min(2 ** (over - 1), CEILING)
}

const view = ref<View>('swap')
const shape = ref(0)
const policy = ref('exponential-jitter')
const tries = ref(3)

const ladder = computed(() =>
  Array.from({ length: 5 }, (_, i) => ({
    attempt: i + 2,
    seconds: waits(policy.value, i + 2),
    jitter: policy.value === 'exponential-jitter',
  })),
)
const tallest = computed(() => Math.max(1, ...ladder.value.map((one) => one.seconds)))

interface Beat {
  at: number
  said: string
  kind: 'try' | 'wait' | 'moved' | 'landed' | 'ended'
  account: number
}

const beats = ref<Beat[]>([])
const clock = ref(0)
const playing = ref(false)
let frame = 0
let last = 0

// One second of a turn's waiting is 260ms here: the shape of a policy is what there is to
// read, and a minute of real backoff is a minute of nothing happening.
const SPEED = 260

function script(): Beat[] {
  const made: Beat[] = []
  let at = 0
  for (let which = 0; which < ACCOUNTS.value.length; which += 1) {
    const account = ACCOUNTS.value[which]
    for (let attempt = 1; attempt <= tries.value; attempt += 1) {
      const wait = attempt > 1 ? waits(policy.value, attempt) : 0
      if (wait) {
        made.push({
          at,
          said: `waited ${wait.toFixed(wait < 10 ? 1 : 0)}s`,
          kind: 'wait',
          account: which,
        })
        at += wait
      }
      made.push({
        at,
        said: `try ${attempt} · ${account.fails ? account.why : 'the turn lands'}`,
        kind: account.fails ? 'try' : 'landed',
        account: which,
      })
      at += 1.4
      if (!account.fails) return made
    }
    if (which + 1 < ACCOUNTS.value.length) {
      made.push({
        at,
        said: `falls back to ${ACCOUNTS.value[which + 1].name} — inside the same session`,
        kind: 'moved',
        account: which + 1,
      })
      at += 1.2
    }
  }
  made.push({
    at,
    said: 'the end of the chain, and the turn fails',
    kind: 'ended',
    account: ACCOUNTS.value.length - 1,
  })
  return made
}

function play() {
  beats.value = script()
  clock.value = 0
  playing.value = true
  last = performance.now()
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(tick)
}

function tick(now: number) {
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now
  clock.value += (dt * 1000) / SPEED
  const done = beats.value.length ? beats.value[beats.value.length - 1].at + 1.4 : 0
  if (clock.value >= done) {
    playing.value = false
    clock.value = done
    return
  }
  frame = requestAnimationFrame(tick)
}

const shown = computed(() => beats.value.filter((one) => one.at <= clock.value))
const running = computed(() => shown.value[shown.value.length - 1]?.account ?? 0)
const landed = computed(() => shown.value.some((one) => one.kind === 'landed'))

function flip(which: number) {
  ACCOUNTS.value[which].fails = !ACCOUNTS.value[which].fails
  beats.value = []
  clock.value = 0
  playing.value = false
  cancelAnimationFrame(frame)
}

onUnmounted(() => cancelAnimationFrame(frame))
</script>

<template>
  <div class="accounts hmz-panel">
    <div class="tabs" role="group" aria-label="which half">
      <button type="button" :class="{ on: view === 'swap' }" @click="view = 'swap'">
        the swap
      </button>
      <button type="button" :class="{ on: view === 'chain' }" @click="view = 'chain'">
        the chain
      </button>
    </div>

    <div v-if="view === 'swap'" class="swap">
      <svg viewBox="0 0 1000 250" role="img" aria-label="a path the CLI names, answered with another">
        <rect x="26" y="92" width="212" height="66" rx="10" class="box" />
        <text x="132" y="120" class="title mid">the CLI</text>
        <text x="132" y="138" class="sub mid">not asked, and not told</text>

        <rect x="330" y="80" width="228" height="90" rx="10" class="box strong" />
        <text x="444" y="108" class="title mid">the supervisor</text>
        <text x="444" y="128" class="sub mid">a seccomp filter over the</text>
        <text x="444" y="144" class="sub mid">calls that name a path, and</text>
        <text x="444" y="160" class="sub mid">an argument rewritten in place</text>

        <rect x="650" y="46" width="324" height="66" rx="10" class="box lit" />
        <text x="812" y="72" class="title mid">the account's own directory</text>
        <text x="812" y="92" class="sub mid">under ~/.humanize/providers/…</text>

        <rect x="650" y="150" width="324" height="62" rx="10" class="box faint" />
        <text x="812" y="176" class="title mid">whoever this machine is signed in as</text>
        <text x="812" y="196" class="sub mid">never opened, and never written to</text>

        <path d="M 238 125 L 330 125" class="wire on" />
        <path d="M 558 112 C 606 112 610 79 650 79" class="wire on" />
        <path d="M 558 140 C 606 140 610 181 650 181" class="wire off" />

        <text x="284" y="114" class="tag mid">openat</text>
        <text x="604" y="70" class="tag mid">answered</text>
        <text x="606" y="206" class="tag mid dim">refused</text>
      </svg>

      <div class="picker three">
        <button
          v-for="(one, i) in SHAPES"
          :key="one.named"
          type="button"
          :class="{ on: shape === i }"
          @click="shape = i"
        >
          <code>{{ one.named }}</code>
        </button>
      </div>

      <div class="swapped">
        <div class="line">
          <span class="lab">it names</span><code>{{ SHAPES[shape].named }}</code>
        </div>
        <div class="line to">
          <span class="lab">it is given</span><code>{{ SHAPES[shape].answered }}</code>
        </div>
        <p class="note">{{ SHAPES[shape].about }}</p>
      </div>
    </div>

    <div v-else class="chain">
      <div class="controls">
        <label>
          <span>waits like</span>
          <select v-model="policy">
            <option v-for="one in POLICIES" :key="one.name" :value="one.name">
              {{ one.name }}
            </option>
          </select>
        </label>
        <label>
          <span>tries per account</span>
          <input v-model.number="tries" type="range" min="1" max="5" step="1" />
          <b>{{ tries }}</b>
        </label>
        <div class="spacer" />
        <button class="go" type="button" :disabled="playing" @click="play">
          {{ playing ? 'running…' : 'take a turn' }}
        </button>
      </div>

      <div class="ladder">
        <div class="bars">
          <div v-for="one in ladder" :key="one.attempt" class="bar">
            <div class="col">
              <span
                class="fill"
                :class="{ jitter: one.jitter }"
                :style="{ height: `${(one.seconds / tallest) * 100}%` }"
              />
            </div>
            <span class="tickmark">{{ one.seconds ? `${one.seconds}s` : '0' }}</span>
          </div>
        </div>
        <p class="about">
          {{ POLICIES.find((one) => one.name === policy)?.about }}.
          <template v-if="policy === 'exponential-jitter'">
            The bar is the ceiling of each wait and the roll is anywhere below it, which is what
            keeps a flow's agents from all coming back on the same second.
          </template>
          Never longer than a minute, however far it has climbed.
        </p>
      </div>

      <div class="rows">
        <div
          v-for="(one, i) in ACCOUNTS"
          :key="one.name"
          class="row"
          :class="{
            here: beats.length > 0 && running === i,
            spent: beats.length > 0 && running > i,
            fails: one.fails,
          }"
        >
          <button class="flip" type="button" @click="flip(i)">
            {{ one.fails ? 'failing' : 'answering' }}
          </button>
          <code>{{ one.name }}</code>
          <span class="kind">{{ one.kind }}</span>
          <span class="about">{{ one.about }}</span>
        </div>
      </div>

      <ol class="log" :class="{ empty: !shown.length }">
        <li v-for="(one, i) in shown" :key="i" :class="one.kind">
          <span class="who">{{ ACCOUNTS[one.account].name }}</span>
          {{ one.said }}
        </li>
        <li v-if="!shown.length" class="idle">
          the chain is walked inside the session that was running — the conversation is the
          backend's own and carries on under the next account
        </li>
      </ol>
      <p v-if="landed" class="note">
        An agent that has moved stays moved. The account that went down is not one to try again
        every turn.
      </p>
    </div>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.tabs button {
  padding: 5px 14px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}

.tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

svg {
  display: block;
  width: 100%;
  height: auto;
}

.box {
  fill: var(--vp-c-bg-soft);
  stroke: var(--hmz-panel-border);
}

.box.strong {
  fill: var(--vp-c-bg-elv);
  stroke: var(--vp-c-brand-3);
}

.box.lit {
  stroke: var(--hmz-accent);
}

.box.faint {
  opacity: 0.5;
  stroke-dasharray: 4 5;
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
}

.tag.dim {
  opacity: 0.6;
}

.wire {
  fill: none;
  stroke-width: 2;
  stroke-dasharray: 3 7;
}

.wire.on {
  stroke: var(--hmz-accent);
  animation: crawl 1.1s linear infinite;
}

.wire.off {
  stroke: var(--vp-c-divider);
}

@keyframes crawl {
  to {
    stroke-dashoffset: -20;
  }
}

.picker {
  display: grid;
  gap: 8px;
  padding: 4px 16px 0;
}

.picker.three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.picker button {
  padding: 7px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
  text-align: left;
  cursor: pointer;
  overflow: hidden;
}

.picker button code {
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}

.picker button.on {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.swapped {
  padding: 14px 16px 16px;
}

.line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 4px 0;
  overflow-x: auto;
}

.line .lab {
  flex: none;
  width: 76px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--vp-c-text-3);
}

.line code {
  font-size: 12.5px;
  color: var(--vp-c-text-2);
  white-space: nowrap;
}

.line.to code {
  color: var(--hmz-accent);
  font-weight: 600;
}

.controls {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding: 12px 16px 0;
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.controls label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.controls select {
  padding: 3px 8px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 12px;
}

.controls input[type='range'] {
  width: 92px;
  accent-color: var(--vp-c-brand-1);
}

.controls b {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
}

.spacer {
  flex: 1;
}

.go {
  padding: 5px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.go:disabled {
  opacity: 0.55;
  cursor: default;
}

.ladder {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 16px 0;
}

.bars {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex: none;
}

.bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 30px;
}

.col {
  display: flex;
  align-items: flex-end;
  width: 100%;
  height: 54px;
  border-bottom: 1px solid var(--vp-c-divider);
}

.fill {
  width: 100%;
  min-height: 2px;
  border-radius: 4px 4px 0 0;
  background: var(--vp-c-brand-1);
  transition: height 0.35s ease;
}

.fill.jitter {
  background: linear-gradient(180deg, var(--vp-c-brand-1), transparent);
}

.tickmark {
  font-size: 10px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.ladder .about {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

.rows {
  padding: 14px 16px 0;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  margin-bottom: 8px;
  font-size: 12px;
  background: var(--vp-c-bg);
  transition: border-color 0.25s, opacity 0.25s, background 0.25s;
}

.row.here {
  border-color: var(--hmz-accent);
  background: var(--vp-c-brand-soft);
}

.row.spent {
  opacity: 0.45;
}

.row code {
  color: var(--vp-c-text-1);
  font-weight: 600;
}

.row .kind {
  color: var(--vp-c-text-2);
}

.row .about {
  flex: 1;
  text-align: right;
  color: var(--vp-c-text-3);
}

.flip {
  flex: none;
  width: 84px;
  padding: 3px 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--hmz-accent);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.row.fails .flip {
  color: var(--hmz-warm);
  border-color: var(--hmz-warm);
}

.log {
  margin: 6px 16px 0;
  padding: 10px 14px;
  list-style: none;
  border-radius: 10px;
  background: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.9;
  min-height: 96px;
  color: var(--vp-c-text-2);
}

.log .who {
  display: inline-block;
  min-width: 132px;
  color: var(--vp-c-text-3);
}

.log .wait {
  color: var(--vp-c-text-3);
}

.log .moved {
  color: var(--hmz-warm);
}

.log .landed {
  color: var(--hmz-accent);
}

.log .idle {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
  line-height: 1.6;
}

.note {
  margin: 0;
  padding: 12px 16px 15px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

@media (max-width: 780px) {
  .picker.three {
    grid-template-columns: minmax(0, 1fr);
  }

  .ladder {
    flex-direction: column;
    align-items: flex-start;
  }

  .row .about {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .wire.on {
    animation: none;
  }
}
</style>
