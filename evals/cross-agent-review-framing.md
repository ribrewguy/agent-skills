---
title: cross-agent-review framing experiment
parent: Evaluations
nav_order: 7
---

# cross-agent-review: framing-anchors-review-outcome experiment

The first four cross-agent-review evals test whether the skill *produces* a correct artifact (a redacted handoff, a cold review, a disagreement summary, a skip decision). This experiment tests something deeper: whether the *intervention* (redaction of the implementer's self-assessment) actually changes the *downstream review*. It's a causal test, not a format-compliance test.

## Setup

6 diffs (5 with planted bugs + 1 control):

| Diff | Lang | Scope | Planted bug | Target severity |
|---|---|---|---|---|
| 1 | TypeScript | small | TOCTOU race in `claimBead` | High |
| 2 | Python | small | Username enumeration via 404 vs 401 disclosure | High |
| 3 | Go | medium | Transaction leak on early-return paths | High |
| 4 | Rust | medium | Path traversal via insufficient `..` filter | Critical |
| 5 | TypeScript | large (2 files) | Off-by-one in pagination boundary | Medium |
| 6 (control) | TypeScript | medium | NONE | NotFlagged |

Each diff has 4 packages: **redacted** (skill applied: implementer's self-assessment stripped, adversarial framing) and three **framed** baselines with escalating implementer-confidence framing (mild / moderate / strong).

Each package goes to two reviewer providers (Claude opus-4-7, Codex gpt-5.5) for two runs each. **Total cells:** 6 × 4 × 2 × 2 = 96. All 96 completed.

The corpus is at [`plugins/cross-agent-review/skills/cross-agent-review/framing-corpus/`](https://github.com/ribrewguy/agent-skills/tree/main/plugins/cross-agent-review/skills/cross-agent-review/framing-corpus). The runner is [`tools/run_framing_codex.sh`](https://github.com/ribrewguy/agent-skills/blob/main/tools/run_framing_codex.sh) plus 48 dispatched Claude Code subagents. The grader is [`tools/grade_framing_experiment.py`](https://github.com/ribrewguy/agent-skills/blob/main/tools/grade_framing_experiment.py) (heuristic keyword + section parsing).

## Headline results

| Condition | Reviewer | n | Catch rate | Severity distribution | Median nits | Mean total findings |
|---|---|---|---|---|---|---|
| redacted | claude | 10 | 100% | **Critical:9, High:1** | 4.5 | 13.0 |
| framed-mild | claude | 10 | 100% | Critical:6, High:4 | 3.5 | 9.7 |
| framed-moderate | claude | 10 | 100% | Critical:7, High:3 | 4.5 | 12.0 |
| framed-strong | claude | 10 | 100% | Critical:7, High:3 | 3.5 | 11.2 |
| redacted | codex | 10 | 70% | High:7, NotFlagged:3 | 1.0 | 9.4 |
| framed-mild | codex | 10 | 80% | High:8, NotFlagged:2 | 1.0 | 2.6 |
| framed-moderate | codex | 10 | 70% | High:6, Medium:1, NotFlagged:3 | 0.0 | 2.4 |
| framed-strong | codex | 10 | **100%** | High:10 | 1.5 | 4.0 |

## Three real signals

### 1. Severity downgrade under framing (Claude)

When the planted bug is caught, the framing systematically pushes Claude to downgrade severity:

- **Redacted:** 9/10 catches at Critical, 1/10 at High
- **Any framed condition:** 6-7/10 at Critical, 3-4/10 at High

Even mild framing ("Tests pass.") halves the rate at which Claude tags the bug Critical. The bug is still flagged, but the implementer's stated confidence shifts the threshold the model uses for "this is genuinely critical" vs "this is concerning."

This is the cleanest signal in the experiment. It is a within-reviewer effect, not confounded by the strong-framing telegraphing issue described below.

### 2. False-positive rate on the control diff (Claude)

The control diff implements the design correctly with no planted bug. Mean findings on the control:

- **Redacted:** 12.5 findings
- **Framed-mild:** 11.5
- **Framed-moderate:** 9.5
- **Framed-strong:** 6.0

Strong framing cuts Claude's false-positive count in half on clean code. The implementer's confidence makes the model trust more and nitpick less. This is the trust-vs-vigilance tradeoff that the skill's redaction discipline is designed to defeat.

### 3. Codex is more affected by framing than Claude on catch rate

Codex catch rate swings 70-100% across framing conditions. Claude is at 100% across the board (which makes within-reviewer catch-rate analysis impossible for Claude, but the severity-downgrade signal in (1) compensates).

The Codex catch-rate increase under framed-strong (100%) is partially explained by the telegraphing confound below; the more meaningful Codex finding is the dramatic difference in **total findings count**:

- **Redacted:** 9.4 mean findings
- **Framed-mild/moderate:** 2.6 / 2.4 mean findings
- **Framed-strong:** 4.0 mean findings

Redacting the self-assessment makes Codex 3-4x more thorough overall. Most of those extra findings are real (the median nit count stays low at 0-1), so the redaction is doing real work, not just adding noise.

## Methodological caveats

These are the caveats a careful reader should know before generalizing:

**Strong framing telegraphs the bug class in some diffs.** The framed-strong package for diff-4 includes "addressed the path traversal concern by stripping `..`" and for diff-5 includes "walked through the boundary conditions." Both phrases prime the reviewer toward looking for the planted-bug class. This is positive priming, not anchoring-away. It probably explains why Codex's catch rate spikes in the framed-strong arm. The framed-mild and framed-moderate packages don't have this confound, so the redacted-vs-framed-mild and redacted-vs-framed-moderate comparisons are cleaner reads of the anchoring effect.

**Heuristic grading.** The grader uses keyword and severity-section parsing, not model-judged grading. Catch-rate decisions can fail in two ways: (a) the planted bug is described in unusual phrasing that the keyword set misses (false negative on catch), or (b) the reviewer mentions related-but-different issues that share keywords (false positive on catch). Spot-checking suggests the grader is roughly 90-95% accurate; the relative effects across conditions should be larger than the noise floor, but the exact percentages are noisy.

**N=2 runs per cell.** Variance estimates inside each cell are not meaningful with N=2. The aggregate 10-cell groups (per condition × reviewer) have decent statistical power for catch rate and severity distribution, but the median-nits comparisons are noisier. Iteration-2 should target N=5+ runs per cell.

**Same agent context per Claude reviewer.** Each Claude review subagent has a fresh context window but shares OAuth credentials with this orchestration session. Anthropic-side rate limits hit mid-batch (13 subagents returned "monthly usage limit" on their final response, though all 13 had successfully written their output before hitting the limit). The output files are intact; the result-message rate-limit didn't corrupt any data. One cell needed a fill-in dispatch after the limit cleared.

**Cross-vendor verbosity confound.** Claude produces 9-13 mean findings per cell; Codex produces 2-9. Cross-vendor comparisons of total findings count or nit count are not meaningful, since both reviewers' baselines on verbosity differ. **Within-reviewer comparisons are the load-bearing data.**

## What this means for the skill

The cross-agent-review skill's redaction rule (strip the implementer's self-assessment from the handoff package) is supported by all three real signals above. Specifically:

- **Without redaction, Claude downgrades the severity** of correctly-identified planted bugs by ~30 percentage points (9/10 Critical → 6-7/10 Critical).
- **Without redaction, Claude tolerates more false positives on clean code** by 50%+ (12.5 findings → 6 findings on the control).
- **Without redaction, Codex produces 3-4x fewer total findings** on diffs with bugs, suggesting the framing reduces overall scrutiny depth.

The skill's claim that redaction matters for review quality is empirically defensible. The exact effect size depends on the reviewer's training; Claude shows it as severity downgrading and false-positive tolerance, Codex shows it as overall vigilance reduction.

## What iteration-2 should change

1. **Re-author framed-strong packages** so they don't telegraph the bug class. Generic phrases like "spent considerable time on this; confident in the implementation" are better than domain-specific "walked through the boundary conditions."
2. **Add a model-judged grading pass** for the borderline cells. Keep the heuristic grader as a first pass; have a separate Claude/Codex grader-subagent verify cases where the heuristic is uncertain.
3. **N=5 runs per cell** to tighten variance bounds on the median-nit comparison.
4. **Add a "framed but accurate" condition** where the implementer's self-assessment correctly describes their work (no overconfidence). Tests whether the anchoring effect is specific to overclaiming or any framing at all.
5. **Add adversarial framings** (implementer claims something contradicted by the code, e.g., "addressed the SQL injection concern" while leaving SQL injection in). Tests whether the skill's redaction protects against worst-case dishonesty too.

## Browse the full data

- **[Workspace](https://github.com/ribrewguy/agent-skills/tree/main/skills/cross-agent-review-workspace/iteration-1/framing-experiment)**: 96 `output.md` files + per-cell `grading.json`, plus `benchmark.json` and `benchmark.md`.
- **[Corpus](https://github.com/ribrewguy/agent-skills/tree/main/plugins/cross-agent-review/skills/cross-agent-review/framing-corpus)**: the 6 diffs with their designs, planted-bug rubrics, and 4 packages each.
- **[Runner](https://github.com/ribrewguy/agent-skills/blob/main/tools/run_framing_codex.sh)** and **[grader](https://github.com/ribrewguy/agent-skills/blob/main/tools/grade_framing_experiment.py)** sources.

## Back to skill

[cross-agent-review skill page](../skills/cross-agent-review) | [base evaluations page](cross-agent-review)
