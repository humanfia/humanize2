# Literature Survey: Deterministic Program Orchestration vs. Agentic Tool-Calling Loops

**Date:** 2026-08-31
**Context:** Preliminary research for a paper proposing that deterministic Python programs orchestrating LLM calls consume fewer tokens than agents managing the same workflow via iterative tool calls.

## Executive Summary

**Core Finding:** The exact controlled experiment (deterministic orchestration vs. LLM-controlled loop, same model/tools/tasks, only control-flow owner varies) **has been published** in a narrow domain (COBOL→Python, arXiv:2605.09894, May 2026), showing up to 3.5× token reduction at comparable accuracy. However, multiple weaknesses in that work leave room for a stronger, multi-domain contribution.

**Novelty Assessment:** A general framework demonstration across heterogeneous benchmarks, with proper statistical rigor, cache-aware cost accounting, and characterization of when the pattern wins vs. loses, remains unpublished.

**Critical Threats:**
1. **Prompt caching counterargument**: Raw token counts may not translate to dollar savings if programmatic workflows break cache prefixes while agentic loops preserve them (verified: r=0.15 between token reduction and cost reduction in one study).
2. **Architecture explains only 0.5% of variance** in one multi-architecture evaluation, versus 27.8% for model choice (though this result lacks token measurements and has wide CIs).
3. **One empirical study shows ReAct beating a fixed workflow on both accuracy AND tokens** on open-ended QA (HotpotQA, 200 examples), though the workflow was minimal.

---

## 1. Direct Prior Art (Closest Matches)

### 1.1 Deterministic vs. LLM-Controlled Orchestration (COBOL Modernization)

**Citation:** Naing Oo Lwin, Rajesh Kumar. "Deterministic vs. LLM-Controlled Orchestration for COBOL-to-Python Modernization." arXiv:2605.09894 [cs.SE], 11 May 2026. https://arxiv.org/abs/2605.09894

**System:** ATLAS (Autonomous Transpilation for Legacy Application Systems), single-agent.

**Benchmark:** NIST COBOL85 Test Suite, 382 programs, avg ~1,200 LOC/program.

**Experimental Design:**
- **Two arms within same framework:**
  - Deterministic: Fixed stage-based pipeline; model does not pick tools, order, retries, or termination; predicates over system state decide branching; fallback strategies in predefined order.
  - LLM-controlled: Model selects tools, execution order, repair strategies, termination decision; traces can diverge run-to-run.
- **Held constant:** Model architecture/version, temperature, seeds, system prompts, task instructions, formatting, source programs, test inputs, environment, timeouts, validation config, tool set (6 tools: `read_file`, `write_file`, `list_files`, `web_scrape`, `run_command`, `git`), interfaces, permissions.
- **Sole variable:** Execution control.

**Models:** Claude-Sonnet-4-5, GPT-5.1-Codex-Max, Grok-Code-Fast-1.

**Results (Table 1 — Computational Accuracy, Success Rate, P5-CA, CVaR₀.₁):**

| Model | Orchestration | CA | SR | P5-CA | CVaR₀.₁ |
|---|---|---|---|---|---|
| Claude-Sonnet-4-5 | Deterministic | 0.966 | **0.902** | 0.959 | 0.953 |
| Claude-Sonnet-4-5 | LLM-controlled | 0.964 | **0.918** | 0.956 | 0.949 |
| GPT-5.1-Codex-Max | Deterministic | 0.969 | **0.910** | 0.962 | 0.956 |
| GPT-5.1-Codex-Max | LLM-controlled | 0.964 | **0.937** | 0.958 | 0.951 |
| Grok-Code-Fast-1 | Deterministic | 0.961 | **0.872** | 0.951 | 0.943 |
| Grok-Code-Fast-1 | LLM-controlled | 0.958 | **0.906** | 0.941 | 0.934 |

- CA gaps: +0.002, +0.005, +0.003 (all <1pp).
- **Success Rate gaps: -0.016, -0.027, -0.034 — LLM-controlled wins on SR across all three models**, at larger margins than CA.

**Token/Cost (prose only, not tabulated):**
- NC, SQ modules: LLM-controlled 1.75M–2.25M tokens; deterministic 400K–700K tokens.
- Headline claim: "up to 3.5×" reduction (note: endpoints imply 3.2–4.4×, internally inconsistent).
- SQ cost: LLM-controlled >$140/success vs. deterministic ~$40.

**Limitations (§5.5, authors' own):**
- "Structured workflows with well-defined stages and validation **may amplify** deterministic advantages relative to exploratory tasks."
- "Where validators are weak, poorly specified, or absent, deterministic pipelines **may provide fewer advantages** than adaptive agentic approaches."
- COBOL→Python only; NIST suite omits production dependencies (JCL, CICS, VSAM, DBs, vendor dialects); correctness bounded by test-oracle coverage; conclusions depend on chosen models/prompts; cost excludes latency/infrastructure/engineering overhead.

**Statistical Rigor Issues:**
- N (number of seeded runs) never stated.
- No confidence intervals, variance figures, or significance tests anywhere.
- Only two modules (NC, SQ) have token counts; no per-module table.

**Relation to Our Claim:**
- **This is the closest published match**: same system, same controlled experiment, same conclusion.
- **Weaknesses leave room for stronger work**: (a) single narrow domain with explicit validators; (b) no statistical rigor; (c) SR result partially contradicts CA claim; (d) no cache-aware cost accounting; (e) no characterization of when the pattern wins vs. loses.

---

### 1.2 Compiled AI (Zero-Runtime-LLM Workflows)

**Citation:** Geert Trooskens et al. (9 authors, XY.AI Labs / Stanford / Cornell / Harvard). "Compiled AI: Deterministic Code Generation for LLM-Based Workflow Automation." arXiv:2604.05150 [cs.SE], 6 Apr 2026 (v2 31 Jul 2026). https://arxiv.org/abs/2604.05150

**Core Difference from Our Claim:**
- LLM invoked **once at compile time** to generate code; resulting workflow artifact runs with **zero LLM calls at execution time**.
- Our proposal: LLM remains in the runtime loop as a function call; determinism is about who controls flow, not about eliminating the model.

**Benchmarks:** BFCL function-calling (n=400), DocILE document intelligence (n=5,680 invoices).

**Results:**
- BFCL: 96% task completion, zero runtime tokens; break-even vs. runtime inference at ~17 transactions; **57× token reduction at 1,000 transactions**.
- DocILE: ties Direct LLM at 80.0% KILE, leads at 80.4% LIR (no accuracy loss).
- Security (n=135): 96.7% prompt-injection detection, 87.5% static code safety, zero false positives.

**Citability:** Strong quantitative evidence but architecturally distinct (compile-once-run-forever vs. deterministic-loop-with-LLM-calls).

---

### 1.3 LLM-as-Code (Framework Argument, No Token Experiment)

**Citation:** Junjia Qi et al. "LLM-as-Code: Agentic Programming for Agent Harness." arXiv:2606.15874 [cs.AI, cs.SE], KDD 2026 AgenticSE Workshop. https://arxiv.org/abs/2606.15874

**Core Argument (fully aligned with our thesis):**
- Control flow (looping, branching, sequencing) belongs in deterministic program code.
- LLM demoted from orchestrator to callable subroutine; model retains freedom inside each call but cannot redirect execution path.
- Per-call context assembled from execution history DAG, so context size depends on call depth instead of growing with accumulated steps.

**Empirical Evidence:**
- One computer-use agent case study.
- Reported outcome: "stability of long visual operation sequences" — **no token measurements**.
- Abstract explicitly states token argument is analytical/theoretical (O(depth) vs. O(steps) in prose, no formal complexity analysis).

**Relation to Our Claim:**
- **Good news**: The thesis is published, but the evidence is missing — we can cite this as motivation and fill the gap it left.
- No controlled token experiment, no benchmark numbers, no head-to-head comparison.

---

## 2. Classical Decoupling Baselines (Plan-Then-Execute)
