---
pageClass: hmz-feature
---

# Every run has an allowance

A run can be given an **allowance** — how many hours it may take, how many millions of output
tokens it may come out with, how many dollars it may cost — and when one of them is reached,
the run stops. Every flow has one, whether or not the flow says anything about it.

```yaml
# budget.yaml
budget:
  hours: 6
  tokens: 10
  dollars: 50
```

```sh
hmz exec -f ralph_loop -a claude/MODEL:high -c budget.yaml "$(cat TASK.md)"
```

Whichever of the three is reached first is the one that stops it. Each is a non-negative
number and **0 is no cap on that dimension**, so an allowance with nothing named in it is a run
under nothing at all.

## Why three, and why these three

**Hours** are wall clock, and they are the only dimension that moves whether or not anything is
being spent. That is what makes them the one that stops a loop whose every turn is failing: a
turn that could not run spends no tokens and costs no money, so a refused account would go
round on the same failure for as long as it was left.

**Tokens** are millions of *output* tokens. Output because that is what the work is — the input
of a turn is the conversation so far, sent again at every request and mostly served from a
cache — and millions because that is the size a run comes in: a round is thousands, and a day
of rounds is millions. A number with six zeros on it is a number nobody can type without
counting the zeros twice.

**Dollars** are what you actually pay. It is the one of the three that cannot always be read: a
model nobody lists has no price, and humanize answers `None` for it rather than `$0.00`, which
would say the run had been free. A cap that cannot be read is a cap that will never bite, and
it looks exactly like one that has not bitten yet — so a run whose dollars cannot be read says
so on stderr before it takes its first turn.

## It is not a flow's to implement

It used to be. Six flows in the official flowverse each carried a copy of the same `budget`
setting, the same million, and the same `if spent >= budget` block. Six copies is six places to
get it wrong, a cap that only those flows had, a cap that read only the tokens those flows
happened to count, and a cap nobody could set from the menu they set everything else from.

Now it is held to once, off the meters every backend already feeds, at the edges of every turn
of every session of every agent of the run. No driver cooperates and none can opt out — the
check is on the session base class rather than on a moment a flow hangs a hook on, because a
hook is the *flow's* seam and an allowance the person set must not be defeatable by a flow
hanging one.

A flow may still say what a run of it is worth **by default**:

```python
@flow(budget=Allowance(hours=6, tokens=10.0, dollars=50))
def run(agents: tuple[Agent], task: str) -> None:
    ...
```

and whoever runs it overrides that. Saying nothing is a flow with no opinion.

## What "stopped" means

The turn that spends the last of it still answers with what it said. A turn cut off has done
what it did — its edits are on disk, its conversation is open — so it is a round that ended
rather than a round that failed; read as a failure a loop would take it again, on an allowance
that is already spent.

The *next* turn raises `Stopped`. Not waiting, because an allowance only ever runs out and
nothing that waits here is ever released; and not answering with nothing, because a flow cannot
tell `""` from a round that failed. `Stopped` is not a `CalledProcessError`, so the loops that
carry on past a turn that failed do not carry on past this one.

The allowance is the run's, so the moment one reading says it is spent it is spent for every
session at once. There is no set of blocked sessions to collect: every agent is stopped
together, which closes every session each of them holds, so a turn running elsewhere on the
run's money ends too. The run is written down as `stopped` rather than as having finished what
it set out to do.

## Clones count, and so do stand-ins

An agent cloned mid-flow is another agent for every other purpose — it has opened no
conversation, is watched by nobody, and is written down in the trace as itself. It is not
another agent for money. A flow that does all of its work through clones, which is how a flow
that recurses is written, would otherwise read as having spent nothing at all and run under an
allowance that could never bite.

An agent that fell through to a stand-in spends the run's too: an account going down is not a
reason for the money to stop being counted.

## Per run, not across runs

The allowance is this run's. The flow budgets it replaces accumulated across every run of a
flow in a workspace, so forty restarts of a week-long loop shared one ten-million budget; now
they get forty. That is the intended change: a budget somebody has just set in the menu that
reads as already spent from a run last week is not one anybody can reason about.

Which means a run stopped by its allowance is a run to **pick up**, not one that is over. Its
kept state is left exactly as a stalled run's is, and running the flow again carries on from
where it stopped under a fresh allowance.

## Setting one

From a command line, `-c file.yaml` with a top-level `budget:` in it, as above. It has to be a
mapping of the dimensions — a bare `budget: 25` is refused, naming all three things it could
have meant, because a quarter of a day, twenty-five million tokens and twenty-five dollars are
not each other and a run held to the wrong one stops a thousand times too early or never.

From the interface, `/flow` has a **budget** row on the page a flow's agents are on. It says
what the run is held to without being opened, because an allowance nobody can see without
opening something is one nobody checks.

## When nothing will stop it

Three dimensions and none of them set is a run that goes until somebody notices, for whatever
days of a model cost. That is a fair thing to ask for and a poor thing to arrive at by not
answering three questions, and the two are identical afterwards. So saving one in the interface
asks once whether that is what was meant.

`hmz exec` does not ask. A run with nobody at a terminal is a run with nobody to answer, and a
blocking question there would hang every unattended flow there has ever been — so it says
plainly on stderr that nothing will stop the run, and goes.

A flow that is *meant* to run unbounded says so in its own file:

```python
@flow(budget=Allowance())
def run(agents: Chat, task: str) -> None:
    ...
```

which is what `chat` writes. A conversation ends when the person stops typing, and there is no
round of it they did not ask for. Any flow may make the same claim; the question exists to stop
an accidental unbounded run rather than a deliberate one — and it is one reviewable line in one
file rather than a list of names kept in the interface, the command line and the settings
alike.

See [A turn can be cut off](/features/budgets) for the cap on one turn rather than on the run,
[Cost and rate](/user/tally) for what the readings are made of, and
[Stopping](/user/stopping) for ending a run by hand.
