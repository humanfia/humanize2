# Exporting a run — `/export`

`/export` packages the whole run up as one archive:

```
.humanize/<run>.epic.tar.gz
```

Reach for it when something went wrong and you want somebody else to be able to see it. The
screen was never the run: the turns went to a coding agent that wrote its own log, under an id
of its own, in a directory of its own, and what humanize keeps is a link pointing at that log.
A link is worth nothing on any machine but yours. An export follows every one of them and
carries what is behind it.

## Try it

Run `/export`, then look at what it names:

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
| `transcript.md` | the screen, as the text it was written as rather than the rows it was drawn as — only for an export from the prompt |
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

**The transcript is the whole screen**, everything drawn since the interface opened or since
the last `/clear` — not the tail of it, so an export of a nine-hour run is the whole of it.
Pressing **tab** steps between conversations and draws each into the same transcript, so it
holds every conversation you have read rather than only the one showing now; see [Many
conversations at once](/user/conversations). Whether tool calls and thinking are in it depends
on what [`/details`](/user/details) is showing. And it goes in as it was written, not as it was
wrapped: a line too long for your terminal is drawn over four rows and exported as the line, so
a break in the file is a break that was really there.

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
  same taking-out [`hmz flowverses`](/weaver/flowverses) does when it prints where a private
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

## A run that is not the one on the screen

[`/epics`](/user/tracing#what-a-run-writes-down) lists every run of this directory, newest
first. Enter on one opens what there is to do with it, and **export it** is there beside
collecting its trace. Use that for a run from last week: there is no transcript in it, because
what is on your screen is not that run.

From a command line, [`hmz export`](/reference/cli#hmz-export):

```sh
hmz export                                  # the last run here
hmz export 20260809T0144                    # a run of this directory, by name
hmz export -o /tmp/for-the-issue.tar.gz     # somewhere to attach it from
```

It prints where the archive landed, what is in it and how big it came out:

```console
$ hmz export
/home/you/code/.humanize/20260809T014455.212Z-9f21ab.epic.tar.gz of 20260809T014455.212Z-9f21ab: 3 sessions, 4 logs, 812 kB
```

The archive is named for the run rather than for the moment you asked, so exporting the same
run twice replaces the first — the second one is the first plus whatever has happened since.

## Copying instead

For a few lines, the mouse is faster and leaves no file:

| Gesture | What it takes |
| --- | --- |
| **drag** | Everything between where you pressed and where you let go. |
| **double click** | The word under it — so a path or an id comes whole. |
| **triple click** | The whole line, however many rows it was drawn over. |

The status line says `copied` for a moment. That is the only sign there is.

This copies what was written rather than what was drawn, exactly as the transcript in an export
is. The box the interface opens with is a picture rather than a line. Dragging across it gives
you its rows as they are drawn, borders and all.

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
| `/export`, `hmz export` | the whole run: every record, every session log in full, the transcript, and a manifest | `.humanize/<run>.epic.tar.gz` |
| [`hmz trace collect`](/user/tracing) | every session of every agent as one timeline, with tool input and output | `traces/<datetime>.trace.json`, in the run's own epic |
| the epic itself | the same records, with the session logs as links into the backends' own homes | `~/.humanize/epics/<workspace>/<run>/` |
| the clipboard | whatever you dragged across | your machine's clipboard |

A trace is for reading a run yourself, on the machine it ran on. An export is for sending it
to somebody who was not there — it holds the trace as well.

## See also

- [Tracing](/user/tracing)
- [Reporting](/user/reporting)
- [The runs of this directory](/user/tracing#what-a-run-writes-down)
- [`hmz export`](/reference/cli#hmz-export)
- [TUI › Selecting and copying](/reference/tui#selecting-and-copying)
