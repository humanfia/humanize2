import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'

import { defineConfig, type SiteConfig } from 'vitepress'

// Deployed to https://docs.humanfia.ai/humanize2/ by .github/workflows/build-docs.yml.
// The custom domain belongs to the organisation's own pages, so this repository is a project
// page served under a subdirectory of it, and `base` is that subdirectory: without it every
// stylesheet, script and link would ask for a path at the domain root, where nothing of this
// site is. Internal links are still written from the site's own root -- VitePress prepends
// the base to each of them -- so nothing in a page names the subdirectory.
const BASE = '/humanize2/'

/** Where somebody arriving at the site's root is sent. */
const FRONT = `${BASE}features/`

export default defineConfig({
  base: BASE,
  title: 'humanize',
  description: 'Orchestrate, execute, and observe agent flows',
  lang: 'en-US',
  cleanUrls: true,
  lastUpdated: true,

  // `docs/tapes/` is the machinery the demos are rendered by, not a page of the site: its
  // README is written for somebody standing in that directory with docker. Left in, VitePress
  // publishes it at /tapes/README -- a page no sidebar holds, that the search still offers.
  // What a reader needs of it is in Contributing.
  srcExclude: ['tapes/**'],

  head: [
    // Written out with the base in it: VitePress prepends the base to a theme's own
    // links and to what a page names, and hands `head` to the template as it is.
    ['link', { rel: 'icon', href: '/humanize2/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#3c8772' }],
  ],

  themeConfig: {
    logo: '/logo.svg',

    // Five sections, and features come first: what there is, drawn rather than described, is
    // what somebody who has never run this wants before anything else -- so it is also what
    // the site's root goes to, there being no front page above it. Then flows, which is what
    // there is to run; tutorials, which teach a whole piece of work end to end; guides, which
    // answer "how do I use this one feature"; and reference, which spells all of it out.
    nav: [
      { text: 'Features', link: '/features/', activeMatch: '/features/' },
      { text: 'Flows', link: '/flows/', activeMatch: '/flows/' },
      { text: 'Tutorials', link: '/tutorials/', activeMatch: '/tutorials/' },
      { text: 'Guides', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Reference', link: '/reference/cli', activeMatch: '/reference/' },
      {
        text: 'Contributing',
        link: '/contributing/',
        activeMatch: '/contributing/',
      },
    ],

    // Every sidebar opens with its own section as a link rather than with an entry inside a
    // group of the same name: a group called Features holding an item called "All of them" is
    // a title nobody would write on the page itself, and the page is what it goes to. So the
    // section is the first line, and the groups under it are what they were.
    sidebar: {
      // One page per feature, each built around a diagram you can push. The first group is
      // the one to send somebody who wants to know what is unusual about this.
      '/features/': [
        { text: 'Features', link: '/features/' },
        {
          text: 'The deep end',
          collapsed: false,
          items: [
            { text: 'The anchor', link: '/features/anchor' },
            { text: 'Two accounts of one CLI', link: '/features/accounts' },
            { text: 'One timeline', link: '/features/tracing' },
            { text: 'A line typed mid-turn', link: '/features/steering' },
            { text: 'Answers in a shape', link: '/features/shapes' },
          ],
        },
        {
          text: 'The shape of a run',
          collapsed: false,
          items: [
            { text: 'Ten CLIs, one agent', link: '/features/backends' },
            { text: 'A flow is Python', link: '/features/flows' },
            { text: 'Many turns at once', link: '/features/concurrency' },
            { text: 'Picked up where it stopped', link: '/features/resuming' },
          ],
        },
        {
          text: 'Who is at the other end',
          collapsed: false,
          items: [
            { text: 'It decides when it is done', link: '/features/goals' },
            { text: 'The moments of a turn', link: '/features/hooks' },
            { text: 'You, as one of the agents', link: '/features/human' },
          ],
        },
      ],

      // One page per flow, named the way `-f` takes it. The order is the order they are worth
      // reading in rather than alphabetical: the three that ship, then the flowverse's, ending
      // with the two that are seven agents at once.
      '/flows/': [
        { text: 'Flows', link: '/flows/' },
        {
          text: 'The three that ship',
          collapsed: false,
          items: [
            { text: 'chat', link: '/flows/chat' },
            { text: 'ralph_loop', link: '/flows/ralph-loop' },
            { text: 'stateful_ralph', link: '/flows/stateful-ralph' },
          ],
        },
        {
          text: 'One agent, in the flowverse',
          collapsed: false,
          items: [
            { text: 'official/continue_loop', link: '/flows/continue-loop' },
            { text: 'official/goal', link: '/flows/goal' },
            { text: 'official/fixed_juice_ralph', link: '/flows/fixed-juice-ralph' },
          ],
        },
        {
          text: 'More than one agent',
          collapsed: false,
          items: [
            { text: 'official/flame_chase', link: '/flows/flame-chase' },
            { text: 'official/rlar', link: '/flows/rlar' },
            { text: 'official/humanize1', link: '/flows/humanize1' },
          ],
        },
        {
          text: 'Three lanes at once',
          collapsed: false,
          items: [
            { text: 'official/parallel_flame_chase', link: '/flows/parallel-flame-chase' },
            {
              text: 'official/parallel_flame_chase_mission',
              link: '/flows/parallel-flame-chase-mission',
            },
          ],
        },
      ],

      '/tutorials/': [
        { text: 'Tutorials', link: '/tutorials/' },
        {
          text: 'Start here',
          collapsed: false,
          items: [{ text: '1 · Quickstart', link: '/tutorials/quickstart' }],
        },
        {
          text: 'Three pieces of real work',
          collapsed: false,
          items: [
            { text: '2 · Beat a benchmark', link: '/tutorials/take-home' },
            { text: '3 · Port a project', link: '/tutorials/port-a-project' },
            { text: '4 · Build a coding agent', link: '/tutorials/build-an-agent' },
          ],
        },
        {
          text: 'Writing flows of your own',
          collapsed: false,
          items: [
            { text: '5 · Build under test', link: '/tutorials/flow-checked-build' },
            { text: '6 · Four agents on a maths problem', link: '/tutorials/flow-prove' },
          ],
        },
      ],

      '/guide/': [
        { text: 'Guides', link: '/guide/' },
        {
          text: 'Start here',
          items: [
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Concepts', link: '/guide/concepts' },
            { text: 'Security', link: '/guide/security' },
            { text: 'Troubleshooting', link: '/guide/troubleshooting' },
          ],
        },
        {
          text: 'At the prompt',
          collapsed: false,
          items: [
            { text: 'Talking to a running turn', link: '/guide/steering' },
            { text: 'Side questions (/btw)', link: '/guide/btw' },
            { text: 'Many conversations at once', link: '/guide/conversations' },
            { text: 'Showing the working (/details)', link: '/guide/details' },
            { text: 'The shape of a run (/status)', link: '/guide/status' },
            { text: 'Being away (/afk)', link: '/guide/afk' },
            { text: 'Completion', link: '/guide/completion' },
            { text: 'History', link: '/guide/history' },
            { text: 'Exporting a transcript', link: '/guide/export' },
            { text: 'What a project remembers', link: '/guide/settings' },
            { text: 'Stopping', link: '/guide/stopping' },
          ],
        },
        {
          text: 'Setting an agent up',
          collapsed: false,
          items: [
            { text: 'Efforts', link: '/guide/efforts' },
            { text: 'Permissions', link: '/guide/permissions' },
            { text: 'Skills', link: '/guide/skills' },
            { text: 'Goals', link: '/guide/goals' },
            { text: 'Questions', link: '/guide/questions' },
            { text: 'Answers in a shape', link: '/guide/shapes' },
            { text: 'Hooks', link: '/guide/hooks' },
            { text: 'Cost and rate', link: '/guide/tally' },
            { text: 'The person as an agent', link: '/guide/human-agent' },
            { text: 'Reporting', link: '/guide/reporting' },
          ],
        },
        {
          text: 'Writing flows',
          collapsed: false,
          items: [
            { text: 'Writing a flow', link: '/guide/writing-a-flow' },
            { text: 'Loops', link: '/guide/loops' },
            { text: 'Settings of its own', link: '/guide/flow-settings' },
            { text: 'Many turns at once', link: '/guide/async-flows' },
            { text: 'A flow that calls a flow', link: '/guide/calling-flows' },
            { text: 'Testing a flow', link: '/guide/testing-flows' },
            { text: 'Flowverses', link: '/guide/flowverses' },
          ],
        },
        {
          text: 'Where the work lands',
          collapsed: false,
          items: [
            { text: 'Providers', link: '/guide/providers' },
            { text: 'Falling back', link: '/guide/fallback' },
            { text: 'Containers', link: '/guide/containers' },
            { text: 'Remote execution', link: '/guide/remote-execution' },
            { text: 'Worktrees', link: '/guide/worktrees' },
          ],
        },
        {
          text: 'Running it, and reading it back',
          collapsed: false,
          items: [
            { text: 'Run it unattended', link: '/guide/unattended' },
            { text: 'humanize in CI', link: '/guide/ci' },
            { text: 'Tracing', link: '/guide/tracing' },
            { text: 'Picking a run up', link: '/guide/resuming' },
          ],
        },
      ],

      '/reference/': [
        {
          text: 'Command line',
          items: [
            { text: 'CLI', link: '/reference/cli' },
            { text: 'TUI', link: '/reference/tui' },
          ],
        },
        {
          text: 'Python',
          items: [
            { text: 'Flows', link: '/reference/flows' },
            { text: 'Agents', link: '/reference/agents' },
            { text: 'Machines', link: '/reference/machines' },
            { text: 'Providers', link: '/reference/providers' },
            { text: 'Remote execution', link: '/reference/remote-execution' },
            { text: 'Tracing', link: '/reference/tracing' },
          ],
        },
      ],

      '/contributing/': [
        { text: 'Contributing', link: '/contributing/' },
        {
          text: 'How the repository works',
          items: [
            { text: 'Architecture', link: '/contributing/architecture' },
            { text: 'Working on these docs', link: '/contributing/docs' },
          ],
        },
      ],
    },

    socialLinks: [{ icon: 'github', link: 'https://github.com/humanfia/humanize2' }],

    editLink: {
      pattern: 'https://github.com/humanfia/humanize2/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },

    search: { provider: 'local' },

    outline: { level: [2, 3] },

    footer: {
      message: 'Released under the Apache-2.0 licence.',
      copyright: 'Copyright © 2026 Zijian Zhang',
    },
  },

  // There is no home page. A front page that explains nothing, above four sections that
  // explain everything, is a page a reader passes through on the way to Features -- so the
  // root goes there, and what the front page used to draw is drawn on the page it goes to.
  // GitHub Pages serves files, so the redirect has to be one: an index.html with nothing in
  // it but the way on, written after the build so no page has to pretend to be it.
  async buildEnd(site: SiteConfig) {
    await writeFile(
      join(site.outDir, 'index.html'),
      [
        '<!doctype html>',
        '<html lang="en-US">',
        '<head>',
        '<meta charset="utf-8">',
        `<meta http-equiv="refresh" content="0; url=${FRONT}">`,
        `<link rel="canonical" href="https://docs.humanfia.ai${FRONT}">`,
        '<title>humanize</title>',
        '</head>',
        `<body><a href="${FRONT}">humanize documentation</a></body>`,
        '</html>',
        '',
      ].join('\n'),
    )
  },

  vite: {
    plugins: [
      {
        // The same redirect while `pnpm dev` is running, where nothing has been built yet and
        // there is no index.html to serve. Without it the root is a 404 in development and a
        // features page in production, which is the sort of difference nobody finds until it
        // is deployed.
        name: 'hmz-no-home',
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            const asked = (req.url ?? '').split('?')[0]
            if (asked !== BASE && asked !== '/') return next()
            res.statusCode = 302
            res.setHeader('location', FRONT)
            res.end()
          })
        },
      },
    ],
  },
})
