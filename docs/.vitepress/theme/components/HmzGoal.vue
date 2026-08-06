<script setup lang="ts">
// Two ways a turn does not end. On the left the backend's own goal feature: the model judges
// the objective and starts the next turn itself. On the right the same thing written by hand:
// a refused STOP, decided by code that can read whatever it likes, bounded by how many times
// it has already refused. Tick the boxes and watch the right-hand loop stop.
import { onUnmounted, ref } from 'vue'

interface Turn {
  n: number
  said: string
  end: boolean
}

const HAVE = [
  { name: 'claude', has: true },
  { name: 'codex', has: true },
  { name: 'dsh', has: true },
  { name: 'kimi', has: true },
  { name: 'pi', has: false },
  { name: 'opencode', has: false },
  { name: 'mimo', has: false },
]

const PURSUED = [
  'runs the suite · three failures',
  'fixes the retry path · one failure',
  'fixes the fixture · the suite passes',
  'reads the diff · nothing was stubbed out',
  'the model says the objective is met',
]

const goal = ref<Turn[]>([])
const goalRunning = ref(false)
let goalTimer = 0

function pursue() {
  goal.value = []
  goalRunning.value = true
  let n = 0
  window.clearInterval(goalTimer)
  goalTimer = window.setInterval(() => {
    if (n >= PURSUED.length) {
      window.clearInterval(goalTimer)
      goalRunning.value = false
      return
    }
    goal.value = [...goal.value, { n: n + 1, said: PURSUED[n], end: n === PURSUED.length - 1 }]
    n += 1
  }, 800)
}

const boxes = ref([false, false, false])
const hook = ref<Turn[]>([])
const hookRunning = ref(false)
const again = ref(0)
let hookTimer = 0

function take() {
  hook.value = []
  again.value = 0
  hookRunning.value = true
  window.clearInterval(hookTimer)
  hookTimer = window.setInterval(() => {
    const left = boxes.value.filter((one) => !one).length
    const n = hook.value.length + 1
    if (!left) {
      hook.value = [...hook.value, { n, said: 'nothing left unticked · the turn ends', end: true }]
      stop()
      return
    }
    if (again.value >= 5) {
      hook.value = [
        ...hook.value,
        { n, said: 'refused five times · the hook stops refusing', end: true },
      ]
      stop()
      return
    }
    again.value += 1
    hook.value = [
      ...hook.value,
      { n, said: `STOP refused · ${left} box${left === 1 ? '' : 'es'} still unticked`, end: false },
    ]
  }, 900)
}

function stop() {
  window.clearInterval(hookTimer)
  hookRunning.value = false
}

onUnmounted(() => {
  window.clearInterval(goalTimer)
  window.clearInterval(hookTimer)
})
</script>

<template>
  <div class="goal hmz-panel">
    <div class="cols">
      <section class="col">
        <header>
          <strong>the model decides</strong>
          <span>the backend's own goal feature</span>
        </header>
        <p class="lede">
          A goal is not a prompt asking for one. It is the feature the CLI's own goal command
          reaches: a turn that would have ended starts another, and the backend starts it. humanize
          follows the goal across all of them and answers with the last.
        </p>
        <button type="button" class="go" :disabled="goalRunning" @click="pursue">
          {{ goalRunning ? 'pursuing…' : 'give it an objective' }}
        </button>
        <p class="objective">“the suite passes and nothing has been stubbed out”</p>
        <ol class="turns">
          <li v-for="one in goal" :key="one.n" :class="{ end: one.end }">
            <span class="n">turn {{ one.n }}</span>
            {{ one.said }}
          </li>
        </ol>
        <footer>
          <span
            v-for="one in HAVE"
            :key="one.name"
            class="has"
            :class="{ no: !one.has }"
            >{{ one.name }}</span
          >
          <em
            >A flow built on a goal says so where it declares its agents, and one whose backend
            has none is refused before the first turn — not an hour into a loop.</em
          >
        </footer>
      </section>

      <section class="col hand">
        <header>
          <strong>your code decides</strong>
          <span>a refused STOP</span>
        </header>
        <p class="lede">
          The same shape, written by hand and hung on the moment a turn tries to end. Refusing it
          sends the agent on, with what the hook said as its next prompt — so the condition can be
          anything Python can read.
        </p>
        <div class="task">
          <span class="file">TASK.md</span>
          <label v-for="(one, i) in boxes" :key="i">
            <input v-model="boxes[i]" type="checkbox" />
            {{ ['port the parser', 'port the printer', 'port the CLI'][i] }}
          </label>
        </div>
        <button type="button" class="go alt" :disabled="hookRunning" @click="take">
          {{ hookRunning ? 'running…' : 'take a turn' }}
        </button>
        <ol class="turns">
          <li v-for="one in hook" :key="one.n" :class="{ end: one.end }">
            <span class="n">again = {{ one.n - 1 }}</span>
            {{ one.said }}
          </li>
        </ol>
        <footer class="plain">
          <em>
            The hook is told how many times it has already sent this turn on, so one that keeps
            refusing can decide to stop. A goal costs turns you did not ask for; a refused STOP
            costs one extra turn per refusal.
          </em>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.col {
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.col + .col {
  border-left: 1px solid var(--hmz-panel-border);
}

header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

header strong {
  font-size: 14px;
  color: var(--vp-c-brand-1);
}

.hand header strong {
  color: var(--hmz-accent);
}

header span {
  font-size: 11.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.lede {
  margin: 8px 0 12px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.go {
  align-self: flex-start;
  padding: 5px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.go.alt {
  border-color: var(--hmz-accent);
  color: var(--hmz-accent);
  background: transparent;
}

.go:disabled {
  opacity: 0.5;
  cursor: default;
}

.objective {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--vp-c-text-3);
  font-style: italic;
}

.task {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-2);
}

.task .file {
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
  margin-bottom: 2px;
}

.task label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.task input {
  accent-color: var(--hmz-accent);
}

.turns {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  min-height: 150px;
  font-size: 12px;
  line-height: 1.75;
  color: var(--vp-c-text-2);
}

.turns li {
  display: flex;
  gap: 10px;
  animation: land 0.3s ease;
}

.turns .n {
  flex: none;
  width: 78px;
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  color: var(--vp-c-text-3);
}

.turns li.end {
  color: var(--hmz-accent);
  font-weight: 600;
}

@keyframes land {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}

footer {
  margin-top: auto;
  padding-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.has {
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid var(--hmz-accent);
  color: var(--hmz-accent);
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
}

.has.no {
  border-color: var(--vp-c-divider);
  color: var(--vp-c-text-3);
  text-decoration: line-through;
}

footer em {
  flex: 1 0 100%;
  font-style: normal;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

@media (max-width: 780px) {
  .cols {
    grid-template-columns: minmax(0, 1fr);
  }

  .col + .col {
    border-left: 0;
    border-top: 1px solid var(--hmz-panel-border);
  }
}

@media (prefers-reduced-motion: reduce) {
  .turns li {
    animation: none;
  }
}
</style>
