---
layout: home

hero:
  name: humanize
  text: Orchestrate, execute, and observe agent flows
  tagline: One flow, ten coding agents, and a timeline of everything they did.
  image:
    src: /logo.svg
    alt: humanize
  actions:
    - theme: brand
      text: Quickstart
      link: /tutorials/quickstart
    - theme: alt
      text: See it running
      link: '#gallery'
    - theme: alt
      text: GitHub
      link: https://github.com/humanfia/humanize2
---

<HmzInstall />

<section class="hmz-section">
  <header>
    <p class="hmz-eyebrow">a run, as it happens</p>
    <h2>One flow, <em>many agents</em>, one trace</h2>
    <p>Every turn's tool calls land on the timeline as they are made. Hover a lane; change how many agents are on it.</p>
  </header>
  <HmzOrchestra />
</section>

<section class="hmz-section">
  <header>
    <p class="hmz-eyebrow">features</p>
    <h2>What it does, <em>one picture each</em></h2>
  </header>
  <HmzFeatures />
  <p class="hmz-note">
    All of it, described in one page: <a href="/features/">Features</a>.
  </p>
</section>

<section class="hmz-section">
  <header>
    <p class="hmz-eyebrow">the deep end</p>
    <h2>The agent runs here. Its <em>syscalls</em> land there.</h2>
    <p>A seccomp-filtered ptrace supervisor decides every call one at a time. No plugin, no configuration, no cooperation — the agent is told none of it.</p>
  </header>
  <HmzAnchor />
  <p class="hmz-note">
    Full detail in <a href="/guide/remote-execution">Remote execution</a>, and what you are
    deliberately not entitled to in <a href="/reference/remote-execution">its reference</a>.
  </p>
</section>

<section class="hmz-section">
  <header>
    <p class="hmz-eyebrow">architecture</p>
    <h2>Twelve layers, <em>one direction</em></h2>
    <p>Everything points downward and nothing points both ways — a rule a test enforces rather than a diagram that hopes.</p>
  </header>
  <HmzStack />
  <p class="hmz-note">
    The whole tree, the rules and the exemptions:
    <a href="/contributing/architecture">Architecture</a>.
  </p>
</section>

<section id="gallery" class="hmz-section">
  <header>
    <p class="hmz-eyebrow">gallery</p>
    <h2>The real thing, <em>recorded</em></h2>
    <p>Hover to play, click to open.</p>
  </header>
  <HmzGallery />
  <p class="hmz-note">
    Recorded against a stand-in coding agent, in a container of its own — see
    <a href="/contributing/docs#the-terminal-demos">Working on these docs</a>.
  </p>
</section>

<section class="hmz-section">
  <div class="hmz-paths">
    <a href="/tutorials/quickstart">
      <strong>Never used it</strong>
      <span>Nothing installed to a run you can open in Perfetto, in fifteen minutes.</span>
    </a>
    <a href="/guide/">
      <strong>One feature</strong>
      <span>A page each, opening with something you can paste.</span>
    </a>
    <a href="/reference/cli">
      <strong>Looking it up</strong>
      <span>Every command, key, flag and Python call.</span>
    </a>
  </div>
  <p class="hmz-warn">
    humanize runs every agent with permission prompts disabled, and nothing turns them back on.
    Read <a href="/guide/security">Security</a> before pointing one at a repository you care
    about.
  </p>
</section>
