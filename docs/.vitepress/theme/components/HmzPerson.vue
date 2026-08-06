<script setup lang="ts">
// The person, driven as an agent. Given a shape, they are not shown a schema: they are asked
// a question per field, the description is the question, and the model is built out of what
// they typed. What the model refuses is put back on the field it was refused for, in the
// model's own words. Nobody there is an answer too.
import { computed, ref } from 'vue'

interface Field {
  name: string
  type: string
  asks: string
  offers?: string[]
  fallback?: string
  reads: (said: string) => string | null
  refuses?: string
}

const FIELDS: Field[] = [
  {
    name: 'approach',
    type: 'Literal["fast", "careful"]',
    asks: 'Which way should this be built?',
    offers: ['fast', 'careful'],
    reads: (said) => (said === 'fast' || said === 'careful' ? said : null),
    refuses: "Input should be 'fast' or 'careful'",
  },
  {
    name: 'tests',
    type: 'bool',
    asks: 'Write tests for it?',
    offers: ['yes', 'no'],
    reads: (said) => (said === 'yes' ? 'True' : said === 'no' ? 'False' : null),
    refuses: 'Input should be a valid boolean',
  },
  {
    name: 'rounds',
    type: 'int = 3',
    asks: 'How many rounds may it take?',
    fallback: '3',
    reads: (said) => {
      if (said === '-' || said === '') return '3'
      const n = Number(said)
      return Number.isInteger(n) && n > 0 ? String(n) : null
    },
    refuses: 'Input should be a valid integer greater than 0',
  },
]

const answers = ref<(string | null)[]>([null, null, null])
const put = ref('')
const refused = ref('')
const again = ref(0)
const away = ref(false)

const at = computed(() => answers.value.findIndex((one) => one === null))
const field = computed(() => (at.value < 0 ? null : FIELDS[at.value]))
const done = computed(() => at.value < 0)

function answer(said: string) {
  const one = FIELDS[at.value]
  const read = one.reads(said)
  if (read === null) {
    // Bounded: a person who keeps typing something the model will not take is a questionnaire
    // that ends with nothing rather than one that goes on for ever.
    again.value += 1
    refused.value = again.value >= 3 ? '' : `${one.refuses} · ${one.asks}`
    if (again.value >= 3) nobody()
    return
  }
  refused.value = ''
  put.value = ''
  answers.value = answers.value.map((held, i) => (i === at.value ? read : held))
}

function nobody() {
  away.value = true
  answers.value = [null, null, null]
  put.value = ''
  refused.value = ''
}

function start() {
  away.value = false
  again.value = 0
  answers.value = [null, null, null]
  put.value = ''
  refused.value = ''
}

const built = computed(() =>
  FIELDS.map((one, i) => `${one.name}=${answers.value[i] ?? '…'}`).join(', '),
)
</script>

<template>
  <div class="person hmz-panel">
    <div class="bar">
      <span class="what">a flow asks for a <code>Settled</code>, and this time it asks you</span>
      <div class="spacer" />
      <button class="ctl" type="button" @click="start">start over</button>
      <button class="ctl away" type="button" @click="nobody">nobody is there</button>
    </div>

    <div class="body">
      <section class="asking">
        <template v-if="away">
          <p class="gone">
            <strong>Answered with nothing.</strong> A flow run from a command line, or an
            interface told its user is away, answers a question the same way: nobody is there.
            The backend is told that rather than left waiting — a turn waiting on an answer that
            is not coming is a flow that has stopped.
          </p>
          <p class="gone dim">
            The flow reads <code>None</code> under suppress and takes that branch. Which is the
            same branch it takes when a model answers with something that is not the shape it was
            asked for.
          </p>
        </template>

        <template v-else-if="field">
          <p class="which">question {{ at + 1 }} of {{ FIELDS.length }}</p>
          <h4>{{ field.asks }}</h4>
          <p class="from">
            the line the field was declared with — not the schema, and not a form
          </p>
          <div v-if="field.offers" class="offers">
            <button v-for="one in field.offers" :key="one" type="button" @click="answer(one)">
              {{ one }}
            </button>
          </div>
          <form v-else class="typed" @submit.prevent="answer(put)">
            <input
              v-model="put"
              type="text"
              :placeholder="`type a number, or - for ${field.fallback}`"
              aria-label="your answer"
            />
            <button type="submit">answer</button>
          </form>
          <p v-if="refused" class="refused">{{ refused }}</p>
        </template>

        <template v-else>
          <p class="landed">
            <strong>Settled({{ built }})</strong>
          </p>
          <p class="from">
            The flow reads a field. It put the same decision to a person that it would have put
            to a model, in the same shape, with the same branch for an answer that never came.
          </p>
        </template>
      </section>

      <aside class="model">
        <header>the model the flow declared</header>
        <div v-for="(one, i) in FIELDS" :key="one.name" class="field" :class="{ got: answers[i] }">
          <div class="head">
            <code>{{ one.name }}</code>
            <span class="type">{{ one.type }}</span>
          </div>
          <p>{{ one.asks }}</p>
          <span class="value">{{ answers[i] ?? (away ? '—' : 'not yet') }}</span>
        </div>
        <footer>
          A <code>Literal</code> becomes the words it offers, a <code>bool</code> becomes yes and
          no, a default becomes “or <code>-</code> for that”. Each question goes the road a coding
          agent's own question goes, so it is a real question wherever the flow is being watched.
        </footer>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
  font-size: 12px;
  color: var(--vp-c-text-3);
}

.bar code {
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-2);
}

.spacer {
  flex: 1;
}

.ctl {
  padding: 4px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-3);
  font-size: 11.5px;
  cursor: pointer;
}

.ctl.away {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

.body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 340px);
  gap: 16px;
  padding: 16px;
}

.asking {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 200px;
  padding: 16px 18px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}

.which {
  margin: 0 0 6px;
  font-size: 10.5px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.asking h4 {
  margin: 0;
  font-size: 17px;
  line-height: 1.35;
  color: var(--vp-c-text-1);
}

.from {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

.offers {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.offers button {
  padding: 6px 16px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.offers button:hover {
  background: var(--vp-c-brand-1);
  color: var(--vp-c-bg);
}

.typed {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.typed input {
  flex: 1;
  padding: 6px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-1);
  font-size: 13px;
  outline: none;
}

.typed button {
  padding: 6px 14px;
  border: 1px solid var(--vp-c-brand-1);
  border-radius: 8px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.refused {
  margin: 10px 0 0;
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--hmz-warm);
}

.landed {
  margin: 0;
  font-size: 15px;
  font-family: var(--vp-font-family-mono);
  color: var(--hmz-accent);
}

.gone {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--vp-c-text-2);
}

.gone.dim {
  color: var(--vp-c-text-3);
  margin: 0;
}

.model {
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  overflow: hidden;
}

.model header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.field {
  padding: 10px 12px;
  border-bottom: 1px dashed var(--vp-c-divider);
  opacity: 0.6;
  transition: opacity 0.25s;
}

.field.got {
  opacity: 1;
}

.field .head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.field code {
  font-size: 12.5px;
  color: var(--vp-c-brand-1);
  font-weight: 650;
}

.field .type {
  font-size: 10.5px;
  font-family: var(--vp-font-family-mono);
  color: var(--vp-c-text-3);
}

.field p {
  margin: 3px 0 4px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

.field .value {
  font-size: 12px;
  font-family: var(--vp-font-family-mono);
  color: var(--hmz-accent);
}

.field:not(.got) .value {
  color: var(--vp-c-text-3);
}

.model footer {
  padding: 10px 12px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--vp-c-text-3);
}

.model footer code {
  font-size: 11px;
}

@media (max-width: 820px) {
  .body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
