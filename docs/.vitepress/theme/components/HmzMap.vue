<script setup lang="ts">
// The feature tree, compressed into its five systems and nineteen capability groups. Each
// group names the guarantee it owns and leads to the page that explains it best.
import { computed, ref } from 'vue'
import { withBase } from 'vitepress'

interface CapabilityGroup {
  code: string
  name: string
  link: string
  guarantee: string
  start?: boolean
}

interface SystemDomain {
  code: string
  name: string
  sub: string
  groups: CapabilityGroup[]
}

const SYSTEMS: SystemDomain[] = [
  {
    code: 'A',
    name: 'Flow system',
    sub: 'express · prove · compose · resume',
    groups: [
      {
        code: 'A1',
        name: 'Expression & compilation',
        link: '/features/prophecy',
        start: true,
        guarantee:
          'Free-form Python shares one runtime with an atlas, whose restricted body compiles into a graph.',
      },
      {
        code: 'A2',
        name: 'Static correctness & proving',
        link: '/features/prophecy',
        guarantee:
          'Structural mistakes are rejected before a model call costs time, money, or a live run.',
      },
      {
        code: 'A3',
        name: 'Composition & hot reload',
        link: '/features/flows',
        guarantee:
          'Flows and skills can nest; regular flows can reload current source between calls.',
      },
      {
        code: 'A4',
        name: 'Scheduling, state & resumption',
        link: '/features/resuming',
        guarantee:
          'Placement and fan-out pair with explicit state or atlas node-level resumption.',
      },
    ],
  },
  {
    code: 'B',
    name: 'Agent control plane',
    sub: 'sessions · tools · recovery · identity',
    groups: [
      {
        code: 'B1',
        name: 'Backend unification',
        link: '/features/backends',
        guarantee:
          'Different CLIs and app servers expose one session protocol without flattening their capabilities.',
      },
      {
        code: 'B2',
        name: 'Turn & session control',
        link: '/features/steering',
        start: true,
        guarantee:
          'Typed, capability-aware controls steer, clone, and pursue goals where a backend supports them.',
      },
      {
        code: 'B3',
        name: 'Tools & skills',
        link: '/weaver/tools',
        guarantee:
          'Skills are selected per session, while flow callbacks can become temporary native tools.',
      },
      {
        code: 'B4',
        name: 'Failure recovery',
        link: '/features/accounts',
        guarantee:
          'A failed session can recover in place, migrate accounts, or use another CLI without losing intent.',
      },
      {
        code: 'B5',
        name: 'Accounts & credentials',
        link: '/features/accounts',
        guarantee:
          'Credential inputs can be isolated, redirected, and reused without leaking provider state.',
      },
    ],
  },
  {
    code: 'C',
    name: 'Execution fabric',
    sub: 'local control · remote work',
    groups: [
      {
        code: 'C1',
        name: 'Transparent remote execution',
        link: '/features/anchor',
        start: true,
        guarantee:
          'A local agent operates a remote machine within documented process and signal boundaries.',
      },
      {
        code: 'C2',
        name: 'Shadow workspace & consistent writes',
        link: '/features/anchor',
        guarantee:
          'Remote workspaces appear immediately and writes land atomically as files arrive on demand.',
      },
      {
        code: 'C3',
        name: 'Portable transport runtime',
        link: '/features/anchor',
        guarantee:
          'Targets need no install: one protocol carries processes, files, environment, and working directory.',
      },
      {
        code: 'C4',
        name: 'Machine lifecycle',
        link: '/features/anchor',
        guarantee:
          'Machines can be isolated per agent or shared for a run, with explicit lifecycle ownership.',
      },
    ],
  },
  {
    code: 'D',
    name: 'Run continuity & observability',
    sub: 'detach · recover · reconstruct · scrub',
    groups: [
      {
        code: 'D1',
        name: 'Detached operation',
        link: '/features/daemon',
        start: true,
        guarantee:
          'Runs outlive terminals: a workspace daemon preserves PTYs, replay, attach, and stop control.',
      },
      {
        code: 'D2',
        name: 'Persistent state & layered logs',
        link: '/features/resuming',
        guarantee:
          'State and nested journals are written through, so a crash leaves a readable recovery record.',
      },
      {
        code: 'D3',
        name: 'Trace reconstruction',
        link: '/features/tracing',
        guarantee:
          'Sessions, sub-agents, and processes rebuild onto one calibrated, session-bounded timeline.',
      },
      {
        code: 'D4',
        name: 'Telemetry privacy',
        link: '/features/tracing',
        guarantee:
          'Reporting has explicit consent state and is scrubbed before anything leaves the machine.',
      },
    ],
  },
  {
    code: 'E',
    name: 'Product surfaces',
    sub: 'discover · configure · invoke',
    groups: [
      {
        code: 'E1',
        name: 'Discovery, forking & config',
        link: '/features/surfaces',
        guarantee:
          'Flows can be discovered locally, forked atomically, and configured from their schemas.',
      },
      {
        code: 'E2',
        name: 'Unified entry points',
        link: '/features/surfaces',
        start: true,
        guarantee:
          'SDK, CLI, terminal interface, and daemon reach the same underlying flow and run model.',
      },
    ],
  },
]

const hovered = ref<CapabilityGroup | null>(null)
const focused = ref<CapabilityGroup | null>(null)
const active = computed(() => focused.value ?? hovered.value)
const groupCount = SYSTEMS.reduce((count, system) => count + system.groups.length, 0)
const caption = computed(
  () =>
    active.value?.guarantee ??
    `${SYSTEMS.length} systems, ${groupCount} capability groups. Hover or focus a group for its core guarantee; open it for the closest explanation.`,
)
</script>

<template>
  <div class="map hmz-panel">
    <div class="systems">
      <section
        v-for="system in SYSTEMS"
        :key="system.code"
        class="system"
        :aria-labelledby="`domain-${system.code}`"
      >
        <header>
          <span class="domain-code">{{ system.code }}</span>
          <strong :id="`domain-${system.code}`">{{ system.name }}</strong>
          <span>{{ system.sub }}</span>
        </header>
        <a
          v-for="group in system.groups"
          :key="group.code"
          class="chip"
          :class="{ start: group.start, held: active?.code === group.code }"
          :href="withBase(group.link)"
          :aria-label="`${group.code}. ${group.name}`"
          :aria-describedby="`guarantee-${group.code}`"
          @mouseenter="hovered = group"
          @mouseleave="hovered = null"
          @focus="focused = group"
          @blur="focused = null"
        >
          <small>{{ group.code }}</small>
          <span>{{ group.name }}</span>
          <i v-if="group.start">start here</i>
          <span :id="`guarantee-${group.code}`" class="guarantee">
            {{ group.guarantee }}
          </span>
        </a>
      </section>
    </div>
    <p class="caption">{{ caption }}</p>
  </div>
</template>

<style scoped>
.systems {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  padding: 16px 16px 0;
  position: relative;
}

.systems::before {
  content: '';
  position: absolute;
  left: 16px;
  right: 16px;
  top: 92px;
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

.system {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.system header {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto 1fr;
  column-gap: 7px;
  min-height: 70px;
  margin-bottom: 12px;
}

.system header .domain-code {
  grid-row: 1 / 3;
  align-self: start;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 7px;
  color: var(--vp-c-brand-1);
  font-size: 10px;
  line-height: 1;
  font-weight: 700;
}

.system header strong {
  min-width: 0;
  font-size: 12.5px;
  line-height: 1.3;
  color: var(--vp-c-text-1);
}

.system header > span:last-child {
  font-size: 10.5px;
  line-height: 1.35;
  color: var(--vp-c-text-3);
}

.chip {
  display: block;
  min-width: 0;
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

.chip small {
  display: block;
  margin-bottom: 3px;
  color: var(--vp-c-text-3);
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.chip:hover,
.chip.held {
  transform: translateY(-2px);
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-text-1);
  background: var(--vp-c-brand-soft);
}

.chip:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.chip.start {
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
  min-height: 74px;
}

.guarantee {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 980px) {
  .systems {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .systems::before {
    display: none;
  }
}

@media (max-width: 660px) {
  .systems {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chip .guarantee {
    position: static;
    display: block;
    width: auto;
    height: auto;
    padding: 0;
    margin: 6px 0 0;
    overflow: visible;
    clip: auto;
    white-space: normal;
    border: 0;
    color: var(--vp-c-text-3);
    font-size: 10.5px;
    line-height: 1.45;
  }
}

@media (max-width: 420px) {
  .systems {
    grid-template-columns: minmax(0, 1fr);
  }

  .system header {
    min-height: 0;
    margin-bottom: 4px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .systems::before {
    animation: none;
  }

  .chip {
    transition: none;
  }

  .chip:hover,
  .chip.held {
    transform: none;
  }
}
</style>
