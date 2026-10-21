---
title: JVM quality family verification
parent: Evaluations
nav_order: 9
---

# JVM quality family verification

This family contains `jvm-quality`, `maven-practices`, `java-practices`, and
`kotlin-practices`. Validation uses real disposable Maven projects, independently
of the four authored behavioral prompts per skill. No with-skill/baseline model
benchmark or comparative pass rate is claimed.

## What is exercised

The fixture has Java-only, Kotlin-only and mixed Java/Kotlin production modules,
plus an empty POM module, under one reactor. The complete fixture command is:

```sh
./mvnw -B -ntp -Pquality,java-analysis verify
```

The profiles are explicit. The quality profile runs tests, formatting checks,
Java style where applicable, Kotlin analysis where applicable, and per-module
coverage with missing-data guards. The Java analysis profile adds Error Prone,
SpotBugs/FindSecBugs, and curated PMD/CPD only to the Java-bearing modules.
The complete reactor is checked both cleanly and incrementally. Individual
failure probes may select a module to isolate the intended diagnostic.

| Positive case | Required evidence |
|---|---|
| Clean and incremental full reactor | Exit zero with all selected profiles |
| Java-only | Unit and integration tests; Java formatting, style and selected analyzers |
| Kotlin-only | Kotlin tests, ktlint formatting and type-dependent detekt rule |
| Mixed Java/Kotlin | References in both directions compile; both test languages discovered |
| Empty POM module | Hygiene applies without requiring nonexistent production coverage |
| Coverage | Expected production classes and line/branch counters; module checks execute |
| Agent composition | Existing JVM sentinel property and a second real Java agent survive JaCoCo attachment |
| Child JVM | Explicit separate instrumentation, raw child data and merged production coverage |
| Effective configuration | Required inherited executions; no Java analyzers in the Kotlin-only module |
| Supported runtime | Separate test run on the fixture's supported runtime JDK |
| Local discovery | Four canonical links and 16 tool-specific links resolve in a disposable home |

Negative probes check nonzero exit **and the intended diagnostic**, rather than
counting unrelated build errors as success. They cover Java/Kotlin formatting,
integration failure, module coverage floors, missing agents, missing integration
coverage, skipped required tests, compiler warnings, above-target Java APIs in
both languages, detekt, Checkstyle on tests, Error Prone, SpotBugs, PMD and CPD.
Source hashes verify normal verification does not mutate source files. Each
mutation is restored, and positive verification runs again.

The small fixture reaches complete line/branch coverage with four unit tests
and four integration tests per full reactor run. Its floors, runtime JDK,
tooling JDK and formatting choices are test inputs, not universal standards.

## Reproduce

Prerequisites are Python, a bootstrap Maven, a compatible full build JDK with
`java`, `javac` and `jar` on PATH, and network access to Maven artifacts. The
bootstrap generates a real Maven Wrapper; subsequent fixture commands use it.
The Java analyzer fixture constrains its build JDK deliberately; inspect the
fixture generator and adapt that test input if verifying a different toolchain.

```sh
python3 tools/jvm-quality/verify.py --versions /tmp/jvm-versions.json --resolve-versions
# Review candidate releases and compatibility; adjust this fixture-owned JSON as needed.
python3 tools/jvm-quality/verify.py --versions /tmp/jvm-versions.json --output /tmp/jvm-fixture
python3 tools/jvm-quality/verify.py --versions /tmp/jvm-versions.json --existing /tmp/jvm-fixture --case mutations
python3 tools/jvm-quality/verify.py --versions /tmp/jvm-versions.json --existing /tmp/jvm-fixture --case java-analysis
```

Use a new output path: the harness refuses to overwrite an existing directory.
`--existing` requires its fixture ownership marker. The harness generates only
disposable test projects; it is not a universal POM installer for consuming
repositories. A failed probe restores source mutations and leaves logs for
investigation. Do not run concurrent cases against the same fixture directory.

`--case runtime` runs the supported-runtime unit-test path with the caller's
`JAVA_HOME`/PATH. This is a separate compatibility check, not a substitute for
the required full tooling-JDK gate. The fixture's tooling-JDK Enforcer check is
explicitly omitted on that compatibility path; application sources still compile
against the fixture's selected API target.

Version resolution selects stable candidates from Maven metadata; compatibility
verification is a separate step. During this run the newest formatter candidate
failed in the chosen adapter, while the preceding stable formatter passed. The
fixture JSON records that selection. Current ktlint was checked against official
stable releases rather than copied from preview integration docs. No tool release
numbers are embedded in the distributed skill instructions or examples.

## Evidence and limits

See the [verification summary](https://github.com/ribrewguy/agent-skills/blob/main/evals/jvm-quality-workspace/verification.json)
for command/exit/diagnostic results and the
[fixture inputs](https://github.com/ribrewguy/agent-skills/blob/main/evals/jvm-quality-workspace/versions.json)
for the dated historical toolchain. These files are test receipts outside the
plugins; they are not recommended release pins. Logs and report counters are
stored with those receipts. Skill metadata, local references, manifests, authored
eval structure and absence of tool release pins are checked separately.

This validates the exercised Maven integrations and selected common Java/Kotlin
syntax. It does not certify every compiler feature, detekt metadata combination,
rule, runtime or operating system. Kover and Gradle integrations are documented
selection paths, not executed alternatives in this fixture. Dependency
vulnerability policy is documented; no live dependency-database scan was run.
The original 16 tooling prompts are authored, not scored model evaluation
results. Subsequent Java design additions are evaluated separately in the
[Java design report](java-practices).

## Primary sources checked

The implementation research checked official documentation and stable releases
on 2026-10-20. Links in each skill reference route future setup/upgrade work back
to maintained primary sources; release-specific behavior still needs verification.

- [Maven lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html), [Failsafe](https://maven.apache.org/surefire/maven-failsafe-plugin/), [Enforcer](https://maven.apache.org/enforcer/maven-enforcer-plugin/), [Wrapper](https://maven.apache.org/tools/wrapper/)
- [JaCoCo Maven](https://www.jacoco.org/jacoco/trunk/doc/maven.html) and [check implementation](https://github.com/jacoco/jacoco/blob/master/jacoco-maven-plugin/src/org/jacoco/maven/CheckMojo.java)
- [Spotless Maven](https://github.com/diffplug/spotless/tree/main/plugin-maven), [google-java-format](https://github.com/google/google-java-format), [Checkstyle check](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html)
- [Error Prone](https://errorprone.info/docs/installation), [SpotBugs check](https://spotbugs.github.io/spotbugs-maven-plugin/check-mojo.html), [FindSecBugs](https://find-sec-bugs.github.io/), [PMD checks](https://maven.apache.org/plugins/maven-pmd-plugin/check-mojo.html)
- [Kotlin Maven](https://kotlinlang.org/docs/maven-configure-project.html), [ktlint releases](https://github.com/ktlint/ktlint/releases), [detekt type resolution](https://detekt.dev/docs/gettingstarted/type-resolution/), [Kover Maven](https://kotlin.github.io/kotlinx-kover/maven-plugin/)
