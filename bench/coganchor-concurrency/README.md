# How many anchored agents fit on one machine

A rig for the one question humanize deliberately refuses to answer for you. [Many turns at
once](../../docs/features/concurrency.md) says it plainly:

> **How wide it runs is a question about the machine**, not about this library, so nothing
> caps it.

This measures the machine. It runs real `hmz`, with real coganchor interception, against a
mock controlled end, and climbs the concurrency ladder until something stops behaving.

## Table of Contents

- [What is real and what stands in](#what-is-real-and-what-stands-in)
- [Install](#install)
- [Usage](#usage)
- [What a rung means](#what-a-rung-means)
- [Results](#results)

## What is real and what stands in

| | |
| --- | --- |
| **Real** | `hmz` itself: the backends, the argv they build, the anchor, the ptrace supervisor, the mirror, the protocol, and the agent CLIs — `claude`, `codex`, `grok`, `kimi`, `dsh` — as installed. |
| **Stood in for** | The target's *data*: `hmz anchor serve` really serves, over a real TCP channel, but the workspace it serves is synthetic. |
| **Stood in for** | The model provider: one local server answering the Anthropic Messages, OpenAI Responses and OpenAI Chat shapes with a scripted turn. |

Both stand-ins run **outside** the constrained cgroup, deliberately. In production the target
is another machine and the model is somebody else's API, so neither belongs in the budget
being sized. `ramp.py` records the target's own CPU alongside the measurement, so a run can
say whether the stand-in was anywhere near its own limit — if it was, the ceiling found is a
fact about the rig rather than about the machine.

Every backend is given the **same** scripted turn — three shell commands, each reading a
seeded file and appending to another — so the numbers compare backends rather than prompts.
A turn counts only if the agent said the sentence the script ends on *and* its work is on the
target, which is what distinguishes a turn that ran from one that merely reported.

## Install

Needs `uv`, the five agent CLIs on `PATH`, and `sudo` for the cgroup:

```sh
npm install --global @xai-official/grok @moonshot-ai/kimi-code @deepseek-ai/dsh
```

## Usage

```sh
bash backdrop.sh start                 # stand-ins up, outside the cgroup
bash ladder.sh claude                  # climb until two rungs in a row misbehave
RUNGS="256 320 384" APPEND=1 bash ladder.sh codex
bash refine.sh codex 208 224 240       # narrow a ceiling, keeping stderr
python3 summarise.py                   # the table
bash backdrop.sh stop
```

`run_one.sh <backend> <n>` is one rung on its own. The cgroup is the whole of the constraint:

```sh
sudo systemd-run --scope -p AllowedCPUs=0-7,112-119 -p MemoryMax=64G -p MemorySwapMax=0 ...
```

`AllowedCPUs` names eight physical cores **and their hyperthread siblings** — sixteen logical
CPUs, which is what a 16-vCPU machine is, and what `nproc` reports inside the scope. Naming
`0-15` instead would quietly hand the benchmark sixteen *physical* cores.

## What a rung means

One rung is N agents in one `hmz` process, one session each, one turn each, all going at
once — the fan-out shape the concurrency guide describes, aimed at an anchor. Each agent gets
a workspace of its own, mirrored from a copy of its own on the mock target.

A rung is **normal** when every agent finished, said the sentence, and left its work on the
target. The ladder stops after two consecutive rungs that are not.

## Results

See [RESULTS.md](RESULTS.md).
