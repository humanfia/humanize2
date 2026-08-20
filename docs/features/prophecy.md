---
pageClass: hmz-feature
---

# Python becomes a prophecy

A regular flow is deliberately unconstrained Python: its next step is whatever its body does.
An **atlas** makes the other bargain. Its small declarative body is read before its first node
runs and compiled into a **prophecy** — a typed, canonical graph of every node, edge, branch,
loop and way out.

The graph is not a picture made after the run. It is the thing the run walks.

<HmzProphecy />

## The narrowness stops at the atlas body

An atlas body may bind the answer of one call, branch on a value already bound, loop back to
the node that answered it, and return. Arithmetic, nested calls, exception handling and every
other piece of work belong in a node.

That leaves the work itself as ordinary Python:

- A **mind** is one agent turn. It has one way out, because what a model happened to say is
  not yet a decision the graph can promise.
- A **logic** node is Python that drives no agent. It may count, reshape an answer, enforce a
  budget, and make the decision a branch reads.
- A **supernode** is another atlas. From outside it is one node; inside it is another complete
  prophecy.

Only the declarative body is restricted. A node may use the full language, and the ordinary
[flow](/features/flows) remains the better choice when the shape of the work is meant to emerge
while it runs.

## Compiling settles the graph before model time

The compiler reads syntax trees without importing or executing the flow. Each call site becomes
a node with a stable id; calling the same function twice makes two nodes. The node inputs and
outputs name their shapes, and every connection is checked before a turn can spend a token.

A loop becomes an explicit back-edge. Its head is run again with the values the body changed.
If the body changes nothing the head reads, the loop would make the same decision forever and
is refused. A return becomes a named way out of the graph, so a supernode answers with what the
return chose rather than whatever happened to run last.

The result is all or nothing. A call inside another call, a branch hung straight off a mind,
an incompatible shape, an unbound value, or a graph nested back inside itself produces findings
and no prophecy to guess from.

## The static reader proves only what it can see

The same zero-execution reading checks ordinary node code and regular flows. It can establish
useful absences one function at a time:

- a constant loop with no exit, or one that only sleeps, is an error;
- a loop whose every exit waits for an agent's shaped verdict is warned about unless the
  function also owns a bound;
- a suppressed shaped answer whose field is read before the answer is guarded is warned about;
- a field compared with a literal its declared shape can never hold is warned about.

It deliberately does not pretend to prove that an exit is reachable, follow a value through
arbitrary calls, or predict a model. Those questions belong to tests that drive the flow with
stand-in agents and adversarial answers. Static reading and executable proof meet at the same
boundary: neither needs a real model.

## One graph has one identity

A prophecy has a canonical text: nodes, edges, shapes and nested prophecies are ordered by what
they are, not by source formatting. Its identity is the first sixteen hexadecimal characters
of the canonical text's SHA-256 digest. Reflowing a docstring or adding a comment therefore
does not invent a new graph.

Changing a node's implementation does not change the graph either. Changing a call site, an
edge, a shape or a nested prophecy does. That distinction is what lets the work under a stable
graph evolve without pretending a changed graph is the old one.

A flowverse may ship the compiled prophecy beside its atlas. A run then walks that shipped
graph, while the static reading still compiles the source and reports when the two digests have
drifted apart. The shipped bytes may rebuild only the small set of tuple types a prophecy is
made of; malformed bytes or a pickle naming anything else are refused rather than executed or
silently replaced with a newly guessed graph.

## A graph may contain another graph

A supernode is compiled into the prophecy that reaches it. Its own nodes and shapes remain
visible underneath, and its answer is checked against the outer node that receives it. An
atlas may reach only another atlas this way: a dynamically loaded ordinary flow could have any
shape, which would leave a hole where the promised graph should be.

The compiler follows the nesting before the outer run begins and refuses a path that reaches
back into a prophecy already being compiled. During one run, a reached atlas is read once and
held; code is not swapped underneath a graph halfway through a round.

That is a deliberate difference from a regular flow. A regular flow handle keeps a name and
reads the target, including modules beside it, again at each call; a running flow may rewrite
that target and load it again. An atlas gives up that within-run hot reload so its prophecy
has no holes. Its files are read again by the next run.

## Picking up is another walk over the same graph

Every completed visit writes its answer under both the node id and the visit number. That last
part matters inside a loop: the third visit to one node is not allowed to overwrite the first
two. Visits inside a supernode are kept beneath the outer visit, however deep the nesting goes.

When a stopped run is picked up, humanize starts at the graph's way in and rebuilds the values
already written down. Completed visits return their kept answers without running. The first
visit with no answer is exactly where work continues; by default, a node interrupted partway
runs again. A side-effecting node that has certainly taken effect may instead declare that it
should be skipped on resume, but it must answer with nothing so no missing value is hidden.

This is precise workflow recovery, not process recovery. Backend conversations do not come
back. And the saved state carries the prophecy digest: if the graph changed, the old visits are
cleared and the run starts at the top. If only a node body changed, the digest still matches,
so completed visits stay completed and the first unfinished visit runs its node's current
code.

## Where the detail is

- [An atlas](/guide/atlas) — writing the restricted body and reading the compiled graph
- [Checking a flow](/guide/checking-flows) — the zero-execution findings and their limits
- [Testing a flow](/guide/testing-flows) — stand-in agents instead of model calls
- [Picking a run up](/guide/resuming) — how runs and saved state relate
- [Flows reference](/reference/flows) — every mark, graph field and finding
