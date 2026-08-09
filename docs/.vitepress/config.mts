import { defineConfig } from 'vitepress'

// Deployed to https://docs.humanfia.ai/humanize2/ by .github/workflows/build-docs.yml.
// The custom domain belongs to the organisation's own pages, so this repository is a project
// page served under a subdirectory of it, and `base` is that subdirectory: without it every
// stylesheet, script and link would ask for a path at the domain root, where nothing of this
// site is. Internal links are still written from the site's own root -- VitePress prepends
// the base to each of them -- so nothing in a page names the subdirectory.
export default defineConfig({
  base: '/humanize2/',
  title: 'humanize',
  description: 'Orchestrate, execute, and observe agent flows',
  lang: 'en-US',
  cleanUrls: true,
  lastUpdated: true,

  head: [
    // Written out with the base in it: VitePress prepends the base to a theme's own
    // links and to what a page names, and hands `head` to the template as it is.
    ['link', { rel: 'icon', href: '/humanize2/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#3c8772' }],
  ],

  themeConfig: {
    logo: '/logo.svg',

    // Four sections, and features come first: what there is, drawn rather than described, is
    // what somebody who has never run this wants before anything else. Then tutorials, which
    // teach a whole piece of work end to end; guides, which answer "how do I use this one
    // feature"; and reference, which spells all of it out.
    nav: [
      { text: 'Features', link: '/features/', activeMatch: '/features/' },
      { text: 'Tutorials', link: '/tutorials/', activeMatch: '/tutorials/' },
      { text: 'Guides', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Reference', link: '/reference/cli', activeMatch: '/reference/' },
      {
        text: 'Contributing',
        link: '/contributing/',
        activeMatch: '/contributing/',
      },
    ],

    sidebar: {
      // One page per feature, each built around a diagram you can push. The first group is
      // the one to send somebody who wants to know what is unusual about this.
      '/features/': [
        {
          text: 'Features',
          items: [{ text: 'All of them', link: '/features/' }],
        },
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

      '/tutorials/': [
        {
          text: 'Tutorials',
          items: [
            { text: 'All six', link: '/tutorials/' },
            { text: '1 · Quickstart', link: '/tutorials/quickstart' },
          ],
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
        {
          text: 'Start here',
          items: [
            { text: 'All the guides', link: '/guide/' },
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
        {
          text: 'Contributing',
          items: [
            { text: 'How to contribute', link: '/contributing/' },
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
})
