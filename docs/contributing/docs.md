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
├── .vitepress/config.mts     nav, sidebars, the root's redirect, everything
├── .vitepress/theme/         the palette, and every diagram on the site
├── features/                 one page per feature, each built on a diagram you can push
├── flows/                    one page per flow, each with its own loop played on it
├── tutorials/                six, in order, each a whole piece of work
├── guide/                    one page per feature, answering "how do I use this?"
├── reference/                CLI, TUI, and the Python API
├── contributing/             this
├── public/                   served at the site root: logo.svg, tui.svg, demo/*.gif, demo/*.png
└── tapes/                    the VHS scripts the demos are rendered from
```

**There is no `index.md`.** The site's root is a redirect to `/features/`, written into the
built site by `buildEnd` and served by a dev-server middleware beside it — both in
`config.mts`, both naming one constant. A front page that explained nothing, above five
sections that explain everything, was a page a reader passed through; what it used to draw is
drawn on the page it now goes to.

`tapes/` is the one directory under `docs/` that is not the site: `srcExclude` keeps its README
out of the build, because a page written for somebody standing in that directory with docker is
not a page a reader of the site is looking for. What they need of it is below.

Five kinds of page, and a page that is two of them is two pages.

| | | |
| --- | --- | --- |
| **Features** | understanding | One page per feature, built around a diagram the reader can push. What it is and why it works the way it does. **No commands and no code**: a reader who wants to run it is one click from the guide, which every page ends by naming. Its index is the front of the site. |
| **Flows** | what there is to run | One page per flow humanize or the official flowverse ships, named the way `-f` takes it, opening with the `hmz exec` line and the shape of its loop. What it is for, what it takes, and what a run picked up carries in. |
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
- Do not add a `## Table of Contents`. The right-hand outline is generated, from `##` and `###`.
  A page whose `###`s are dozens of error messages sets `outline: 2` in its frontmatter, the way
  [Troubleshooting](/guide/troubleshooting) does: forty half-sentences, each cut off at the same
  width, name nothing. The handful of places they happen in do.
- The first `#` heading is the page title.
- Wrap prose at 95 columns, as the rest of the repository does.
- A guide opens with two or three sentences under the title saying what the feature is and when
  you would reach for it, then a `## Try it`. A tutorial opens with how long it takes and what
  the reader will have at the end.

Adding a page means adding it to `sidebar` in `.vitepress/config.mts`; it will not appear
otherwise.

## The front of the site

`features/index.md` is what somebody arriving is handed: one line of install with the way to
the quickstart beside it, four drawings, the recorded demos, and the index of the feature
pages. It explains nothing at length — a reader who wants to know how to use something is one
click from a tutorial, a guide or the reference, and every one of those is a better page for it.

```
.vitepress/theme/
├── index.ts                  registers the components; the rest is VitePress's default theme
├── style.css                 the palette, the shell every diagram is drawn in, and the width
│                              the nav folds into a button at
├── flows.ts                  every flow there is, and the shape of each one
└── components/
    ├── HmzInstall.vue        the one line, a button that copies it, and the way to the quickstart
    ├── HmzOrchestra.vue      a run simulated lane by lane, landing on a trace strip
    ├── HmzFeatures.vue       eight features, one small drawing each
    ├── HmzAnchor.vue         pick a syscall, watch which side of the anchor answers it
    └── HmzGallery.vue        the recorded demos, played on hover and opened on click
```

## The flow pages

Two components and one module, and the module is the point: `theme/flows.ts` holds every flow's
name, where it comes from, what it drives and what stops it — **and** the script of turns its
loop is, which `HmzFlowShape` plays. The catalogue and the diagrams cannot disagree, and a flow
added to the flowverse is one entry there rather than a page and a drawing that drift apart.

```
HmzFlows.vue        flows/               every flow as a card, its loop drawn small and moving
HmzFlowShape.vue    flows/*              one flow's rounds, played: who takes a turn, on
                                          whose session, and what it hands the next one
```

What the shapes are read off is the flows themselves: `src/hmz/flows/builtin/` for the three
humanize ships, and [humanfia/flowverse](https://github.com/humanfia/flowverse) for the rest.
A `new` box is a session the flow opened for that turn and a `held` box is another turn of the
one it had — which is most of what separates these flows from each other, and so is the thing
the diagram draws largest.

## The feature pages

One page, one diagram, one component, registered in the same `index.ts` — the feature pages,
and the one elsewhere that is built the same way:

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
HmzStack.vue        contributing/architecture
                                         the layers, and what each is allowed to name
```

Four things they are all held to:

- **A drawing says what the code does.** `HmzAnchor` and `HmzSyscalls` route each call the way
  `coganchor/SPEC.md` and `coganchor/linux/seccomp.py` route it; `HmzStack`'s edges are the
  `ALLOWED` table in `tests/test_layering.py`; every box in `theme/flows.ts` is a turn a flow
  really takes; `HmzBackends` is `hmz/backends.py` and which
  session base each agent class derives from; `HmzAccounts`' waits are the formulas in
  `providers/retry.py`; every agent on `HmzOrchestra` is spelled the way `hmz exec -a` would
  take it. A diagram that drifts from those is a diagram that lies to a reader.
- **A simulation is not dressed up as a recording.** `HmzOrchestra`, the feature diagrams and
  the flow shapes are drawn; the gallery below them is what the real thing looks like, and says
  so.
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
