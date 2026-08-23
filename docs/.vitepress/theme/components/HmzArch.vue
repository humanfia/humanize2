<script setup lang="ts">
// Four bands, and what passes downward between them. The rough shape of the system, for the
// page at the site's root -- `HmzMap` on the features landing is the detailed one, and this
// deliberately is not that.
//
// Everything drawn here is checked against the code: the flow names are `theme/flows.ts` and
// `hmz/flows/builtin/`, and the backend row is the `PROFILES` tuple in `hmz/backends.py` --
// eleven command lines, plus DeepSeek Harness, which is a Python SDK that ships inside
// humanize rather than a CLI you install, and so is drawn apart from them.
//
// What each band is responsible for is written out rather than hidden behind a hover: hovering
// only lifts the band it is over. Nothing here is said only by a moving thing.
import { withBase } from 'vitepress'

interface Band {
  name: string
  owns: string
  tone: string
  chips: string[]
  /** The odd one out, drawn dashed: in this diagram, the backend that is not a CLI. */
  apart?: string
  /** What this band hands the one below it. */
  down?: string
}

const BANDS: Band[] = [
  {
    name: 'Flows',
    owns: 'what the work is: which agents are driven, what each is asked, and when to stop',
    tone: 'var(--hmz-lane-3)',
    chips: [
      'chat',
      'ralph_loop',
      'stateful_ralph',
      'official/rlar',
      'official/flame_chase',
      'and yours',
    ],
    down: 'a flow, and one agent for every agent it drives',
  },
  {
    name: 'humanize',
    owns: 'the runner: it takes the turns, keeps the sessions, and writes the whole run down',
    tone: 'var(--hmz-lane-1)',
    chips: [
      'the runner',
      'sessions and turns',
      'agents',
      'providers and accounts',
      'machines',
      'the epic',
      'the trace',
    ],
    down: 'a turn: a prompt, an effort, and the session to put it on',
  },
  {
    name: 'Agent CLIs',
    owns: 'the model, reached through a coding agent you already have and are already logged into',
    tone: 'var(--hmz-lane-2)',
    chips: [
      'claude',
      'codex',
      'cursor',
      'kimi',
      'pi',
      'grok',
      'qwen',
      'agy',
      'opencode',
      'mimo',
      'zcode',
    ],
    apart: 'DeepSeek Harness',
    down: 'edits, commands, and every syscall the agent makes',
  },
  {
    name: 'Environment',
    owns: 'where the work actually lands, and what it is allowed to touch there',
    tone: 'var(--hmz-lane-4)',
    chips: [
      'this machine',
      'a container of its own',
      'a remote target through hmz anchor',
      'worktrees',
    ],
  },
]
</script>

<template>
  <div class="arch">
    <div class="stack">
      <template v-for="band in BANDS" :key="band.name">
        <section class="band" :style="{ '--tone': band.tone }">
          <header>
            <h3>{{ band.name }}</h3>
            <p>{{ band.owns }}</p>
          </header>
          <ul class="chips">
            <li v-for="chip in band.chips" :key="chip">{{ chip }}</li>
            <li v-if="band.apart" class="apart">
              {{ band.apart }}
              <span>a Python SDK that ships inside humanize — not a CLI you install</span>
            </li>
          </ul>
        </section>

        <p v-if="band.down" class="down">
          <span class="arrow" aria-hidden="true"></span>
          {{ band.down }}
        </p>
      </template>
    </div>

    <p class="hmz-note">
      The rough shape. Every capability, grouped and linked to its explanation, is on
      <a :href="withBase('/features/')">Features</a>; every backend against what a flow may ask
      of it is <a :href="withBase('/features/backends')">Many backends, one agent</a>, which
      also covers anything that speaks the Agent Client Protocol.
    </p>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.band {
  padding: 18px 20px 16px;
  border: 1px solid var(--hmz-panel-border);
  border-left: 3px solid var(--tone);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  transition:
    border-color 0.25s,
    background 0.25s;
}

.band:hover {
  border-color: var(--tone);
  background: var(--vp-c-bg);
}

header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 14px;
}

h3 {
  margin: 0;
  border: 0;
  padding: 0;
  color: var(--tone);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

header p {
  flex: 1 1 22rem;
  margin: 0;
  color: var(--vp-c-text-3);
  font-size: 13px;
  line-height: 1.55;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 13px 0 0;
  padding: 0;
  list-style: none;
}

.chips li {
  margin: 0;
  padding: 5px 10px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 8px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.4;
}

/* The backend that is not a command line, drawn as the exception it is. */
.chips .apart {
  display: inline-flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 3px 8px;
  border-style: dashed;
  border-color: var(--tone);
  color: var(--vp-c-text-1);
}

.chips .apart span {
  color: var(--vp-c-text-3);
  font-family: var(--vp-font-family-base);
  font-size: 11.5px;
}

/* What passes from one band to the next, on the arrow that carries it. */
.down {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0;
  padding: 9px 0 9px 22px;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
  line-height: 1.4;
}

.arrow {
  flex: none;
  width: 1px;
  height: 26px;
  background: linear-gradient(var(--hmz-panel-border), var(--vp-c-text-3));
  position: relative;
}

.arrow::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: -3px;
  width: 7px;
  height: 7px;
  border-right: 1px solid var(--vp-c-text-3);
  border-bottom: 1px solid var(--vp-c-text-3);
  transform: rotate(45deg);
}

@media (max-width: 640px) {
  .band {
    padding: 15px 15px 13px;
  }

  header p {
    flex-basis: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .band {
    transition: none;
  }
}
</style>
