# Falling back — `/fallback`

Two things go wrong, and they are not the same thing.

| What failed | What answers it |
| --- | --- |
| An **account**. A subscription runs out, a key is refused, a gateway answers 503. The model is fine and the CLI is fine. | Another account of the same backend, **inside the conversation that was running**: it is the backend's own and named by an id, so the next account picks it up mid-thought. That is said in [`/providers`](/user/providers). |
| A **place**. The model was retired this morning, the CLI will not start, the region has gone dark, the whole account is rate-limited rather than one request. No other account of that backend answers any of those. | Another place — another CLI, another account, another model. The conversation cannot come with it, because no backend takes another backend's session id. That is `/fallback`. |

`/fallback` is the layer between an agent and its accounts, and a place is three things and no
more:

```
CLI[@ACCOUNT]/MODEL
```

How hard the agent thinks, what it may reach for, whether it may search the web and which of a
flow's skills it carries are what that **agent** is, settled where it was made. They come
across the step unchanged. What failed was the place, so the place is what moves.

## Try it

```
/fallback
```

One page, one row per place, with `add` and `save` set below them. `a`, or the `add` row,
chooses the place that cannot run — the CLI, then one of its accounts, then one of the models it
says it runs — and then the place that takes its turns. Enter on a row asks the three things
there are to say about a step: where its turns go, how many times over a failed turn is taken
again first, and whether to be rid of it at all. Taking it away is the last row in there rather
than a key on the list — what the step says is what says whether it is wanted.

Nothing lands until the `save` row is chosen, **shift+enter** (or **ctrl+j**) is pressed, or the
menu is left and saving confirmed — as on every menu.

## From Python

The steps are `Hmz().fallbacks`, which is the object the page itself is drawing — so a step
written from a script is a step the next run walks, and a step written at the prompt is one a
script reads back:

```python
from hmz.sdk import Hmz

falls = Hmz().fallbacks

falls.points("claude/claude-opus-5", "codex/gpt-5.6-sol")
falls.retrying("claude/claude-opus-5", 3, "exponential", 90)
falls.all()
falls.clear("claude/claude-opus-5")
```

An account is part of which place this is, after an `@`. `claude@work/claude-opus-5` and
`claude@key/claude-opus-5` are two places rather than one written twice, the account being one
of the three things a turn can fail for having named:

```python
falls.points("claude@work/claude-opus-5", "codex@key/gpt-5.6-sol")
```

`chain` answers the whole walk rather than the one step, since the walk is what a failed turn
actually does:

```python
falls.chain("claude@work/claude-opus-5")
# ['claude@work/claude-opus-5', 'codex@key/gpt-5.6-sol', 'dsh/deepseek-v4-flash']
```

What is written against one place on its own is `tried`, and the waits there are to choose from
are `policies`. All of them are [SDK › Fallbacks](/reference/sdk#fallbacks).

## Trying again

How many times over a failed turn is taken again is written here rather than on the account,
because it is a thing about the place a turn runs at rather than about the credentials it runs
with. One row says both, both being answers to the one thing that went wrong.

| | |
| --- | --- |
| `tries` | how many goes beyond the first; `0` is a failed turn that is a failed turn |
| `policy` | how long to wait between them — the ladder below |
| `timeout` | the longest the trying again may go on for, or `0` for as long as the tries take |

Nothing is retried unless you say so: a prompt the model refused is the same refusal every
time, and only you know which of your places fails the other way. The waits themselves are the
ones everybody uses, the first being one second and no single wait longer than a minute however
far the backoff has climbed:

| Policy | The waits before the 2nd, 3rd, 4th… try |
| --- | --- |
| `none` | none at all |
| `constant` | 1s, 1s, 1s |
| `linear` | 1s, 2s, 3s |
| `exponential` | 1s, 2s, 4s, 8s |
| `exponential-jitter` | anywhere up to the exponential wait — the default, and what to reach for when several agents are failing at once: full jitter is what keeps a flow's agents from all coming back on the same second |
| `fibonacci` | 1s, 1s, 2s, 3s, 5s |

The time the retrying is given is checked **before** a wait rather than after it, so a turn is
never started knowing the time it was given is already spent.

## What a turn actually does

In order, and it stops at the first thing that works:

1. **Takes the turn.** If it lands, none of the rest happens — nothing is looked up, and no
   stand-in is started.
2. **Works out what went wrong**, out of what the CLI said, how it exited and — for the one
   backend that keeps it there — its own log. See [what went wrong](#what-went-wrong): each
   kind gets a different answer, and the three steps below are what that answer is made of.
3. **Tries again at the same place**, as many times and with whatever wait the step says, plus
   whatever the failure itself asks for. Nothing is retried unless you asked for it, except
   the few kinds where another go *is* the answer.
4. **Walks the account chain**, in the conversation that was running. An agent that has moved
   stays moved: the account that went down is not one to try again each turn. Skipped for the
   kinds no account answers.
5. **Walks the chain of places**, once there is no account left. The turn is taken in a new
   session of an agent at the next place, configured exactly as the agent it left — carrying
   its effort, its permission rung, the skills the flow gave it and the
   [callbacks](/weaver/tools) the agent is offering.

## What went wrong

Two things go wrong is where this page started, and it is truer than that: seven do, and each
of them takes a different answer. A rate limit wants a long wait and then another account. A
key that was refused wants no wait at all — it is refused a minute later too — and the account
chain is the whole of the answer. A model that was retired wants neither, every account of that
CLI being offered the same catalogue. Retried identically, which is what they all were before
this, three of those are a flow that makes no progress and one is a flow hammering a service
that has just asked it to stop.

| What happened | What a turn does about it |
| --- | --- |
| **Too many requests** — HTTP 429, a quota spent, `RESOURCE_EXHAUSTED`, `overloaded` | Waits at least 30 seconds, then walks the account chain. The account is spending too fast; the next one is not. |
| **Refused the credentials** — 401, 403, a login that expired, a model this account is not entitled to | Nothing is tried again here. Walks the account chain, and says that the account it left needs signing in. |
| **No such model** — 404, a model retired, one the service says does not exist | Nothing here and no account either: they are all offered the same catalogue. Goes straight to the next **place**. |
| **Its own store was busy** — opencode's `database is locked` | Three goes here, a second apart. Two turns of it are sharing one SQLite database, and that clears itself. |
| **Lost the connection** — `ECONNRESET`, `EPIPE`, a gateway that went away | Reopens the transport, resumes the conversation by its id, and goes again. What was lost was the socket, not the session. |
| **Was killed rather than answered** — a signal, an out-of-memory kill | Reopens, waits a second, and says what killed it. The machine may be out of memory. |
| **Is not installed here** — nothing to run, or nothing that would start | A failed turn that says which line installs it, and goes to the next place. |
| **Anything else** | Exactly what a failed turn has always done: the goes the step asked for, the step's own wait, and then the account chain. |

Every one of those narrates itself while it happens, so a run that is recovering does not read
as a run that has hung:

```
claude is rate-limited (this account has spent its quota; another one, or a wait, is what
answers it); trying again in 30s (1 of 1)
claude is rate-limited (…); carrying on as work
```

Whatever is watching the agent sees those as `notice` events; where nothing is watching, they
go on stderr beside the progress the backend itself puts there. A turn told to wait half a
minute is exactly the turn you would otherwise watch do nothing at all — which is why they are
their own kind rather than tool calls, and why [`/details`](/user/details) does not hide them
with the working.

A backend that already knows which kind it was says so itself and is believed. Nothing guesses
at a message when the CLI has named the failure.

Antigravity is the exception that needed one: it exits with `Agent execution terminated due to
error` and puts the HTTP status in `~/.gemini/antigravity-cli/log/`. Its log is read when its
streams say nothing, which is how a rate-limited turn of it stops reading as a turn that simply
failed.

The flow sees one turn either way. The events come back through the session it asked, between
the same `begins` and `ends`, and the transcript says where it was picked up.

Nothing is built until it is needed: the agent standing in is made the first time a turn has
nowhere left to go, since a chain of four places all started when the run was would be three
CLIs held open for a failure that never came.

## What it will not do

- **Carry the conversation across the move.** Step 4 opens a session on the other side, and
  the agent arrives reading the repository rather than a history. It is lost once rather than
  every turn, though: that session is held for as long as the one that asked for it, so a
  stateful loop that moved is one conversation on the other side and not one a round.
- **Come round on itself.** A chain ends at the second sight of a place, and a place cannot
  fall back to itself — either would be a turn that never ran out of places to go.
- **Fork.** One place has one place to go. Writing a step again says the new thing and not
  both.
- **Move a setting the CLI taking over cannot be told.** An agent told not to search the web
  does not fall back to a CLI with no way of being told: a setting quietly ignored would be a
  setting that lies, so the turn fails as it failed before anybody wrote a step down. The
  same goes for what is in front of the model rather than configured on it — a turn taken
  with the flow's own [callbacks](/weaver/tools) offered does not move to a backend that has
  no way of being given one.
- **Rescue a turn that failed for a reason another try cannot fix.** A prompt longer than the
  context window is that long at the next place too. Those are `Unrecoverable`, and are
  [taken once](/reference/agents#when-an-account-goes-down) whatever any chain says.

## See also

- [Providers](/user/providers) — the accounts an agent runs as, and the chain between them
- [Unattended runs](/user/unattended) — where having somewhere to fall back to earns its keep
- [TUI › `/fallback`](/reference/tui#where-a-turn-goes-when-it-cannot-be-taken) — the page itself
- [SDK › Fallbacks](/reference/sdk#fallbacks) — the same steps as one object
