import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'

import { defineConfig, type SiteConfig } from 'vitepress'

// Deployed to https://docs.humanfia.ai/humanize2/ by .github/workflows/build-docs.yml.
// The custom domain belongs to the organisation's own pages, so this repository is a project
// page served under a subdirectory of it, and `base` is that subdirectory: without it every
// stylesheet, script and link would ask for a path at the domain root, where nothing of this
// site is. Internal links are still written from the site's own root -- VitePress prepends
// the base to each of them -- so nothing in a page names the subdirectory.
const BASE = '/humanize2/'

// Where a page used to be, and where it is now. Guides used to be one flat section serving two
// audiences at once; they are a User Guide and a Weaver Guide now, and the tutorials went with
// the audience each one teaches. GitHub Pages serves files and nothing else, so a page that
// moved is a 404 for every bookmark and search result unless a file is left where it was --
// which is what `buildEnd` below writes, one small redirect apiece.
//
// This table is a record of what the paths once were rather than a second copy of what they
// are: nothing new belongs in it, and an entry only ever comes out if the page it names is
// finally allowed to go cold.
const MOVED_TO_USER = [
  'installation',
  'concepts',
  'security',
  'troubleshooting',
  'steering',
  'btw',
  'conversations',
  'details',
  'status',
  'board',
  'afk',
  'fallback',
  'completion',
  'history',
  'export',
  'settings',
  'stopping',
  'efforts',
  'permissions',
  'skills',
  'questions',
  'tally',
  'reporting',
  'providers',
  'containers',
  'remote-execution',
  'unattended',
  'ci',
  'tracing',
  'resuming',
]

const MOVED_TO_WEAVER = [
  'writing-a-flow',
  'loops',
  'flow-settings',
  'async-flows',
  'calling-flows',
  'atlas',
  'goals',
  'shapes',
  'hooks',
  'tools',
  'human-agent',
  'worktrees',
  'checking-flows',
  'testing-flows',
  'flowverses',
]

const MOVED: Record<string, string> = {
  ...Object.fromEntries(MOVED_TO_USER.map((page) => [`guide/${page}`, `user/${page}`])),
  ...Object.fromEntries(MOVED_TO_WEAVER.map((page) => [`guide/${page}`, `weaver/${page}`])),
  'guide/': 'user/',
  'tutorials/': 'user/',
  // The quickstart is not a page any more. It is the first of the three the home page opens on.
  'tutorials/quickstart': '#run-a-flow',
  'tutorials/take-home': 'user/tutorials/take-home',
  'tutorials/port-a-project': 'user/tutorials/port-a-project',
  'tutorials/build-an-agent': 'user/tutorials/build-an-agent',
  'tutorials/flow-checked-build': 'weaver/tutorials/checked-build',
  'tutorials/flow-prove': 'weaver/tutorials/prove',
}

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
    ['meta', { name: 'theme-color', content: '#2a6ea6' }],
  ],

  themeConfig: {
    logo: '/logo.svg',

    // Six sections. Features is what there is, drawn rather than described; flows is what
    // there is to run; then a guide per role -- the person running flows, and the weaver
    // writing them -- then contributing, for the person working on humanize itself; and
    // reference, which spells all of it out. The home page sits above the six and sends a
    // reader to whichever of the three roles is theirs.
    nav: [
      { text: 'Features', link: '/features/', activeMatch: '/features/' },
      { text: 'Flows', link: '/flows/', activeMatch: '/flows/' },
      { text: 'User Guide', link: '/user/', activeMatch: '/user/' },
      { text: 'Weaver Guide', link: '/weaver/', activeMatch: '/weaver/' },
      {
        text: 'Contributing',
        link: '/contributing/',
        activeMatch: '/contributing/',
      },
      { text: 'Reference', link: '/reference/', activeMatch: '/reference/' },
    ],

    // Every sidebar opens with its own section as a link rather than with an entry inside a
    // group of the same name: a group called Features holding an item called "All of them" is
    // a title nobody would write on the page itself, and the page is what it goes to. So the
    // section is the first line, and the groups under it are what they were.
    //
    // The three role guides then open with Tutorials, because a reader who has arrived at
    // their own section wants to be led once before being asked to look something up.
    sidebar: {
      // The capability map groups the whole system; the pages beneath it take one mechanism
      // far enough to explain its trade-offs, each around a diagram the reader can push.
      '/features/': [
        { text: 'Features', link: '/features/' },
        { text: 'Capability map', link: '/features/capabilities' },
        {
          text: 'Flow system',
          collapsed: false,
          items: [
            { text: 'Python becomes a prophecy', link: '/features/prophecy' },
            { text: 'A flow is Python', link: '/features/flows' },
            { text: 'Many turns at once', link: '/features/concurrency' },
            { text: 'Picked up where it stopped', link: '/features/resuming' },
          ],
        },
        {
          text: 'Agent control plane',
          collapsed: false,
          items: [
            { text: 'Many backends, one agent', link: '/features/backends' },
            { text: 'Two accounts of one CLI', link: '/features/accounts' },
            { text: 'A line typed mid-turn', link: '/features/steering' },
            { text: 'Answers in a shape', link: '/features/shapes' },
            { text: 'It decides when it is done', link: '/features/goals' },
            { text: 'The moments of a turn', link: '/features/hooks' },
            { text: 'You, as one of the agents', link: '/features/human' },
          ],
        },
        {
          text: 'Execution fabric',
          collapsed: false,
          items: [{ text: 'The anchor', link: '/features/anchor' }],
        },
        {
          text: 'Run continuity and observability',
          collapsed: false,
          items: [
            { text: 'The terminal can leave', link: '/features/daemon' },
            { text: 'One timeline', link: '/features/tracing' },
          ],
        },
        {
          text: 'Product surfaces',
          collapsed: false,
          items: [{ text: 'One system, four ways in', link: '/features/surfaces' }],
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

      // For the person who runs flows: the interface, the agents they point at it, where the
      // work lands, and how to read a run back. Where one of these pages has a Python half --
      // the flow on the other side of the board, of a question, of a container -- it is there
      // to say what the weaver did, and links on rather than teaching it here.
      '/user/': [
        { text: 'User Guide', link: '/user/' },
        {
          text: 'Tutorials',
          collapsed: false,
          items: [
            { text: 'Beat a benchmark', link: '/user/tutorials/take-home' },
            { text: 'Port a project', link: '/user/tutorials/port-a-project' },
            { text: 'Build a coding agent', link: '/user/tutorials/build-an-agent' },
          ],
        },
        {
          text: 'Start here',
          collapsed: false,
          items: [
            { text: 'Installation', link: '/user/installation' },
            { text: 'Concepts', link: '/user/concepts' },
            { text: 'Security', link: '/user/security' },
            { text: 'Troubleshooting', link: '/user/troubleshooting' },
          ],
        },
        {
          text: 'At the prompt',
          collapsed: false,
          items: [
            { text: 'Talking to a running turn', link: '/user/steering' },
            { text: 'Side questions (/btw)', link: '/user/btw' },
            { text: 'Many conversations at once', link: '/user/conversations' },
            { text: 'Showing the working (/details)', link: '/user/details' },
            { text: 'The shape of a run (/status)', link: '/user/status' },
            { text: 'The mission board', link: '/user/board' },
            { text: 'Being away (/afk)', link: '/user/afk' },
            { text: 'Falling back', link: '/user/fallback' },
            { text: 'Completion', link: '/user/completion' },
            { text: 'History', link: '/user/history' },
            { text: 'Exporting a transcript', link: '/user/export' },
            { text: 'What a project remembers', link: '/user/settings' },
            { text: 'Stopping', link: '/user/stopping' },
          ],
        },
        {
          text: 'Setting an agent up',
          collapsed: false,
          items: [
            { text: 'Efforts', link: '/user/efforts' },
            { text: 'Permissions', link: '/user/permissions' },
            { text: 'Skills', link: '/user/skills' },
            { text: 'Questions', link: '/user/questions' },
            { text: 'Cost and rate', link: '/user/tally' },
            { text: 'Reporting', link: '/user/reporting' },
          ],
        },
        {
          text: 'Where the work lands',
          collapsed: false,
          items: [
            { text: 'Providers', link: '/user/providers' },
            { text: 'Containers', link: '/user/containers' },
            { text: 'Remote execution', link: '/user/remote-execution' },
          ],
        },
        {
          text: 'Running it, and reading it back',
          collapsed: false,
          items: [
            { text: 'Run it unattended', link: '/user/unattended' },
            { text: 'humanize in CI', link: '/user/ci' },
            { text: 'Tracing', link: '/user/tracing' },
            { text: 'Picking a run up', link: '/user/resuming' },
          ],
        },
      ],

      // For the weaver: the person who writes the flow. Everything here is Python, and the
      // reader is expected to have run one before writing one.
      '/weaver/': [
        { text: 'Weaver Guide', link: '/weaver/' },
        {
          text: 'Tutorials',
          collapsed: false,
          items: [
            { text: 'Build under test', link: '/weaver/tutorials/checked-build' },
            { text: 'Four agents on a maths problem', link: '/weaver/tutorials/prove' },
          ],
        },
        {
          text: 'Writing a flow',
          collapsed: false,
          items: [
            { text: 'Writing a flow', link: '/weaver/writing-a-flow' },
            { text: 'Loops', link: '/weaver/loops' },
            { text: 'Settings of its own', link: '/weaver/flow-settings' },
            { text: 'Many turns at once', link: '/weaver/async-flows' },
            { text: 'A flow that calls a flow', link: '/weaver/calling-flows' },
            { text: 'An atlas', link: '/weaver/atlas' },
          ],
        },
        {
          text: 'What an agent can be asked',
          collapsed: false,
          items: [
            { text: 'Goals', link: '/weaver/goals' },
            { text: 'Answers in a shape', link: '/weaver/shapes' },
            { text: 'Hooks', link: '/weaver/hooks' },
            { text: 'Callbacks as tools', link: '/weaver/tools' },
            { text: 'The person as an agent', link: '/weaver/human-agent' },
            { text: 'Worktrees', link: '/weaver/worktrees' },
          ],
        },
        {
          text: 'Checking and publishing',
          collapsed: false,
          items: [
            { text: 'Checking a flow', link: '/weaver/checking-flows' },
            { text: 'Testing a flow', link: '/weaver/testing-flows' },
            { text: 'Flowverses', link: '/weaver/flowverses' },
          ],
        },
      ],

      '/contributing/': [
        { text: 'Contributing', link: '/contributing/' },
        {
          text: 'Tutorials',
          collapsed: false,
          items: [
            { text: 'Your first patch', link: '/contributing/tutorials/first-patch' },
            { text: 'Add a page to these docs', link: '/contributing/tutorials/a-page-of-docs' },
          ],
        },
        {
          text: 'How the repository works',
          collapsed: false,
          items: [
            { text: 'Architecture', link: '/contributing/architecture' },
            { text: 'Working on these docs', link: '/contributing/docs' },
          ],
        },
      ],

      '/reference/': [
        { text: 'Reference', link: '/reference/' },
        {
          text: 'Command line',
          items: [
            { text: 'CLI', link: '/reference/cli' },
            { text: 'TUI', link: '/reference/tui' },
            { text: 'Daemon', link: '/reference/daemon' },
          ],
        },
        {
          text: 'Python',
          items: [
            { text: 'SDK', link: '/reference/sdk' },
            { text: 'Flows', link: '/reference/flows' },
            { text: 'Agents', link: '/reference/agents' },
            { text: 'Machines', link: '/reference/machines' },
            { text: 'Providers', link: '/reference/providers' },
            { text: 'Remote execution', link: '/reference/remote-execution' },
            { text: 'Tracing', link: '/reference/tracing' },
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

  // One file per moved page, written after the build so no page has to pretend to be a
  // redirect. `cleanUrls` means GitHub Pages answers /humanize2/guide/afk with guide/afk.html,
  // so that is the name each one is written under, and a path that ended in a slash is the
  // index.html of its directory.
  async buildEnd(site: SiteConfig) {
    await Promise.all(
      Object.entries(MOVED).map(async ([from, to]) => {
        const at = join(site.outDir, from.endsWith('/') ? `${from}index.html` : `${from}.html`)
        const way = `${BASE}${to}`
        await mkdir(dirname(at), { recursive: true })
        await writeFile(
          at,
          [
            '<!doctype html>',
            '<html lang="en-US">',
            '<head>',
            '<meta charset="utf-8">',
            '<meta name="robots" content="noindex">',
            `<meta http-equiv="refresh" content="0; url=${way}">`,
            `<link rel="canonical" href="https://docs.humanfia.ai${way}">`,
            '<title>humanize</title>',
            '</head>',
            `<body>This page moved to <a href="${way}">${way}</a>.</body>`,
            '</html>',
            '',
          ].join('\n'),
        )
      }),
    )
  },

  vite: {
    plugins: [
      {
        // The same redirects while `pnpm dev` is running, where nothing has been built yet and
        // there is no file to serve. Without it an old path is a 404 in development and a
        // redirect in production, which is the sort of difference nobody finds until it is
        // deployed.
        name: 'hmz-moved',
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            const asked = (req.url ?? '').split('?')[0]
            if (!asked.startsWith(BASE)) return next()
            const to = MOVED[asked.slice(BASE.length)]
            if (to === undefined) return next()
            res.statusCode = 302
            res.setHeader('location', `${BASE}${to}`)
            res.end()
          })
        },
      },
    ],
  },
})
