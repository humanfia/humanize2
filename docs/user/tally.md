# Cost and rate

Every session and every agent tells you what it has spent, how fast it is spending it, and how
hard it is thinking. Reach for this when you want to know what a run is costing while it is
still running — in tokens, and in money.

## Try it

The readout sits under the agent lines, above the editor:

```
              builder · claude/claude-opus-5:high · ● 2 · reading
              reviewer · codex/gpt-5.6-sol:high · ○ 3 · unread
    input 12.4k · output 2.1k · cache_read 1.02M+ · cache_write 48.2k+
                              $1.34 · 91 out/s
```

**Each kind of token is counted on its own**, never as one total over the lot of them. An
input token, an output token, a cached read and a cached write are four different things
bought at four different prices, and a single figure over all of them cannot tell a long
conversation from a lot of work.

The money is **per model**, since two agents at one model are one bill, and the rate covers **a
recent window only**, so a flow that has stopped reads as stopped.
[`/monitor`](/user/monitor) is the fuller version, with the handover graph beside it.

## The `+` on a kind

A `+` means *at least this much*. It is there when **some agent of the run drives a CLI that
does not report that kind at all** — Codex says nothing about a cache write, so a run mixing
Codex with Claude Code has a `cache_write` column made of Claude's writes alone. The union of
two backends is still the right figure to show; what would be wrong is showing it as though it
were the whole.

With **one** agent running there is nothing for a figure to be short of, so nothing is marked
and what you see is that backend's own reckoning — every kind it counts, whether or not
anything has gone on it yet. A column that appeared the first time a cache was written to
would be a readout that shuffles sideways while you are reading it.

A `+` is also there when **something was counted without its kind being said** — a backend that
reports a lump, a turn that spanned two models and named the kinds of neither. Those tokens
went on some kind and there is nothing to say which, so every column is short by part of them.

Which kinds each backend reports is a capability like any other: `counts:cache_read` and its
four siblings say who serves each one, and `hmz.flows.briefed()` lists them.

## What refreshes it, and when

Every **five seconds**, and again the moment an agent does anything at all — a tool call, a
word, an answer. Not only when a count arrives: a turn is minutes long and spends most of them
between the moments it reports one, and a rate is tokens over *seconds on the clock*. A figure
that moved only when a count landed would stand still through every tool call of a turn and
then jump as the turn ended, which reads as a run that stalled and recovered rather than as one
working.

## The money

**Where the money comes from.** The unit prices are not written down in humanize — vendors move
them without asking anybody, and a list shipped in a release is wrong the week after it ships.
They are fetched from [OpenLLMPrices](https://openllmprices.com/), which publishes one JSON
file of them, and kept under `~/.humanize/prices.json`. The interface fetches it once as it
opens, on a thread of its own, and refreshes it about once a day. **Nothing you type ever waits
on that**: what is drawn is read out of the file that is already there.

**A model nobody lists shows tokens and no money at all.** The list covers a few dozen models;
humanize drives whatever CLI you have installed. So the unlisted model is the ordinary case,
not the broken one:

```
   Tokens:   claude-opus-5              48.2k    $1.34     91 out/s
             some-local-model            9.1k              12 out/s
   Kinds:    input                       1.2k
             output                        980
             cache_read                 46.0k+
             cache_write                 9.1k+
             + a floor: not every agent here reports that kind
```

The blank is deliberate. `$0.00` beside a model nobody priced would be a claim about a bill,
and a false one. Where a run mixes a priced model with an unpriced one, the total above the
editor is marked `$1.34+`: it is what the priced part came to, and a floor on the whole.

**What the figure is, and what it is not.**

| | |
| --- | --- |
| Priced **per kind** | an output token costs five or ten times an input one, so the kinds are billed at their own rates and never at an average |
| The **standard tier** | a model priced higher above some context length is taken at the price it starts at, so a very long turn cost more than this says |
| A **floor**, not an invoice | it is what the tokens humanize saw come past come to, at list price, in US dollars — not what your account was charged |

It errs downwards on purpose. A kind of token nobody prices adds nothing rather than being
guessed at, and a kind only ever stands in for another where standing in cannot overstate: a
cache write nobody prices separately is taken at the input price, since a cache write is an
input token and a surcharge on it — while a cache *read* nobody prices is left out, being a
tenth of an input token, and a turn being mostly cache reads.

A subscription is not metered by the token at all, and an account with negotiated rates is not
on the list price. Read this as *what this work is worth at the counter*, which is the number
worth steering by, rather than as a statement from your provider.

**Where a backend does its own accounting in money, believe the backend.** This figure is the
least authoritative of the three sources humanize has — the vendor's own number beats it, and
so does the vendor's own token count. It is close: on one measured turn of `claude-haiku-4.5`
(10 in, 448 out, 35,188 cache-written) Claude Code's own `total_cost_usd` said $0.0472 and this
said $0.0462 — 2% low, and low in the direction it is meant to err.

**A backend that reports a lump of tokens without saying which kind each was gets no money
figure either.** Some do: a Codex rollout row may name a total and nothing else. Tokens with no
bill beside them is the honest reading of that.

**If the file has never been fetched** — a first start, an air-gapped machine, a network that
was down — everything reads as tokens alone until it lands. Setting `HUMANIZE_PRICES=off` turns
the fetching off for good; setting it to a path or a URL reads the list from there instead.

## Three readings, three questions

The rest of this page is the weaver's — whoever wrote the flow. Every session and every agent
answers the same three:

| | Answers | Moves with |
| --- | --- | --- |
| `spent()` | what has this cost | everything |
| `rate()` | how fast is the bill running up | how many turns are going at once |
| `juice()` | how hard is it thinking | the [effort](/user/efforts) |

```python
session.spent()          # Usage(input=41230, output=2180, cache_read=980100)
session.rate()           # tokens a second, by kind, over the last five minutes
session.rate(over=60)    # over the last minute instead
session.juice(over=60)   # output tokens an average turn of the model came out with
agent.spent()            # every session this agent has opened, dropped ones included
agent.rate(over=60)
agent.juice()
```

And what any of those came to, in money:

```python
from hmz import prices

prices.cost(agent.spent(), agent.config.model)   # dollars, or None for an unlisted model
prices.price("claude-haiku-4-5-20251001")        # Price(model="claude-haiku-4.5", …)
prices.money(1.34)                               # "$1.34" — and "$0.0012" under a cent
```

`cost` answers `None` — never `0.0` — for a model nobody lists, so a flow steering by money can
tell *not priced* from *free*. Neither call touches the network.

`price` matches a model to a listed one by stripping what is known not to be the model — and
promises no more than that:

| Stripped | Because |
| --- | --- |
| a provider or account in front — `anthropic/claude-sonnet-5` | the account is not the model |
| a gateway route, and the cloud it names — `azure/anthropic/claude-opus-5`, `aws/anthropic/bedrock-claude-opus-5` | where a request goes is not what it costs |
| a hosted qualifier — `us.anthropic.claude-opus-5-v1:0` | Bedrock's spelling of `claude-opus-5` |
| a release date or version behind — `claude-haiku-4-5-20251001` | which is `claude-haiku-4.5` |
| the punctuation two spellings disagree about | `claude-haiku-4-5` and `Claude Haiku 4.5` |

So one model reached three ways is one bill. It does not guess further: a near miss is a miss,
because the price of the neighbouring model is a wrong answer rather than an approximate one.
`gpt-5` is not `gpt-5.6-sol`. Behind a gateway offering hundreds of models against a list of a
few dozen, most of what you run is unmatched — and reads as tokens with no money beside them.

One thing the matching does *not* do is merge the rows. `/monitor` lists what has been spent
under each name the backends used, so a model your gateway spells one way and its own log
spells another is two lines. Each line's money is that line's.

## `spent` — a mapping of kind to tokens

`input` and `output` are the two that every backend counts, and they sit on the mapping as
attributes. The rest differ from CLI to CLI: a cache read, a cache write, or the reasoning a
backend counts beside the output rather than inside it. The five names are
`hmz.coganchor.agents.KINDS`, and every driver reports under them — a kind is the same word
whichever CLI counted it, because the prices are per kind and a usage written down under one
CLI's own spelling is a lump nothing can price.

So **a kind that is not there is one that backend does not report**:

```python
spent = session.spent()
spent.input, spent.output, spent.total       # always
spent.get("cache_read", 0)                   # for a backend that counts one
dict(spent)                                  # everything it does count
```

The kinds are also what a bill is made of. A reasoning count kept beside the output is bought
as output. A backend that says what a turn cost without saying which kinds it went on gets no
bill at all — the tokens are counted and nothing is claimed about them.

They add up to the whole of what crossed the wire, and never to more. A backend that counts its
reasoning inside the output does not also carry it beside the output, and one that counts a
cached read inside the input has the read taken back out: a token counted twice is a token
billed twice.

**Which kinds a backend reports is a fact about the backend, not about the turn**, and it is
declared rather than guessed: a turn that spent nothing on a cache write is missing that kind
exactly as a CLI that never counts one is. `AgentBase.counts` says it, the catalogue serves it
as `counts:<kind>`, and a flow can be refused an agent whose backend never reports what it
means to steer by:

| Backend | Counts |
| --- | --- |
| Claude Code, Kimi Code, pi, DeepSeek Harness, Grok Build, Qwen Code | `input`, `output`, `cache_read`, `cache_write` |
| opencode, mimocode | those four and `reasoning` |
| Antigravity | `input`, `output`, `cache_read`, `reasoning` |
| Codex, ZCode | `input`, `output` — each counts its cached reads inside the input |
| Cursor | nothing: it reports a duration and no tokens |

`reasoning` is only there for the backends that count it **beside** the output. Grok Build
reports a `reasoning_tokens` and it is deliberately not among its kinds: one measured turn,
asked to think at length and answer in one word, came back with `output_tokens: 1141` and
`reasoning_tokens: 1140`, so counting it separately would count those tokens twice and — the
prices billing reasoning as output — bill for them twice.

The interface reads the CLIs' own logs as well as their drivers, and a kind either of them
names counts as reported — Codex's server never names a cached read, and the rollout it writes
does. Only once that log has actually been read here, though: an agent whose turns land on
another machine writes its rollout there, and nothing on this one can show a kind out of it.

The `result` event a turn ends on carries the same reckoning, beside the per-model `tokens` it
already carried. `result.spent.total` is what `result.tokens` comes to.

## `rate` — seconds on the clock

**A rate is tokens a second over seconds on the clock**, not seconds an agent was talking. A
flow sleeps between rounds, commits and reads what the last turn wrote. That time is time the
tokens were spent over, and it is the honest reading of what a run costs per hour.

**The one the interface draws is output tokens a second, and says so.** The input of a turn is
the conversation so far, sent again at every request and mostly served out of a cache: it grows
with the length of the transcript rather than with the work, so a rate counting it says how
long the conversation has got — and doubles the moment a backend starts reporting what it read
back out of its cache. `session.rate()` itself is per kind, so a flow can read whichever it
means.

The window defaults to five minutes — `hmz.flows.WINDOW`, the same window the interface's
readout uses. A run younger than the window is measured **over the run**, so a rate read a
minute in is what that minute came to, not a fifth of it.

**The rate moves while the turn is still running.** A turn is minutes long, so a number that
only moved when one ended would stand still for all of them. Each backend is read where it says
what a request to the model cost:

| Backend | Read from |
| --- | --- |
| Claude Code, pi | the message it answered with |
| Codex | `thread/tokenUsage/updated` |
| opencode, mimocode | each step |
| Kimi Code | the session it is polling anyway |
| ZCode | its `model-io` log, a row per request the turn made |

## `juice` — and it is not a clock at all

`juice()` is what **one turn of the model** came out with: one request and the answer to it. A
turn a flow asks for is many of these.

A model asked to think harder writes more in each answer and takes longer over it, so that
average is what an [effort](/user/efforts) moves. It is the number to steer by when you hold
*how hard the thing is thinking*, rather than how fast a bill is running up.

```python
if agent.juice(over=120) < target:
    agent.effort = harder(agent.effort)
```

That is what [`fixed_juice_ralph`](/flows/fixed-juice-ralph) does, a rung a round, to
hold the agent to a target.

A window with no turn in it reads as `0.0`. There is nothing to go on, and a flow tells that
apart from a turn that said nothing.

A backend that states a whole turn's cost **after** having said what each request in it came to
is settling up rather than taking another turn. It is not counted as one, or the average would
be halved by the accounting.

## Two backends that report nothing

opencode and mimocode keep a session in a database rather than in a log file. So the interface
has nothing to read a running cost out of, and [gathering a run's trace](/user/tracing) —
**enter** on it in `/epics` — has nothing to gather. What their turns cost still reaches a flow:
each says it as the turn lands.

## See also

- [Efforts](/user/efforts) — what `juice` responds to
- [A turn can be cut off](/features/budgets) — the same reading, used as a cap on one turn
- [Every run has an allowance](/features/allowances) — the same reading, used as a cap on the
  whole run, money included
- [Watching a run](/user/monitor)
- [Agents › What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast)
