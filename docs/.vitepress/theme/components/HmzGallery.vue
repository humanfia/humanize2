<script setup lang="ts">
// The real screens, recorded from the real program. A card holds a still until it is asked
// for, so the page arrives without nine animations in flight; hover plays one, and a click
// opens it at full size.
import { onMounted, onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

interface Shot {
  src: string
  poster?: string
  title: string
  caption: string
  href: string
}

const SHOTS: Shot[] = [
  {
    src: '/demo/tui.gif',
    title: 'hmz',
    caption: 'The interface: / for the commands, and a flow picked from the sheet.',
    href: '/reference/tui',
  },
  {
    src: '/demo/collect.gif',
    poster: '/demo/collect.png',
    title: 'hmz trace collect',
    caption: 'A run gathered into one Chrome trace — sessions, slices, programs.',
    href: '/guide/tracing',
  },
  {
    src: '/demo/epics.gif',
    poster: '/demo/epics.png',
    title: '/epics',
    caption: 'Every run this directory has had, and the ones that can be picked up.',
    href: '/guide/resuming',
  },
  {
    src: '/demo/flowverses.gif',
    poster: '/demo/flowverses.png',
    title: '/flowverses',
    caption: 'Where flows come from, and what one of them holds.',
    href: '/guide/flowverses',
  },
  {
    src: '/demo/checks.gif',
    title: 'hmz exec',
    caption: 'A flow run with nobody watching, and the status it exits with.',
    href: '/guide/unattended',
  },
  {
    src: '/demo/providers.gif',
    poster: '/demo/providers-show.png',
    title: '/providers',
    caption: 'An account made, and the turn under it answered by somebody else’s endpoint.',
    href: '/guide/providers',
  },
  {
    src: '/demo/profiling.gif',
    poster: '/demo/profiling.png',
    title: 'a profiled run',
    caption: 'The programs an agent started, sampled off the process tree into the trace.',
    href: '/guide/tracing',
  },
  {
    src: '/demo/alike.gif',
    poster: '/demo/alike.png',
    title: 'one key, several CLIs',
    caption: 'An account copied to the backends that take the same credentials.',
    href: '/reference/providers',
  },
  {
    src: '/demo/cli.gif',
    title: 'hmz --help',
    caption: 'Every command there is, and what each one is for.',
    href: '/reference/cli',
  },
]

const playing = ref<string[]>([])
const open = ref<number | null>(null)

function play(shot: Shot) {
  if (!playing.value.includes(shot.src)) playing.value = [...playing.value, shot.src]
}

const shown = (shot: Shot) =>
  !shot.poster || playing.value.includes(shot.src) ? shot.src : shot.poster

function show(i: number) {
  play(SHOTS[i])
  open.value = i
}

function close() {
  open.value = null
}

function onKey(event: KeyboardEvent) {
  if (open.value === null) return
  if (event.key === 'Escape') close()
  if (event.key === 'ArrowRight') show((open.value + 1) % SHOTS.length)
  if (event.key === 'ArrowLeft') show((open.value + SHOTS.length - 1) % SHOTS.length)
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="gallery">
    <button
      v-for="(shot, i) in SHOTS"
      :key="shot.src"
      class="shot"
      type="button"
      @mouseenter="play(shot)"
      @focusin="play(shot)"
      @click="show(i)"
    >
      <span class="frame">
        <img :src="withBase(shown(shot))" :alt="shot.caption" loading="lazy" />
        <span class="zoom">open</span>
      </span>
      <span class="meta">
        <code>{{ shot.title }}</code>
        <em>{{ shot.caption }}</em>
      </span>
    </button>
  </div>

  <Teleport to="body">
    <div v-if="open !== null" class="lightbox" @click.self="close">
      <figure>
        <img :src="withBase(SHOTS[open].src)" :alt="SHOTS[open].caption" />
        <figcaption>
          <code>{{ SHOTS[open].title }}</code>
          <span>{{ SHOTS[open].caption }}</span>
          <a :href="withBase(SHOTS[open].href)">read the guide →</a>
        </figcaption>
      </figure>
      <button class="close" type="button" aria-label="close" @click="close">✕</button>
    </div>
  </Teleport>
</template>

<style scoped>
.gallery {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.shot {
  display: block;
  padding: 0;
  border: 0;
  background: none;
  text-align: left;
  cursor: zoom-in;
}

.frame {
  display: block;
  position: relative;
  aspect-ratio: 25 / 14;
  overflow: hidden;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 12px;
  background: var(--vp-c-bg-alt);
  transition: transform 0.28s, border-color 0.28s, box-shadow 0.28s;
}

.shot:hover .frame,
.shot:focus-visible .frame {
  transform: translateY(-4px);
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 18px 40px -24px rgba(0, 0, 0, 0.6);
}

.frame img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top left;
}

.zoom {
  position: absolute;
  right: 10px;
  bottom: 10px;
  padding: 3px 9px;
  border-radius: 20px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  font-size: 11px;
  font-weight: 600;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.25s, transform 0.25s;
}

.shot:hover .zoom,
.shot:focus-visible .zoom {
  opacity: 0.94;
  transform: translateY(0);
}

.meta {
  display: block;
  padding: 10px 2px 0;
}

.meta code {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--vp-c-brand-1);
}

.meta em {
  display: block;
  margin-top: 3px;
  font-style: normal;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--vp-c-text-3);
}

.lightbox {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 5vh 4vw;
  background: rgba(8, 10, 14, 0.82);
  backdrop-filter: blur(6px);
  animation: fade 0.2s ease-out;
}

@keyframes fade {
  from {
    opacity: 0;
  }
}

.lightbox figure {
  margin: 0;
  max-width: 1100px;
  width: 100%;
}

.lightbox img {
  display: block;
  width: 100%;
  border-radius: 12px;
  box-shadow: 0 30px 80px -30px #000;
}

figcaption {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 12px;
  padding: 14px 4px 0;
  color: rgba(255, 255, 255, 0.72);
  font-size: 13px;
}

figcaption code {
  color: #fff;
  font-weight: 700;
}

figcaption a {
  margin-left: auto;
  color: #8cb8de;
  font-weight: 600;
}

.close {
  position: fixed;
  top: 18px;
  right: 22px;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 15px;
  cursor: pointer;
}

.close:hover {
  background: rgba(255, 255, 255, 0.24);
}

@media (max-width: 900px) {
  .gallery {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .gallery {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
