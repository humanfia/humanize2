import { defineConfig } from 'vitepress'

// Deployed to https://docs.humanfia.ai by .github/workflows/build-docs.yml, which is a
// custom domain and so is the site's root: no base is prepended, and every internal link is
// written from that root. The project page it was built for -- humanfia.github.io/humanize2
// -- redirects here, so nothing is served under a subdirectory any more. A base left set to
// one would be every stylesheet, script and link asking for a path that is not there.
export default defineConfig({
  title: 'humanize',
  description: 'Orchestrate, execute, and observe agent flows',
  lang: 'en-US',
  cleanUrls: true,
  lastUpdated: true,

  head: [
    ['link', { rel: 'icon', href: '/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#3c8772' }],
  ],

  themeConfig: {
    logo: '/logo.svg',

    nav: [
      { text: 'Guide', link: '/guide/getting-started', activeMatch: '/guide/' },
      { text: 'Features', link: '/features/', activeMatch: '/features/' },
      { text: 'Reference', link: '/reference/cli', activeMatch: '/reference/' },
      {
        text: 'Contributing',
        link: '/contributing/',
        activeMatch: '/contributing/',
      },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Start here',
          items: [
            { text: 'What humanize is', link: '/guide/' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Getting started', link: '/guide/getting-started' },
            { text: 'Concepts', link: '/guide/concepts' },
            { text: 'Security', link: '/guide/security' },
          ],
        },
        {
          text: 'Tutorials · at the prompt',
          collapsed: false,
          items: [
            { text: '1 · Your first run', link: '/guide/tutorial-first-run' },
            { text: '2 · Put a loop under it', link: '/guide/tutorial-ralph-loop' },
            { text: '3 · Two agents at once', link: '/guide/tutorial-two-agents' },
            { text: '4 · Run it unattended', link: '/guide/tutorial-unattended' },
            { text: '5 · Read the run back', link: '/guide/tutorial-trace' },
          ],
        },
        {
          text: 'Tutorials · writing flows',
          collapsed: false,
          items: [
            { text: '6 · Write your first flow', link: '/guide/tutorial-first-flow' },
            { text: '7 · Actor and reviewer', link: '/guide/tutorial-actor-reviewer' },
            { text: '8 · Settings of its own', link: '/guide/tutorial-flow-settings' },
            { text: '9 · Many turns at once', link: '/guide/tutorial-async-flow' },
            { text: '10 · A flow that calls a flow', link: '/guide/tutorial-calling-flows' },
            { text: '11 · Hooks', link: '/guide/tutorial-hooks' },
            { text: '12 · Asking a person', link: '/guide/tutorial-questions' },
            { text: '13 · Answers in a shape', link: '/guide/tutorial-shapes' },
            { text: '14 · Testing a flow', link: '/guide/tutorial-testing-flows' },
            { text: '15 · Publish a flowverse', link: '/guide/tutorial-flowverse' },
          ],
        },
        {
          text: 'Tutorials · where work lands',
          collapsed: false,
          items: [
            { text: '16 · Two accounts of one CLI', link: '/guide/tutorial-providers' },
            { text: '17 · A container of its own', link: '/guide/tutorial-container' },
            { text: '18 · Another machine', link: '/guide/tutorial-remote' },
            { text: '19 · humanize in CI', link: '/guide/tutorial-ci' },
          ],
        },
        {
          text: 'When it goes wrong',
          items: [{ text: 'Troubleshooting', link: '/guide/troubleshooting' }],
        },
      ],

      '/features/': [
        {
          text: 'Features',
          items: [{ text: 'All of them', link: '/features/' }],
        },
        {
          text: 'At the prompt',
          collapsed: false,
          items: [
            { text: 'Being away (/afk)', link: '/features/afk' },
            { text: 'Showing the working (/details)', link: '/features/details' },
            { text: 'The shape of a run (/status)', link: '/features/status' },
            { text: 'Talking to a running turn', link: '/features/steering' },
            { text: 'Many conversations at once', link: '/features/conversations' },
            { text: 'Completion', link: '/features/completion' },
            { text: 'History', link: '/features/history' },
            { text: 'Exporting a transcript', link: '/features/export' },
            { text: 'What a project remembers', link: '/features/settings' },
            { text: 'Stopping', link: '/features/stopping' },
          ],
        },
        {
          text: 'What an agent is',
          collapsed: false,
          items: [
            { text: 'Efforts', link: '/features/efforts' },
            { text: 'Permissions', link: '/features/permissions' },
            { text: 'Skills', link: '/features/skills' },
            { text: 'Reporting', link: '/features/reporting' },
            { text: 'Goals', link: '/features/goals' },
            { text: 'Questions', link: '/features/questions' },
            { text: 'Answers in a shape', link: '/features/shapes' },
            { text: 'Hooks', link: '/features/hooks' },
            { text: 'Cost and rate', link: '/features/tally' },
            { text: 'The person as an agent', link: '/features/human-agent' },
          ],
        },
        {
          text: 'Where the work lands',
          collapsed: false,
          items: [
            { text: 'Providers', link: '/features/providers' },
            { text: 'Containers', link: '/features/containers' },
            { text: 'Remote execution', link: '/features/remote-execution' },
            { text: 'Worktrees', link: '/features/worktrees' },
          ],
        },
        {
          text: 'What a run leaves behind',
          collapsed: false,
          items: [
            { text: 'Flowverses', link: '/features/flowverses' },
            { text: 'Tracing', link: '/features/tracing' },
            { text: 'Picking a run up', link: '/features/resuming' },
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
