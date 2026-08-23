<script setup lang="ts">
// A terminal is a reader, not the owner. Advance the run with either, leave and return to
// see a current-screen redraw, or stall one reader until only its bounded backlog is dropped.
// Stopping is a separate axis: the run may unwind, or its holder may be ended where it stands.
import { computed, reactive, ref } from 'vue'

type RunState = 'running' | 'stopping' | 'stopped' | 'killed'
type ReaderState = 'live' | 'away' | 'slow' | 'released' | 'replay'

interface Reader {
  id: 'desk' | 'watcher'
  name: string
  place: string
  attached: boolean
  slow: boolean
  released: boolean
  seen: number
  backlog: number
  replayedAt: number | null
}

const BURST = 384
const LIMIT = 1024

const runState = ref<RunState>('running')
const frame = ref(3)
const journal = ref(5)
const stateRevision = ref(3)
const lastEvent = ref('two terminals are reading one PTY')

const readers = reactive<Reader[]>([
  {
    id: 'desk',
    name: 'your terminal',
    place: 'the shell that opened it',
    attached: true,
    slow: false,
    released: false,
    seen: 3,
    backlog: 0,
    replayedAt: null,
  },
  {
    id: 'watcher',
    name: 'another terminal',
    place: 'a second view of the same run',
    attached: true,
    slow: false,
    released: false,
    seen: 3,
    backlog: 0,
    replayedAt: null,
  },
])

const attached = computed(() => readers.filter((reader) => reader.attached).length)
const holderAlive = computed(
  () => runState.value === 'running' || runState.value === 'stopping',
)

const runLabel = computed(() => {
  if (runState.value === 'stopping') return 'the flow is unwinding'
  if (runState.value === 'stopped') return 'the flow returned'
  if (runState.value === 'killed') return 'the holder ended here'
  return `turn ${frame.value} is running`
})

const screenLines = computed(() => [
  `round ${frame.value}`,
  frame.value % 2 ? 'actor is checking the patch' : 'actor is running the tests',
  !holderAlive.value
    ? 'the PTY closed with its holder'
    : attached.value
    ? `${attached.value} terminal${attached.value === 1 ? '' : 's'} attached`
    : 'nobody is looking',
])

function readerState(reader: Reader): ReaderState {
  if (reader.released) return 'released'
  if (!reader.attached) return 'away'
  if (reader.slow) return 'slow'
  if (reader.replayedAt !== null) return 'replay'
  return 'live'
}

function readerLabel(reader: Reader) {
  if (!holderAlive.value) return 'run ended; terminal restored'
  const state = readerState(reader)
  if (state === 'released') return 'slow reader released'
  if (state === 'away') return 'terminal left; run stayed'
  if (state === 'slow') return `${reader.backlog} KiB waiting`
  if (state === 'replay') return `screen redrawn at round ${reader.replayedAt}`
  return 'live output'
}

function advance() {
  if (runState.value !== 'running') return
  frame.value += 1
  journal.value += 1
  stateRevision.value += 1
  let releasedThisBurst = false

  for (const reader of readers) {
    if (!reader.attached) continue
    reader.replayedAt = null
    if (!reader.slow) {
      reader.seen = frame.value
      reader.backlog = 0
      continue
    }
    reader.backlog += BURST
    if (reader.backlog > LIMIT) {
      reader.attached = false
      reader.slow = false
      reader.released = true
      reader.backlog = 0
      releasedThisBurst = true
      lastEvent.value = `${reader.name} crossed its 1 MiB bound; only that socket closed`
    }
  }

  if (!releasedThisBurst) {
    lastEvent.value = attached.value
      ? `round ${frame.value} reached every reader that was ready`
      : `round ${frame.value} was written with no terminal attached`
  }
}

function leave(reader: Reader) {
  reader.attached = false
  reader.slow = false
  reader.released = false
  reader.backlog = 0
  reader.replayedAt = null
  lastEvent.value = `${reader.name} left; the daemon and PTY did not`
}

function reconnect(reader: Reader) {
  if (runState.value === 'stopped' || runState.value === 'killed') return
  reader.attached = true
  reader.slow = false
  reader.released = false
  reader.backlog = 0
  reader.seen = frame.value
  reader.replayedAt = frame.value
  lastEvent.value = `${reader.name} received a full-screen redraw, then joined live output`
}

function toggleSlow(reader: Reader) {
  if (!reader.attached || runState.value !== 'running') return
  reader.slow = !reader.slow
  if (!reader.slow) {
    reader.backlog = 0
    reader.seen = frame.value
    lastEvent.value = `${reader.name} caught up without changing the run`
  } else {
    reader.replayedAt = null
    lastEvent.value = `${reader.name} stopped reading; its own bounded queue is growing`
  }
}

function askToStop() {
  if (runState.value !== 'running') return
  runState.value = 'stopping'
  lastEvent.value = 'the holder asked the interface to stop; the flow is unwinding'
}

function finishStop() {
  if (runState.value !== 'stopping') return
  runState.value = 'stopped'
  journal.value += 1
  for (const reader of readers) leave(reader)
  lastEvent.value = 'the flow returned; the journal gained its complete ending'
}

function kill() {
  if (runState.value === 'stopped' || runState.value === 'killed') return
  runState.value = 'killed'
  for (const reader of readers) leave(reader)
  lastEvent.value = 'the holder ended where it stood; the last complete writes remain'
}

function reset() {
  runState.value = 'running'
  frame.value = 3
  journal.value = 5
  stateRevision.value = 3
  lastEvent.value = 'two terminals are reading one PTY'
  readers.forEach((reader) => {
    reader.attached = true
    reader.slow = false
    reader.released = false
    reader.seen = 3
    reader.backlog = 0
    reader.replayedAt = null
  })
}
</script>

<template>
  <div class="daemon hmz-panel">
    <div class="bar">
      <span class="workspace"><i /> one workspace · one holder</span>
      <span class="count">{{ attached }} attached</span>
      <div class="spacer" />
      <button type="button" :disabled="runState !== 'running'" @click="advance">
        draw next burst
      </button>
      <button
        class="stop"
        type="button"
        :disabled="runState !== 'running'"
        @click="askToStop"
      >
        ask to stop
      </button>
      <button
        v-if="runState === 'stopping'"
        class="finish"
        type="button"
        @click="finishStop"
      >
        flow returns
      </button>
      <button
        class="kill"
        type="button"
        :disabled="runState === 'stopped' || runState === 'killed'"
        @click="kill"
      >
        end holder directly
      </button>
      <button class="reset" type="button" @click="reset">start over</button>
    </div>

    <div class="body">
      <section class="readers" aria-label="terminals reading the run">
        <article
          v-for="reader in readers"
          :key="reader.id"
          class="reader"
          :class="readerState(reader)"
        >
          <header>
            <div>
              <strong>{{ reader.name }}</strong>
              <span>{{ reader.place }}</span>
            </div>
            <em>{{ reader.attached ? 'socket open' : 'socket closed' }}</em>
          </header>

          <div class="terminal" :class="{ blank: !reader.attached }">
            <template v-if="reader.attached">
              <span>round {{ reader.seen }}</span>
              <span>{{ reader.seen % 2 ? 'checking the patch' : 'running the tests' }}</span>
              <span v-if="reader.slow">output waiting behind this screen…</span>
              <span v-else>❯ live from the shared PTY</span>
            </template>
            <template v-else>
              <span>this terminal is back at its shell</span>
              <span v-if="holderAlive">the PTY is still held elsewhere</span>
              <span v-else>the PTY and its holder are gone</span>
            </template>
          </div>

          <p class="reader-state">{{ readerLabel(reader) }}</p>
          <div class="reader-actions">
            <button v-if="reader.attached" type="button" @click="leave(reader)">leave</button>
            <button
              v-else
              type="button"
              :disabled="runState === 'stopped' || runState === 'killed'"
              @click="reconnect(reader)"
            >
              reconnect
            </button>
            <button
              v-if="reader.id === 'watcher' && reader.attached"
              class="slow-toggle"
              type="button"
              :disabled="runState !== 'running'"
              @click="toggleSlow(reader)"
            >
              {{ reader.slow ? 'let it catch up' : 'stall this reader' }}
            </button>
          </div>
        </article>
      </section>

      <section class="holder" :class="runState" aria-label="the workspace daemon">
        <header>
          <div>
            <span class="eyebrow">workspace daemon</span>
            <strong>{{ holderAlive ? 'detached process' : 'detached process ended' }}</strong>
          </div>
          <span class="lock">kernel lock {{ holderAlive ? 'held' : 'released' }}</span>
        </header>

        <div class="layers">
          <div class="socket">
            <span>framed local socket</span>
            <small>input · output · resize · control</small>
          </div>
          <div class="pty">
            <div class="pty-head">
              <strong>{{ holderAlive ? 'one PTY' : 'PTY closed' }}</strong>
              <span>{{ attached }} reader{{ attached === 1 ? '' : 's' }}</span>
            </div>
            <div class="screen">
              <span v-for="line in screenLines" :key="line">{{ line }}</span>
            </div>
          </div>
          <div class="run">
            <span class="pulse" />
            <div>
              <strong>the interface and flow</strong>
              <small>{{ runLabel }}</small>
            </div>
          </div>
        </div>
      </section>

      <aside
        class="disk"
        :aria-label="holderAlive ? 'records written while the run continues' : 'records left by the run'"
      >
        <header>{{ holderAlive ? 'on disk while it runs' : 'what the run left on disk' }}</header>
        <div class="file identity">
          <strong>daemon.json</strong>
          <span v-if="holderAlive">holder identity · whole-file note</span>
          <span v-else>removed with the closed socket</span>
        </div>
        <div class="file journal">
          <strong>epic.jsonl</strong>
          <span>{{ journal }} complete lines · append as events happen</span>
        </div>
        <div class="file state">
          <strong>state.json</strong>
          <span>revision {{ stateRevision }} · replace when the flow writes</span>
        </div>
        <div class="file errors">
          <strong>daemon.log</strong>
          <span>append failures that no terminal could show</span>
        </div>
        <p>
          The terminal screen is not kept here. The journal records the run's shape, state is
          what a resumable flow chose to keep, and the backend owns the conversation.
        </p>
      </aside>
    </div>

    <div class="explain">
      <p aria-live="polite"><strong>Now:</strong> {{ lastEvent }}.</p>
      <p class="bound">
        Each press stands in for a large output burst so the source's per-reader 1 MiB bound
        is visible. A stalled reader never delays the frame counter or the ready reader.
      </p>
    </div>
  </div>
</template>

<style scoped>
.daemon {
  overflow: hidden;
}

.bar {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.workspace {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 650;
  color: var(--vp-c-text-2);
}

.workspace i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--hmz-accent);
}

.count {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--vp-c-default-soft);
  font-size: 10.5px;
  color: var(--vp-c-text-3);
}

.spacer {
  flex: 1;
}

.bar button,
.reader-actions button {
  padding: 5px 10px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  background: transparent;
  color: var(--vp-c-text-2);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.bar button:first-of-type {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.bar .stop,
.bar .finish {
  border-color: var(--hmz-accent);
  color: var(--hmz-accent);
}

.bar .kill {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

.bar .reset {
  color: var(--vp-c-text-3);
  font-weight: 500;
}

button:disabled {
  opacity: 0.38;
  cursor: default;
}

.body {
  display: grid;
  grid-template-columns: minmax(190px, 0.85fr) minmax(260px, 1.2fr) minmax(205px, 0.9fr);
  gap: 12px;
  padding: 14px;
}

.readers {
  display: grid;
  align-content: start;
  gap: 10px;
}

.reader,
.holder,
.disk {
  min-width: 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
}

.reader {
  overflow: hidden;
  transition: border-color 0.2s, opacity 0.2s;
}

.reader.live,
.reader.replay {
  border-color: color-mix(in srgb, var(--hmz-accent) 65%, var(--vp-c-divider));
}

.reader.slow {
  border-color: var(--hmz-warm);
}

.reader.away,
.reader.released {
  opacity: 0.72;
  border-style: dashed;
}

.reader > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
}

.reader header div {
  min-width: 0;
}

.reader header strong,
.reader header span {
  display: block;
}

.reader header strong {
  font-size: 11.5px;
  color: var(--vp-c-text-1);
}

.reader header span {
  margin-top: 1px;
  font-size: 9.5px;
  line-height: 1.35;
  color: var(--vp-c-text-3);
}

.reader header em {
  flex: none;
  font-size: 9px;
  font-style: normal;
  color: var(--hmz-accent);
}

.reader.away header em,
.reader.released header em {
  color: var(--vp-c-text-3);
}

.terminal {
  min-height: 76px;
  margin: 0 8px;
  padding: 8px 9px;
  border-radius: 7px;
  background: #17202c;
  color: #b9d3e8;
  font-family: var(--vp-font-family-mono);
  font-size: 9.5px;
  line-height: 1.55;
}

.terminal span {
  display: block;
}

.terminal span:first-child {
  color: #75dacd;
}

.terminal.blank {
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-3);
}

.terminal.blank span:first-child {
  color: var(--vp-c-text-2);
}

.reader-state {
  min-height: 30px;
  margin: 0;
  padding: 7px 9px 0;
  font-size: 9.5px;
  line-height: 1.35;
  color: var(--vp-c-text-3);
}

.reader.slow .reader-state,
.reader.released .reader-state {
  color: var(--hmz-warm);
}

.reader.replay .reader-state {
  color: var(--hmz-accent);
}

.reader-actions {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  padding: 7px 8px 9px;
}

.reader-actions button {
  padding: 3px 8px;
  font-size: 9.5px;
}

.reader-actions .slow-toggle {
  border-color: var(--hmz-warm);
  color: var(--hmz-warm);
}

.holder {
  align-self: start;
  overflow: hidden;
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 0 0 3px var(--vp-c-brand-soft);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.holder.stopping {
  border-color: var(--hmz-accent);
}

.holder.stopped,
.holder.killed {
  border-color: var(--vp-c-divider);
  box-shadow: none;
}

.holder.killed {
  border-style: dashed;
}

.holder > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
}

.holder header strong,
.holder header span {
  display: block;
}

.eyebrow {
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.holder header strong {
  font-size: 13px;
  color: var(--vp-c-text-1);
}

.holder .lock {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  font-size: 9px;
  color: var(--vp-c-brand-1);
}

.layers {
  display: grid;
  gap: 8px;
  padding: 10px;
}

.socket,
.pty,
.run {
  border: 1px solid var(--vp-c-divider);
  border-radius: 9px;
}

.socket {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  color: var(--vp-c-text-2);
  font-size: 10.5px;
}

.socket small {
  color: var(--vp-c-text-3);
  font-size: 8.5px;
  text-align: right;
}

.pty {
  padding: 8px;
  background: var(--vp-c-bg-soft);
}

.pty-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.pty-head strong {
  color: var(--vp-c-brand-1);
  font-size: 11px;
}

.pty-head span {
  color: var(--vp-c-text-3);
  font-size: 9px;
}

.screen {
  min-height: 112px;
  padding: 10px 11px;
  border-radius: 7px;
  background: #17202c;
  color: #c5daea;
  font-family: var(--vp-font-family-mono);
  font-size: 10.5px;
  line-height: 1.7;
}

.screen span {
  display: block;
}

.screen span:first-child {
  color: #75dacd;
}

.screen span:last-child {
  color: #e8a66f;
}

.run {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px;
}

.pulse {
  width: 9px;
  height: 9px;
  flex: none;
  border-radius: 50%;
  background: var(--hmz-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--hmz-accent) 16%, transparent);
}

.stopping .pulse {
  background: var(--hmz-warm);
}

.stopped .pulse,
.killed .pulse {
  background: var(--vp-c-text-3);
  box-shadow: none;
}

.run strong,
.run small {
  display: block;
}

.run strong {
  font-size: 10.5px;
  color: var(--vp-c-text-1);
}

.run small {
  margin-top: 1px;
  font-size: 9.5px;
  color: var(--vp-c-text-3);
}

.disk {
  align-self: start;
  overflow: hidden;
}

.disk > header {
  padding: 9px 10px;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--vp-c-text-3);
}

.file {
  margin: 8px 9px 0;
  padding: 7px 8px;
  border-left: 2px solid var(--vp-c-brand-1);
  background: var(--vp-c-bg-soft);
}

.file.journal {
  border-left-color: var(--hmz-accent);
}

.file.state {
  border-left-color: var(--hmz-accent-2);
}

.file.errors {
  border-left-color: var(--hmz-warm);
}

.file strong,
.file span {
  display: block;
}

.file strong {
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  color: var(--vp-c-text-1);
}

.file span {
  margin-top: 2px;
  font-size: 9px;
  line-height: 1.35;
  color: var(--vp-c-text-3);
}

.disk p {
  margin: 0;
  padding: 10px;
  font-size: 9.5px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

.explain {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 10px 14px 12px;
  border-top: 1px solid var(--hmz-panel-border);
  background: var(--vp-c-bg);
}

.explain p {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
}

.explain strong {
  color: var(--vp-c-text-1);
}

.explain .bound {
  margin-left: auto;
  max-width: 390px;
  color: var(--vp-c-text-3);
  font-size: 9.5px;
}

@media (max-width: 860px) {
  .body {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .readers {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .body,
  .readers {
    grid-template-columns: minmax(0, 1fr);
  }

  .readers {
    grid-column: auto;
  }

  .explain {
    display: block;
  }

  .explain .bound {
    margin: 6px 0 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .reader,
  .holder {
    transition: none;
  }
}
</style>
