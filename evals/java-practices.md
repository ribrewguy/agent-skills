---
title: Java design preferences evaluation
parent: Evaluations
nav_order: 10
---

# Java design preferences evaluation

The owner's Java preferences now include Joshua Bloch-inspired design decisions:
immutable values, owned mutable boundaries, invariant preservation, composition,
small APIs and consistent value semantics. The existing compiler/formatter/
analyzer guidance remains. The skill has ten prompt cases: four retained tooling
cases and six new design cases.

## Executed comparison

Two fresh generation contexts received identical six-case prompts and the same
mutable Parcel fixture. One received the previous tool-focused skill and its
reference; the other received the updated skill and its references. Neither saw
the evaluation rubric, contract tests, other candidate or parent conversation.
Each generated the requested Java files and review/notes in a disposable directory.
A third context graded anonymized candidates against the prewritten expectations.

The parent evaluator compiled each implementation with the fixture's Java release
and ran contract probes on the fixture JDK. These are fixture inputs, not runtime
or tooling pins in the skill.

| Case | Executable probes, previous | Executable probes, updated | Final design criteria, previous/updated |
|---|---|---|---|
| Shipment snapshot: nested elements, arrays and retained validation | 8/8 | 8/8 | 4/4 each |
| Legacy dates: ownership, subtype cloning and range checks | 6/6 | 6/6 | 4/4 each |
| Mutable ledger: rejected batches, stable snapshots and valid changes | 10/10 | 10/10 | 4/4 each |
| Counting Set: delegation, duplicates, bulk operations and removals | 6/6 | 6/6 | 4/4 each |
| Money: scale, hashing, currencies and exact arithmetic | 8/8 | 8/8 | 4/4 each |
| Export review: ordered effects, borrowed Writer, live view and partial failure | Static review | Static review | 4/4 each |
| **Total** | **38/38** | **38/38** | **24/24 each** |

Both conditions performed equally well. This run verifies the expanded guidance
can produce correct behavior on these cases; it does not demonstrate improvement
over the previous skill. The prompts specify many required behaviors explicitly,
and one generation per condition is insufficient to estimate reliability or
variance. All six cases share a context within each condition, so they are not
independent samples within that condition.

## Grading calibration

The initial source-only grade was 23/24 for each candidate: neither output
explicitly supplied its own Money hash-collection test. The user prompt requested
an implementation and notes, not a test artifact. The independent contract probes
then verified equal-key map lookup and set deduplication for both implementations.
After receiving those results under anonymous labels, the grader assigned 24/24
for the required code properties. Requiring author-supplied verification instead
would retain 23/24 each. Both static and final grading are preserved; the score
change does not reflect a code change or an advantage for either condition.

The harness was also checked against two deliberately broken copies: an accessor
leaking an owned array, and a ledger returning a backed map view instead of a
snapshot. The intended ownership probes rejected both. Original generated
candidates were not edited to achieve passing results.

## Reproduce the executable checks

Use a compatible JDK with the fixture release supported; no Maven or additional
libraries are required. From the repository root:

```sh
python3 tools/java-practices/verify_behavior.py \
  --outputs evals/java-practices-workspace/iteration-1/previous \
  --result /tmp/java-previous-contracts.json
python3 tools/java-practices/verify_behavior.py \
  --outputs evals/java-practices-workspace/iteration-1/updated \
  --result /tmp/java-updated-contracts.json
```

The harness compiles into temporary directories and leaves candidate sources
unchanged. It exits nonzero for a compilation or contract failure. Supply
`--java` and `--javac` to select the actual JDK executables explicitly. The
checked-in generated Java and prompts allow the same probe run to be repeated;
fresh model generations may differ.

To repeat the model comparison, provide each condition's archived skill snapshot,
case prompts and Parcel fixture in a separate fresh context. Request the named
source files/notes without revealing criteria or probe code. Grade anonymized
outputs independently, retain file/line evidence, and record sample count and
limitations. Do not substitute this comparison for the retained tooling evals.

## Evidence

All files below are receipts outside the canonical plugin:

- [Benchmark and methodology](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/benchmark.json)
- [Previous-skill outputs](https://github.com/ribrewguy/agent-skills/tree/main/evals/java-practices-workspace/iteration-1/previous) and [updated-skill outputs](https://github.com/ribrewguy/agent-skills/tree/main/evals/java-practices-workspace/iteration-1/updated), including skill snapshots
- [Previous contract results](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/previous-contracts.json) and [updated contract results](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/updated-contracts.json)
- [Static grading](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/grading-static.json), [final grading](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/grading.json), and [anonymous-label mapping](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/blind-mapping.json)
- [Broken-control results](https://github.com/ribrewguy/agent-skills/blob/main/evals/java-practices-workspace/iteration-1/control-results.json)

The four existing tooling prompt cases remain authored but were not rerun as
model evaluations in this iteration. Prior executable Maven enforcement evidence
is in the [JVM quality report](jvm-quality). No comparative claim is made about
unexercised book recommendations or all future Java code.
