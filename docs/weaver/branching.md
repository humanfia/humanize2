# Branching a conversation

A session can be **forked**: a second conversation carrying this one's history, going its own
way from the moment it was made. Reach for it when a conversation has got somewhere expensive
and you want to try more than one way out of it.

## Try it

```python
session = agent.new()
session("read src/ and tell me what this service does")

careful, quick = session.fork(), session.fork()
careful("now rewrite the retry logic, and mind the timeouts")
quick("now rewrite the retry logic, fastest thing that works")
```

Both children start out knowing everything `session` knew — the hour of reading is paid for
once. What either of them is told afterwards is its own: the original is untouched, and the two
never see each other's turns.

## What the child is

The CLI's own fork does the carrying. There is no transcript replayed into a fresh session and
no context handed between two processes: the backend loads the conversation it already has and
calls what follows a session of its own.

So the child is a conversation in every way a run counts one:

| | |
| --- | --- |
| **Its own id** | `child.id` is the backend's id for the new conversation, not the old one |
| **Its own spending** | `child.spent()` starts at nothing; nothing spent on the parent counts twice |
| **Its own place** | it is in `agent.opened` and in the run's record, beside the one it came from |
| **Its own future** | turns of one are not turns of the other |

What the conversation was *running by* comes across, since that is what the child continues:
the effort it had got to, the skills it is carrying now, the callbacks it is offering. What the
agent was set up with is the agent's and was never the session's.

A fork costs nothing until it is used. The backend call happens on the child's first turn, so
`[session.fork() for _ in range(8)]` is eight objects and no backend calls.

## Use the child before the parent moves on

Because the fork *is* the child's first turn, the branch point is where you called `fork()` —
and it can only stay there if the parent has not been given another turn in between:

```python
child = session.fork()
session("carry on here")        # the parent moves on
child("and here")               # RuntimeError: fork it again to branch from where it is now
```

That is refused rather than done, because the alternative is a child branched from somewhere
nobody chose which reads exactly like the branch that was asked for. Fork again when you want
the newer boundary. Driving one child does not move the parent, so the two-children pattern
above is unaffected.

## Which backends can

| Backend | |
| --- | --- |
| Claude Code | `--fork-session` |
| Codex | `thread/fork` |
| Grok Build | `--fork-session` |
| Kimi Code | `kimi fork` |
| opencode, mimocode | `run --fork` |
| pi | `--fork` |
| Qwen Code | `--fork-session` |
| A CLI you added | ACP's `session/fork` |
| Antigravity, Cursor, DeepSeek Harness, ZCode | no |

On a backend without one, `fork` raises `NotImplementedError`. It is not answered with a second
handle on the same conversation: two loops each continuing what they take to be their own is a
run nothing downstream could explain.

Ask first rather than catching it:

```python
if session.forks:
    other = session.fork()
```

`session.forks` is a fact about the backend, read out of the one place a fact about a CLI is
written down. A CLI you added yourself answers `True`, because the protocol has the call — an
agent that has not implemented it refuses where the fork is asked for instead.

## When there is nothing to fork

```python
session = agent.new()
session.fork()   # RuntimeError: session has not run a turn yet
```

A conversation that has got nowhere has no history to carry, so it is one to open rather than
one to fork. Open a second session instead.

## Not `agent.clone`

The two are halves of one idea, which is why they are not one word:

| | |
| --- | --- |
| `agent.clone()` | another **agent**, set up like this one, which has held no conversation |
| `session.fork()` | another **conversation** of this one agent, which knows what this one knows |

An agent is structure, so cloning one copies the structure and none of the history. A session
is history, so forking one copies the history and none of the structure. See
[Concepts › Agent](/user/concepts#agent).

## Reading it back afterwards

The run writes down which conversation a child was forked from, because the backend's own log
does not: it shows only a session that opened on an agent already knowing things. So a
[trace](/user/tracing) of the run reads back as the branches it actually ran in.

## See also

- [Many conversations at once](/user/conversations)
- [Many turns at once](/weaver/async-flows), for driving both branches together
- [Worktrees](/weaver/worktrees), for branching the files rather than the conversation
