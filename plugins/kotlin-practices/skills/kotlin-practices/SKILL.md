---
name: kotlin-practices
description: Audit, configure, and follow Kotlin JVM compiler, ktlint formatting, detekt analysis, coverage, and Java interoperability practices. Use for Kotlin JVM source or tooling changes in Maven or other JVM builds.
---

# Kotlin practices

Own Kotlin JVM language/tool choices. `jvm-quality` owns shared testing, coverage,
runtime and version policy. `maven-practices` owns Maven lifecycle mechanics.
Use the project's integration for other build tools; do not migrate to Maven
or invent a required Gradle companion skill.

## Audit, configure, develop

**Audit:** read project instructions, compiler configuration, Kotlin and Java
production/test roots, runtime targets, `.editorconfig`, formatter/analyzer
configuration, coverage engine, baselines and CI. Inspect executed tests and
gates, not just declared plugins.

**Configure:** preserve compatible existing integrations and close requested
gaps. Read [Kotlin tooling and mixed builds](references/tooling-and-interop.md)
for target constraints, ktlint/detekt integration, compilation ordering and
coverage selection. Verify a clean build plus isolated deliberate violations.

**Develop:** use existing style, add tests for changed behavior, address findings
and run required project verification. Do not upgrade tooling, regenerate
baselines or reformat unrelated code as a side effect.

## Kotlin requirements

- Align Kotlin JVM bytecode target with the Java target and supported runtime.
  A `jvmTarget` alone permits references to newer JDK APIs. Constrain Java API
  availability using a supported compiler release option or appropriate JDK
  toolchain, then verify on the supported runtime. Check availability/limitations
  of compiler flags in the selected release.
- Use **ktlint** for Kotlin formatting/style and **detekt** for complementary
  analysis. Keep `.editorconfig`, IDE formatting and automated formatting in
  agreement. Normal verification checks without rewriting files; local fixes
  use a separate explicit command. Include applicable production/test Kotlin
  roots and deliberately selected Kotlin scripts.
- At setup or explicit upgrades, resolve current stable compatible ktlint from
  official releases. Distinguish the ktlint engine from its Maven/Gradle/Spotless
  integration version. If an adapter lags the engine, verify a compatible adapter
  or isolated CLI integration rather than silently using its old default.
  Project configuration holds the exact pins; skill text has no release pins.
- Curate detekt rules for useful signal. Do not enable its formatting rules on
  top of ktlint without deliberate ownership. Baselines are reviewed adoption
  debt, not a command to rerun whenever verification fails.
- Verify analyzer/compiler syntax compatibility and configured type resolution
  for rules that need it. Provide the selected tool's expected compile/test
  classpaths, output directories, JDK and target; a successful syntax-only scan
  does not prove type-dependent rules ran.
- In mixed builds, prove Java-to-Kotlin and Kotlin-to-Java references compile,
  both test languages are discovered, and default build executions do not run
  Java compilation prematurely. Keep Java-specific source analysis confined to
  Java sources. JVM bytecode analysis needs language-specific signal review.
- Select **one** coverage implementation deliberately: JaCoCo or Kover according
  to verified build integration, suite support and Kotlin filtering needs.
  Confirm Maven-specific limitations rather than assuming Gradle capabilities
  carry across. Avoid redundant instrumentation. Apply the shared module floors,
  missing-data and exception policy from `jvm-quality`.

## Evidence

Show formatter and detekt findings cause the canonical gate to fail, without
mutating sources. Show test discovery, mixed-language compilation where relevant,
supported-runtime/API verification and coverage of actual Kotlin production
classes. Disclose unsupported syntax, type-resolution or coverage-suite gaps;
do not hide them by adding broad exclusions or disabling checks.
