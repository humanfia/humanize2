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
├── index.md                  the home page
├── guide/                    start here, and the numbered tutorials
├── features/                 one page per feature
├── reference/                CLI, TUI, and the Python API
├── contributing/             this
├── public/                   served at the site root: logo.svg, tui.svg, demo/*.gif, demo/*.png
└── tapes/                    the VHS scripts the demos are rendered from
```

**Guide** is for reading through, **Features** for "how do I use X", **Reference** for looking
something up. A page that is two of those is two pages.

## Writing a page

- Links are written from the site root, without the extension: `/features/afk`. VitePress checks
  them at build time.
- Assets in `public/` are referenced from the root without `public`: `![…](/tui.svg)`.
- Do not add a `## Table of Contents`. The right-hand outline is generated.
- The first `#` heading is the page title.
- Wrap prose at 100 columns, as the rest of the repository does.

Adding a page means adding it to `sidebar` in `.vitepress/config.mts`; it will not appear
otherwise.

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
- What the [`collect`](/features/tracing) demo reads, and the runs `/cycles` lists, are what
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
[docs.humanfia.ai](https://docs.humanfia.ai), which is a custom domain and so is the site's own
root: the config sets **no `base`**, and `docs/public/CNAME` is what keeps the domain on the
artifact each deploy publishes. `humanfia.github.io/humanize2` redirects here.

Serving it under a subdirectory again would mean setting `base` back — and a `base` that does not
match where the site is served is a page whose every stylesheet, script and link asks for a path
that is not there, which is a site that looks like unstyled markdown.

## The other documentation

- **`README.md`** follows [standard-readme](https://github.com/RichardLitt/standard-readme) and
  must not explain how anything works. It links here.
- **`**/SPEC.md`** beside the packages are contracts. **Do not modify one** unless you were asked
  to.
- **Docstrings** are Google style and are checked by `ruff`.
