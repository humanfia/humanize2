# Exporting a run

An export packages one whole run up as one archive:

```
.humanize/<run>.epic.tar.gz
```

Reach for it when something went wrong and you want somebody else to be able to see it. The
screen was never the run: the turns went to a coding agent that wrote its own log, under an id
of its own, in a directory of its own, and what humanize keeps is a link pointing at that log.
A link is worth nothing on any machine but yours. An export follows every one of them and
carries what is behind it.

## Try it

[`/epics`](/user/tracing#what-a-run-writes-down) lists every run of this directory, newest
first. Enter on one opens what there is to do with it, and **export it** is there beside
collecting its trace — a run is exported where the runs are, rather than by a command about
whichever one your screen happens to be showing. Then look at what it names:

```sh
tar tzf .humanize/20260809T014455.212Z-9f21ab.epic.tar.gz
```

## What is in it

Everything the run wrote down about itself, and everything its sessions were logged to:

| | |
| --- | --- |
| `epic.jsonl` | what happened, a line at a time: which flow, on what, by which agents, which session each of them opened, and how it ended |
| `epic.<flow>_<id>.jsonl` | the same again for every flow this run [called](/weaver/calling-flows) — one run, however many flows it took |
| `state.json` | what a [resumable](/user/resuming) flow left behind |
| `profile.jsonl` | the programs it ran, for a [profiled](/user/tracing#profiling-a-run) run |
| `traces/…` | every [trace](/user/tracing) gathered of it |
| `sessions/<session>/…` | the backends' own logs, **as their contents** rather than as the links the run keeps — one directory per session, named for the agent, the CLI, the account and the id |
| `transcript.md` | a screen that went with the run, as the text it was written as rather than the rows it was drawn as — only where one was [handed in from Python](#from-python) |
| `manifest.json` | what this was: see below |

The manifest is what makes the rest readable by somebody who was not there — humanize's own
version, Python's and the machine's; the flow, the task and how it went; one line per agent
saying the CLI, the model, the effort, what it was allowed and the account **by name**; the
workspace and the commit it is on if it is a git repository; and, per backend, the version it
says it is and the SHA-256 of the executable that actually took the turns. These CLIs move
weekly, so a bug is a bug in a build.

It also says the shape the run ran in: every flow it called, however deep, each naming the
record that called it, and every session naming the record it was opened in. A flow called
twice is two records and two conversations, so the flow name alone would not tell you which of
them a log belongs to.

**A session with no log says so.** opencode and mimocode keep their sessions in a database of
their own and write nothing humanize can read; a bundle that answered that with an empty
directory would read exactly like a bundle that lost the logs. The manifest says which it is,
against that session and against the backend.

**No screen goes in by itself.** A run out of the list may be a week old, and what is on your
screen now is not it — a bundle carrying somebody else's transcript would be a bundle saying
something untrue. Something driving humanize from Python can hand one in, and then it goes in
as it was written rather than as it was wrapped: a line too long for a terminal is drawn over
four rows and written out as the line, so a break in the file is a break that was really there.

## What is never in it

An export is you sending your own run, on purpose, so what it carries is yours: the task, the
prompts, what the agents said, whatever of your files they wrote into a log. That is the
opposite of what [reporting](/user/reporting) sends on humanize's initiative, and it is meant
to be — a bug report without the run in it is a report nobody can develop against.

A credential is not yours to send. Every byte of every file in the archive is scrubbed on the
way in:

- **The variables your accounts run turns with**, by value. An [account](/user/providers) is
  `ANTHROPIC_AUTH_TOKEN` and a base URL and whatever else that way asked for, and no pattern
  knows what you pasted — so every value of every account here is struck out wherever it
  appears, the endpoint among them. The address of your private gateway is as much yours as
  the key that opens it. Less what the run itself says it ran: an account may hold the model
  to ask for, and a bundle with the model name taken out of it says nothing about what ran.
- **Keys in the shapes the vendors mint them**: `sk-…`, `sk-ant-…`, `ghp_…`, `AIza…`, a JWT.
- **Whatever is signed into a URL** — a user, a password, or a token in a query string. The
  same taking-out [`/flowverses`](/weaver/flowverses) does when it shows where a private
  place came from.
- **Anything a log named as a token, a secret, a key or a password.**

What stands in the place of each is `[redacted]`, one word, so you can read a bundle for what
was struck as easily as for what was not. What a turn cost is left alone: `input_tokens` is how
these backends write down the bill, and a bundle with those numbers taken out is one nobody can
read a bill out of.

An archive also records who wrote it. This one does not: no owner, no group, no login name.
The file itself is `0600` — readable by you and nobody else, since what is in it is your
prompts and your agents' output and a shared machine is a shared machine.

::: tip Look before you send
It is your run. `tar xzf` it somewhere and read it — that is the point of it being one archive
of plain files rather than something only humanize opens.
:::

## Where it went

[`/epics`](/user/tracing#what-a-run-writes-down) lists every run of this directory, newest
first. Enter goes **into** the run under the cursor — which says where it is written down —
and **export it** is there. Use that for a run from last week: there is no transcript in it,
because what is on your screen is not that run.

**It gathers the trace too.** Collecting a trace was a row beside this one, and what it wrote
went into `traces/` — which an export carries anyway. So **export it** gathers a
[trace](/user/tracing) of **that run's** sessions first and packs it, and the line it reports
says what went in the trace as well as how big the archive came out:

```console
/home/you/code/.humanize/20260809T014455.212Z-9f21ab.epic.tar.gz · 812 kB · 3 sessions, 412 slices
```

Which is the point of a bundle: the person you send it to can open the timeline rather than
having to gather one themselves.

It says where the archive landed and how big it came out under the list, and again in the
transcript, so a bundle made an hour ago is still found by reading back rather than by hunting
through a directory.

The archive is named for the run rather than for the moment you asked, so exporting the same
run twice replaces the first — the second one is the first plus whatever has happened since.

## From Python

They are still two calls, and the one export in the menu is both of them:

```python
from hmz.sdk import Hmz

Hmz().epics.traced(epic)                                     # into the run's own traces/
Hmz().epics.bundled(epic, output="/tmp/for-the-issue.tar.gz")
```

`epic` is the run's own directory — the path drawn at the top once you are inside the run on
`/epics`, and what [`Hmz().epics.all()`](/reference/sdk#epics) hands back. An output that is a
directory is written into under the run's own name, and no output at all is `.humanize/` beside
wherever this is running. There is a `transcript=` as well, for a screen of your own that went
with the run; nothing in the interface passes it, a run out of the list not being the run on
your screen.

## Copying instead

For a few lines, the mouse is faster and leaves no file:

| Gesture | What it takes |
| --- | --- |
| **drag** | Everything between where you pressed and where you let go. |
| **double click** | The word under it — so a path or an id comes whole. |
| **triple click** | The whole line, however many rows it was drawn over. |

The status line says `copied` for a moment. That is the only sign there is.

This copies what was written rather than what was drawn. The box the interface opens with is a
picture rather than a line. Dragging across it gives you its rows as they are drawn, borders and
all.

**It works over ssh.** The interface has the mouse, so your terminal never sees the drag. What
is selected goes out as OSC 52, the escape a terminal takes for its clipboard. It therefore
reaches the clipboard of the machine you are sitting at, not the one the flow is running on.
Some terminals want it turned on: `set-clipboard on` in tmux, `Allow reporting` in VTE-based
ones. Holding **shift** while dragging is your terminal's own selection instead. It copies the
screen as drawn, wrapping and all.

Changing the width of your terminal lets go of whatever was selected. The lines wrap again, so
a selection made against the old wrapping is dropped rather than left pointing a line or two
off.

## The ways of keeping a run

| | What it holds | Where |
| --- | --- | --- |
| **export it** on a run of `/epics` | the whole run: every record, every session log in full, every [trace](/user/tracing) gathered of it, and a manifest | `.humanize/<run>.epic.tar.gz` |
| the trace **export it** gathers on its way in | every session of that run as one [timeline](/user/tracing), with tool input and output | `traces/export.trace.json`, in the run's own epic |
| the epic itself | the same records, with the session logs as links into the backends' own homes | `~/.humanize/epics/<workspace>/<run>/` |
| the clipboard | whatever you dragged across | your machine's clipboard |

A trace is for reading a run yourself, on the machine it ran on. An export is for sending it
to somebody who was not there — and a bundle carries whatever traces the run has, which is why
**export it** gathers one first rather than leaving the two to be asked for separately.

## See also

- [Tracing](/user/tracing)
- [Reporting](/user/reporting)
- [The runs of this directory](/user/tracing#what-a-run-writes-down)
- [SDK › Epics](/reference/sdk#epics) — the same bundle from Python
- [TUI › Selecting and copying](/reference/tui#selecting-and-copying)
