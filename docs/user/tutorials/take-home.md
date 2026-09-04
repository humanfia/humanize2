# Beat a benchmark

**An hour of your attention, several of the machine's.** You will point
[`official/flame_chase`](https://github.com/humanfia/flowverse) at Anthropic's open performance
take-home and watch two agents take turns driving a kernel from 147,734 simulated cycles down
past 1,790.

::: tip Before you start
Finish the [quickstart on the home page](/#run-a-flow). You need two backends logged in — this
tutorial uses Claude Code and Codex, and any two will do, including the same one twice.
:::

## The shape of work this is for

Some problems have a number attached. Optimisation is the obvious one: the measurement is cheap
to take, and every attempt is either better than the last or it is not. For that shape the
useful thing an agent can do is try something, measure, and write down what it learnt — not
reason about its own earlier reasoning until the context window is a record of ideas that did
not work.

`flame_chase` is eighteen lines long and does exactly one thing about that:

```python
@flow
def run(agents: tuple[Agent, Agent], task: str) -> None:
    while True:
        for agent in agents:
            agent(task, suppress=True)  # each agent reads the repository, not a history
            time.sleep(5)
```

Two agents, alternating. Each turn opens a **session** — a conversation with the model — that
has never seen anything, so what passes between them is not a transcript but the repository:
the code as it now stands, and whatever notes the last turn left behind. The repository is the
memory, and it is a memory a measurement has already checked.

## Step 1 — get the problem

```sh
git clone https://github.com/anthropics/original_performance_takehome
cd original_performance_takehome
```

Anthropic's original take-home, opened to the public: you optimise a kernel for a simulated
VLIW SIMD machine. `problem.py` is the simulator, `perf_takehome.py` is the kernel you are
allowed to change, and `tests/submission_tests.py` measures it.

Measure the starting point:

```sh
python tests/submission_tests.py
```

```console
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  147734
Speedup over baseline:  1.0
```

147,734 cycles, and eight of the nine tests failing. Each failing test is a threshold somebody
already reached:

| Test | Threshold | Who |
| --- | --- | --- |
| `test_kernel_updated_starting_point` | 18,532 | where the two-hour version of the take-home starts you |
| `test_opus4_many_hours` | 2,164 | Claude Opus 4, many hours in a test-time compute harness |
| `test_opus45_casual` | 1,790 | Claude Opus 4.5 in an ordinary Claude Code session — about the best human result in two hours |
| `test_opus45_2hr` | 1,579 | Claude Opus 4.5, two hours in the harness |
| `test_sonnet45_many_hours` | 1,548 | Claude Sonnet 4.5, many more than two hours |
| `test_opus45_11hr` | 1,487 | Claude Opus 4.5, 11.5 hours |
| `test_opus45_improved_harness` | 1,363 | Claude Opus 4.5, an improved harness |

## Step 2 — write the task down

A loop runs the same prompt for hours, so the prompt is worth more care than a chat message.
Put it in a file:

```sh
cat > TASK.md <<'EOF'
Make `perf_takehome.py` run the kernel in as few simulated clock cycles as
possible, without breaking it.

The rules, from the repository's own Readme:

- Do not touch anything under `tests/`. `git diff origin/main tests/` must stay
  empty. A solution that edits the tests is not a solution.
- Do not fake a speedup. Multicore is disabled on purpose; `N_CORES` stays 1.
  Nothing may be stubbed, special-cased for the test inputs, or made to skip
  work the kernel is supposed to do.
- `python tests/submission_tests.py` is the only measurement that counts. It
  prints CYCLES and the thresholds passed.

Where you are starting from: 147734 cycles.

Each turn: measure first, make one substantial optimisation, measure again, and
keep it only if the cycle count went down and the tests still pass. Write what
you tried and what it measured into NOTES.md, so whoever takes the next turn
does not repeat it.
EOF
git add -A && git commit -qm "the task"
```

Three parts of that prompt are doing real work.

- **The rules against cheating.** The repository's own Readme warns that none of the sub-1,300
  submissions on the first day were valid — in each case a model had edited the tests. An agent
  running unattended with permissions disabled will find that shortcut, so name it, and name
  the command that proves you did not take it.
- **Measure, change, measure.** Without it a turn can end believing it made things faster.
- **`NOTES.md`.** Each turn starts from nothing, so anything worth carrying has to be written
  to a file. Ask for that explicitly and the agents build themselves a lab notebook — which is
  what makes an alternating loop worth more than one long session.

## Step 3 — start the loop

```sh
hmz exec -f official/flame_chase \
    -a claude/claude-opus-4-8:high \
    -a codex/gpt-5.6-sol:high \
    "$(cat TASK.md)"
```

Two `-a` flags because `flame_chase` drives two agents, taken in the order you write them: the
first turn goes to Claude Code, the second to Codex, and round it goes.

The first time you name `official/…`, humanize fetches the [official
flowverse](/weaver/flowverses) — a git repository of flows — into `~/.humanize/flowverses/`.

::: warning `flame_chase` never stops itself
There is no exit condition in those eighteen lines, because "as few cycles as possible" has no
end. Stop it with **ctrl+c** at a command line, or **ctrl+c** twice in the interface, when the
curve flattens.
:::

## Step 4 — watch the number, not the transcript

Leave the run going and measure from another terminal:

```sh
cd original_performance_takehome
python tests/submission_tests.py 2>&1 | grep -E "CYCLES|Speedup" | tail -2
```

The transcript tells you what an agent *believes*; the test tells you what is true.

::: warning You are measuring a working tree somebody is editing
Run that command in the middle of a turn and you may catch the kernel halfway through a
rewrite, with `test_kernel_correctness` failing. That is not the run going wrong. Measure again
a minute later, when the turn has landed.
:::

After about half an hour on this machine, both agents having had several turns:

```console
CYCLES:  1770
Speedup over baseline:  83.46553672316384
```

83× faster than the starting point, and past `test_opus45_casual` — the threshold Anthropic's
own Readme puts at roughly the best human result in two hours.

Read what they wrote themselves:

```sh
head -30 NOTES.md
```

```console
# Optimization notes for perf_takehome.py

## Machine model (from problem.py)
- VLIW bundle = `{engine: [slots]}`. All slots in a bundle run in the SAME cycle.
  Writes take effect at END of cycle (reads see old values). A bundle with any
  non-debug slot costs 1 cycle. Debug-only bundles cost 0.
- Slot limits/cycle: alu 12, valu 6, load 2, store 2, flow 1, debug 64.
…
## Bottleneck analysis
- Total gathers (node_val) = rounds*batch = 16*256 = 4096 scalar loads. At 2
  loads/cycle that's a HARD floor of ~2048 cycles for the naive per-lane gather.
```

That file was not there when the run started. It is what the loop has instead of a memory, and
it is why turn twelve is not turn one again.

## Step 5 — check that it did not cheat

Before you believe any of the above:

```sh
git diff origin/main tests/
```

Empty output means the tests are exactly as they shipped. If it prints a diff, the number is
worthless — throw it away, put the rule more bluntly in `TASK.md`, and start again.

```sh
python tests/submission_tests.py
```

`test_kernel_correctness` is the one that matters most. A fast kernel that computes the wrong
thing is not a result.

## Step 6 — read the run back

```sh
hmz trace collect
```

Open the file it names in [ui.perfetto.dev](https://ui.perfetto.dev). Each agent is a process
and each of its turns is a track, so the two appear as two lanes taking it in turns. Click any
slice to see the prompt, the reasoning, the tool call and the tool output that produced it.

For a run measured in hours, this is where you find out which turn actually moved the number —
and which four turns after it were an expensive way of confirming the fifth.

## What to change

- **Stop when the curve flattens.** Two turns in a row that measure the same is the signal.
  Ratchet it by editing `TASK.md` to name the new floor, and start again.
- **Change who is in the loop.** `flame_chase` takes any two agents. Two models that are wrong
  in different ways beat two copies of the stronger one, because each turn starts fresh and so
  inherits the other's blind spots rather than its own.
- **Raise the effort.** `:high` is deliberately not the hardest setting. `:max` costs more per
  turn and is worth it on the last stretch, when the easy wins are gone. See
  [Efforts](/user/efforts).

## Next

The opposite arrangement — one agent that remembers everything, and a reviewer that remembers
nothing: [Port a project](/user/tutorials/port-a-project).
