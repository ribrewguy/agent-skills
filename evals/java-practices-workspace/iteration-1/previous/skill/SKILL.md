---
name: java-practices
description: Audit, configure, and follow Java compilation, formatting, style, correctness, and security analysis practices. Use for Java source or Java tooling changes, with build wiring delegated to the project's build tool.
---

# Java practices

Own Java language/tool choices. `jvm-quality` owns shared testing, coverage,
runtime and version policy; `maven-practices` owns Maven integration when used.
Apply Java source rules to Java sources, including applicable tests. Do not
apply them to Kotlin-only modules.

## Choose the workflow

- **Audit:** inspect Java production/test roots, generated sources, runtime/API
  target, build JDK, compiler warnings, formatter, style rules, analyzer rules,
  exclusions and actual CI execution. Identify each ineffective gate precisely.
- **Configure:** preserve compatible existing choices; close authorized gaps
  using [tool selection and integration](references/tooling.md). Align tools
  with the actual compiler JDK and project syntax. Verify isolated violations
  fail, formatter output passes style checks, and tests are included in style.
- **Develop:** follow existing formatting and warning rules, test changed
  behavior, address selected findings, and run project verification. Keep broad
  reformatting and unrelated tool upgrades out of feature work.

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

Report configuration paths, selected rule ownership, complete verification
command/results, known findings/exceptions, and compatibility limits. Verify
formatting changes are intentional and the normal check command is nonmutating.
