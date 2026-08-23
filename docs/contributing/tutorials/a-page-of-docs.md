# Add a page to these docs

**Twenty minutes.** You will run this site locally, write a page, put it in the sidebar, and
prove that every link on it resolves — which is exactly what CI asks of a pull request.

::: tip Before you start
Node and [pnpm](https://pnpm.io/), and nothing Python: the site is
[VitePress](https://vitepress.dev/) under `docs/` and builds without humanize installed. CI
uses Node 24 and pnpm 10; `packageManager` in `docs/package.json` pins the pnpm version
corepack fetches.
:::

## Run the site

```sh
cd docs
pnpm install
pnpm dev        # http://localhost:5173/
```

Leave it running. It reloads on save, the sidebar included.

## Decide which section it belongs in

Six of them, and the split is the [Diátaxis](https://diataxis.fr/) one: a page that is two
kinds is two pages.

| | |
| --- | --- |
| [Features](/features/) | Understanding. What a mechanism is and why it works the way it does, built around a diagram — no commands and no code. |
| [Flows](/flows/) | What there is to run. One page per flow, named the way `-f` takes it, opening with its `hmz exec` line and the shape of its loop. |
| [User Guide](/user/) | Doing, for the person running flows. One page per thing humanize does, each opening with a `## Try it` short enough to paste. |
| [Weaver Guide](/weaver/) | Doing, for the **weaver** — whoever writes the flow. Everything here is Python, and the reader has run one before writing one. |
| [Contributing](/contributing/) | Working on humanize itself: the layers, the gates, and the docs. This page is one. |
| [Reference](/reference/) | Looking up. Complete and dry — every flag, key, argument and return. |

The three guide sections each open with a **Tutorials** group, because a reader who has found
their own section wants to be led once before being asked to look anything up. A tutorial is
taken start to finish with every command written out; a guide answers one question for somebody
who already knows what they want. [Working on these docs](/contributing/docs#the-layout) states
the split in full.

## Write it

```sh
$EDITOR docs/user/my-thing.md
```

- The first `#` heading is the page title. Do not write a `## Table of Contents` — the
  right-hand outline is generated from `##` and `###`. A page whose `###`s are dozens of error
  messages sets `outline: 2` in its frontmatter instead.
- Links are written from the site root, without the extension: `/user/afk`, `/weaver/atlas`.
  Assets in `public/` are named from the root without `public`: `![…](/tui.svg)`.
- Wrap prose at 95 columns, as the rest of the repository does.
- A guide opens with two or three sentences saying what the thing is and when you would reach
  for it, then a `## Try it`. A tutorial opens with how long it takes and what the reader has
  at the end.

## Put it in the sidebar

**A page that is not in `sidebar` does not appear.** Open `.vitepress/config.mts`, find the
sidebar keyed by the section's path, and add the entry to the group it belongs in:

```ts
'/user/': [
  { text: 'User Guide', link: '/user/' },
  // ...
  {
    text: 'At the prompt',
    collapsed: false,
    items: [
      // ...
      { text: 'My thing', link: '/user/my-thing' },
    ],
  },
],
```

`link` is the route rather than the file: no `docs/`, no `.md`. The `nav` above it is the six
sections themselves and does not change.

## Build it

```sh
pnpm build          # fails on a dead internal link
pnpm check:anchors  # fails on a dead #fragment
pnpm preview        # serve what it built
```

The two checks catch different things. VitePress resolves every internal link and fails the
build on one that goes nowhere; it then stops, so a `#fragment` written the way GitHub would
slugify it passes the build and silently drops the reader at the top of the page.
`check:anchors` reads the ids the site really built and says which link missed:

```
user/my-thing.md: /user/tracing#whats-collected -- no such heading -- did you mean #what-s-collected

1 dead fragment(s).
```

A happy run prints one line:

```
every #fragment resolves
```

Renaming a `##` on a page that already exists moves its `#fragment`, and this is what finds
whatever pointed at the old one. Check before you rename, not after.

## Commit it

```sh
git add docs
git commit -m "docs(user): what my thing is and when to reach for it"
```

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), with the section as the
scope. `.github/workflows/build-docs.yml` then runs `pnpm install --frozen-lockfile` and
exactly the two checks above on every pull request that touches `docs/`, and deploys to GitHub
Pages on a push to `main` — so a dead link is a red pull request rather than a 404 somebody
finds a month later.

## What you have now

A page in the section it belongs to, in the sidebar, with every link and every fragment on it
checked. [Working on these docs](/contributing/docs) is the rest of the site: the theme
components each diagram lives in, how the terminal demos are recorded, and why `base` is what
it is.
