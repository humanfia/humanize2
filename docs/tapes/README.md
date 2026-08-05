# The terminal demos

The GIFs and stills under `docs/public/demo/` are rendered from the `.tape` scripts here by
[VHS](https://github.com/charmbracelet/vhs), inside a container built by the `Dockerfile`
beside them. A tape may `Screenshot` a moment worth its own still as well as writing its GIF.

```sh
./render.sh                 # every tape
./render.sh tui.tape        # one of them
```

Needs `docker` and nothing else. The first run builds the image; after that a tape takes a few
seconds. The GIFs are **committed**; nothing in CI renders them.

## A demo must not record anything private

That is the whole reason this is a container rather than a script you run on your own machine.

| | |
| --- | --- |
| the prompt | VHS's own `>` — no user, no host, no path |
| the workspace | `/work/demo`, built by `stage.py` |
| the homes | `/root/.humanize` and `/root/.claude`, inside the container |
| the backends | `standin/claude` and `standin/codex`, which run nothing and exit 1 |
| the accounts | made with `--no-login`, or by a way that runs nothing, at `gateway.example.invalid`, with `not-a-real-token` and `not-a-real-key` |
| the runs, and the transcripts `hmz trace collect` reads | invented by `stage.py` |

**No tape takes a turn.** The interface demos open, show their own lists, and leave.

Look at what you rendered before you commit it.

## The pieces

| | |
| --- | --- |
| `Dockerfile` | VHS, humanize built out of this checkout, and the stand-ins |
| `Dockerfile.dockerignore` | so the build context is a few files rather than the tree |
| `stage.py` | builds the throwaway world, at image build time |
| `standin/` | the coding agent CLIs that are not coding agent CLIs |
| `render.sh` | builds the image, runs the tapes, and refuses a GIF over 450 KB |
| `*.tape` | one demo each |

## Keeping them small

`check-added-large-files` refuses anything over 500 KB, and `render.sh` refuses anything over
450 KB. The clock is not bounded; the file is. What the current tapes are written against:

- `Set Width 1000`, `Set Height` between 500 and 620;
- `Set Framerate` between 10 and 20 — the slower for a tape that is mostly a menu being read —
  and `Set TypingSpeed` between 20ms and 50ms;
- 8 to 20 seconds end to end, which those settings keep under 420 KB.

A tape that has grown too large is usually one with too much `Sleep` in it.
