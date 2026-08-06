# 3 · Port a project

**An hour, mostly waiting.** You will use
[`official/rlar`](https://github.com/humanfia/flowverse) to move a module of a real C# project
to Python — one agent doing the work in a long conversation, a fresh reviewer reading what
actually landed, and the loop ending when the reviewer says it is finished rather than when the
worker says so.

::: tip Before you start
Finish the [Quickstart](/tutorials/quickstart). This tutorial uses DeepSeek Harness, so an API
key is enough; any two backends work.
:::

## The shape of work this is for

A port is not an optimisation. There is no number that goes down. What there is instead is a
long list of small decisions — this C# `Exception` return becomes a Python `None`, this
`TheoryData` table becomes a `pytest.mark.parametrize` — and one agent making them in sequence
does a better job than five agents making them independently, because consistency is most of
the work.

So the worker should remember everything. That is exactly what makes it a bad judge of its own
output: by the time it has written a thousand lines, it has also written a thousand lines of
reasoning about why each one is right.

`rlar` — **r**alph **l**oop with **a**ctor and **r**eviewer — separates the two:

```python
@flow
def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()          # one session, held for the whole run
    prompt = task
    while True:
        worked = working(prompt, suppress=True)
        if worked:
            review = agents.reviewer(REVIEW_PROMPT + task, suppress=True, schema=Review)
            if review is not None and review.done:
                print(review.notes)
                return
            prompt = (review.notes if review else "") or prompt
        time.sleep(5)
```

Three things are worth stopping on.

**`agents.actor.new()` is outside the loop.** One session, held across every round. The actor
remembers.

**`agents.reviewer(...)` is inside it.** Calling an agent rather than a session opens a fresh
conversation. Every review starts from a blank context, is handed the task again as if for the
first time, and reads the repository with `git diff` and `cat` rather than reading the actor's
account of it.

**`schema=Review`.** The reviewer does not answer in prose. It fills in a
[pydantic](https://docs.pydantic.dev/) model with two fields — `done`, a boolean, and `notes`,
the message the actor hears next. The loop ends on the boolean. A review that says the words
"this is done" in a paragraph does not end anything, which means the reviewer cannot end the
run by accident. See [Answers in a shape](/guide/shapes).

## Step 1 — get the project

[lip](https://github.com/futrime/lip) is a general package installer, written in C#, about
5,000 lines across `src/`.

```sh
git clone https://github.com/futrime/lip
cd lip
```

You are going to port one project out of its solution: `src/Golang.Org.X.Mod/`, which is a C#
port of Go's `golang.org/x/mod` — semantic version comparison and module-path validation. Two
files:

```sh
wc -l src/Golang.Org.X.Mod/*.cs tests/Golang.Org.X.Mod.Tests/*.cs
```

```console
  227 src/Golang.Org.X.Mod/Semver.cs
  408 src/Golang.Org.X.Mod/Module.cs
   68 tests/Golang.Org.X.Mod.Tests/SemverTests.cs
  198 tests/Golang.Org.X.Mod.Tests/ModuleTests.cs
```

This is a good first slice of a migration for three reasons. It has no I/O and no network, so
correctness is decidable. It has an existing test suite with tables of cases in it, so
"finished" is checkable. And the C# is itself a port, so the original Go is a second opinion
whenever the C# is unclear.

It also has a trap in it. Some methods in the C# are unfinished:

```sh
grep -c NotImplementedException src/Golang.Org.X.Mod/*.cs
```

```console
src/Golang.Org.X.Mod/Module.cs:18
src/Golang.Org.X.Mod/Semver.cs:7
```

Twenty-five of them. A literal port would reproduce twenty-five Python functions that raise
`NotImplementedError` and a test suite that carefully never calls them. The task has to say so.

## Step 2 — write the task down

```sh
cat > TASK.md <<'EOF'
Migrate this repository's `Golang.Org.X.Mod` project from C# to Python, as the
first slice of moving lip to Python.

Make a Python package at `python/golang_x_mod/` with:

- `semver.py`, the port of `src/Golang.Org.X.Mod/Semver.cs`
- `module.py`, the port of `src/Golang.Org.X.Mod/Module.cs`

and a pytest suite at `python/tests/` ported from
`tests/Golang.Org.X.Mod.Tests/`, keeping every case in the xunit tables.

Rules:

- The C# leaves some methods as `throw new NotImplementedException()`. The
  Python port must implement them, matching `golang.org/x/mod`, which is what
  the C# is a port of. Do not port the stub.
- Python names are snake_case; C# `Semver.MajorMinor` becomes
  `semver.major_minor`. Keep the behaviour identical, including what the Go
  original returns for malformed input (the empty string, not an exception).
- Where the C# returns an `Exception` rather than raising it, the Python
  returns `None` or an exception instance the same way — a caller must still
  be able to tell "this path is fine" from "this path is not".
- Do not weaken, delete or special-case a test to make it pass.
- `cd python && python -m pytest` must pass, and must be the check you run.

Set the package up so `python -m pytest` works from `python/` with no
installation: a `pyproject.toml` and a `conftest.py` if you need one.
EOF
git add -A && git commit -qm "the task"
```

The most important line in there is the last rule but one. A loop that ends when a suite is
green, run by an agent that can edit the suite, has an obvious shortcut in it. `rlar`'s
reviewer prompt already treats reward hacking as the thing it is most there to catch, and
saying it again in the task costs nothing.

## Step 3 — run it

```sh
export DEEPSEEK_API_KEY=sk-…
hmz exec -f official/rlar \
    -a dsh/deepseek-v4-pro:high \
    -a dsh/deepseek-v4-pro:high \
    "$(cat TASK.md)"
```

Two `-a` flags: the actor first, then the reviewer, in the order `rlar` declares them. Giving
both the same model is normal and is not the same as giving the job to one agent — what makes
the reviewer independent is that its conversation has never seen the actor's, not that it runs
a different model.

`rlar` also brings a **skill** with it: `skills/review-notes`, a Markdown file mounted onto
every session either agent opens, which says how to read a round of work and how to write the
review the actor is then handed. It lives inside the flow's own directory, so forking the flow
and editing that file is how you change the way reviews are written. See
[Skills](/guide/skills).

## Step 4 — watch a round go by

Each round is one long actor turn followed by a short reviewer turn. The reviewer's `notes`
become the actor's next prompt word for word, so the loop reads as a conversation between two
agents that never actually meet.

From another terminal:

```sh
cd lip/python && python -m pytest -q
```

Early on that fails because there is nothing there yet. Then it starts passing, and the
interesting part begins — the reviewer keeps saying `done: false` even with a green suite,
because a green suite is not the question it was asked. In this run it sent the actor back to
check the port against the upstream Go test vectors, which the C# tests do not all cover:

```console
match_path_major fails 0
match_prefix_patterns fails 0
checkpath family fails 0
```

That is the actor verifying its own work against a third source, because a reviewer that had
never seen its reasoning asked it to.

## Step 5 — see where it stopped

The run ends by itself when the reviewer sets `done: true`, and prints its final notes as it
goes:

```console
Port is complete and correct. python/golang_x_mod/semver.py implements
build/canonical/compare/is_valid/major/major_minor/max/prerelease/sort with
golang.org/x/mod semantics (invalid versions return "", comparisons follow Go
precedence). python/golang_x_mod/module.py implements every NotImplementedException
stub … python/tests/test_module.py contains all 105 CheckPathTests rows plus the 2
EscapePath and 8 SplitPathVersion InlineData cases, with the same assertions as the
C# xunit methods (I diffed the tables against the C# sources; they match exactly, and
no test was deleted, weakened or special-cased). … I additionally ran the Python
semver/module/pseudo functions against the upstream golang.org/x/mod test vectors …
and they all pass.
```

That is the reviewer's `notes` field, and it is worth reading closely. It cites row counts, it
says how it checked that the tables were not quietly shortened, and it names a third source it
verified against. None of that was in the flow's prompt — it is what the loop drove the actor
to do, round after round, by refusing to say `done`.

```sh
cd python && python -m pytest -q
```

```console
.........................................................    [100%]
389 passed in 0.47s
```

```sh
wc -l golang_x_mod/*.py tests/*.py
```

```console
    5 golang_x_mod/__init__.py
  846 golang_x_mod/module.py
  313 golang_x_mod/semver.py
  177 tests/test_module.py
   58 tests/test_semver.py
```

Twenty-five stubs implemented, 635 lines of C# and 266 lines of xunit turned into a Python
package with 389 passing cases.

Check that the growth is real rather than the suite having been made easier:

```sh
git diff --stat
git log --oneline
```

## Step 6 — read the run back

```sh
hmz trace collect
```

In [ui.perfetto.dev](https://ui.perfetto.dev) this run looks quite different from
[`flame_chase`](/tutorials/take-home). The actor is one long track — a single session, one
slice per turn, running the length of the trace. The reviewer is a row of short separate
tracks, one per round, each starting and ending inside a single round.

That picture is the flow. If you ever want to know what a flow does, collect a trace of it.

## What to change

**Point it at the next project.** `src/Lip.Core/` is the rest of the migration. The same
`TASK.md`, the same command, a new slice named in it. Landing a migration one verifiable
project at a time is the technique; the flow is only what runs it.

**Give the reviewer a different model.** The reviewer's job is to disagree. Two models that
fail differently disagree more usefully than one model twice.

**Change what "done" means.** Fork the flow — press **f** on it in `/flow`, or copy it out of
`~/.humanize/flowverses/official/flows/rlar/` — and edit the `description` on the `done` field.
That description is the whole instruction the backend is held to. Adding "and `ruff check`
passes" to it changes what ends the run. See [Answers in a shape](/guide/shapes).

## Next

Neither of the first two flows built anything from nothing. The third does: [Build a coding
agent](/tutorials/build-an-agent).
