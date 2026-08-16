<script setup lang="ts">
// The features, laid out as the thing they belong to: a line you type, a flow that drives
// agents, an agent driving a CLI, work landing somewhere, and a record of all of it. Hover
// one to read what it is; click it for the page.
import { computed, ref } from 'vue'
import { withBase } from 'vitepress'

interface Feature {
  said: string
  link: string
  about: string
  deep?: boolean
}

interface Stage {
  name: string
  sub: string
  features: Feature[]
}

const STAGES: Stage[] = [
  {
    name: 'you',
    sub: 'at the prompt, or not there at all',
    features: [
      {
        said: 'a line typed mid-turn',
        link: '/features/steering',
        deep: true,
        about: 'It goes into the turn that is running rather than starting another one after it.',
      },
      {
        said: 'you, as one of the agents',
        link: '/features/human',
        about: 'A flow puts a decision to a person the same way it puts one to a model, in the same shape.',
      },
    ],
  },
  {
    name: 'the flow',
    sub: 'a directory of Python',
    features: [
      {
        said: 'a flow is Python',
        link: '/features/flows',
        about: 'A loop, a subprocess call, a file read between turns — and the agents are its arguments.',
      },
      {
        said: 'many turns at once',
        link: '/features/concurrency',
        about: 'Turns are only sequential inside one session, so two hundred conversations are two hundred turns.',
      },
      {
        said: 'picked up where it stopped',
        link: '/features/resuming',
        about: 'A week-long loop is a loop that will be stopped. What it was keeping track of survives.',
      },
    ],
  },
  {
    name: 'the agent',
    sub: 'a CLI, a model, an effort, an account',
    features: [
      {
        said: 'answers in a shape',
        link: '/features/shapes',
        deep: true,
        about: 'A turn given a model answers with that model, so a flow reads a field rather than a paragraph.',
      },
      {
        said: 'it decides when it is done',
        link: '/features/goals',
        about: "The backend's own goal feature: a turn that would have ended starts another.",
      },
      {
        said: 'the moments of a turn',
        link: '/features/hooks',
        about: 'Python callables hung on the points a turn passes through, and taken down while it runs.',
      },
    ],
  },
  {
    name: 'the CLI',
    sub: 'the one you already have',
    features: [
      {
        said: 'eleven CLIs, one agent',
        link: '/features/backends',
        about: 'Driven through whatever each of them offers, and asked what it runs rather than told.',
      },
      {
        said: 'two accounts of one CLI',
        link: '/features/accounts',
        deep: true,
        about: 'A CLI signs in once. humanize runs it as an account it was never signed into, without asking it.',
      },
    ],
  },
  {
    name: 'where it lands',
    sub: 'here, or somewhere else entirely',
    features: [
      {
        said: 'the anchor',
        link: '/features/anchor',
        deep: true,
        about: 'The agent runs here and every syscall it makes is decided one at a time: replayed there, or answered here.',
      },
    ],
  },
  {
    name: 'what it leaves',
    sub: 'a run you can read back',
    features: [
      {
        said: 'one timeline',
        link: '/features/tracing',
        deep: true,
        about: 'Every agent, every sub-agent and every program they ran, on one clock, in one document.',
      },
    ],
  },
]

const held = ref<Feature | null>(null)
const caption = computed(
  () =>
    held.value?.about ??
    'Six stages, twelve pages. The ones marked are worth reading even if you never run it.',
)
</script>

<template>
  <div class="map hmz-panel">
    <div class="stages">
      <section v-for="stage in STAGES" :key="stage.name" class="stage">
        <header>
          <strong>{{ stage.name }}</strong>
          <span>{{ stage.sub }}</span>
        </header>
        <a
          v-for="one in stage.features"
          :key="one.link"
          class="chip"
          :class="{ deep: one.deep, held: held?.link === one.link }"
          :href="withBase(one.link)"
          @mouseenter="held = one"
          @mouseleave="held = null"
          @focus="held = one"
          @blur="held = null"
        >
          <span>{{ one.said }}</span>
          <i v-if="one.deep">the deep end</i>
        </a>
      </section>
    </div>
    <p class="caption">{{ caption }}</p>
  </div>
</template>

<style scoped>
.stages {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  padding: 16px 16px 0;
  position: relative;
}

.stages::before {
  content: '';
  position: absolute;
  left: 16px;
  right: 16px;
  top: 74px;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(
    90deg,
    var(--vp-c-brand-1),
    var(--hmz-accent),
    var(--hmz-accent-2),
    var(--vp-c-brand-1)
  );
  background-size: 220% 100%;
  opacity: 0.35;
  animation: drift 9s linear infinite;
}

@keyframes drift {
  to {
    background-position: 220% 0;
  }
}

.stage {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stage header {
  display: flex;
  flex-direction: column;
  min-height: 52px;
  margin-bottom: 12px;
}

.stage header strong {
  font-size: 12.5px;
  color: var(--vp-c-text-1);
}

.stage header span {
  font-size: 10.5px;
  line-height: 1.35;
  color: var(--vp-c-text-3);
}

.chip {
  display: block;
  padding: 10px 12px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 11px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  font-size: 12px;
  line-height: 1.35;
  text-decoration: none;
  transition: transform 0.2s, border-color 0.2s, background 0.2s, color 0.2s;
}

.chip:hover,
.chip.held {
  transform: translateY(-2px);
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-text-1);
  background: var(--vp-c-brand-soft);
}

.chip.deep {
  border-color: var(--hmz-accent);
}

.chip i {
  display: block;
  margin-top: 5px;
  font-style: normal;
  font-size: 9.5px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--hmz-accent);
}

.caption {
  margin: 0;
  padding: 16px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
  min-height: 58px;
}

@media (max-width: 980px) {
  .stages {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .stages::before {
    display: none;
  }
}

@media (max-width: 620px) {
  .stages {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .stages::before {
    animation: none;
  }
}
</style>
