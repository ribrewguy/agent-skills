---
name: java-practices
description: Write and review Java using the owner's Joshua Bloch-inspired preferences for immutability, defensive boundaries, small APIs, composition, and explicit contracts. Also audit Java compiler, formatter, and analyzer gates; delegate build wiring to the project's build tool.
---

# Java practices

Own Java code design and language/tool choices. The owner's default is Joshua
Bloch's Effective Java approach: protect invariants, minimize mutable state and
API surface, and make correct usage straightforward. Apply these preferences
when writing or reviewing Java, even when all tool checks already pass.
`jvm-quality` owns shared testing, coverage,
runtime and version policy; `maven-practices` owns Maven integration when used.
Apply Java source rules to Java sources, including applicable tests. Do not
apply them to Kotlin-only modules.

## Choose the workflow

- **Audit:** inspect Java production/test roots, generated sources, runtime/API
  target, build JDK, compiler warnings, formatter, style rules, analyzer rules,
  exclusions and actual CI execution. Review object ownership and API contracts
  as well as gates. Identify concrete violations and explain their effects.
- **Configure:** preserve compatible existing choices; close authorized gaps
  using [tool selection and integration](references/tooling.md). Align tools
  with the actual compiler JDK and project syntax. Verify isolated violations
  fail, formatter output passes style checks, and tests are included in style.
- **Develop:** apply the design defaults below, follow existing formatting and
  warning rules, test changed behavior, and run project verification. Keep broad
  reformatting and unrelated tool upgrades out of feature work.

## Java design defaults

Read [design and defensive boundaries](references/design-and-defensive-boundaries.md)
when designing, implementing or reviewing Java objects and APIs. It expands the
following preferences into ownership rules, tradeoffs and verification probes.

- **Favor immutable values.** Fully establish invariants at construction; use
  private final state and control subclassing. Prefer records for suitable
  transparent values on supported releases. A final reference or record does
  not make referenced arrays, collections or elements immutable.
- **Own mutable state at boundaries.** Snapshot mutable inputs before validating
  the retained values, and prevent mutable outputs from exposing internals.
  Distinguish a backed unmodifiable view, a shallow snapshot and ownership of
  nested elements. Copy only where ownership requires it; immutable values can
  be shared. Do not trust an arbitrary subtype's `clone()` as a defensive copy.
- **Validate before changing observable state.** Check arguments explicitly at
  public boundaries, document null/range rules, and preserve invariants when an
  operation fails. Assertions are not public-input validation. Keep purposeful
  mutation contained rather than forcing immutable redesigns on every class.
- **Keep APIs small.** Use the least visibility needed. Prefer composition and
  delegation for reuse; subclass only an intentional extension contract. Inject
  external dependencies where it makes behavior explicit and testable. Choose
  factories/builders when they clarify creation, not as mandatory ceremony.
- **Honor value contracts.** Keep equality and hashing consistent; stable map
  keys must not change identity state. Align ordering with equality or document
  a deliberate distinction. Handle array contents and decimal scale deliberately;
  generated methods do not automatically express domain equality.
- **Use meaningful types and honest results.** Prefer generics, interfaces and
  domain types over raw collections, magic flags and strings. Represent empty
  collections with empty results; use Optional for meaningful absent single
  results, not indiscriminately. Use decimal/integer representations for exact
  amounts with explicit rounding policy.
- **Make effects explicit.** Release owned resources with try-with-resources,
  preserve useful exception context, keep stream operations understandable and
  avoid shared mutable state in pipelines. State thread-safety/ownership contracts
  for shared objects instead of assuming final fields solve concurrency.

Preserve project compatibility and established public contracts. Explain a
necessary exception rather than mechanically applying every preference or doing
unrelated refactors. Formatters and analyzers support these decisions; ownership,
aliasing, invariants and failure behavior need code review and behavioral tests.

## Compilation

Set an explicit release/API target, not only source and bytecode versions.
For javac, prefer `--release` when available and appropriate; prove a reference
to an API newer than the supported runtime is rejected. Check third-party
dependency compatibility separately.

Enable compiler warnings and fail on the selected warning set, for example
project-selected `-Xlint` categories with `-Werror`. Justify narrow exceptions;
do not silence all warnings to compensate for a generated or legacy source.
Make annotation-processor discovery explicit when required by the build JDK.

## Formatting and analysis

| Responsibility | Suggested tool | Decision constraint |
|---|---|---|
| Deterministic layout | Spotless with google-java-format | One formatter; preserve an existing compatible formatter/style |
| Source conventions | Checkstyle | Agree with formatter output; include Java production and test roots |
| Compile-time correctness | Error Prone | Compatible javac runtime, internals access, processor setup and project target |
| Bytecode correctness | SpotBugs | Check goal must fail on selected findings; verify bytecode support |
| Security bug patterns | FindSecBugs with SpotBugs | Compatible detector/engine combination; supplement dependency scanning |
| Additional source/design/duplication rules | Curated PMD/CPD | Add useful signal with clear ownership, not every rule by default |

This is a suggested stack, not a mandate to replace every existing tool.
Curate overlaps: formatter owns layout, Checkstyle owns selected source
conventions, analyzers own chosen correctness/security concerns. Do not stack
contradictory whitespace/import rules or duplicate the same rule everywhere.

Generated-source exclusions must name the actual generation boundary and reason.
Use individual, justified suppressions when a finding is false or intentionally
accepted. Shared exception and coverage policy belongs to `jvm-quality`.

## Tool compatibility and evidence

At setup/upgrades, resolve current stable compatible releases from official
sources and store exact pins in the project. Keep plugin and engine versions
distinct. No tool release numbers belong in this skill's examples.

Error Prone and google-java-format use compiler internals: check their current
runtime requirements and the actual JDK invoking them. In-process compiler
exports belong to the build JVM; forked javac needs its own JVM arguments.
Do not copy flags or obsolete compiler adapters without confirming applicability.

For code changes, show tests for relevant aliasing, invalid input, failure-state
preservation and equality/hash behavior. Include negative/control cases that
confirm intentional mutation and valid extension contracts are preserved.
Report configuration paths, selected rule ownership, complete verification
command/results, known findings/exceptions, and compatibility limits. Verify
formatting changes are intentional and the normal check command is nonmutating.
