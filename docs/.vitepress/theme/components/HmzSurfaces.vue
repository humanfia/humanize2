<script setup lang="ts">
// A flow found in a flowverse becomes the local copy without changing its name; the model
// it declares becomes every setup surface; and each way into humanize reaches the same
// workspace, loader and runner without pretending that every way in has the same job.
import { computed, ref } from 'vue'

type LookupState = 'hit' | 'miss' | 'later'
type PlanMode = 'discussion' | 'direct'
type SurfaceKey = 'python' | 'cli' | 'tui' | 'daemon'

const PLAN_MODES: PlanMode[] = ['discussion', 'direct']

interface LookupRow {
  key: string
  name: string
  note: string
  state: LookupState
}

interface Surface {
  key: SurfaceKey
  label: string
  about: string
  path: string[]
  nodes: string[]
}

interface GraphNode {
  id: string
  label: string
  x: number
  y: number
  width: number
}

interface GraphEdge {
  id: string
  d: string
}

const forked = ref(false)
const genIdea = ref(true)
const genPlan = ref(true)
const planMode = ref<PlanMode>('discussion')
const surface = ref<SurfaceKey>('tui')
const attached = ref(1)

const lookup = computed<LookupRow[]>(() =>
  forked.value
    ? [
        {
          key: 'local',
          name: 'this project',
          note: 'the whole fork is here',
          state: 'hit',
        },
        { key: 'user', name: 'your home', note: 'not reached', state: 'later' },
        { key: 'builtin', name: 'built in', note: 'not reached', state: 'later' },
        {
          key: 'official',
          name: 'official',
          note: 'still there, not reached',
          state: 'later',
        },
        { key: 'added', name: 'added flowverses', note: 'not reached', state: 'later' },
      ]
    : [
        { key: 'local', name: 'this project', note: 'no flow by this name', state: 'miss' },
        { key: 'user', name: 'your home', note: 'no flow by this name', state: 'miss' },
        { key: 'builtin', name: 'built in', note: 'no flow by this name', state: 'miss' },
        {
          key: 'official',
          name: 'official',
          note: 'the first match',
          state: 'hit',
        },
        { key: 'added', name: 'added flowverses', note: 'not reached', state: 'later' },
      ],
)

const configAccepted = computed(() => !genIdea.value || genPlan.value)
const configState = computed(() =>
  configAccepted.value
    ? [
        'accepted',
        `idea ${genIdea.value ? 'on' : 'off'}`,
        `plan ${genPlan.value ? 'on' : 'off'}`,
        planMode.value,
      ].join(' · ')
    : 'refused · gen idea is on while gen plan is off',
)
const resolved = computed(() =>
  forked.value
    ? 'this project’s humanize1:gen-plan'
    : 'official’s humanize1:gen-plan',
)

const SURFACES: Surface[] = [
  {
    key: 'python',
    label: 'Python SDK',
    about:
      'Builds a Run around the loaded runner and task, then runs it here or on a ' +
      'thread of its own.',
    path: [
      'python-workspace',
      'workspace-run',
      'run-runner',
      'runner-conversations',
      'runner-cycle',
    ],
    nodes: ['python', 'workspace', 'run', 'runner', 'conversations', 'cycle'],
  },
  {
    key: 'cli',
    label: 'CLI',
    about:
      'Reads the line into the same flow, agents, task and setup, then drives the SDK ' +
      'Run to its return.',
    path: [
      'cli-workspace',
      'workspace-run',
      'run-runner',
      'runner-conversations',
      'runner-cycle',
    ],
    nodes: ['cli', 'workspace', 'run', 'runner', 'conversations', 'cycle'],
  },
  {
    key: 'tui',
    label: 'TUI',
    about:
      'Keeps the workspace and runner in hand so it can configure, watch and steer the ' +
      'agent conversations while they run.',
    path: ['tui-workspace', 'workspace-runner', 'runner-conversations', 'runner-cycle'],
    nodes: ['tui', 'workspace', 'runner', 'conversations', 'cycle'],
  },
  {
    key: 'daemon',
    label: 'daemon',
    about:
      'Holds the same terminal interface apart from any terminal. Its Session boundary ' +
      'counts readers and lets them detach.',
    path: [
      'daemon-session',
      'session-tui',
      'tui-workspace',
      'workspace-runner',
      'runner-conversations',
      'runner-cycle',
    ],
    nodes: ['daemon', 'session', 'tui', 'workspace', 'runner', 'conversations', 'cycle'],
  },
]

const NODES: GraphNode[] = [
  { id: 'python', label: 'Python SDK', x: 88, y: 42, width: 146 },
  { id: 'cli', label: 'CLI', x: 88, y: 102, width: 146 },
  { id: 'tui', label: 'terminal interface', x: 88, y: 162, width: 146 },
  { id: 'daemon', label: 'daemon', x: 88, y: 238, width: 146 },
  { id: 'workspace', label: 'one Hmz workspace', x: 304, y: 102, width: 166 },
  { id: 'session', label: 'Session boundary', x: 304, y: 238, width: 166 },
  { id: 'run', label: 'Run lifecycle', x: 510, y: 54, width: 150 },
  { id: 'runner', label: 'one runner', x: 710, y: 102, width: 150 },
  { id: 'cycle', label: 'cycle record', x: 510, y: 222, width: 150 },
  { id: 'conversations', label: 'agent conversations', x: 710, y: 222, width: 166 },
]

const EDGES: GraphEdge[] = [
  { id: 'python-workspace', d: 'M 161 42 C 205 42, 207 82, 221 94' },
  { id: 'cli-workspace', d: 'M 161 102 L 221 102' },
  { id: 'tui-workspace', d: 'M 161 162 C 202 162, 205 122, 221 110' },
  { id: 'daemon-session', d: 'M 161 238 L 221 238' },
  { id: 'session-tui', d: 'M 221 230 C 202 217, 202 172, 161 164' },
  { id: 'workspace-run', d: 'M 387 92 C 414 72, 426 58, 435 56' },
  { id: 'run-runner', d: 'M 585 56 C 617 58, 621 88, 635 96' },
  { id: 'workspace-runner', d: 'M 387 116 C 482 154, 576 151, 635 112' },
  { id: 'runner-conversations', d: 'M 710 124 L 710 200' },
  { id: 'runner-cycle', d: 'M 650 124 C 620 174, 592 207, 585 216' },
]

const pickedSurface = computed(() => SURFACES.find((one) => one.key === surface.value)!)
const activeEdges = computed(() => new Set(pickedSurface.value.path))
const activeNodes = computed(() => new Set(pickedSurface.value.nodes))
const graphDescription = computed(
  () => `${pickedSurface.value.label}. ${pickedSurface.value.about}`,
)

function forkFlow() {
  forked.value = true
}

function reset() {
  forked.value = false
  genIdea.value = true
  genPlan.value = true
  planMode.value = 'discussion'
  surface.value = 'tui'
  attached.value = 1
}
</script>

<template>
  <div class="surfaces hmz-panel">
    <div class="bar">
      <span>one flow, one accepted setup, one runtime</span>
      <button type="button" class="reset" @click="reset">start over</button>
    </div>

    <div class="upper">
      <section class="pane discovery">
        <header>
          <span class="step">1</span>
          <div>
            <strong>Find it near you, then make it yours</strong>
            <p>An unqualified name stops at the first place that holds it.</p>
          </div>
        </header>

        <div class="query">
          <span>humanize1 : gen-plan</span>
          <em>nearest first</em>
        </div>
        <ol class="lookup" aria-label="flow lookup order">
          <li v-for="(one, i) in lookup" :key="one.key" :class="one.state">
            <span class="number">{{ i + 1 }}</span>
            <strong>{{ one.name }}</strong>
            <span>{{ one.note }}</span>
          </li>
        </ol>

        <div class="fork">
          <button type="button" :disabled="forked" @click="forkFlow">
            {{ forked ? 'forked into this project' : 'fork the official flow' }}
          </button>
          <p aria-live="polite">
            <template v-if="forked">
              Staged beside the destination, then moved into place whole. The source is
              unchanged.
            </template>
            <template v-else>
              The entry point, helpers and skills travel together; an existing local flow is
              never overwritten.
            </template>
          </p>
        </div>

        <p class="qualified">
          <strong>official / humanize1 : gen-plan</strong> stays pinned to the source, before
          and after the fork.
        </p>
      </section>

      <section class="pane config">
        <header>
          <span class="step">2</span>
          <div>
            <strong>Let the flow draw its own setup</strong>
            <p>A few fields from this flow's model, grouped the way the model groups them.</p>
          </div>
        </header>

        <div class="group">gen-idea</div>
        <label class="field switch">
          <span class="field-copy">
            <strong>gen idea</strong>
            <span>open the idea into a grounded draft</span>
          </span>
          <span class="toggle">
            <input v-model="genIdea" type="checkbox" />
            {{ genIdea ? 'on' : 'off' }}
          </span>
        </label>

        <div class="group plan">gen-plan</div>
        <label class="field switch">
          <span class="field-copy">
            <strong>gen plan</strong>
            <span>turn the draft into a plan</span>
          </span>
          <span class="toggle">
            <input v-model="genPlan" type="checkbox" />
            {{ genPlan ? 'on' : 'off' }}
          </span>
        </label>

        <div class="field">
          <div class="field-copy">
            <strong>plan mode</strong>
            <span>converge, or write it once</span>
          </div>
          <div class="choices" role="group" aria-label="plan mode">
            <button
              v-for="one in PLAN_MODES"
              :key="one"
              type="button"
              :aria-pressed="planMode === one"
              :class="{ on: planMode === one }"
              @click="planMode = one"
            >
              {{ one }}
            </button>
          </div>
        </div>

        <p
          id="surface-config-state"
          class="validation"
          :class="{ wrong: !configAccepted }"
          aria-live="polite"
        >
          {{ configState }}
        </p>
        <p class="model-note">
          Turn gen plan off while gen idea remains on. The model refuses the relationship;
          the interface only shows what it said. The whole set is validated again when the
          current flow is loaded.
        </p>
      </section>
    </div>

    <section class="runtime">
      <header>
        <span class="step">3</span>
        <div>
          <strong>Enter through the surface that fits the job</strong>
          <p>The highlighted path changes. The resolved flow and accepted setup do not.</p>
        </div>
      </header>

      <div class="surface-tabs" role="group" aria-label="way into humanize">
        <button
          v-for="one in SURFACES"
          :key="one.key"
          type="button"
          :aria-pressed="surface === one.key"
          :class="{ on: surface === one.key }"
          @click="surface = one.key"
        >
          {{ one.label }}
        </button>
      </div>

      <div class="context" :class="{ blocked: !configAccepted }">
        <div>
          <span>resolved flow</span>
          <strong>{{ resolved }}</strong>
        </div>
        <div>
          <span>flow setup</span>
          <strong>
            {{ configAccepted ? configState.replace('accepted · ', '') : 'refused' }}
          </strong>
        </div>
        <div>
          <span>run</span>
          <strong>{{ configAccepted ? 'ready to start' : 'not made' }}</strong>
        </div>
      </div>

      <div class="graph">
        <svg
          viewBox="0 0 820 280"
          role="img"
          :aria-label="graphDescription"
        >
          <title>How each product surface reaches the shared runtime</title>
          <desc>{{ graphDescription }}</desc>
          <defs>
            <marker
              id="surface-arrow"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 0 L 8 4 L 0 8 z" class="arrow" />
            </marker>
            <marker
              id="surface-arrow-active"
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 0 L 8 4 L 0 8 z" class="arrow active" />
            </marker>
          </defs>

          <path
            v-for="edge in EDGES"
            :key="edge.id"
            :d="edge.d"
            class="edge"
            :class="{ on: activeEdges.has(edge.id) }"
            :marker-end="
              activeEdges.has(edge.id)
                ? 'url(#surface-arrow-active)'
                : 'url(#surface-arrow)'
            "
          />

          <g
            v-for="node in NODES"
            :key="node.id"
            class="node"
            :class="{
              on: activeNodes.has(node.id),
              blocked: !configAccepted && node.id === 'run',
            }"
          >
            <rect
              :x="node.x - node.width / 2"
              :y="node.y - 22"
              :width="node.width"
              height="44"
              rx="10"
            />
            <text :x="node.x" :y="node.y + 5">{{ node.label }}</text>
          </g>

          <text x="304" y="272" class="session-count">
            <template v-if="surface === 'daemon'">
              {{ attached }} terminal{{ attached === 1 ? '' : 's' }} reading
            </template>
            <template v-else>used only when the interface is held</template>
          </text>
        </svg>
      </div>

      <div class="surface-note">
        <p aria-live="polite">
          <strong>{{ pickedSurface.label }}</strong>
          {{ pickedSurface.about }}
          <span v-if="surface === 'daemon'">
            {{ attached }} terminal{{ attached === 1 ? '' : 's' }} attached.
          </span>
        </p>
        <div v-if="surface === 'daemon'" class="session-actions">
          <button type="button" :disabled="attached >= 3" @click="attached += 1">
            another terminal arrives
          </button>
          <button type="button" :disabled="attached === 0" @click="attached = 0">
            detach all
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.surfaces {
  overflow: hidden;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
}

.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  color: var(--vp-c-text-3);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: default;
  opacity: 0.48;
}

.reset {
  padding: 4px 11px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  letter-spacing: 0;
  text-transform: none;
}

.upper {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.pane {
  min-width: 0;
  padding: 16px;
}

.pane + .pane {
  border-left: 1px solid var(--hmz-panel-border);
}

header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.step {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  font-weight: 700;
}

header strong {
  display: block;
  color: var(--vp-c-text-1);
  font-size: 13.5px;
}

header p {
  margin: 3px 0 0;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  line-height: 1.5;
}

.query {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 0 8px;
  padding: 7px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
  background: var(--vp-c-bg);
}

.query span {
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
}

.query em {
  color: var(--vp-c-text-3);
  font-size: 10.5px;
  font-style: normal;
}

.lookup {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.lookup li {
  display: grid;
  grid-template-columns: 22px minmax(92px, 0.8fr) minmax(0, 1.2fr);
  gap: 8px;
  align-items: center;
  min-height: 29px;
  padding: 4px 8px;
  border-radius: 8px;
  color: var(--vp-c-text-3);
  font-size: 11px;
}

.lookup li.hit {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.lookup li.later {
  opacity: 0.58;
}

.lookup .number {
  font-family: var(--vp-font-family-mono);
  text-align: center;
}

.lookup strong {
  color: inherit;
  font-size: 11.5px;
}

.fork {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--vp-c-divider);
}

.fork button {
  padding: 5px 12px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 11.5px;
  font-weight: 650;
}

.fork p,
.qualified,
.model-note {
  margin: 0;
  color: var(--vp-c-text-3);
  font-size: 10.8px;
  line-height: 1.5;
}

.qualified {
  margin-top: 10px;
}

.qualified strong {
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 10.8px;
}

.group {
  margin: 14px 0 4px;
  color: var(--vp-c-brand-1);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 48px;
  border-bottom: 1px solid var(--vp-c-divider);
}

.field-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.field-copy strong {
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
}

.field-copy span {
  color: var(--vp-c-text-3);
  font-size: 10.8px;
}

.choices {
  display: flex;
  gap: 5px;
}

.choices button,
.surface-tabs button,
.session-actions button {
  padding: 4px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
}

.choices button.on,
.surface-tabs button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
}

.toggle input {
  accent-color: var(--vp-c-brand-1);
}

.group.plan {
  margin-top: 10px;
}

.validation {
  margin: 11px 0 7px;
  color: var(--hmz-accent);
  font-family: var(--vp-font-family-mono);
  font-size: 10.8px;
}

.validation.wrong {
  color: var(--hmz-warm);
}

.runtime {
  padding: 16px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.surface-tabs {
  display: flex;
  gap: 6px;
  margin: 14px 0 10px;
  flex-wrap: wrap;
}

.context {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-divider);
}

.context div {
  min-width: 0;
  padding: 8px 10px;
  background: var(--vp-c-bg-soft);
}

.context span,
.context strong {
  display: block;
}

.context span {
  margin-bottom: 2px;
  color: var(--vp-c-text-3);
  font-size: 10px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.context strong {
  overflow-wrap: anywhere;
  color: var(--vp-c-text-2);
  font-size: 11.5px;
}

.context.blocked div:last-child strong {
  color: var(--hmz-warm);
}

.graph {
  overflow-x: auto;
  margin-top: 8px;
}

svg {
  display: block;
  width: 100%;
  min-width: 700px;
  height: auto;
}

.edge {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 1.5;
  opacity: 0.72;
  transition: stroke 0.25s, stroke-width 0.25s, opacity 0.25s;
}

.edge.on {
  stroke: var(--vp-c-brand-1);
  stroke-width: 2.5;
  opacity: 1;
}

.arrow {
  fill: var(--vp-c-divider);
}

.arrow.active {
  fill: var(--vp-c-brand-1);
}

.node rect {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-divider);
  transition: fill 0.25s, stroke 0.25s;
}

.node text {
  fill: var(--vp-c-text-3);
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  text-anchor: middle;
  transition: fill 0.25s;
}

.node.on rect {
  fill: var(--vp-c-brand-soft);
  stroke: var(--vp-c-brand-1);
}

.node.on text {
  fill: var(--vp-c-brand-1);
}

.node.blocked rect {
  stroke: var(--hmz-warm);
  stroke-dasharray: 4 4;
}

.node.blocked text {
  fill: var(--hmz-warm);
}

.session-count {
  fill: var(--vp-c-text-3);
  font-size: 10.5px;
  text-anchor: middle;
}

.surface-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-height: 46px;
  padding-top: 10px;
  border-top: 1px solid var(--vp-c-divider);
}

.surface-note p {
  margin: 0;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  line-height: 1.55;
}

.surface-note strong {
  margin-right: 5px;
  color: var(--vp-c-brand-1);
}

.session-actions {
  display: flex;
  flex: none;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.session-actions button:last-child {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

@media (max-width: 800px) {
  .upper {
    grid-template-columns: minmax(0, 1fr);
  }

  .pane + .pane {
    border-top: 1px solid var(--hmz-panel-border);
    border-left: 0;
  }

  .surface-note {
    align-items: flex-start;
    flex-direction: column;
  }

  .session-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 560px) {
  .fork {
    grid-template-columns: minmax(0, 1fr);
  }

  .fork button {
    justify-self: start;
  }

  .context {
    grid-template-columns: minmax(0, 1fr);
  }

  .lookup li {
    grid-template-columns: 22px minmax(86px, 0.8fr) minmax(0, 1.2fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .edge,
  .node rect,
  .node text {
    transition: none;
  }
}
</style>
