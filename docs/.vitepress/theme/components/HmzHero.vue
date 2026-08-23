<script setup lang="ts">
// The first screenful of the site: what humanize is, the line that installs it, and the three
// people who arrive here. Each button lands on that reader's quickstart further down this same
// page, so nobody has to guess which tab in the nav is theirs.
//
// It is full-bleed. `VPHomeContent` holds the page in a 1280px column and sets `--vp-offset` to
// the distance from that column's edge to the viewport's, which is the supported way for one
// child to reach past it -- the default theme's own sponsor and team blocks do the same.
import { onUnmounted, ref } from 'vue'

const LINE = 'pip install git+https://github.com/humanfia/humanize2.git'

// Same-page fragments, so no `withBase`: these resolve against whatever the page is served as,
// which under `base: '/humanize2/'` is the only spelling that stays right.
const ROLES = [
  { href: '#run-a-flow', name: 'Run a flow', under: 'point agents at your repository' },
  { href: '#weave-a-flow', name: 'Weave a flow', under: 'write the Python a flow is' },
  { href: '#work-on-humanize', name: 'Work on humanize', under: 'hack on humanize itself' },
]

const copied = ref(false)
let clearing: ReturnType<typeof setTimeout> | undefined

async function copy() {
  try {
    await navigator.clipboard.writeText(LINE)
  } catch {
    return
  }
  copied.value = true
  clearTimeout(clearing)
  clearing = setTimeout(() => (copied.value = false), 1600)
}

onUnmounted(() => clearTimeout(clearing))
</script>

<template>
  <section class="hero">
    <div class="inner">
      <h1 class="wordmark">humanize</h1>

      <p class="define">
        humanize runs <strong>flows</strong> — directories of Python that drive one or more
        coding agents in a loop and write down everything they did. Most backends drive a
        coding agent you already have, under its existing login.
      </p>

      <button class="line" type="button" :aria-label="`Copy: ${LINE}`" @click="copy">
        <span class="prompt">$</span>
        <code>{{ LINE }}</code>
        <span class="copy" :class="{ done: copied }">{{ copied ? 'copied' : 'copy' }}</span>
      </button>

      <nav class="roles" aria-label="Quickstarts">
        <a v-for="role in ROLES" :key="role.href" :href="role.href">
          <strong>{{ role.name }}</strong>
          <em>{{ role.under }}</em>
        </a>
      </nav>

      <p class="under">Python ≥ 3.12 · reuses the CLI logins you already have</p>

      <a class="cue" href="#how-it-fits-together" aria-label="How it fits together">
        <span class="chev" aria-hidden="true"></span>
      </a>
    </div>
  </section>
</template>

<style scoped>
.hero {
  /* Out to both viewport edges, and back in again for the content. */
  margin-left: var(--vp-offset, calc(50% - 50vw));
  margin-right: var(--vp-offset, calc(50% - 50vw));
  /* The nav bar is fixed over the top of the page, so a screenful is what is left under it. */
  min-height: calc(100svh - var(--vp-nav-height));
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px 72px;
}

.inner {
  position: relative;
  width: 100%;
  max-width: 760px;
  text-align: center;
}

.wordmark {
  margin: 0;
  border: 0;
  padding: 0;
  font-size: clamp(52px, 11vw, 96px);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.035em;
  background: var(--hmz-wordmark);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.define {
  margin: 22px auto 0;
  max-width: 40rem;
  font-size: clamp(15px, 1.7vw, 18px);
  line-height: 1.65;
  color: var(--vp-c-text-2);
}

.define strong {
  color: var(--vp-c-text-1);
  font-weight: 650;
}

.line {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  max-width: 100%;
  margin-top: 30px;
  padding: 12px 14px 12px 18px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-mono);
  font-size: 14px;
  cursor: pointer;
  transition:
    border-color 0.25s,
    box-shadow 0.25s,
    transform 0.25s;
}

.line:hover {
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 0 0 4px var(--vp-c-brand-soft);
  transform: translateY(-1px);
}

.prompt {
  color: var(--hmz-accent);
  font-weight: 700;
}

.line code {
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: inherit;
  font-size: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.copy {
  flex: none;
  padding: 4px 9px;
  border-radius: 7px;
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-2);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.copy.done {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

/* Three doors, one per reader. Equal width, because none of them is the main one. */
.roles {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 34px;
  text-align: left;
}

.roles a {
  display: block;
  padding: 15px 17px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  text-decoration: none;
  transition:
    border-color 0.25s,
    background 0.25s,
    transform 0.25s;
}

.roles a:hover {
  border-color: var(--vp-c-brand-1);
  background: var(--vp-c-bg);
  transform: translateY(-2px);
}

.roles strong {
  display: block;
  color: var(--vp-c-brand-1);
  font-size: 15px;
  font-weight: 650;
}

.roles strong::after {
  content: ' →';
  font-weight: 400;
}

.roles em {
  display: block;
  margin-top: 4px;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
  font-style: normal;
  line-height: 1.5;
}

.under {
  margin: 26px 0 0;
  color: var(--vp-c-text-3);
  font-size: 12.5px;
}

/* The scroll cue: a chevron that says there is a page under this, and takes you to it. */
.cue {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  margin-top: 26px;
  border-radius: 999px;
  color: var(--vp-c-text-3);
  animation: hmz-cue 2.4s ease-in-out infinite;
}

.cue:hover {
  color: var(--vp-c-brand-1);
}

.chev {
  width: 11px;
  height: 11px;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: translateY(-2px) rotate(45deg);
}

@keyframes hmz-cue {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(5px);
  }
}

@media (max-width: 720px) {
  .hero {
    /* A phone screen is not tall enough to centre this and still show the cue. */
    min-height: 0;
    padding: 28px 20px 48px;
  }

  .line {
    padding-left: 12px;
    font-size: 11.5px;
  }

  .roles {
    grid-template-columns: minmax(0, 1fr);
  }

  .cue {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .line,
  .roles a,
  .cue {
    animation: none;
    transition: none;
  }

  .line:hover,
  .roles a:hover {
    transform: none;
  }
}
</style>
