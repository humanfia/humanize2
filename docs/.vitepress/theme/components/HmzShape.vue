<script setup lang="ts">
// A turn given a shape answers in it. The model is the whole of what the backend is asked --
// its fields, their types, which are required, the line each was declared with -- and the
// answer is read back through it whichever of the two roads the backend took.
import { computed, ref } from 'vue'

interface Field {
  name: string
  type: string
  about: string
  answer: string
  reads: string
}

interface Shape {
  key: string
  name: string
  about: string
  fields: Field[]
  branch: string
}

const SHAPES: Shape[] = [
  {
    key: 'review',
    name: 'Review',
    about: 'what one round of a loop comes to',
    branch: 'the loop takes another round, with notes as the next prompt',
    fields: [
      {
        name: 'done',
        type: 'bool',
        about: 'True only if there is nothing left to do or to fix.',
        answer: 'false',
        reads: 'a bool, not a paragraph to search',
      },
      {
        name: 'notes',
        type: 'str',
        about: 'What to say to the agent, passed on word for word.',
        answer: '"name the case that fails, then fix it"',
        reads: 'the next prompt, word for word',
      },
    ],
  },
  {
    key: 'plan',
    name: 'Settled',
    about: 'a decision a flow has to make before it acts',
    branch: 'the flow builds it the careful way, with tests, for up to three rounds',
    fields: [
      {
        name: 'approach',
        type: 'Literal["fast", "careful"]',
        about: 'Which way should this be built?',
        answer: '"careful"',
        reads: 'one of two words, and never a third',
      },
      {
        name: 'tests',
        type: 'bool',
        about: 'Write tests for it?',
        answer: 'true',
        reads: 'yes or no',
      },
      {
        name: 'rounds',
        type: 'int = 3',
        about: 'How many rounds may it take?',
        answer: '3',
        reads: 'a number, defaulted where nothing said',
      },
    ],
  },
]

interface Backend {
  name: string
  held: boolean
  how: string
}

const BACKENDS: Backend[] = [
  { name: 'claude', held: true, how: '--json-schema · it validates the answer itself' },
  { name: 'codex', held: true, how: "the turn's own outputSchema" },
  { name: 'agy', held: true, how: '--json-schema on the run' },
  { name: 'grok', held: true, how: '--json-schema on the run' },
  { name: 'qwen', held: true, how: '--json-schema on the run' },
  { name: 'dsh', held: false, how: 'asked in the prompt, and what it says is read back' },
  { name: 'kimi', held: false, how: 'asked in the prompt, and what it says is read back' },
  { name: 'pi', held: false, how: 'asked in the prompt, and what it says is read back' },
  { name: 'opencode', held: false, how: 'asked in the prompt, and what it says is read back' },
  { name: 'mimo', held: false, how: 'asked in the prompt, and what it says is read back' },
  { name: 'zcode', held: false, how: 'asked in the prompt, and what it says is read back' },
]

const shape = ref(0)
const backend = ref(0)
const obeys = ref(true)

const picked = computed(() => SHAPES[shape.value])
const cli = computed(() => BACKENDS[backend.value])
</script>

<template>
  <div class="shape hmz-panel">
    <div class="bar">
      <div class="tabs" role="group" aria-label="which shape">
        <button
          v-for="(one, i) in SHAPES"
          :key="one.key"
          type="button"
          :class="{ on: shape === i }"
          @click="shape = i"
        >
          {{ one.name }}
        </button>
      </div>
      <span class="about">{{ picked.about }}</span>
      <div class="spacer" />
      <label class="sw">
        <input v-model="obeys" type="checkbox" />
        it answers in the shape
      </label>
    </div>

    <div class="flowline">
      <section class="card model">
        <header>the model is the question</header>
        <div class="rows">
          <div v-for="one in picked.fields" :key="one.name" class="field">
            <code>{{ one.name }}</code>
            <span class="type">{{ one.type }}</span>
            <p>{{ one.about }}</p>
          </div>
        </div>
        <footer>nothing about the shape is said twice in the prompt</footer>
      </section>

      <div class="arrow">
        <span />
        <em>{{ cli.held ? 'held to it' : 'asked for it' }}</em>
      </div>

      <section class="card asked">
        <header>how this one is held</header>
        <div class="chips">
          <button
            v-for="(one, i) in BACKENDS"
            :key="one.name"
            type="button"
            :class="{ on: backend === i, held: one.held }"
            @click="backend = i"
          >
            {{ one.name }}
          </button>
        </div>
        <p class="how">
          <strong>{{ cli.name }}</strong> — {{ cli.how }}
        </p>
        <footer>
          {{
            cli.held
              ? 'a setting of the turn, so the backend itself refuses an answer of another shape'
              : 'no setting for it, so the shape goes in the prompt — and either way the answer is read back through the model'
          }}
        </footer>
      </section>

      <div class="arrow">
        <span />
        <em>read back</em>
      </div>

      <section class="card answer" :class="{ bad: !obeys }">
        <header>what the flow gets</header>
        <div v-if="obeys" class="rows">
          <div v-for="one in picked.fields" :key="one.name" class="got">
            <code>{{ one.name }}</code>
            <span class="value">{{ one.answer }}</span>
            <p>{{ one.reads }}</p>
          </div>
        </div>
        <div v-else class="rows">
          <div class="got none">
            <code>None</code>
            <span class="value">under suppress</span>
            <p>
              An answer that is not what was asked for is a turn that did not do what it was
              told, however cleanly the backend exited. Without suppress it raises instead.
            </p>
          </div>
        </div>
        <footer>
          {{
            obeys
              ? picked.branch
              : 'the flow takes this round again — which is almost always the right branch to write'
          }}
        </footer>
      </section>
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

.tabs {
  display: inline-flex;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  overflow: hidden;
}

.tabs button {
  padding: 4px 14px;
  border: 0;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 12px;
  font-weight: 600;
  font-family: var(--vp-font-family-mono);
  cursor: pointer;
}

.tabs button.on {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.spacer {
  flex: 1;
}

.sw {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--vp-c-text-2);
  cursor: pointer;
}

.sw input {
  accent-color: var(--vp-c-brand-1);
}

.flowline {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 76px minmax(0, 1fr) 76px minmax(0, 1fr);
  align-items: stretch;
  padding: 16px;
  gap: 0;
}

.card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.card header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.card footer {
  margin-top: auto;
  padding: 9px 12px;
  border-top: 1px solid var(--vp-c-divider);
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--vp-c-text-3);
}

.rows {
  padding: 10px 12px;
}

.field,
.got {
  padding: 6px 0;
  border-bottom: 1px dashed var(--vp-c-divider);
}

.field:last-child,
.got:last-child {
  border-bottom: 0;
}

.field code,
.got code {
  font-size: 12.5px;
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.field .type {
  margin-left: 8px;
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.got .value {
  margin-left: 8px;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--hmz-accent);
}

.field p,
.got p {
  margin: 3px 0 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

.answer.bad code {
  color: var(--hmz-warm);
}

.answer.bad {
  border-color: var(--hmz-warm);
}

.arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.arrow span {
  width: 68%;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--vp-c-divider), var(--vp-c-brand-1));
}

.arrow em {
  font-style: normal;
  font-size: 10px;
  text-align: center;
  line-height: 1.3;
  color: var(--vp-c-text-3);
  padding: 0 4px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px 0;
}

.chips button {
  padding: 3px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11px;
  font-family: var(--vp-font-family-mono);
  cursor: pointer;
}

.chips button.held {
  border-style: solid;
  color: var(--vp-c-text-2);
}

.chips button.on {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.how {
  margin: 10px 12px 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-2);
}

.how strong {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-1);
}

@media (max-width: 880px) {
  .flowline {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .arrow {
    flex-direction: row;
    gap: 10px;
    height: 22px;
  }

  .arrow span {
    width: 40%;
    background: linear-gradient(90deg, var(--vp-c-divider), var(--vp-c-brand-1));
  }
}
</style>
