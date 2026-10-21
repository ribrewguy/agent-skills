---
name: maven-practices
description: Audit, configure, and maintain reproducible Maven builds and lifecycle quality gates, including reactor inheritance, Surefire/Failsafe, coverage agents, profiles, and required CI verification. Use for POM, wrapper, or Maven build changes.
---

# Maven practices

Own Maven mechanics. Use `jvm-quality` for coverage/exception/version policy and
the applicable language skills for compiler and analyzer choices. If companions
are unavailable, identify the policy gap rather than inventing project floors
or language standards. Do not upgrade tools during unrelated feature work.

## Audit, configure, develop

**Audit:** read instructions, wrapper, parent and child POMs, `.mvn/`, settings
assumptions, test suites and required CI. Identify aggregation versus inheritance,
active profiles, build JDK/toolchains, plugin declarations, executions and skips.
Inspect effective POMs for representative modules and actual lifecycle logs.

**Configure:** implement requested gaps while preserving compatible project
choices. Use [lifecycle and reactor guidance](references/lifecycle-and-reactors.md)
for binding checks, Enforcer, profiles and CI. Use
[coverage wiring](references/coverage-wiring.md) for JaCoCo, test JVM arguments,
integration/child JVMs, freshness and missing-data guards.

**Develop:** use the wrapper and documented profiles. Run the full required gate
before reporting completion; targeted module checks are useful during iteration
but do not substitute for required reactor checks. Do not weaken checks to pass.

## Build invariants

- Commit Maven Wrapper scripts and configuration for the chosen distribution;
  pin dependencies, BOMs, build plugins and independently configurable engines
  in the project. Generate wrapper files with the official wrapper tooling.
  Do not rely on an agent's globally installed Maven or implicit plugin releases.
- Use Enforcer for supported Maven and tool JDK versions. Evaluate convergence,
  upper bounds, duplicate declarations/classes and dependency bytecode rules
  against project needs; these rules are not interchangeable or all compatible
  with every dependency-management strategy.
- Centralize configuration, then prove intended children execute it.
  `pluginManagement` supplies defaults; it does not by itself schedule arbitrary
  quality plugins. Aggregating a module does not make the aggregator its parent.
- Bind failing **check** goals into the build lifecycle, not just report goals
  into `reporting`/`site`. Bind only checks to normal verification; formatting or
  automatic fixes get a separate, explicit local command.
- Use Surefire for unit tests and both Failsafe `integration-test` **and** `verify`
  for integration tests. Verify naming/provider discovery and useful test counts.
  Do not invoke `integration-test` as the final CI command: failure checking and
  teardown must complete through `verify`.
- Prefer `./mvnw -B -ntp verify`. If profiles are required, document the complete
  command and execute it explicitly in required CI. Do not let JDK activation
  silently remove quality gates from all required jobs.
- Preserve existing JVM flags and other agents when adding coverage. Separate
  agent properties by suite, use late evaluation where needed, and initialize
  empty properties for supported noninstrumented paths. Forked/child JVMs need
  explicit coverage propagation; avoid concurrent writers to one data file.
- Collect integration coverage deliberately, then combine it or enforce separate
  checks. Reset intended data before the suites; detect missing/empty data and
  expected classes. Reports and aggregates are not threshold enforcement.
- Make empty POM/test-only modules explicit exceptions to code coverage rather
  than applying production-code guards indiscriminately across the reactor.

## Evidence before completion

Run a clean reactor gate, the canonical incremental gate, and isolated negative
cases appropriate to the change. Show that formatting, selected analyzer
findings, failed integration tests and inadequate/missing coverage return
nonzero for the intended reason. Check inherited execution, profile activation,
test discovery, JVM argument preservation and source immutability. Keep fixture
versions in fixture/project configuration, never in skill instructions.
