---
name: jvm-quality
description: Audit and configure JVM quality gates for tests, coverage, runtime compatibility, and dependency vulnerability policy. Apply during JVM development to follow existing gates without unrelated tooling upgrades. Compose with the relevant language and build skills.
---

# JVM quality

Own the shared quality policy for JVM projects. Build-tool skills implement the
policy; language skills choose compatible compilers, formatters, and analyzers.
Repository commands and required CI jobs enforce it. Loading a skill alone
does not establish an effective gate.

## Choose the workflow

- **Audit:** read repository instructions, build files, CI, source/test roots,
  exclusions and baselines. Identify languages, modules, generated sources,
  supported runtimes, build JDKs and the canonical verification command. Report
  missing or ineffective gates with configuration paths and execution evidence.
  An audit does not authorize changing project policy.
- **Configure:** when setup/fixes are requested, preserve compatible existing
  choices, close the identified gaps, and run both a clean build and isolated
  deliberate violations. Separate adoption work from feature changes.
- **Develop:** follow the project's established checks, add meaningful tests for
  changed behavior, and run applicable verification. Do not trigger unrelated
  formatter, compiler or analyzer migrations.

Use [adoption and verification](references/adoption-and-verification.md) when
establishing or assessing policy, coverage, exceptions or CI enforcement.

## Shared requirements

1. Record separately the JDK running tools, the application's supported runtime,
   and the bytecode/API target. A successful build on a newer JDK does not prove
   the application runs on its oldest supported runtime. Include dependency
   compatibility and execute appropriate runtime tests.
2. Require deterministic formatting checks, useful static analysis, meaningful
   unit/integration tests, and enforced coverage. Normal verification must not
   rewrite source files.
3. Set explicit **per-module** line and branch coverage floors where supported.
   An aggregate report must not hide an under-tested module. For existing code,
   measure coverage first and establish reviewed floors; there is no universal
   percentage. For new code, agree a meaningful standard with the project.
4. Require current coverage data from the intended suites and production
   classes. Missing instrumentation, empty reports, stale data or silently
   undiscovered tests must fail wherever coverage/tests are required.
5. Handle modules with no production code, no tests, or no applicable branches
   explicitly. Exempt an identified module category with a reason; do not turn
   missing evidence into a blanket success or exclude all difficult code.
6. Keep generated-code exclusions narrow and justified. Suppress the individual
   finding with a reason where possible. Review baselines and suppressions as
   code changes. Never lower floors, disable gates or widen exclusions merely
   to get green; deliberate policy changes need rationale and project authority.
7. Document one canonical verification command and execute it in required CI.
   Document mandatory profiles and separate scheduled gates. A compatibility
   matrix may run fewer analyzers when tool runtime requirements differ, but a
   required job must still run every quality gate on a compatible build JDK.
8. Define dependency vulnerability scan cadence, failure severity, data freshness
   handling, and reviewed exceptions with owners and expiry/review dates.

## Versions belong to projects

At initial setup or an explicit tooling upgrade, consult official releases and
migration/compatibility documentation, select current stable compatible tooling,
verify integration, and pin exact versions **in the consuming project**.
Track integration/plugin versions separately from configurable engine versions.
During normal development, use the existing pins. Do not store specific tool
release numbers in this skill or its examples, use floating build dependencies,
or describe an undated release as permanently latest. Preview documentation may
describe unreleased behavior; check the selected release.

## Composition and delivery

Select by actual source/build applicability:

| Project | Skills to apply |
|---|---|
| Java with Maven | jvm-quality, maven-practices, java-practices |
| Kotlin with Maven | jvm-quality, maven-practices, kotlin-practices |
| Mixed Java/Kotlin with Maven | All four |
| Kotlin with another build tool | jvm-quality, kotlin-practices; use the project's build integration |

These are named capabilities, not assumed co-installed files. If a companion is
unavailable, state the gap and use official documentation for the missing
mechanics. Keep build wiring out of shared policy and language rules out of
unrelated sources. Do not recursively route through companions already loaded.

Report changed configuration, commands/results, deliberate failure evidence,
remaining gaps and adoption impact. Distinguish authored, validated, installed
and published states.
