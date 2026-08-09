# Working on these docs

The site is [VitePress](https://vitepress.dev/) under `docs/`, built and deployed by
`.github/workflows/build-docs.yml`.

## Running it

```sh
cd docs
pnpm install
pnpm dev        # http://localhost:5173/
```

```sh
pnpm build      # what CI runs
pnpm preview    # serve what it built
```

`pnpm build` **fails on a dead internal link**, which is the point: a page moved without its
inbound links moving is a red build rather than a 404 somebody finds later.

## The layout

```
docs/
├── .vitepress/config.mts     nav, sidebars, everything
├── .vitepress/theme/         the palette, and the diagrams the home page is made of
├── index.md                  the home page
├── features/                 one page per feature, each built on a diagram you can push
├── tutorials/                six, in order, each a whole piece of work
├── guide/                    one page per feature, answering "how do I use this?"
├── reference/                CLI, TUI, and the Python API
├── contributing/             this
├── public/                   served at the site root: logo.svg, tui.svg, demo/*.gif, demo/*.png
└── tapes/                    the VHS scripts the demos are rendered from
```

Four kinds of page, and a page that is two of them is two pages.

| | | |
| --- | --- | --- |
| **Features** | understanding | One page per feature, built around a diagram the reader can push. What it is and why it works the way it does. **No commands and no code**: a reader who wants to run it is one click from the guide, which every page ends by naming. |
| **Tutorials** | learning | Taken in order, start to finish, with every command written out. A reader following one is not choosing anything; they are being led. Six of them, and adding a seventh means arguing that one of the six should go. |
| **Guides** | doing | "How do I use X?" One feature each. Opens with a `## Try it` section short enough to paste, then explains the rest. A reader here has a job and knows what they want. |
| **Reference** | looking up | Complete and dry. Every flag, key, argument and return. A reader here already knows what they are looking for. |

That split is the [Diátaxis](https://diataxis.fr/) one, and the reason the docs were
reorganised: everything used to be in **Guide**, which made a reader with a job read a tutorial
and a reader learning read a feature page.

## Writing a page

- Links are written from the site root, without the extension: `/guide/afk`. VitePress checks
  them at build time.
- Assets in `public/` are referenced from the root without `public`: `![…](/tui.svg)`.
- Do not add a `## Table of Contents`. The right-hand outline is generated.
- The first `#` heading is the page title.
- Wrap prose at 95 columns, as the rest of the repository does.
- A guide opens with two or three sentences under the title saying what the feature is and when
  you would reach for it, then a `## Try it`. A tutorial opens with how long it takes and what
  the reader will have at the end.

Adding a page means adding it to `sidebar` in `.vitepress/config.mts`; it will not appear
otherwise.

## The home page

`index.md` is a frontmatter hero, one line of install, and five drawings. It explains nothing:
a reader who wants to know how to use something is one click from a tutorial, a guide or the
reference, and every one of those is a better page for it than a front page is.

```
.vitepress/theme/
├── index.ts                  registers the components; the rest is VitePress's default theme
├── style.css                 the palette, the hero, and the shell every section is drawn in
└── components/
    ├── HmzInstall.vue        the one line, and a button that copies it
    ├── HmzOrchestra.vue      a run simulated lane by lane, landing on a trace strip
    ├── HmzFeatures.vue       eight features, one small drawing each
    ├── HmzAnchor.vue         pick a syscall, watch which side of the anchor answers it
    ├── HmzStack.vue          the layers, and what each is allowed to name
    └── HmzGallery.vue        the recorded demos, played on hover and opened on click
```

## The feature pages

One page, one diagram, one component, registered in the same `index.ts`:

```
HmzMap.vue          features/            the six stages, and every page hung off one
HmzSyscalls.vue     features/anchor      a call, the seccomp verdict, and where it lands
HmzAccounts.vue     features/accounts    the path swap, then the chain and its waits
HmzTimeline.vue     features/tracing     a trace, with the programs and the clock as switches
HmzSteer.vue        features/steering    type a line into a running turn, or queue behind it
HmzShape.vue        features/shapes      a model, how a backend is held to it, what comes back
HmzBackends.vue     features/backends    eleven backends against what a flow may ask for
HmzLoops.vue        features/flows       the shapes a loop takes, stepped through
HmzTurns.vue        features/concurrency twelve prompts, scheduled across n conversations
HmzResume.vue       features/resuming    pull the plug, then run it again
HmzGoal.vue         features/goals       the model deciding, beside your code deciding
HmzMoments.vue      features/hooks       hang a hook, run the turn, read what it said
HmzPerson.vue       features/human       a questionnaire built out of a pydantic model
```

Four things they are all held to:

- **A drawing says what the code does.** `HmzAnchor` and `HmzSyscalls` route each call the way
  `coganchor/SPEC.md` and `coganchor/linux/seccomp.py` route it; `HmzStack`'s edges are the
  `ALLOWED` table in `tests/test_layering.py`; `HmzBackends` is `hmz/backends.py` and which
  session base each agent class derives from; `HmzAccounts`' waits are the formulas in
  `providers/retry.py`; every agent on `HmzOrchestra` is spelled the way `hmz exec -a` would
  take it. A diagram that drifts from those is a diagram that lies to a reader.
- **A simulation is not dressed up as a recording.** `HmzOrchestra` and the feature diagrams are
  drawn; the gallery on the home page is what the real thing looks like.
- **Interaction is the argument.** The switch on `HmzTimeline` exists because the clock
  correction is hard to believe in prose, and the one on `HmzTurns` because "two turns on one
  session are sequential" is a rule people read past. A control that does not settle a question
  should not be there.
- **Motion is optional.** Every diagram reads `prefers-reduced-motion` and holds still at
  something worth looking at; the animated ones also stop while they are scrolled off screen.
  Nothing is said only by a moving thing.

## The terminal demos

The GIFs under `docs/public/demo/` are rendered by [VHS](https://github.com/charmbracelet/vhs)
from the `.tape` scripts beside them, in a container built for the purpose.

```sh
docs/tapes/render.sh              # every tape
docs/tapes/render.sh tui.tape     # one of them
```

It needs `docker` and nothing else. The first run builds the image, which takes a couple of
minutes; after that a tape is a few seconds.

::: danger A demo must not record anything private
Every tape runs **inside the container**, in a scratch `HOME`, in a throwaway project, against a
**stand-in coding agent CLI** — never your account, never your machine, never a real credential.

Concretely:

- The prompt is VHS's own `>`. No user, no host, no path in it.
- Every tape starts `cd /work/demo`, and the only homes that appear are the container's
  `/root/.humanize` and `/root/.claude`.
- No provider is ever signed in: `hmz providers add` is only ever recorded with `--no-login`, an
  account made in the interface is only ever made by a way that runs nothing, and the values are
  obviously invalid — `gateway.example.invalid`, `not-a-real-token`, `not-a-real-key`.
- No turn is ever run. `/opt/standin/claude` and `/opt/standin/codex` exist so that humanize
  offers those backends; both exit 1 if anything actually calls them.
- What the [`collect`](/guide/tracing) demo reads, and the runs `/cycles` lists, are what
  `stage.py` invented.

If you add a tape, look at the rendered GIF before committing it. Frame by frame is worth it:

```sh
docker run --rm -v "$PWD/docs/public/demo:/out" -v /tmp/frames:/frames \
    --entrypoint ffmpeg humanize-vhs \
    -i /out/tui.gif -vf 'select=not(mod(n\,20))' -vsync 0 /frames/tui_%02d.png
```
:::

Keep them small — `check-added-large-files` refuses anything over 500 KB, `render.sh` refuses
anything over 450 KB, and a doc page with a two-megabyte GIF on it is a doc page nobody waits
for. It is the file that is bounded rather than the clock: what the current tapes are written
against is `Width 1000`, `Height` between 500 and 620, `Framerate` between 10 and 20 — the
slower for a tape that is mostly a menu being read — and the `Set TypingSpeed`/`Sleep` values
already in them, which run 8 to 20 seconds end to end.

## The deploy

`.github/workflows/build-docs.yml` builds on every push and pull request that touches `docs/`, and
deploys to GitHub Pages on a push to `main`. It is served at
[docs.humanfia.ai/humanize2](https://docs.humanfia.ai/humanize2/). The custom domain is the
organisation's own pages site, so this repository is a project page under a subdirectory of it:
the config sets **`base: '/humanize2/'`**, and this repository publishes no `CNAME` of its own —
one here would move the whole site to a domain root that belongs to something else.
`humanfia.github.io/humanize2` redirects here.

A `base` that does not match where the site is served is a page whose every stylesheet, script
and link asks for a path that is not there, which is a site that looks like unstyled markdown.
So anything written by hand that names a path from the site's root — a `head` link in the
config, an `href` or `src` in a component under `.vitepress/theme` — must go through
`withBase`, or name the base itself where it cannot. What a markdown page links to, and what
the nav, the sidebar and the theme's own logo name, VitePress prepends the base to already.

## The other documentation

- **`README.md`** follows [standard-readme](https://github.com/RichardLitt/standard-readme) and
  must not explain how anything works. It links here.
- **`**/SPEC.md`** beside the packages are contracts. **Do not modify one** unless you were asked
  to.
- **Docstrings** are Google style and are checked by `ruff`.
