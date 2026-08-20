<script setup lang="ts">
// An atlas is read into a prophecy before its first node runs. This drawing keeps the same
// small review loop under four lenses: what the compiler settles, what the static reading
// refuses, which edits change the graph, and where a stopped walk continues.
import { computed, ref } from 'vue'

type Mode = 'compile' | 'check' | 'evolve' | 'resume'
type Check = 'sound' | 'dead' | 'shape' | 'verdict'
type Edit = 'format' | 'body' | 'graph'

interface Choice<T extends string> {
  key: T
  name: string
}

interface Finding extends Choice<Check> {
  level: 'pass' | 'error' | 'warning'
  code: string
  said: string
}

const MODES: Choice<Mode>[] = [
  { key: 'compile', name: 'compile it' },
  { key: 'check', name: 'read it statically' },
  { key: 'evolve', name: 'change the source' },
  { key: 'resume', name: 'pick it up' },
]

const CHECKS: Finding[] = [
  {
    key: 'sound',
    name: 'sound graph',
    level: 'pass',
    code: 'prophecy emitted',
    said: 'Every call is shaped, the branch follows logic, and the loop changes what its head reads.',
  },
  {
    key: 'dead',
    name: 'unchanged loop head',
    level: 'error',
    code: 'dead-loop',
    said: 'The round changes a draft but never the verdict its head reads, so the next decision cannot differ.',
  },
  {
    key: 'shape',
    name: 'wrong edge shape',
    level: 'error',
    code: 'shape-mismatch',
    said: 'This connection offers a Draft where the deciding node declares that it takes a Verdict.',
  },
  {
    key: 'verdict',
    name: 'impossible verdict',
    level: 'warning',
    code: 'unknown-verdict',
    said: 'The declared answer offers “done” and “redo”; comparing it with “DONE” guards nothing.',
  },
]

const EDITS: Choice<Edit>[] = [
  { key: 'format', name: 'comment or layout' },
  { key: 'body', name: 'node body' },
  { key: 'graph', name: 'edge or shape' },
]

const BASE_DIGEST = '06ebb726641e4a5f'
const MOVED_DIGEST = '4c9a01ab2f7e5510'

const mode = ref<Mode>('compile')
const nested = ref(false)
const check = ref<Check>('sound')
const edit = ref<Edit>('format')
const shipped = ref(true)
const graphChanged = ref(false)
const resumed = ref(false)

const finding = computed(() => CHECKS.find((one) => one.key === check.value) ?? CHECKS[0])
const currentDigest = computed(() => (edit.value === 'graph' ? MOVED_DIGEST : BASE_DIGEST))
const drifted = computed(() => shipped.value && currentDigest.value !== BASE_DIGEST)

const rail = computed(() => {
  if (mode.value === 'compile') {
    return ['restricted atlas body', 'syntax-tree reading', 'typed prophecy']
  }
  if (mode.value === 'check') return ['every Python file', 'zero execution', finding.value.code]
  if (mode.value === 'evolve') return ['source graph', 'canonical text', currentDigest.value]
  return ['saved visits', 'same digest?', 'first visit with no answer']
})

const intro = computed(() => {
  if (mode.value === 'compile') {
    return nested.value
      ? 'Open the supernode: one node in the outer graph is a complete prophecy underneath.'
      : 'The body is never called. Its call sites, bindings, branches and return become this graph.'
  }
  if (mode.value === 'check') {
    return 'Change one fact. The reading says everything it can establish without importing the flow.'
  }
  if (mode.value === 'evolve') {
    return 'Change the source and compare graph identity. A graph edit is different from an implementation edit.'
  }
  return graphChanged.value
    ? 'The stopped run names another prophecy. Picking it up must begin at the way in.'
    : 'The stopped run has four answers and stopped inside the fifth visit.'
})

const aria = computed(() => {
  if (mode.value === 'check') return `A review-loop prophecy showing ${finding.value.code}`
  if (mode.value === 'evolve') return `A review-loop prophecy with digest ${currentDigest.value}`
  if (mode.value === 'resume') {
    if (!resumed.value) return 'A review-loop prophecy stopped inside review visit two'
    return graphChanged.value
      ? 'A changed prophecy starting again at write visit one'
      : 'The same prophecy continuing at review visit two'
  }
  return nested.value
    ? 'A review-loop prophecy with review expanded as a nested prophecy'
    : 'A typed review-loop prophecy compiled from an atlas'
})

const completed = computed(() => {
  if (mode.value !== 'resume' || graphChanged.value) return new Set<string>()
  return new Set(['write', 'review', 'settled', 'write2'])
})

const stale = computed(() => {
  if (mode.value !== 'resume' || !graphChanged.value || resumed.value) return new Set<string>()
  return new Set(['write', 'review', 'settled', 'write2'])
})

const active = computed(() => {
  if (mode.value !== 'resume' || !resumed.value) return ''
  return graphChanged.value ? 'write' : 'review2'
})

const stopped = computed(() =>
  mode.value === 'resume' && !resumed.value ? 'review2' : '',
)

const readout = computed(() => {
  if (mode.value === 'compile') {
    return nested.value
      ? {
          kicker: 'one node outside · one prophecy within',
          title: 'The nested graph is compiled too',
          body:
            'Its nodes, edges and shapes sit beneath reviewing. A path back into a prophecy already being compiled is refused, so the nesting always has a bottom.',
        }
      : {
          kicker: 'nodes · edges · shapes · ways out',
          title: 'The graph is the executable plan',
          body:
            'Mind nodes take turns; logic nodes decide. The back-edge runs settled again with the new review, and the named way out ends the walk.',
        }
  }
  if (mode.value === 'check') {
    return {
      kicker: `${finding.value.level} · ${finding.value.code}`,
      title: finding.value.name,
      body: finding.value.said,
    }
  }
  if (mode.value === 'evolve') {
    if (edit.value === 'format') {
      return {
        kicker: 'same digest',
        title: 'Formatting is not graph identity',
        body:
          'Comments, docstring layout and line numbers are absent from the prophecy. The source moved; the graph did not.',
      }
    }
    if (edit.value === 'body') {
      return {
        kicker: 'same digest · current implementation',
        title: 'Work may change beneath a stable graph',
        body:
          'Function bodies are not graph structure. The next run loads the current node code while completed visits keep the answers they already wrote.',
      }
    }
    return drifted.value
      ? {
          kicker: 'error · stale-prophecy',
          title: 'The source and shipped graph disagree',
          body:
            'A run walks the shipped graph, so the static reading reports both digests instead of pretending the package now does what the source draws.',
        }
      : {
          kicker: 'new digest',
          title: 'A changed graph is another prophecy',
          body:
            'Changing an edge, node signature, shape or nested prophecy changes identity. Saved visits from the old graph do not cross that line.',
        }
  }
  if (!resumed.value) {
    return {
      kicker: 'stopped · review:2#1',
      title: 'Four visits already have answers',
      body:
        'The current visit was written before it ran. It has no answer yet, which is how the next run knows exactly where work was interrupted.',
    }
  }
  return graphChanged.value
    ? {
        kicker: 'digest mismatch · state cleared',
        title: 'The new graph starts at the top',
        body:
          'Node names that happen to survive an edit are not proof that they still mean the same work. The first visit is write#1 again.',
      }
    : {
        kicker: 'same digest · four answers replayed',
        title: 'The interrupted node runs again',
        body:
          'The walk rebuilds the values above it without rerunning their nodes, then reaches review:2#1 with no answer. By default, unfinished work runs again.',
      }
})

function chooseMode(next: Mode) {
  mode.value = next
  resumed.value = false
}

function chooseGraph(changed: boolean) {
  graphChanged.value = changed
  resumed.value = false
}

function badNode(id: string) {
  if (mode.value !== 'check') return false
  if (check.value === 'shape') return id === 'review' || id === 'settled'
  if (check.value === 'verdict') return id === 'settled'
  if (check.value === 'dead') return id === 'write2'
  return false
}
</script>

<template>
  <div class="prophecy hmz-panel">
    <div class="bar">
      <div class="tabs" role="group" aria-label="which property of the prophecy to inspect">
        <button
          v-for="one in MODES"
          :key="one.key"
          type="button"
          :aria-pressed="mode === one.key"
          :class="{ on: mode === one.key }"
          @click="chooseMode(one.key)"
        >
          {{ one.name }}
        </button>
      </div>

      <div class="spacer" />

      <label v-if="mode === 'compile'" class="switch">
        <input v-model="nested" type="checkbox" />
        open a supernode
      </label>
      <label v-else-if="mode === 'evolve'" class="switch">
        <input v-model="shipped" type="checkbox" />
        a prophecy is shipped
      </label>
      <button
        v-else-if="mode === 'resume'"
        class="resume-button"
        type="button"
        :disabled="resumed"
        @click="resumed = true"
      >
        {{ resumed ? 'picked up' : 'pick it up' }}
      </button>
    </div>

    <p class="intro">{{ intro }}</p>

    <div v-if="mode === 'check'" class="choices" role="group" aria-label="static finding">
      <button
        v-for="one in CHECKS"
        :key="one.key"
        type="button"
        :aria-pressed="check === one.key"
        :class="[{ on: check === one.key }, one.level]"
        @click="check = one.key"
      >
        {{ one.name }}
      </button>
    </div>

    <div v-else-if="mode === 'evolve'" class="choices" role="group" aria-label="source edit">
      <button
        v-for="one in EDITS"
        :key="one.key"
        type="button"
        :aria-pressed="edit === one.key"
        :class="{ on: edit === one.key }"
        @click="edit = one.key"
      >
        {{ one.name }}
      </button>
    </div>

    <div v-else-if="mode === 'resume'" class="choices" role="group" aria-label="prophecy identity">
      <button
        type="button"
        :aria-pressed="!graphChanged"
        :class="{ on: !graphChanged }"
        @click="chooseGraph(false)"
      >
        same prophecy
      </button>
      <button
        type="button"
        :aria-pressed="graphChanged"
        :class="{ on: graphChanged }"
        @click="chooseGraph(true)"
      >
        graph changed
      </button>
    </div>

    <div class="rail">
      <template v-for="(one, i) in rail" :key="one">
        <span :class="{ digest: i === rail.length - 1 && mode === 'evolve' }">{{ one }}</span>
        <i v-if="i < rail.length - 1" aria-hidden="true">→</i>
      </template>
    </div>

    <div class="canvas">
      <svg viewBox="0 0 900 350" role="img" :aria-label="aria">
        <defs>
          <marker
            id="prophecy-arrow"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="4"
            orient="auto"
          >
            <path d="M 0 0 L 8 4 L 0 8 z" class="arrow-head" />
          </marker>
          <marker
            id="prophecy-arrow-bad"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="4"
            orient="auto"
          >
            <path d="M 0 0 L 8 4 L 0 8 z" class="arrow-head bad" />
          </marker>
        </defs>

        <path class="edge" d="M 51 132 L 79 132" />
        <path class="edge" d="M 211 132 L 264 132" />
        <path
          class="edge"
          :class="{ bad: mode === 'check' && check === 'shape' }"
          d="M 396 132 L 459 132"
        />
        <path
          class="edge"
          :class="{
            bad: mode === 'check' && check === 'verdict',
            changed: mode === 'evolve' && edit === 'graph',
          }"
          d="M 591 132 L 773 132"
        />
        <path class="edge" d="M 525 164 L 525 238" />
        <path
          v-if="!(mode === 'check' && check === 'dead')"
          class="edge"
          d="M 459 270 L 396 270"
        />
        <path
          v-if="!(mode === 'check' && check === 'dead')"
          class="edge back"
          d="M 330 238 C 330 198, 420 188, 459 153"
        />
        <path
          v-else
          class="edge back bad"
          d="M 459 270 C 375 270, 380 190, 459 153"
        />

        <text x="238" y="117" class="edge-label">Draft</text>
        <text
          x="427"
          y="117"
          class="edge-label"
          :class="{ bad: mode === 'check' && check === 'shape' }"
        >
          {{ mode === 'check' && check === 'shape' ? 'Draft ≠ Verdict' : 'Verdict' }}
        </text>
        <text
          x="666"
          y="117"
          class="edge-label"
          :class="{ bad: mode === 'check' && check === 'verdict' }"
        >
          {{ mode === 'check' && check === 'verdict' ? 'status = “DONE”' : 'done' }}
        </text>
        <text x="542" y="207" class="edge-label">not done</text>
        <text
          v-if="mode === 'check' && check === 'dead'"
          x="378"
          y="224"
          class="edge-label bad"
        >
          verdict unchanged
        </text>

        <circle cx="38" cy="132" r="13" class="terminal" />
        <text x="38" y="105" class="terminal-label">way in</text>

        <g
          class="node mind"
          :class="{
            bad: badNode('write'),
            done: completed.has('write'),
            stale: stale.has('write'),
            active: active === 'write',
          }"
        >
          <rect x="79" y="100" width="132" height="64" rx="11" />
          <text x="145" y="127" class="node-title">write</text>
          <text x="145" y="149" class="node-kind">mind · Draft</text>
        </g>

        <g
          class="node"
          :class="[
            mode === 'compile' && nested ? 'atlas' : 'mind',
            {
              bad: badNode('review'),
              done: completed.has('review'),
              stale: stale.has('review'),
            },
          ]"
        >
          <rect x="264" y="100" width="132" height="64" rx="11" />
          <text x="330" y="127" class="node-title">
            {{ mode === 'compile' && nested ? 'reviewing' : 'review' }}
          </text>
          <text x="330" y="149" class="node-kind">
            {{ mode === 'compile' && nested ? 'atlas · Verdict' : 'mind · Verdict' }}
          </text>
        </g>

        <g
          class="node logic"
          :class="{
            bad: badNode('settled'),
            done: completed.has('settled'),
            stale: stale.has('settled'),
          }"
        >
          <rect x="459" y="100" width="132" height="64" rx="11" />
          <text x="525" y="127" class="node-title">settled</text>
          <text x="525" y="149" class="node-kind">logic · Verdict</text>
        </g>

        <g
          class="node mind"
          :class="{
            bad: badNode('write2'),
            done: completed.has('write2'),
            stale: stale.has('write2'),
          }"
        >
          <rect x="459" y="238" width="132" height="64" rx="11" />
          <text x="525" y="265" class="node-title">write:2</text>
          <text x="525" y="287" class="node-kind">mind · Draft</text>
        </g>

        <g
          v-if="!(mode === 'check' && check === 'dead')"
          class="node"
          :class="[
            mode === 'compile' && nested ? 'atlas' : 'mind',
            {
              done: completed.has('review2'),
              stale: stale.has('review2'),
              active: active === 'review2',
              stopped: stopped === 'review2',
            },
          ]"
        >
          <rect x="264" y="238" width="132" height="64" rx="11" />
          <text x="330" y="265" class="node-title">
            {{ mode === 'compile' && nested ? 'reviewing:2' : 'review:2' }}
          </text>
          <text x="330" y="287" class="node-kind">
            {{
              active === 'review2'
                ? 'runs again'
                : stopped === 'review2'
                  ? 'stopped here'
                  : mode === 'compile' && nested
                    ? 'atlas · Verdict'
                    : 'mind · Verdict'
            }}
          </text>
        </g>

        <circle cx="800" cy="132" r="19" class="terminal end" />
        <circle cx="800" cy="132" r="9" class="terminal end inner" />
        <text x="800" y="96" class="terminal-label">way out</text>

        <g v-if="mode === 'compile' && nested" class="under">
          <path d="M 330 164 C 470 188, 540 205, 615 224" class="under-line" />
          <rect x="615" y="198" width="250" height="119" rx="13" />
          <text x="740" y="220" class="under-title">under reviewing</text>
          <rect x="634" y="237" width="88" height="48" rx="8" class="under-node mind" />
          <text x="678" y="257" class="under-name">review</text>
          <text x="678" y="275" class="under-kind">mind</text>
          <path d="M 722 261 L 752 261" class="under-line arrow" />
          <rect x="752" y="237" width="94" height="48" rx="8" class="under-node logic" />
          <text x="799" y="257" class="under-name">settled</text>
          <text x="799" y="275" class="under-kind">logic</text>
          <text x="740" y="304" class="under-foot">one node outside · one graph inside</text>
        </g>
      </svg>
    </div>

    <div
      class="readout"
      :class="[
        mode,
        mode === 'check' ? finding.level : '',
        { drifted: mode === 'evolve' && drifted },
      ]"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <section class="explain">
        <span class="kicker">{{ readout.kicker }}</span>
        <strong>{{ readout.title }}</strong>
        <p>{{ readout.body }}</p>
      </section>

      <aside v-if="mode === 'compile'" class="facts">
        <span><b class="mind-dot" />mind <em>one turn · one way out</em></span>
        <span><b class="logic-dot" />logic <em>Python · may decide</em></span>
        <span><b class="atlas-dot" />atlas <em>another prophecy beneath it</em></span>
      </aside>

      <aside v-else-if="mode === 'check'" class="finding">
        <code>{{ finding.code }}</code>
        <span>{{ finding.level === 'pass' ? 'the graph may run' : 'file and line are named' }}</span>
        <small>the reading imported nothing and ran nothing</small>
      </aside>

      <aside v-else-if="mode === 'evolve'" class="digests">
        <span><em>source now</em><code>{{ currentDigest }}</code></span>
        <span v-if="shipped"><em>shipped</em><code>{{ BASE_DIGEST }}</code></span>
        <span v-else><em>shipped</em><code>none</code></span>
        <small>
          shipped bytes may name only the seven tuple types a prophecy is made of
        </small>
      </aside>

      <aside v-else class="state">
        <span><em>prophecy</em><code>{{ BASE_DIGEST }}</code></span>
        <span><em>current graph</em><code>{{ graphChanged ? MOVED_DIGEST : BASE_DIGEST }}</code></span>
        <span><em>at</em><code>{{ resumed && graphChanged ? 'write#1' : 'review:2#1' }}</code></span>
        <span><em>done</em><code>{{ resumed && graphChanged ? '0 visits' : '4 visits' }}</code></span>
      </aside>
    </div>

    <p class="drawn">drawn example · no flow or model was run</p>
  </div>
</template>

<style scoped>
.prophecy {
  overflow: hidden;
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
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

.tabs button,
.choices button,
.resume-button {
  padding: 5px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}

.tabs button.on,
.choices button.on,
.resume-button {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.tabs button:focus-visible,
.choices button:focus-visible,
.resume-button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.spacer {
  flex: 1;
}

.switch {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
  color: var(--vp-c-text-2);
  cursor: pointer;
}

.switch input {
  accent-color: var(--vp-c-brand-1);
}

.resume-button:disabled {
  opacity: 0.55;
  cursor: default;
}

.intro {
  margin: 0;
  padding: 12px 16px 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.choices {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  padding: 11px 16px 0;
}

.choices button {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 550;
}

.choices button.error.on,
.choices button.warning.on {
  border-color: var(--hmz-warm);
  background: color-mix(in srgb, var(--hmz-warm) 12%, transparent);
  color: var(--hmz-warm);
}

.rail {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  flex-wrap: wrap;
  padding: 16px 16px 2px;
  color: var(--vp-c-text-3);
}

.rail span {
  padding: 4px 9px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  background: var(--vp-c-bg);
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
}

.rail span.digest {
  color: var(--vp-c-brand-1);
}

.rail i {
  font-style: normal;
  color: var(--vp-c-brand-1);
}

.canvas {
  overflow-x: auto;
  padding: 0 12px;
}

svg {
  display: block;
  width: 100%;
  min-width: 760px;
  height: auto;
}

.edge,
.under-line {
  fill: none;
  stroke: var(--vp-c-text-3);
  stroke-width: 1.7;
  marker-end: url(#prophecy-arrow);
  transition: stroke 0.25s, stroke-width 0.25s, stroke-dasharray 0.25s;
}

.edge.back {
  stroke: var(--hmz-accent);
}

.edge.bad,
.edge.changed {
  stroke: var(--hmz-warm);
  stroke-width: 2.4;
  stroke-dasharray: 6 5;
  marker-end: url(#prophecy-arrow-bad);
}

.arrow-head {
  fill: var(--vp-c-text-3);
}

.arrow-head.bad {
  fill: var(--hmz-warm);
}

.edge-label,
.terminal-label {
  fill: var(--vp-c-text-3);
  font-size: 10.5px;
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
}

.edge-label.bad {
  fill: var(--hmz-warm);
  font-weight: 700;
}

.terminal {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-text-3);
  stroke-width: 1.8;
}

.terminal.end {
  stroke: var(--vp-c-brand-1);
}

.terminal.end.inner {
  fill: var(--vp-c-brand-1);
  stroke: none;
}

.node rect {
  fill: var(--vp-c-bg);
  stroke: var(--tone);
  stroke-width: 1.7;
  transition: fill 0.25s, stroke 0.25s, stroke-width 0.25s, opacity 0.25s;
}

.node.mind {
  --tone: var(--hmz-lane-1);
}

.node.logic {
  --tone: var(--hmz-accent);
}

.node.atlas {
  --tone: var(--hmz-accent-2);
}

.node-title {
  fill: var(--vp-c-text-1);
  font-size: 13px;
  font-weight: 700;
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
}

.node-kind {
  fill: var(--tone);
  font-size: 10.5px;
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
}

.node.done rect {
  fill: color-mix(in srgb, var(--hmz-accent) 14%, var(--vp-c-bg));
  stroke: var(--hmz-accent);
}

.node.active rect {
  fill: var(--vp-c-brand-soft);
  stroke: var(--vp-c-brand-1);
  stroke-width: 2.8;
}

.node.stopped rect,
.node.bad rect {
  fill: color-mix(in srgb, var(--hmz-warm) 11%, var(--vp-c-bg));
  stroke: var(--hmz-warm);
  stroke-width: 2.4;
  stroke-dasharray: 5 4;
}

.node.stopped .node-kind,
.node.bad .node-kind {
  fill: var(--hmz-warm);
}

.node.stale rect {
  opacity: 0.5;
  stroke-dasharray: 3 4;
}

.under > rect {
  fill: var(--vp-c-bg-soft);
  stroke: var(--hmz-accent-2);
  stroke-width: 1.4;
  stroke-dasharray: 4 4;
}

.under-line {
  stroke: var(--hmz-accent-2);
  marker-end: none;
}

.under-line.arrow {
  marker-end: url(#prophecy-arrow);
}

.under-title,
.under-foot,
.under-name,
.under-kind {
  text-anchor: middle;
  font-family: var(--vp-font-family-mono);
}

.under-title {
  fill: var(--hmz-accent-2);
  font-size: 10.5px;
  font-weight: 700;
}

.under-foot {
  fill: var(--vp-c-text-3);
  font-size: 9.5px;
}

.under-node {
  fill: var(--vp-c-bg);
  stroke-width: 1.4;
}

.under-node.mind {
  stroke: var(--hmz-lane-1);
}

.under-node.logic {
  stroke: var(--hmz-accent);
}

.under-name {
  fill: var(--vp-c-text-1);
  font-size: 10.5px;
  font-weight: 650;
}

.under-kind {
  fill: var(--vp-c-text-3);
  font-size: 9px;
}

.readout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 0.7fr);
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.explain {
  padding: 15px 18px;
}

.kicker {
  display: block;
  margin-bottom: 4px;
  color: var(--vp-c-brand-1);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.readout.error .kicker,
.readout.warning .kicker,
.readout.drifted .kicker {
  color: var(--hmz-warm);
}

.explain strong {
  display: block;
  color: var(--vp-c-text-1);
  font-size: 13px;
}

.explain p {
  margin: 5px 0 0;
  color: var(--vp-c-text-2);
  font-size: 12px;
  line-height: 1.6;
}

.facts,
.finding,
.digests,
.state {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 7px;
  padding: 13px 18px;
  border-left: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg-soft);
}

.facts span {
  display: grid;
  grid-template-columns: 10px 44px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-2);
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
}

.facts b {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.mind-dot {
  background: var(--hmz-lane-1);
}

.logic-dot {
  background: var(--hmz-accent);
}

.atlas-dot {
  background: var(--hmz-accent-2);
}

.facts em {
  color: var(--vp-c-text-3);
  font-style: normal;
}

.finding code {
  color: var(--vp-c-brand-1);
  font-size: 13px;
  font-weight: 700;
}

.readout.error .finding code,
.readout.warning .finding code {
  color: var(--hmz-warm);
}

.finding span,
.finding small,
.digests small {
  color: var(--vp-c-text-3);
  font-size: 10.5px;
  line-height: 1.45;
}

.digests span,
.state span {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.digests em,
.state em {
  color: var(--vp-c-text-3);
  font-size: 10.5px;
  font-style: normal;
}

.digests code,
.state code {
  color: var(--vp-c-brand-1);
  font-size: 10.5px;
}

.readout.drifted .digests code {
  color: var(--hmz-warm);
}

.drawn {
  margin: 0;
  padding: 7px 16px;
  border-top: 1px solid var(--hmz-panel-border);
  color: var(--vp-c-text-3);
  font-size: 9.5px;
  letter-spacing: 0.08em;
  text-align: right;
  text-transform: uppercase;
}

@media (max-width: 760px) {
  .spacer {
    display: none;
  }

  .switch,
  .resume-button {
    margin-left: auto;
  }

  .readout {
    grid-template-columns: minmax(0, 1fr);
  }

  .facts,
  .finding,
  .digests,
  .state {
    border-top: 1px solid var(--hmz-panel-border);
    border-left: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tabs button,
  .choices button,
  .resume-button,
  .edge,
  .under-line,
  .node rect {
    transition: none;
  }
}
</style>
