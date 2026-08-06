# Tutorials

Six tutorials, in order. Each one is a whole piece of work, start to finish, with every command
written out. Follow them and you will have run humanize on real problems rather than on
examples invented to be easy.

Tutorials teach. When you want to look up how one feature works instead, the
[guides](/guide/) have a page each.

## Start here

| | |
| --- | --- |
| **[1 · Quickstart](/tutorials/quickstart)** | Install it, talk to an agent, put a loop around that agent, and open the run as a timeline. Fifteen minutes. |

## Three pieces of real work

Each of these points an existing flow at a real repository. They are worth reading even if you
never run them — the point is what shape of work each flow is for.

| | |
| --- | --- |
| **[2 · Beat a benchmark](/tutorials/take-home)** | `official/flame_chase`: two agents take turns on the same kernel, each starting from the repository rather than from the other's reasoning. The target is Anthropic's open performance take-home. |
| **[3 · Port a project](/tutorials/port-a-project)** | `official/rlar`: one agent works in a long conversation while a fresh reviewer reads what actually landed. The work is moving a C# module of [futrime/lip](https://github.com/futrime/lip) to Python. |
| **[4 · Build a coding agent](/tutorials/build-an-agent)** | `official/humanize1`, all three phases: open an idea into a draft, argue the draft into a plan, then build the plan under review. What gets built is a small coding agent for `deepseek-v4-flash`. |

## Writing flows of your own

A flow is a directory of Python. These two write one from scratch.

| | |
| --- | --- |
| **[5 · Build under test](/tutorials/flow-checked-build)** | About forty lines. One agent writes code, the flow runs `pytest` between turns, and a second agent reviews what passed. The shortest useful flow there is. |
| **[6 · Four agents on a maths problem](/tutorials/flow-prove)** | Four kinds of agent, several turns at once, and answers held to a shape. Nothing compiles a proof, so the flow has to build its own way of telling a good one from a bad one. |

## After that

- Every feature, one page each: [Guides](/guide/).
- Every flag, key and Python call: [Reference](/reference/cli).
- What humanize does, in one page: [Features](/features/).
