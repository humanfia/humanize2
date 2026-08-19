# How many anchored agents fit in 16 CPUs and 64 GiB

Measured 2026-08-29 on an AMD EPYC 7B13, confined to eight physical cores and their
hyperthread siblings (sixteen logical CPUs, which is what `nproc` reports inside the scope)
and 64 GiB with no swap. Real `hmz`, real coganchor, real agent CLIs; the target's data and
the model provider stood in for, both outside the cgroup. See [README](README.md) for what
that means exactly.

Every backend ran the same turn: three shell commands, each reading a seeded file on the
target and appending to another. A turn counts only if the agent said the sentence the script
ends on **and** its work is on the target.

## The short answer

There are three different numbers, and conflating them is how this question gets answered
wrongly.

| | claude | codex | grok | kimi | dsh |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Runs at full speed** (p95 within 2× of one agent alone) | **24** | **24** | **16** | **16** | **16** |
| **Best throughput** (turns/minute peaks here) | **48** | **128** | **48** | **64** | **32** |
| — turns/min there | 336 | 583 | 274 | 116 | 444 |
| **Still all-correct** (everything lands, just slowly) | **640** | **256** | **>832** | **192** | **>832** |
| What stops it there | 64 GiB | its own app-server | not found | 64 GiB | not found |

**Before any of that, on a stock machine, everything stops at about 320** — see
[The first ceiling is descriptors](#the-first-ceiling-is-descriptors).

So: if you want turns to run at the speed they run at alone, **16–24 anchored agents** is the
honest number for a 16-CPU box. If you want the most work done per hour and do not care that
each turn takes longer, **32–128**. Past that you are only lengthening the queue: claude's
throughput peaks at 336 turns/min with 48 agents and has fallen to 222 with 640.

## Cost per agent

| | claude | codex | grok | kimi | dsh |
| --- | ---: | ---: | ---: | ---: | ---: |
| memory | 102 MiB | 27 MiB | 44 MiB | **323 MiB** | 68 MiB |
| processes | 23 | **45** | **60** | 13 | 16 |
| CPU per turn | 2.0 s | 0.9 s | 2.8 s | 3.6 s | 1.1 s |
| one turn, alone | 2.8 s | 1.3 s | 2.4 s | 4.5 s | 1.1 s |

Memory is what decides kimi and claude; nothing else got near 64 GiB. Kimi's 323 MiB is its
`kimi web` daemon, which humanize starts one of per agent.

## The first ceiling is descriptors

**hmz holds about three file descriptors per concurrent anchored agent.** A stock login has
a soft `RLIMIT_NOFILE` of 1024, so the first wall anybody meets is at roughly **320 agents**,
whatever the backend and however much RAM is free. It arrives as `[Errno 24] Too many open
files` from dsh, and as a bare exit from codex, which is the same thing seen from further
away.

With the soft limit raised to the hard one, the same rung goes from 329/384 to **384/384**.
Everything above is measured with it raised.

```sh
ulimit -n 1048576     # or LimitNOFILE in the unit that runs hmz
```

## Where each one actually stops

- **claude — 640, on memory.** 640 agents used 63.74 of the 64 GiB and every turn still
  landed. That is the last rung measured; there is 0.26 GiB of headroom left at it, so the
  next one up was not attempted rather than shown to fail.
- **kimi — 192, on memory.** 192 used 60.5 GiB; 208 pinned the cgroup at exactly 64.00 GiB
  and the OOM killer took daemons out, which the agents saw as `Remote end closed connection
  without response`. 42 of 208 failed.
- **codex — 256, on codex.** Not memory (6.9 GiB), not descriptors, not the target: at 320 it
  loses 13 agents to `app server stopped mid-turn`, at 512 it loses 96, and the ones that die
  die at ~22 s while the survivors take ~45 s. The codex app-server gives up when the machine
  is oversubscribed. It is also the one backend sensitive to being run in a tight loop: 256
  passes cleanly on its own and loses one agent when it follows a 192-agent rung immediately,
  because several thousand processes from the previous rung are still going away.
- **grok and dsh — no ceiling found.** Both did 832 of 832 with nothing failing, at 36 GiB
  and 55 GiB. 832 was the rig's slot count, not the machine's limit. Turns take a long time
  there — 9 minutes for grok, 10 for dsh — but they all land.

## Was the stand-in the bottleneck?

No. The mock controlled end never exceeded **3%** of the 208 CPUs it had to itself, and was
under 1% for most runs. The measured cgroup sat at 80–87% throughout. Every ceiling above is
a fact about the 16-CPU machine or about the agent, not about the rig.

## Three things this found in coganchor

None of codex, kimi or grok could take an anchored turn at all before these. Each is a
separate way for the agent's own runtime to end up on the wrong machine, and each looks like
a backend problem until you look.

1. **Argv entries were read with `PATH_MAX` as the ceiling.** An argv entry is not a path;
   the kernel allows `MAX_ARG_STRLEN`. Codex prefixes every `bash -lc` with a preamble longer
   than 4 KiB, so what reached the target was the first 4096 bytes of the command — which
   parses, runs, and means something else. Codex reported every tool call as successful while
   nothing happened on the target.
2. **`#!/usr/bin/env node` sent the agent to the target.** `env` runs here and then searches
   `PATH` for the interpreter, one `execve` per directory. The first candidate names a path
   that does not exist here, which is not the agent's own by name — so it was run on the
   target, where the name resolves. Kimi's entire agent process ran on the target, read the
   target's `HOME`, and could not find the account it was signed in with. Codex escaped this
   only because its runtime is listed by hand.
3. **A binary in the agent's own state directory was kept local as a path but not as a
   program.** grok installs its native binary under `~/.grok/bin` and re-execs it; that exec
   went to the target, and grok reported `Not signed in`.

## Raw data

`data/ladder-*.jsonl` and `data/refine-codex.jsonl` hold one line per rung.
`data/stock-nofile/` holds the first climb, before the descriptor limit was raised.
