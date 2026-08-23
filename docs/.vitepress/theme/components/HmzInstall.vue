<script setup lang="ts">
// The one line that installs it, a button that copies it, and the ways on from there.
//
// It sits under the title of the features page. The site's root carries the same line in its
// hero, so this is not the only place to find it -- what this adds is that a reader who came
// to features to work out what humanize is can install it without going back, and be sent to
// whichever of the three quickstarts is theirs. Those live on the root page, so each way is
// that page and a fragment of it rather than a page of its own.
import { onUnmounted, ref } from 'vue'
import { withBase } from 'vitepress'

const LINE = 'pip install git+https://github.com/humanfia/humanize2.git'

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
  <div class="hmz-install">
    <button class="line" type="button" :aria-label="`Copy: ${LINE}`" @click="copy">
      <span class="prompt">$</span>
      <code>{{ LINE }}</code>
      <span class="copy" :class="{ done: copied }">{{ copied ? 'copied' : 'copy' }}</span>
    </button>

    <div class="ways">
      <a class="go" :href="withBase('/') + '#run-a-flow'">
        Run a flow
        <em>from nothing installed to a run you can open in Perfetto</em>
      </a>
      <a class="also" :href="withBase('/') + '#weave-a-flow'">Weave one</a>
      <a class="also" :href="withBase('/user/installation')">Installation guide</a>
      <a class="also" :href="withBase('/flows/')">What it can run</a>
    </div>

    <p class="under">
      Python ≥ 3.12 · reuses existing CLI logins · bundled DSH uses provider credentials
    </p>
  </div>
</template>

<style scoped>
.hmz-install {
  margin: 22px 0 8px;
  padding: 20px 22px 18px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 16px;
  background:
    radial-gradient(120% 140% at 8% 0%, var(--vp-c-brand-soft), transparent 62%),
    var(--hmz-panel-bg);
}

.line {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  max-width: 100%;
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

.ways {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 18px;
  margin-top: 16px;
}

.go {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
  padding: 9px 18px;
  border-radius: 10px;
  background: var(--vp-c-brand-1);
  color: var(--vp-c-bg);
  font-size: 14px;
  font-weight: 650;
  text-decoration: none;
  transition: background 0.2s, transform 0.2s;
}

.go:hover {
  background: var(--vp-c-brand-2);
  transform: translateY(-1px);
}

.go::after {
  content: '→';
  font-weight: 400;
}

.go em {
  font-style: normal;
  font-size: 12px;
  font-weight: 400;
  opacity: 0.82;
}

.also {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
  text-decoration: none;
}

.also:hover {
  text-decoration: underline;
}

.under {
  margin: 14px 0 0;
  font-size: 12.5px;
  color: var(--vp-c-text-3);
}

@media (max-width: 720px) {
  .line {
    font-size: 12px;
    padding-left: 12px;
  }

  .go em {
    display: none;
  }
}
</style>
