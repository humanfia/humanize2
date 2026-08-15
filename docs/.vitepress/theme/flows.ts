// Every flow humanize can run, and the shape of each one, in one place.
//
// Two things are written down here, and the second is the reason the first is a module rather
// than a table in a page: what a flow *is* -- its name, where it comes from, how many agents it
// wants, the line that starts it -- and what a run of it *looks like*, as a script of turns the
// diagram plays. The catalogue and the diagrams then cannot disagree, and a flow added to the
// flowverse is one entry here rather than a page and a drawing that drift apart.
//
// The shapes are read off the flows themselves: `src/hmz/flows/builtin/` for the three humanize
// ships, and https://github.com/humanfia/flowverse for the rest. A session marked `new` is one
// the flow opened for that turn; `held` is the same session taking another. That distinction is
// the whole of what separates most of these from each other, so it is the thing the diagram
// draws largest.

/** Where a flow comes from: the package, or the flowverse that is fetched. */
export type Place = 'builtin' | 'official'

/** The small drawing that stands for a flow in the catalogue. */
export type Family =
  | 'talk'
  | 'fresh'
  | 'held'
  | 'nudge'
  | 'goal'
  | 'governor'
  | 'pair'
  | 'review'
  | 'phases'
  | 'lanes'

export interface Flow {
  /** The name `-f` takes, qualified where it needs to be. */
  name: string
  /** The page under /flows/. */
  link: string
  /** How many agents it drives, in the words `/agents` would use. */
  agents: string
  /** One line: what it does. */
  said: string
  /** What stops it. */
  ends: string
  /** What a run picked up carries in, or "" for a flow that keeps nothing. */
  keeps: string
  place: Place
  family: Family
  /** The name flowbench scores it under, where it has one. */
  bench?: string
}

export const FLOWS: Flow[] = [
  {
    name: 'chat',
    link: '/flows/chat',
    agents: '1 + you',
    said: 'One agent, one session, and every line typed between turns is a turn of it.',
    ends: 'you stop typing',
    keeps: '',
    place: 'builtin',
    family: 'talk',
  },
  {
    name: 'ralph_loop',
    link: '/flows/ralph-loop',
    agents: '1',
    said: 'A fresh session every round, so nothing carries over but the repository.',
    ends: 'a budget in output tokens',
    keeps: 'rounds · output',
    place: 'builtin',
    family: 'fresh',
    bench: 'ralph_loop',
  },
  {
    name: 'stateful_ralph',
    link: '/flows/stateful-ralph',
    agents: '1',
    said: 'One session, held for the whole run, re-sent the task every round.',
    ends: 'a budget in output tokens',
    keeps: 'rounds · output',
    place: 'builtin',
    family: 'held',
    bench: 'stateful_ralph',
  },
  {
    name: 'official/continue_loop',
    link: '/flows/continue-loop',
    agents: '1',
    said: 'Sends the task once, then keeps nudging “continue” at the session that heard it.',
    ends: 'a budget in output tokens',
    keeps: 'rounds · output',
    place: 'official',
    family: 'nudge',
    bench: 'continue_loop',
  },
  {
    name: 'official/goal',
    link: '/flows/goal',
    agents: '1',
    said: 'Ralph, with the task set as the agent’s own goal: it decides when a turn is over.',
    ends: 'a budget in output tokens',
    keeps: 'rounds · output',
    place: 'official',
    family: 'goal',
    bench: 'goal',
  },
  {
    name: 'official/fixed_juice_ralph',
    link: '/flows/fixed-juice-ralph',
    agents: '1',
    said: 'Ralph with a governor: the effort moves a rung a round to hold an answer to a size.',
    ends: 'a budget in output tokens',
    keeps: 'rounds · output · effort',
    place: 'official',
    family: 'governor',
    bench: 'fixed_juice_ralph',
  },
  {
    name: 'official/flame_chase',
    link: '/flows/flame-chase',
    agents: '2',
    said: 'Two agents take turns on the same task, each reading the repository rather than a history.',
    ends: 'a budget the pair spend between them',
    keeps: 'turn · rounds · output',
    place: 'official',
    family: 'pair',
    bench: 'flame_chase',
  },
  {
    name: 'official/rlar',
    link: '/flows/rlar',
    agents: 'actor · reviewer',
    said: 'The actor remembers and the reviewer must not. The review is the actor’s next prompt.',
    ends: 'the reviewer agreeing the work is done',
    keeps: 'rounds · the review nobody acted on',
    place: 'official',
    family: 'review',
    bench: 'rlar',
  },
  {
    name: 'official/humanize1',
    link: '/flows/humanize1',
    agents: '1, then 2, then 2 + you',
    said: 'PolyArch/humanize as three flows: an idea, a plan both sides converged on, and a build under review.',
    ends: '--max rounds, for the loop of the three',
    keeps: 'the directory the loop is in, and its round',
    place: 'official',
    family: 'phases',
  },
  {
    name: 'official/parallel_flame_chase',
    link: '/flows/parallel-flame-chase',
    agents: '7',
    said: 'One coordinator plans three isolated lanes, then leaves; six actors alternate and coordinate by report.',
    ends: 'the lanes running out of work, or you',
    keeps: 'the plan, the snapshots, whose turn each lane is on',
    place: 'official',
    family: 'lanes',
  },
  {
    name: 'official/parallel_flame_chase_mission',
    link: '/flows/parallel-flame-chase-mission',
    agents: '7',
    said: 'The same three lanes, with a fresh coordinator returning to audit outcomes, stalls and deadlines.',
    ends: 'the coordinator adjudicating the last mission, or you',
    keeps: 'the missions, the audits, and everything the base flow keeps',
    place: 'official',
    family: 'lanes',
  },
]

/* ------------------------------------------------------------------------------------------
   The shapes. A script of turns, played left to right by <HmzFlowShape>.
   ------------------------------------------------------------------------------------------ */

/** What a step is drawn as. */
export type Tone = 'work' | 'read' | 'plan' | 'ask' | 'stop'

/** What one turn hands to another, and which turn it hands it to. */
export interface Carry {
  said: string
  to: string
}

export interface Step {
  /** Referred to by a carry, and by the loop. */
  id: string
  /** Which lane it is on. */
  lane: string
  /** When it happens. Two steps at the same column happen at once. */
  col: number
  /** How many columns it takes, for a turn that is longer than the others. Default 1. */
  span?: number
  label: string
  /** Whether the flow opened a session for this turn, held the one it had, or took no turn. */
  session?: 'new' | 'held' | 'none'
  tone?: Tone
  /** Turns of the model inside one turn of the flow -- what a goal is. */
  inside?: number
  carry?: Carry[]
}

export interface Lane {
  id: string
  name: string
  note: string
  /** Which of the six lane colours it takes, where two lanes are two halves of one thing.
   *  Left out, a lane takes the colour of its own place in the list. */
  tone?: number
}

export interface Shape {
  /** The flow it is of, as `-f` takes it. */
  of: string
  lanes: Lane[]
  steps: Step[]
  /** The arc back: what a round ends on, what it starts again at, and why. */
  loop?: { from: string; to: string; said: string }
  /** The bar under the diagram, where something other than the flow is what stops it. */
  meter?: { kind: 'budget' | 'juice'; said: string }
  /** One line under the whole thing. */
  caption: string
}

const A = (said: string, to: string): Carry[] => [{ said, to }]

export const SHAPES: Record<string, Shape> = {
  chat: {
    of: 'chat',
    lanes: [
      { id: 'agent', name: 'the agent', note: 'one session throughout' },
      { id: 'you', name: 'you', note: 'and the one that ends it', tone: 6 },
    ],
    steps: [
      {
        id: 'y0',
        lane: 'you',
        col: 0,
        label: 'what you typed first',
        session: 'none',
        tone: 'ask',
        carry: A('the turn', 'a0'),
      },
      {
        id: 'a0',
        lane: 'agent',
        col: 1,
        label: 'a turn',
        session: 'new',
        carry: A('what it said', 'y1'),
      },
      {
        id: 'y1',
        lane: 'you',
        col: 2,
        label: 'a line typed between turns',
        session: 'none',
        tone: 'ask',
        carry: A('the next turn', 'a1'),
      },
      {
        id: 'a1',
        lane: 'agent',
        col: 3,
        label: '…the same session',
        session: 'held',
        carry: A('what it said', 'y2'),
      },
      { id: 'y2', lane: 'you', col: 4, label: 'nothing typed', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'a1', to: 'y1', said: 'for as long as you answer' },
    caption:
      'Saying something to the person is asking what to say next. Answered with nothing — a command line, nobody at the prompt — the flow does the one thing it was given and stops.',
  },

  ralph_loop: {
    of: 'ralph_loop',
    lanes: [{ id: 'agent', name: 'the agent', note: 'a new session a round' }],
    steps: [
      { id: 'r1', lane: 'agent', col: 0, label: 'the task, and the repository', session: 'new' },
      { id: 'r2', lane: 'agent', col: 1, label: 'the task, and the repository', session: 'new' },
      { id: 'r3', lane: 'agent', col: 2, label: 'the task, and the repository', session: 'new' },
      { id: 'r4', lane: 'agent', col: 3, label: 'the task, and the repository', session: 'new' },
    ],
    loop: { from: 'r4', to: 'r1', said: 'nothing carries but the repository' },
    meter: { kind: 'budget', said: 'output tokens, against the budget' },
    caption:
      'Every round starts where the last one did: from the task and from whatever the round before it left in the working directory.',
  },

  stateful_ralph: {
    of: 'stateful_ralph',
    lanes: [{ id: 'agent', name: 'the agent', note: 'one session, longer' }],
    steps: [
      { id: 's1', lane: 'agent', col: 0, label: 'the task', session: 'new' },
      { id: 's2', lane: 'agent', col: 1, label: 'the task, again', session: 'held' },
      { id: 's3', lane: 'agent', col: 2, label: 'the task, again', session: 'held' },
      { id: 's4', lane: 'agent', col: 3, label: 'the task, again', session: 'held' },
    ],
    loop: { from: 's4', to: 's2', said: 'the same conversation, one round longer' },
    meter: { kind: 'budget', said: 'output tokens, against the budget' },
    caption:
      'What grows here is not only the spend: one session is one conversation, and the context window is the other thing a long run of this runs into.',
  },

  continue_loop: {
    of: 'official/continue_loop',
    lanes: [{ id: 'agent', name: 'the agent', note: 'one session, nudged' }],
    steps: [
      { id: 'c1', lane: 'agent', col: 0, label: 'the task', session: 'new' },
      { id: 'c2', lane: 'agent', col: 1, label: '“continue”', session: 'held' },
      { id: 'c3', lane: 'agent', col: 2, label: '“continue”', session: 'held' },
      { id: 'c4', lane: 'agent', col: 3, label: '“continue”', session: 'held' },
    ],
    loop: { from: 'c4', to: 'c2', said: 'until the budget is spent' },
    meter: { kind: 'budget', said: 'output tokens, against the budget' },
    caption:
      'Until a turn lands, the task is sent again rather than “continue”: a word that means something only to a session that heard what it is continuing.',
  },

  goal: {
    of: 'official/goal',
    lanes: [{ id: 'agent', name: 'the agent', note: 'run under a goal' }],
    steps: [
      {
        id: 'g1',
        lane: 'agent',
        col: 0,
        span: 2,
        label: 'pursue(task)',
        session: 'new',
        inside: 4,
      },
      {
        id: 'g2',
        lane: 'agent',
        col: 2,
        span: 2,
        label: 'pursue(task)',
        session: 'new',
        inside: 3,
      },
    ],
    loop: { from: 'g2', to: 'g1', said: 'started over only where it stopped without meeting it' },
    meter: { kind: 'budget', said: 'every turn the goal took, against the budget' },
    caption:
      'The ticks inside one box are turns the backend started itself: a turn that would have ended starts another, until the model says the objective is met.',
  },

  fixed_juice_ralph: {
    of: 'official/fixed_juice_ralph',
    lanes: [{ id: 'agent', name: 'the agent', note: 'a new session, set effort' }],
    steps: [
      { id: 'j1', lane: 'agent', col: 0, label: 'round · high', session: 'new' },
      { id: 'j2', lane: 'agent', col: 1, label: 'round · xhigh', session: 'new', tone: 'plan' },
      { id: 'j3', lane: 'agent', col: 2, label: 'round · xhigh', session: 'new', tone: 'plan' },
      { id: 'j4', lane: 'agent', col: 3, label: 'round · high', session: 'new' },
    ],
    loop: { from: 'j4', to: 'j1', said: 'one rung a round, so it settles rather than swings' },
    meter: { kind: 'juice', said: 'output tokens an average turn of the model came out with' },
    caption:
      'A governor rather than a brake: what it holds steady is the size of an answer. Under the target the agent is asked to think harder, over it to think less — one rung of its own model’s ladder per round.',
  },

  flame_chase: {
    of: 'official/flame_chase',
    lanes: [
      { id: 'one', name: 'the first agent', note: 'a fresh session a turn' },
      { id: 'two', name: 'the second', note: 'a fresh session a turn' },
    ],
    steps: [
      {
        id: 'f1',
        lane: 'one',
        col: 0,
        label: 'the task, and the repository',
        session: 'new',
        carry: A('what it left in the tree', 'f2'),
      },
      {
        id: 'f2',
        lane: 'two',
        col: 1,
        label: 'the task, and the repository',
        session: 'new',
        carry: A('what it left in the tree', 'f3'),
      },
      {
        id: 'f3',
        lane: 'one',
        col: 2,
        label: 'the task, and the repository',
        session: 'new',
        carry: A('what it left in the tree', 'f4'),
      },
      { id: 'f4', lane: 'two', col: 3, label: 'the task, and the repository', session: 'new' },
    ],
    loop: { from: 'f4', to: 'f1', said: 'a round is a turn each, and whose turn it is survives a restart' },
    meter: { kind: 'budget', said: 'what the two have spent between them' },
    caption:
      'Neither of them is told what the other said. What passes between the two is the working directory, which is the only account of the last turn there is.',
  },

  rlar: {
    of: 'official/rlar',
    lanes: [
      { id: 'actor', name: 'the actor', note: 'it has to remember' },
      { id: 'reviewer', name: 'the reviewer', note: 'it must not remember' },
    ],
    steps: [
      {
        id: 'a1',
        lane: 'actor',
        col: 0,
        label: 'the task',
        session: 'new',
        carry: A('a round of work, in the tree', 'v1'),
      },
      {
        id: 'v1',
        lane: 'reviewer',
        col: 1,
        label: 'reads the repository',
        session: 'new',
        tone: 'read',
        carry: A('the notes, word for word', 'a2'),
      },
      {
        id: 'a2',
        lane: 'actor',
        col: 2,
        label: 'the review, as its prompt',
        session: 'held',
        carry: A('a round of work, in the tree', 'v2'),
      },
      {
        id: 'v2',
        lane: 'reviewer',
        col: 3,
        label: 'reads the repository',
        session: 'new',
        tone: 'read',
        carry: A('done: true', 'over'),
      },
      { id: 'over', lane: 'reviewer', col: 4, label: 'the run is over', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'v2', to: 'a2', said: 'while the review says there is something left' },
    caption:
      'The reviewer answers two things at once, both read off a pydantic model rather than off a marker at the end of a paragraph: whether the task is finished, and what the actor hears next.',
  },

  'humanize1-gen-idea': {
    of: 'official/humanize1:gen-idea',
    lanes: [{ id: 'drafter', name: 'the drafter', note: 'one session' }],
    steps: [
      {
        id: 'i1',
        lane: 'drafter',
        col: 0,
        span: 2,
        label: 'explores the idea, n directions at once',
        session: 'new',
        tone: 'plan',
        carry: A('the draft, written to a file', 'i2'),
      },
      { id: 'i2', lane: 'drafter', col: 2, label: '.humanize/ideas/…', session: 'none', tone: 'stop' },
    ],
    caption:
      'One phase, one file, nothing kept. Running it again is meant to write another draft, which is why a run of it is never picked up.',
  },

  'humanize1-gen-plan': {
    of: 'official/humanize1:gen-plan',
    lanes: [
      { id: 'planner', name: 'the planner', note: 'one session throughout' },
      { id: 'analyst', name: 'the analyst', note: 'fresh, each reading' },
    ],
    steps: [
      {
        id: 'p1',
        lane: 'planner',
        col: 0,
        label: 'the draft, into a plan',
        session: 'new',
        tone: 'plan',
        carry: A('the plan as it stands', 'n1'),
      },
      {
        id: 'n1',
        lane: 'analyst',
        col: 1,
        label: 'reads it against the repository',
        session: 'new',
        tone: 'read',
        carry: A('what it does not agree with', 'p2'),
      },
      {
        id: 'p2',
        lane: 'planner',
        col: 2,
        label: '…the same session',
        session: 'held',
        tone: 'plan',
        carry: A('the plan, converged', 'p3'),
      },
      { id: 'p3', lane: 'planner', col: 3, label: 'docs/plan.md', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'p2', to: 'n1', said: 'until the two converge, or the round limit is reached' },
    caption:
      'The side that writes remembers and the side that reads does not — the rule the whole of humanize 1 is built on, here and again in the loop below.',
  },

  'humanize1-rlcr': {
    of: 'official/humanize1:rlcr',
    lanes: [
      { id: 'builder', name: 'the builder', note: 'one session, the loop' },
      { id: 'reviewer', name: 'the reviewer', note: 'fresh, each round' },
      { id: 'you', name: 'you', note: 'asked once, never waited', tone: 6 },
    ],
    steps: [
      {
        id: 'q',
        lane: 'you',
        col: 0,
        label: 'have you read the plan?',
        session: 'none',
        tone: 'ask',
        carry: A('answered, or not', 'b1'),
      },
      {
        id: 'b1',
        lane: 'builder',
        col: 1,
        label: 'builds the plan',
        session: 'new',
        carry: A('tries to stop — a Stop hook', 'v1'),
      },
      {
        id: 'v1',
        lane: 'reviewer',
        col: 2,
        label: 'reviews what landed',
        session: 'new',
        tone: 'read',
        carry: A('[P0-9] findings, as the next prompt', 'b2'),
      },
      { id: 'b2', lane: 'builder', col: 3, label: '…the same session', session: 'held' },
    ],
    loop: { from: 'b2', to: 'v1', said: 'a round is the builder trying to stop, up to --max' },
    caption:
      'The loop is a hook. A round ends when the builder believes the whole plan is done and tries to stop; what the reviewer says is what it hears instead of stopping.',
  },

  parallel_flame_chase: {
    of: 'official/parallel_flame_chase',
    lanes: [
      { id: 'co', name: 'the coordinator', note: 'plans once, then gone', tone: 6 },
      { id: 'l1a', name: 'lane 1 · a', note: 'the source, sole writer', tone: 1 },
      { id: 'l1b', name: 'lane 1 · b', note: 'the source, sole writer', tone: 1 },
      { id: 'l2a', name: 'lane 2 · a', note: 'a private snapshot', tone: 2 },
      { id: 'l2b', name: 'lane 2 · b', note: 'a private snapshot', tone: 2 },
      { id: 'l3a', name: 'lane 3 · a', note: 'a private snapshot', tone: 3 },
      { id: 'l3b', name: 'lane 3 · b', note: 'a private snapshot', tone: 3 },
    ],
    steps: [
      {
        id: 'c0',
        lane: 'co',
        col: 0,
        label: 'plans the three lanes',
        session: 'new',
        tone: 'plan',
        carry: [
          { said: 'lane 1', to: 'x1' },
          { said: 'lane 2', to: 'y1' },
          { said: 'lane 3', to: 'z1' },
        ],
      },
      { id: 'x1', lane: 'l1a', col: 1, label: 'a turn', session: 'new' },
      { id: 'x2', lane: 'l1b', col: 2, label: 'a turn', session: 'new' },
      { id: 'x3', lane: 'l1a', col: 3, label: 'a turn', session: 'new' },
      { id: 'y1', lane: 'l2a', col: 1, label: 'a turn', session: 'new' },
      { id: 'y2', lane: 'l2b', col: 2, label: 'a turn', session: 'new' },
      {
        id: 'y3',
        lane: 'l2a',
        col: 3,
        label: 'a turn',
        session: 'new',
        carry: A('a reconstructable artifact', 'x3'),
      },
      { id: 'z1', lane: 'l3a', col: 1, label: 'a turn', session: 'new' },
      { id: 'z2', lane: 'l3b', col: 2, label: 'a turn', session: 'new' },
      { id: 'z3', lane: 'l3b', col: 3, label: 'a turn', session: 'new' },
    ],
    loop: { from: 'z3', to: 'x1', said: 'each lane alternates a and b, durably across restarts' },
    caption:
      'Three lanes at once, and one of them owns the tree. What lanes 2 and 3 produce reaches lane 1 as a report and an artifact, never as a write.',
  },

  parallel_flame_chase_mission: {
    of: 'official/parallel_flame_chase_mission',
    lanes: [
      { id: 'co', name: 'the coordinator', note: 'plans, then audits', tone: 6 },
      { id: 'l1a', name: 'lane 1 · a', note: 'the source, sole writer', tone: 1 },
      { id: 'l1b', name: 'lane 1 · b', note: 'the source, sole writer', tone: 1 },
      { id: 'l2a', name: 'lane 2 · a', note: 'a private snapshot', tone: 2 },
      { id: 'l2b', name: 'lane 2 · b', note: 'a private snapshot', tone: 2 },
      { id: 'l3a', name: 'lane 3 · a', note: 'a private snapshot', tone: 3 },
      { id: 'l3b', name: 'lane 3 · b', note: 'a private snapshot', tone: 3 },
    ],
    steps: [
      {
        id: 'c0',
        lane: 'co',
        col: 0,
        label: 'plans the missions',
        session: 'new',
        tone: 'plan',
        carry: [
          { said: 'lane 1', to: 'x1' },
          { said: 'lane 2', to: 'y1' },
          { said: 'lane 3', to: 'z1' },
        ],
      },
      { id: 'x1', lane: 'l1a', col: 1, label: 'a turn', session: 'new' },
      { id: 'x2', lane: 'l1b', col: 2, label: 'a turn', session: 'new' },
      { id: 'y1', lane: 'l2a', col: 1, label: 'a turn', session: 'new' },
      {
        id: 'y2',
        lane: 'l2b',
        col: 2,
        label: 'a terminal outcome',
        session: 'new',
        tone: 'stop',
        carry: A('evidence', 'c1'),
      },
      { id: 'z1', lane: 'l3a', col: 1, label: 'a turn', session: 'new' },
      { id: 'z2', lane: 'l3b', col: 2, label: 'a turn', session: 'new' },
      {
        id: 'c1',
        lane: 'co',
        col: 3,
        label: 'a scoped audit',
        session: 'new',
        tone: 'read',
        carry: [
          { said: 'accepted — into the integration queue', to: 'x3' },
          { said: 'redirected', to: 'y3' },
        ],
      },
      { id: 'x3', lane: 'l1a', col: 4, label: 'integrates it', session: 'new' },
      { id: 'y3', lane: 'l2a', col: 4, label: 'a new mission', session: 'new' },
      { id: 'z3', lane: 'l3a', col: 4, label: 'a turn', session: 'new' },
    ],
    loop: { from: 'z3', to: 'x1', said: 'and a global audit every few hours, whatever the lanes are doing' },
    caption:
      'A fresh coordinator each audit, so what it adjudicates is the evidence in front of it rather than the run it planned hours ago.',
  },
}
