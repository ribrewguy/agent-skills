**Critical**
- [evals/cross-agent-review-blindspots-design.md:29](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:29), [lines 31-37](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:31), [line 87](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:87)  
  Problem: The primary analysis treats derived pairs as if they were usable pair-level observations, but all 28 pairs per diff are deterministic recombinations of the same 8 runs. Same-Claude pairs share Claude runs; Same-Codex pairs share Codex runs; cross-vendor pairs share both Claude and Codex runs.  
  Why it matters: This massively overstates effective N and invalidates McNemar-style inference unless the clustering/reuse is modeled. The experiment has 12 diff-level units, not 12 × 28 independent pair units. For Critical, it has only 3 diff-level units.  
  Proposed fix: Make the diff the unit of inference. Predefine per-diff estimands from the 4 Claude and 4 Codex Bernoulli outcomes, then use clustered bootstrap/permutation over diffs or a hierarchical model. Do not report pair-level p-values as inferential. Increase Critical N substantially if Critical is the primary claim.
- [evals/cross-agent-review-blindspots-design.md:87](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:87)  
  Problem: “McNemar-style pairing” is underspecified and likely inapplicable. McNemar requires matched binary outcomes on the same units, but the design has 16 cross-vendor pairs, 6 Same-Claude pairs, and 6 Same-Codex pairs per diff, plus a post-hoc “better same-vendor” comparator.  
  Why it matters: There is no single predeclared matched pair of observations per diff. Choosing or aggregating pairs after recombination can produce anti-conservative results and ambiguous discordant counts.  
  Proposed fix: Define one matched contrast per diff before running: for example `cross_expected_pair_catch - max(same_claude_expected_pair_catch, same_codex_expected_pair_catch)`, computed from the four runs per vendor. Analyze those 12 paired contrasts descriptively with exact uncertainty.
- [evals/cross-agent-review-blindspots-design.md:45](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:45), [line 46](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:46)  
  Problem: Tier-1 sourcing does not defeat author bias; it relocates it. The selector still chooses which incidents, patches, languages, frameworks, extraction boundaries, and “self-contained enough” cases enter the corpus. Those choices can favor the prior without ever making an explicit performance prediction.  
  Why it matters: A biased selector can build a corpus of bugs that feel like one vendor’s blind spots or another vendor’s strengths while claiming the bugs are “real.” Real incident provenance is not randomization.  
  Proposed fix: Freeze a public sampling frame and randomize inclusion before extraction, or use an independent curator blind to the hypothesis and reviewer identities. Pre-register inclusion/exclusion rules, extraction length rules, language/domain quotas, and all discarded candidates.
- [evals/cross-agent-review-blindspots-design.md:68](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:68), [line 69](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:69)  
  Problem: The primary grader is Claude, while Claude is one of the reviewed vendors. “Fresh context” does not remove model-family bias in interpreting Claude-style reviews, verbosity, severity language, or reasoning patterns. The held-out human grader is the author, who has the prior under test.  
  Why it matters: The grading layer can systematically over-credit one vendor’s articulation style or calibrate borderline catches in the direction of the expected result. Tuning the judge prompt after agreement failure compounds this.  
  Proposed fix: Use blinded human graders who do not know vendor/source condition, or use multiple model judges from non-participant vendors plus adjudication. Lock the judge prompt before any labels, and if tuning is needed, tune only on a separate calibration set excluded from final analysis.
**High**
- [evals/cross-agent-review-blindspots-design.md:48](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:48), [line 49](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:49)  
  Problem: The “Gemini is uncorrelated with both reviewers” assumption is unsupported. Gemini, Claude, and Codex share training distributions, public code/security priors, benchmark exposure, and common CWE/OWASP patterns. Claude or a human then validates the planted bug, reintroducing a participant-model or author filter.  
  Why it matters: Tier-2 may not be an independent generative axis. It may create “LLM-planted” bugs with fingerprints that one reviewer family is more or less likely to catch for reasons unrelated to vendor diversity.  
  Proposed fix: Use multiple independent planters, including humans, and blind validation by reviewers not in the experiment. Treat planter identity as a factor in the analysis instead of assuming it is uncorrelated.
- [evals/cross-agent-review-blindspots-design.md:39](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:39), [line 92](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:92)  
  Problem: The conditional-independence test is asserted as mechanistic evidence, but the design does not provide independent conditional observations. Runs share diff difficulty, prompt, package wording, and possibly model release behavior.  
  Why it matters: Apparent within-vendor correlation can be driven by item difficulty or package features, not vendor-correlated blind spots. Apparent cross-vendor independence can be a marginal-rate artifact.  
  Proposed fix: Model catch probability with diff-level random effects and vendor/run effects. Report residual correlation after controlling for diff difficulty. Do not interpret raw `P(run-2 catches | run-1 catches)` as mechanism.
- [evals/cross-agent-review-blindspots-design.md:75](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:75), [line 80](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:80)  
  Problem: The success criterion is underpowered and too easy to narrate around. “≥15pp on Critical” rests on ~3 Critical diffs, and “directionally consistent across 2 of 3” gives a very thin, unstable basis for a vendor-diversity claim.  
  Why it matters: A single idiosyncratic Critical diff can dominate the aggregate. The criterion also ignores cases where cross-vendor loses on Critical but wins elsewhere, or where one large positive diff masks weak/negative evidence.  
  Proposed fix: Increase Critical cases and require a predeclared aggregate effect with uncertainty bounds plus per-diff robustness. Define what result patterns disconfirm, including wins confined to Medium/High or effects driven by one outlier.
- [evals/cross-agent-review-blindspots-design.md:60](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:60)  
  Problem: The sandbox relies partly on prompt instructions forbidding file reads/tool use. Read-only prevents writes, not reads; “Claude-Code-subagent equivalent” is unspecified.  
  Why it matters: A reviewer that reads local skills, rubrics, corpus files, or prior experiment artifacts contaminates the cell. Even one contaminated vendor could create a false cross-vendor signal.  
  Proposed fix: Enforce tool-disabled execution technically, run from an empty directory, remove repo paths/env hints, disable network where possible, log raw tool-call traces, and fail any cell with attempted filesystem/network access.
- [evals/cross-agent-review-blindspots-design.md:69](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:69)  
  Problem: “Tune the judge prompt and re-grade the full 96” is a pre-registration loophole. It allows repeated calibration until the model judge agrees with the author’s held-out labels, then applies that tuned judge to the full dataset.  
  Why it matters: This can become outcome-aligned grading under another name, especially because the author supplies the human labels.  
  Proposed fix: Split grading into calibration and locked evaluation sets. Limit the number and nature of prompt edits in advance. Publish all failed judge prompts and agreement matrices. Never tune on cells used in final estimation.
- [evals/cross-agent-review-blindspots-design.md:96](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:96), [line 98](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:98)  
  Problem: Follow-up surface-and-assess leaks reviewer identity through style. Claude and Codex review prose, verbosity, severity framing, and citation habits are distinctive even if names are stripped.  
  Why it matters: The missing reviewer may respond differently to claims that look like another model family’s writing, confounding “can recognize when surfaced” with “reacts to vendor/style fingerprint.”  
  Proposed fix: Canonicalize all genuine and distractor claims into a neutral template by a blinded paraphraser. Match length, specificity, citation density, and severity language. Do not surface verbatim reviewer prose.
- [evals/cross-agent-review-blindspots-design.md:98](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:98), [line 113](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:113)  
  Problem: Distractor generation is underspecified, and the ~20% disqualification threshold appears uncalibrated. If the author synthesizes distractors, they can be subtly implausible; if a model does, its style may leak.  
  Why it matters: The genuine-vs-distractor gap can be inflated by weak distractors rather than real surfaced recognition.  
  Proposed fix: Pre-generate distractors blind to vendor outcome, validate plausibility with independent graders, and set the distractor-agree threshold from a pilot calibration set excluded from final analysis.
**Medium**
- [evals/cross-agent-review-blindspots-design.md:54](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:54)  
  Problem: The 50/30/20 corpus mix and severity mix are asserted, not justified. Severity is assigned by heterogeneous sources: post-mortem, Gemini, or category convention.  
  Why it matters: Source tier, severity, language, bug class, and difficulty can be confounded. A positive result may be a Tier-1/Tier-2 artifact rather than a vendor-diversity effect.  
  Proposed fix: Predefine quotas by language, bug class, severity, and source tier. Analyze source tier as a factor. Avoid letting Tier source determine severity without independent normalization.
- [evals/cross-agent-review-blindspots-design.md:45](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:45), [line 46](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:46)  
  Problem: Public post-mortems and CVE patches may be in training data. Both reviewers, or one reviewer, may have seen the incident, root cause, or patch pattern.  
  Why it matters: The experiment may measure memorization or training-set exposure, not blind-spot complementarity.  
  Proposed fix: Prefer recent private/held-out incidents where legally usable, or transform incidents enough to remove recognizable identifiers while preserving the defect. Track publication date and model training cutoff risk.
- [evals/cross-agent-review-blindspots-design.md:51](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:51), [line 52](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:52)  
  Problem: “Both vendors should catch these at near-100%” makes Tier-3 distractor bugs a weak control. Easy bugs may create ceiling effects and dilute the measured Critical/High signal.  
  Why it matters: They may make the corpus look balanced without adding information about the hypothesis.  
  Proposed fix: Use calibrated easy/medium/hard items based on independent pilot graders, not assumed CWE familiarity. Keep them separate from the primary Critical analysis.
- [evals/cross-agent-review-blindspots-design.md:54](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:54), [line 117](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:117)  
  Problem: The single no-bug control is not operationalized in the primary analysis. Pair union logic inflates false positives because “at least one member flags it” grows with pair size and verbosity.  
  Why it matters: Cross-vendor review could “win” coverage while also producing more false positives, but the success criterion does not penalize that.  
  Proposed fix: Define pair-level false-positive and precision metrics for the control and for non-planted findings across all diffs. Require no unacceptable false-positive increase as part of success.
- [evals/cross-agent-review-blindspots-design.md:29](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:29)  
  Problem: There is no within-vendor diversity control: same model with different system prompts, temperatures, review checklists, or decoding seeds.  
  Why it matters: If two Claude runs with diverse prompts recover most of the union benefit, the result supports “review diversity” more than “cross-vendor review.”  
  Proposed fix: Add same-vendor diversity baselines: Claude×Claude with different prompts/temperatures, Codex×Codex with different prompts/temperatures, and possibly same-vendor different model versions.
- [evals/cross-agent-review-blindspots-design.md:96](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:96)  
  Problem: The follow-up asymmetry threshold `>=3 of 4` versus missed on `>=3 of 4` leaves only a thin qualifying band and conflates “missed” with “correctly disagreed.”  
  Why it matters: A catching vendor may have false-positive Critical findings. The missing vendor’s disagreement can be correct, but the follow-up frames it as a surfaced missed finding.  
  Proposed fix: Independently adjudicate each qualifying “caught” Critical finding before follow-up. Treat follow-up eligibility as requiring verified genuine issue status, not merely reviewer catch asymmetry.
**Nits**
- [evals/cross-agent-review-blindspots-design.md:9](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:9), [line 83](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:83)  
  Problem: A committed hash is not a sealed pre-registration if the author can amend history, create local files, or rerun design decisions before committing.  
  Proposed fix: Timestamp the pre-registration externally, or push the hash to a remote immutable log before runs.
- [evals/cross-agent-review-blindspots-design.md:118](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:118)  
  Problem: Follow-up cell count says “only diffs where exactly one vendor missed all 4 runs” but the threshold in §9 is missed on ≥3 of 4.  
  Proposed fix: Align the feasibility text with the actual threshold.
- [evals/cross-agent-review-blindspots-design.md:152](/Users/torr/Projects/agent-skills/evals/cross-agent-review-blindspots-design.md:152)  
  Problem: “None blocking” is inaccurate. The statistical unit, grading independence, corpus selection, and follow-up distractor protocol are blocking design issues.  
  Proposed fix: Move these into open questions before sealing predictions.
