---
layout: home

hero:
  name: humanize
  text: Orchestrate, execute, and observe agent flows
  tagline: Drive the coding agent CLIs you already have — one flow, many agents, one timeline you can read afterwards.
  image:
    src: /logo.svg
    alt: humanize
  actions:
    - theme: brand
      text: Quickstart
      link: /tutorials/quickstart
    - theme: alt
      text: Tutorials
      link: /tutorials/
    - theme: alt
      text: View on GitHub
      link: https://github.com/humanfia/humanize2

features:
  - title: One flow, many agents
    details: A flow is a directory of Python that says what each agent is asked, in what order, and when to stop, and carries the skills it works by. Ship it, run it by name, fork one, or run one of the flows humanize already offers.
    link: /tutorials/flow-checked-build
    linkText: Write one
  - title: Ten coding agents, one interface
    details: claude, codex, dsh, agy, grok, kimi, qwen, pi, opencode and mimo, driven through the CLI you already log into — and any other that speaks the Agent Client Protocol. humanize holds no API key and talks to no model provider itself.
    link: /guide/concepts
    linkText: How it fits
  - title: A prompt you can watch
    details: A transcript per conversation, tab to step between the agents that are working, and a line typed mid-turn that goes into the turn rather than after it.
    link: /guide/steering
    linkText: Talk to a running turn
  - title: Two accounts of one CLI
    details: An agent may name the account it runs as, so one flow drives one CLI as a subscription and somebody else's endpoint at the same time.
    link: /guide/providers
    linkText: Providers
  - title: Somewhere other than here
    details: Give an agent a container of its own, or moor it to an ssh host so its commands land there while the process stays on this machine.
    link: /guide/remote-execution
    linkText: Remote execution
  - title: The whole run as a timeline
    details: Every run is written down as it happens. Collect it into a Chrome trace and open it in Perfetto — one process per agent, one track per row of its sessions, one slice per thing it did.
    link: /guide/tracing
    linkText: Tracing
---

## Install it

```sh
pip install git+https://github.com/humanfia/humanize2.git
```

## Run something

```sh
hmz
```

![Opening the humanize interface, typing / to see the commands, and picking a flow](/demo/tui.gif)

<small>Recorded against a stand-in coding agent, in a container of its own — see
[Working on these docs](/contributing/docs#the-terminal-demos).</small>

Or without the interface, over the agents you name, one `-a` apiece:

```sh
hmz exec -f official/flame_chase \
    -a claude/claude-opus-4-8:high -a codex/gpt-5.6-sol:high "fix the build"
```

Then read the whole thing back:

```sh
hmz trace collect
```

## Where to start

- **Never used it.** [Quickstart](/tutorials/quickstart) goes from nothing installed to a run
  you can open in Perfetto, in fifteen minutes.
- **Want to see it do real work.** The [tutorials](/tutorials/) take three real problems from
  start to finish — a benchmark, a port, and building a coding agent from an idea.
- **Want one feature.** The [guides](/guide/) have a page each, and each opens with something
  you can paste.
- **Looking something up.** [CLI](/reference/cli) and [TUI](/reference/tui) are complete.

Before you point one at a repository you care about, read [Security](/guide/security). humanize
runs every agent with permission prompts disabled, and there is no setting that turns them back
on.
