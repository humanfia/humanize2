<script setup lang="ts">
// Thirteen ways of running a coding agent, and what each of them can actually be asked for.
// The rows are `hmz/backends.py` and the classes in `hmz/agents/`: which session base a
// backend derives from is what decides whether it can be talked to mid-turn, `shapes` is
// whether it can be held to a schema, and a `_pursue` of its own is whether it has a goal.
// `trace` means `hmz/tracing/collector.py` has a reader for the backend's logs; it does not
// mean only that the backend writes logs or that humanize can tally them while it runs.
import { computed, ref } from 'vue'

type Driven = 'held' | 'server' | 'command' | 'sdk' | 'protocol'

interface Backend {
  name: string
  called: string
  driven: Driven
  efforts: string[]
  swarms?: boolean
  steer: string
  shape: string
  goal: boolean
  trace: boolean
  skills: string
  note: string
}

const DRIVEN: Record<Driven, string> = {
  held: 'one process, held open across its turns and spoken to a line at a time',
  server: 'the app server it serves its own client from, started once per agent',
  command: 'its command line, one run per turn',
  sdk: 'its Python SDK, which ships inside humanize',
  protocol: 'the Agent Client Protocol, and nothing else is assumed',
}

const BACKENDS: Backend[] = [
  {
    name: 'claude',
    called: 'Claude Code',
    driven: 'held',
    efforts: ['ultracode', 'max', 'xhigh', 'high', 'medium', 'low'],
    steer: 'answered inside the same turn',
    shape: 'held to it',
    goal: true,
    trace: true,
    skills: 'its own, and the project’s',
    note: '“ultracode” is “xhigh” with the turn opted into orchestrating a fleet of its own. It is real, undocumented, and no listing the CLI answers with will ever name it — so humanize writes it down.',
  },
  {
    name: 'codex',
    called: 'Codex',
    driven: 'server',
    efforts: ['ultra', 'max', 'xhigh', 'high', 'medium', 'low'],
    steer: 'a steer on the running turn',
    shape: 'held to it',
    goal: true,
    trace: true,
    skills: 'four places, the shared one included',
    note: 'Its models differ from each other: one takes “ultra” and the one beside it does not, so the ladder is narrowed per model by what the backend itself says when it is asked what it runs.',
  },
  {
    name: 'cursor',
    called: 'Cursor Agent',
    driven: 'command',
    efforts: ['high', 'medium', 'low'],
    steer: 'no',
    shape: 'asked in the prompt',
    goal: false,
    trace: false,
    skills: 'its own, and the project’s',
    note: 'It has no flag for a rung: its models are parameterized, so how hard it thinks and how quickly it is served are written into the model itself — “composer-2.5[effort=high,fast=false]”. A model already spelled with a bracket is passed exactly as it was written.',
  },
  {
    name: 'dsh',
    called: 'DeepSeek Harness',
    driven: 'sdk',
    efforts: ['max', 'high', 'off'],
    steer: 'no',
    shape: 'asked in the prompt',
    goal: true,
    trace: true,
    skills: 'none',
    note: 'The one backend that arrives with humanize rather than being found on your PATH — its SDK and the runtime its turns are taken on are ordinary dependencies.',
  },
  {
    name: 'kimi',
    called: 'Kimi Code',
    driven: 'server',
    efforts: ['max', 'high', 'medium', 'low'],
    swarms: true,
    steer: 'queued, then steered in',
    shape: 'asked in the prompt',
    goal: true,
    trace: true,
    skills: 'its own, the shared one, the project’s',
    note: 'Its effort says how wide as well as how hard: “max” is one agent and “swarmmax” is the same thinking at the width of a fleet, so width is chosen beside the effort rather than among the rungs.',
  },
  {
    name: 'pi',
    called: 'pi',
    driven: 'held',
    efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal', 'off'],
    steer: 'a steer on the run it is making',
    shape: 'asked in the prompt',
    goal: false,
    trace: false,
    skills: 'its own, and the shared one',
    note: '“off” is the model asked not to think at all. That is an effort like any other here: the least of them, not the absence of a setting.',
  },
  {
    name: 'grok',
    called: 'Grok Build',
    driven: 'command',
    efforts: ['xhigh', 'high', 'medium', 'low'],
    steer: 'no',
    shape: 'held to it',
    goal: false,
    trace: false,
    skills: 'eight places, two of them other harnesses’',
    note: 'The ladder is written as it enumerates them when it refuses one, because a rung it refuses is a turn that never starts.',
  },
  {
    name: 'qwen',
    called: 'Qwen Code',
    driven: 'command',
    efforts: ['max', 'xhigh', 'high', 'medium', 'low'],
    steer: 'no',
    shape: 'held to it',
    goal: false,
    trace: false,
    skills: 'four places',
    note: 'It has no flag for an effort — they are a setting of its own settings file, so a turn is pointed at one of humanize’s instead of anybody’s being rewritten.',
  },
  {
    name: 'agy',
    called: 'Antigravity',
    driven: 'command',
    efforts: ['high', 'medium', 'low'],
    steer: 'no',
    shape: 'held to it',
    goal: false,
    trace: false,
    skills: 'its own',
    note: 'A conversation here is rows of a database whose payloads are protobuf, so there is no log to read a run’s cost out of as it is spent, and none to gather afterwards.',
  },
  {
    name: 'opencode',
    called: 'opencode',
    driven: 'command',
    efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'],
    steer: 'no',
    shape: 'asked in the prompt',
    goal: false,
    trace: false,
    skills: 'three places',
    note: 'Its effort is the model variant rather than a thinking level of its own, and a provider with no variants takes the flag and ignores it.',
  },
  {
    name: 'mimo',
    called: 'mimocode',
    driven: 'command',
    efforts: ['xhigh', 'high', 'medium', 'low', 'minimal'],
    steer: 'no',
    shape: 'asked in the prompt',
    goal: false,
    trace: false,
    skills: 'five places',
    note: 'A fork of opencode, and one directory more: it reads Codex’s skills as well as Claude Code’s.',
  },
  {
    name: 'zcode',
    called: 'ZCode',
    driven: 'server',
    efforts: ['max', 'high', 'low', 'enabled', 'nothink', 'disabled'],
    steer: 'no',
    shape: 'asked in the prompt',
    goal: true,
    trace: false,
    skills: 'four places, the shared one included',
    note: 'Its ladder is two vocabularies at once, because its models have two: the ones that take a thinking budget answer “max”, “high”, “low” and “nothink”, and the ones that only take thinking or not answer “enabled” or “disabled”. A model narrows it to its own half.',
  },
  {
    name: 'yours',
    called: 'anything speaking ACP',
    driven: 'protocol',
    efforts: ['as configured'],
    steer: 'no',
    shape: 'asked in the prompt',
    goal: false,
    trace: false,
    skills: 'none',
    note: 'The protocol says nothing about which models an agent runs or how hard it may be asked to think — both are the agent’s own — so one rung is offered and none is sent.',
  },
]

interface Want {
  key: string
  said: string
  holds: (one: Backend) => boolean
}

const WANTS: Want[] = [
  { key: 'steer', said: 'takes a word mid-turn', holds: (one) => one.steer !== 'no' },
  { key: 'shape', said: 'held to a shape', holds: (one) => one.shape === 'held to it' },
  { key: 'goal', said: 'has a goal of its own', holds: (one) => one.goal },
  { key: 'trace', said: 'can be read back into a trace', holds: (one) => one.trace },
  { key: 'swarm', said: 'runs a turn as a fleet', holds: (one) => Boolean(one.swarms) },
]

const wanted = ref<string[]>([])
const opened = ref('claude')

function want(key: string) {
  wanted.value = wanted.value.includes(key)
    ? wanted.value.filter((one) => one !== key)
    : [...wanted.value, key]
}

const asked = computed(() => WANTS.filter((one) => wanted.value.includes(one.key)))
const fits = (one: Backend) => asked.value.every((each) => each.holds(one))
const open = computed(() => BACKENDS.find((one) => one.name === opened.value) ?? BACKENDS[0])
const counted = computed(() => BACKENDS.filter(fits).length)

function backendLabel(one: Backend) {
  return [
    one.name,
    `driven through ${DRIVEN[one.driven]}`,
    `hardest effort ${one.efforts[0]}`,
    `mid-turn ${one.steer}`,
    `shape ${one.shape}`,
    `goal ${one.goal ? 'yes' : 'no'}`,
    `trace ${one.trace ? 'read back' : 'no reader'}`,
  ].join(', ')
}
</script>

<template>
  <div class="backends hmz-panel">
    <div class="bar">
      <span class="what">what a flow may ask an agent for</span>
      <div class="wants" role="group" aria-label="filter backends by capability">
        <button
          v-for="one in WANTS"
          :key="one.key"
          type="button"
          :aria-pressed="wanted.includes(one.key)"
          :class="{ on: wanted.includes(one.key) }"
          @click="want(one.key)"
        >
          {{ one.said }}
        </button>
      </div>
      <span class="count" aria-live="polite">
        {{ counted }} of {{ BACKENDS.length }}
      </span>
    </div>

    <div class="table">
      <div class="head">
        <span>backend</span>
        <span>driven through</span>
        <span>hardest effort</span>
        <span>mid-turn</span>
        <span>a shape</span>
        <span>a goal</span>
        <span>trace</span>
      </div>
      <button
        v-for="one in BACKENDS"
        :key="one.name"
        type="button"
        class="row"
        :class="{ dim: !fits(one), on: opened === one.name }"
        :aria-label="backendLabel(one)"
        :aria-pressed="opened === one.name"
        aria-controls="backend-detail"
        @click="opened = one.name"
      >
        <span class="name">
          <code>{{ one.name }}</code>
          <em>{{ one.called }}</em>
        </span>
        <span class="how">{{
          one.driven === 'held'
            ? 'one process, held open'
            : one.driven === 'server'
              ? 'its own app server'
              : one.driven === 'command'
                ? 'its command line, per turn'
                : one.driven === 'sdk'
                  ? 'its Python SDK'
                  : 'the protocol'
        }}</span>
        <span class="rung">{{ one.efforts[0] }}<em v-if="one.swarms"> · swarm…</em></span>
        <span :class="{ yes: one.steer !== 'no', no: one.steer === 'no' }">{{ one.steer }}</span>
        <span :class="{ yes: one.shape === 'held to it' }">{{ one.shape }}</span>
        <span :class="one.goal ? 'yes' : 'no'">{{ one.goal ? 'yes' : 'no' }}</span>
        <span :class="one.trace ? 'yes' : 'no'">{{ one.trace ? 'read back' : 'no reader' }}</span>
      </button>
    </div>

    <div id="backend-detail" class="open" role="status" aria-live="polite">
      <div class="ladder">
        <span class="lab">{{ open.name }} · its own ladder, hardest first</span>
        <div class="rungs">
          <span v-for="(one, i) in open.efforts" :key="one" :style="{ '--i': i }">
            {{ one }}
          </span>
        </div>
        <p class="cut">
          A model narrows this to the rungs that model takes, in the ladder's own order, and it
          is the backend that says which — asked, not written down.
        </p>
      </div>
      <div class="said">
        <p class="driven"><strong>driven through</strong> {{ DRIVEN[open.driven] }}</p>
        <p class="trace">
          <strong>trace read-back</strong>
          {{
            open.trace
              ? 'humanize can collect this backend’s session log into a Chrome trace'
              : 'no trace reader yet — it may still write logs or report usage while it runs'
          }}
        </p>
        <p class="skills"><strong>skills it would load</strong> {{ open.skills }}</p>
        <p class="note">{{ open.note }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.wants {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
}

.wants button {
  padding: 3px 11px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11px;
  cursor: pointer;
}

.wants button.on {
  border-style: solid;
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.count {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-2);
}

.table {
  padding: 8px 10px 0;
  overflow-x: auto;
}

.head,
.row {
  display: grid;
  grid-template-columns:
    124px minmax(116px, 1.1fr) 76px minmax(104px, 1.2fr)
    minmax(94px, 1fr) 44px minmax(72px, 0.9fr);
  gap: 8px;
  align-items: center;
  min-width: 660px;
  padding: 7px 10px;
  text-align: left;
}

.head {
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
  border-bottom: 1px solid var(--vp-c-divider);
}

.row {
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  font-size: 12px;
  color: var(--vp-c-text-2);
  cursor: pointer;
  transition: opacity 0.2s, background 0.2s, border-color 0.2s;
}

.row:hover {
  background: var(--vp-c-default-soft);
}

.row.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
}

.row.dim {
  opacity: 0.72;
}

.name {
  display: flex;
  flex-direction: column;
}

.name code {
  font-size: 12.5px;
  color: var(--vp-c-text-1);
  font-weight: 650;
}

.name em {
  font-style: normal;
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

.rung {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
}

.rung em {
  font-style: normal;
  color: var(--hmz-accent-2);
}

.row .yes {
  color: var(--hmz-accent);
}

.row .no {
  color: var(--vp-c-text-3);
}

.open {
  display: grid;
  grid-template-columns: minmax(0, 320px) minmax(0, 1fr);
  gap: 18px;
  margin: 12px 16px 16px;
  padding: 14px 16px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}

.lab {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.rungs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0 0;
}

.rungs span {
  padding: 4px 10px;
  border-radius: 7px;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  color: var(--vp-c-text-1);
  background: linear-gradient(
    90deg,
    var(--vp-c-brand-soft) calc(100% - var(--i) * 14%),
    transparent calc(100% - var(--i) * 14%)
  );
  animation: rung 0.4s ease backwards;
  animation-delay: calc(var(--i) * 40ms);
}

@keyframes rung {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
}

.cut {
  margin: 10px 0 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--vp-c-text-3);
}

.said p {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.said strong {
  color: var(--vp-c-text-1);
  margin-right: 8px;
}

.said .note {
  color: var(--vp-c-text-3);
}

@media (max-width: 780px) {
  .open {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .rungs span {
    animation: none;
  }
}
</style>
