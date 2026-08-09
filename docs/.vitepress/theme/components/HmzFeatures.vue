<script setup lang="ts">
// Eight things humanize does, one drawing each. The words are the label on the drawing;
// the feature page behind each card is where the explanation lives.
import { withBase } from 'vitepress'
</script>

<template>
  <div class="grid">
    <a class="card" :href="withBase('/features/backends')">
      <svg class="viz fan" viewBox="0 0 200 88" aria-hidden="true">
        <path d="M 46 44 C 90 44 100 14 152 14" />
        <path d="M 46 44 C 90 44 100 34 152 34" />
        <path d="M 46 44 C 90 44 100 54 152 54" />
        <path d="M 46 44 C 90 44 100 74 152 74" />
        <circle class="hub" cx="38" cy="44" r="9" />
        <g class="ends">
          <circle cx="158" cy="14" r="5.5" />
          <circle cx="158" cy="34" r="5.5" />
          <circle cx="158" cy="54" r="5.5" />
          <circle cx="158" cy="74" r="5.5" />
        </g>
      </svg>
      <h3>One flow, ten CLIs</h3>
      <p>claude · codex · dsh · agy · grok · kimi · qwen · pi · opencode · mimo</p>
    </a>

    <a class="card" :href="withBase('/features/steering')">
      <svg class="viz steer" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="track" x="24" y="26" width="152" height="16" rx="8" />
        <rect class="fill" x="24" y="26" width="14" height="16" rx="8" />
        <rect class="typed" x="24" y="56" width="86" height="14" rx="7" />
        <rect class="caret" x="112" y="56" width="3" height="14" rx="1.5" />
        <path class="into" d="M 100 54 L 100 46" />
      </svg>
      <h3>Typed mid-turn, into the turn</h3>
      <p>Not queued behind it. It reaches the agent that is working.</p>
    </a>

    <a class="card" :href="withBase('/features/tracing')">
      <svg class="viz trace" viewBox="0 0 200 88" aria-hidden="true">
        <g class="slices">
          <rect x="20" y="16" width="42" height="12" rx="3" />
          <rect x="66" y="16" width="28" height="12" rx="3" />
          <rect x="98" y="16" width="56" height="12" rx="3" />
          <rect x="20" y="38" width="30" height="12" rx="3" />
          <rect x="54" y="38" width="64" height="12" rx="3" />
          <rect x="122" y="38" width="36" height="12" rx="3" />
          <rect x="20" y="60" width="58" height="12" rx="3" />
          <rect x="82" y="60" width="24" height="12" rx="3" />
          <rect x="110" y="60" width="70" height="12" rx="3" />
        </g>
        <line class="head" x1="20" y1="10" x2="20" y2="78" />
      </svg>
      <h3>Every run, a timeline</h3>
      <p><code>hmz trace collect</code> — then open it in Perfetto.</p>
    </a>

    <a class="card" :href="withBase('/features/anchor')">
      <svg class="viz away" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="box" x="16" y="26" width="62" height="36" rx="8" />
        <rect class="box there" x="122" y="26" width="62" height="36" rx="8" />
        <path class="link" d="M 78 44 L 122 44" />
        <circle class="pip" cx="80" cy="44" r="4" />
        <text x="47" y="48">agent</text>
        <text x="153" y="48">target</text>
      </svg>
      <h3>Its work lands elsewhere</h3>
      <p>An ssh host or a container of its own. The agent is told nothing.</p>
    </a>

    <a class="card" :href="withBase('/features/shapes')">
      <svg class="viz shape" viewBox="0 0 200 88" aria-hidden="true">
        <g class="prose">
          <rect x="22" y="22" width="104" height="8" rx="4" />
          <rect x="22" y="40" width="132" height="8" rx="4" />
          <rect x="22" y="58" width="74" height="8" rx="4" />
        </g>
        <g class="json">
          <rect class="pane" x="18" y="14" width="164" height="60" rx="8" />
          <rect class="key" x="32" y="26" width="34" height="8" rx="4" />
          <rect class="val" x="72" y="26" width="52" height="8" rx="4" />
          <rect class="key" x="32" y="42" width="26" height="8" rx="4" />
          <rect class="val" x="64" y="42" width="40" height="8" rx="4" />
          <rect class="key" x="32" y="58" width="40" height="8" rx="4" />
          <rect class="val" x="78" y="58" width="30" height="8" rx="4" />
        </g>
      </svg>
      <h3>Answers in a shape</h3>
      <p>A pydantic model in, a field out — no paragraph to parse.</p>
    </a>

    <a class="card" :href="withBase('/features/accounts')">
      <svg class="viz accounts" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="cli" x="70" y="32" width="60" height="24" rx="7" />
        <text x="100" y="48">claude</text>
        <g class="badge one">
          <rect x="16" y="14" width="66" height="20" rx="10" />
          <text x="49" y="28">@work</text>
        </g>
        <g class="badge two">
          <rect x="118" y="54" width="72" height="20" rx="10" />
          <text x="154" y="68">@deepseek</text>
        </g>
      </svg>
      <h3>Two accounts of one CLI</h3>
      <p>Your subscription and somebody else's endpoint, in one run.</p>
    </a>

    <a class="card" :href="withBase('/features/resuming')">
      <svg class="viz resume" viewBox="0 0 200 88" aria-hidden="true">
        <rect class="seg" x="20" y="38" width="62" height="12" rx="6" />
        <rect class="seg gap" x="90" y="38" width="18" height="12" rx="6" />
        <rect class="seg late" x="116" y="38" width="64" height="12" rx="6" />
        <path class="arc" d="M 100 34 C 100 12 150 12 150 32" />
      </svg>
      <h3>Picked up where it stopped</h3>
      <p>A loop stopped on Thursday carries on from its own record.</p>
    </a>

    <a class="card" :href="withBase('/features/human')">
      <svg class="viz human" viewBox="0 0 200 88" aria-hidden="true">
        <g class="row">
          <rect x="20" y="18" width="120" height="10" rx="5" />
          <rect x="20" y="39" width="88" height="10" rx="5" />
          <rect class="you" x="20" y="60" width="104" height="10" rx="5" />
        </g>
        <g class="face">
          <circle cx="164" cy="58" r="8" />
          <path d="M 150 76 C 152 64 176 64 178 76" />
        </g>
      </svg>
      <h3>You, as one of the agents</h3>
      <p>A flow asks a person the same way it asks a model.</p>
    </a>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.card {
  display: block;
  padding: 6px 18px 18px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
  color: inherit;
  text-decoration: none;
  transition: transform 0.25s, border-color 0.25s, box-shadow 0.25s;
}

.card:hover {
  transform: translateY(-3px);
  border-color: var(--vp-c-brand-1);
  box-shadow: 0 10px 30px -18px var(--vp-c-brand-1);
}

.viz {
  display: block;
  width: 100%;
  height: auto;
}

h3 {
  margin: 6px 0 0;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: var(--vp-c-text-1);
}

p {
  margin: 6px 0 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--vp-c-text-3);
}

p code {
  font-size: 11.5px;
  padding: 1px 5px;
  border-radius: 5px;
  background: var(--vp-c-default-soft);
}

svg text {
  fill: var(--vp-c-text-2);
  font-size: 9px;
  font-family: var(--vp-font-family-mono);
  text-anchor: middle;
}

/* one flow, ten CLIs */
.fan path {
  fill: none;
  stroke: var(--vp-c-divider);
  stroke-width: 1.4;
  stroke-dasharray: 3 5;
  animation: crawl 2.4s linear infinite;
}

.fan .hub {
  fill: var(--vp-c-brand-1);
}

.fan .ends circle {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-brand-1);
  stroke-width: 1.6;
  animation: blip 3.2s ease-in-out infinite;
}

.fan .ends circle:nth-child(2) {
  animation-delay: 0.35s;
}

.fan .ends circle:nth-child(3) {
  animation-delay: 0.7s;
}

.fan .ends circle:nth-child(4) {
  animation-delay: 1.05s;
}

@keyframes blip {
  0%,
  60%,
  100% {
    fill: var(--vp-c-bg);
  }
  20%,
  40% {
    fill: var(--hmz-accent);
  }
}

@keyframes crawl {
  to {
    stroke-dashoffset: -16;
  }
}

/* typed mid-turn */
.steer .track {
  fill: var(--vp-c-default-soft);
}

.steer .fill {
  fill: var(--vp-c-brand-1);
  opacity: 0.75;
  animation: grow 4.5s ease-in-out infinite;
}

@keyframes grow {
  0% {
    width: 14px;
  }
  100% {
    width: 152px;
  }
}

.steer .typed {
  fill: var(--vp-c-default-soft);
}

.steer .caret {
  fill: var(--hmz-accent);
  animation: blink 1s steps(2) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.steer .into {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  stroke-linecap: round;
  animation: rise 4.5s ease-in-out infinite;
}

@keyframes rise {
  0%,
  55% {
    opacity: 0;
    transform: translateY(6px);
  }
  70%,
  90% {
    opacity: 1;
    transform: translateY(0);
  }
  100% {
    opacity: 0;
  }
}

/* every run, a timeline */
.trace .slices rect {
  fill: var(--hmz-lane-1);
  opacity: 0.85;
  transform-origin: left center;
  transform-box: fill-box;
  animation: slide 3.6s ease-out infinite;
}

.trace .slices rect:nth-child(n + 4) {
  fill: var(--hmz-lane-2);
}

.trace .slices rect:nth-child(n + 7) {
  fill: var(--hmz-lane-3);
}

.trace .slices rect:nth-child(2),
.trace .slices rect:nth-child(5),
.trace .slices rect:nth-child(8) {
  animation-delay: 0.5s;
}

.trace .slices rect:nth-child(3),
.trace .slices rect:nth-child(6),
.trace .slices rect:nth-child(9) {
  animation-delay: 1s;
}

@keyframes slide {
  0% {
    transform: scaleX(0);
    opacity: 0;
  }
  20%,
  92% {
    transform: scaleX(1);
    opacity: 0.85;
  }
  100% {
    transform: scaleX(1);
    opacity: 0;
  }
}

.trace .head {
  stroke: var(--hmz-accent);
  stroke-width: 2;
  animation: sweep 3.6s linear infinite;
}

@keyframes sweep {
  to {
    transform: translateX(160px);
  }
}

/* its work lands elsewhere */
.away .box {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-divider);
}

.away .box.there {
  stroke: var(--hmz-accent);
}

.away .link {
  stroke: var(--vp-c-divider);
  stroke-width: 1.6;
  stroke-dasharray: 4 4;
  animation: crawl 1.6s linear infinite;
}

.away .pip {
  fill: var(--hmz-accent);
  animation: cross 2.6s ease-in-out infinite;
}

@keyframes cross {
  0%,
  10% {
    cx: 80px;
    opacity: 0;
  }
  20% {
    opacity: 1;
  }
  80% {
    cx: 120px;
    opacity: 1;
  }
  100% {
    cx: 120px;
    opacity: 0;
  }
}

/* answers in a shape */
.shape .prose rect {
  fill: var(--vp-c-default-soft);
  animation: outgoing 5s ease-in-out infinite;
}

.shape .json {
  animation: incoming 5s ease-in-out infinite;
}

.shape .pane {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-brand-1);
}

.shape .key {
  fill: var(--vp-c-brand-1);
}

.shape .val {
  fill: var(--hmz-accent);
  opacity: 0.7;
}

@keyframes outgoing {
  0%,
  38% {
    opacity: 1;
  }
  48%,
  100% {
    opacity: 0;
  }
}

@keyframes incoming {
  0%,
  40% {
    opacity: 0;
  }
  52%,
  92% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

/* two accounts of one CLI */
.accounts .cli {
  fill: var(--vp-c-bg);
  stroke: var(--vp-c-divider);
}

.accounts .badge rect {
  fill: var(--vp-c-default-soft);
  stroke: none;
}

.accounts .badge text {
  fill: var(--vp-c-text-3);
}

.accounts .badge.one {
  animation: takeover 4.4s ease-in-out infinite;
}

.accounts .badge.two {
  animation: takeover 4.4s ease-in-out infinite 2.2s;
}

@keyframes takeover {
  0%,
  45%,
  100% {
    opacity: 0.45;
  }
  10%,
  35% {
    opacity: 1;
  }
}

/* picked up where it stopped */
.resume .seg {
  fill: var(--vp-c-brand-1);
  opacity: 0.8;
}

.resume .seg.gap {
  fill: var(--vp-c-default-soft);
}

.resume .seg.late {
  fill: var(--hmz-accent);
  transform-origin: left center;
  transform-box: fill-box;
  animation: pickup 3.4s ease-in-out infinite;
}

@keyframes pickup {
  0%,
  20% {
    transform: scaleX(0);
  }
  70%,
  100% {
    transform: scaleX(1);
  }
}

.resume .arc {
  fill: none;
  stroke: var(--vp-c-text-3);
  stroke-width: 1.4;
  stroke-dasharray: 3 4;
  animation: crawl 2s linear infinite;
}

/* you, as one of the agents */
.human .row rect {
  fill: var(--vp-c-default-soft);
}

.human .row .you {
  fill: var(--hmz-lane-6);
  opacity: 0.55;
  animation: attend 3.6s ease-in-out infinite;
}

@keyframes attend {
  0%,
  100% {
    opacity: 0.35;
  }
  50% {
    opacity: 0.9;
  }
}

.human .face circle {
  fill: var(--vp-c-brand-1);
}

.human .face path {
  fill: none;
  stroke: var(--vp-c-brand-1);
  stroke-width: 2.4;
  stroke-linecap: round;
}

@media (max-width: 1000px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .viz *,
  .viz {
    animation: none !important;
  }
}
</style>
