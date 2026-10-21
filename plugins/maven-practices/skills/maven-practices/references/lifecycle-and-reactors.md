# Lifecycle and reactors

Use when configuring or auditing Maven gates. All version properties in examples
must be resolved and pinned in the consuming project; snippets are fragments,
not a universal POM.

## Execution map

| Concern | Typical execution | Evidence |
|---|---|---|
| Build/dependency policy | Enforcer `enforce` at validate | Deliberate applicable violation fails |
| Formatting | Spotless `check` at verify | Check fails without source edits; `spotless:apply` is separate |
| Java style | Checkstyle `check` | Selected source/test violation fails |
| Java compile analysis | javac with Error Prone | Selected finding fails compilation |
| Java bytecode/security | SpotBugs `check` with selected detectors | Finding fails, not just appears in a report |
| Curated Java source/duplication | PMD `check`, CPD `cpd-check` | Selected findings fail |
| Kotlin analysis | Verified detekt Maven adapter, CLI or Ant integration | Nonzero tool exit propagates |
| Unit tests | Surefire `test` | Expected tests discovered |
| Integration tests | Failsafe `integration-test` and `verify` | Failed IT makes final verify nonzero |
| Coverage | Collect, report, presence/population guards, threshold checks | Missing data and low coverage fail |

These bindings implement selected project policy; do not install every optional
analyzer indiscriminately. Use the language skill's compatibility/rule decisions.
The official [Maven lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
defines execution ordering. Goals in the same phase run in effective declaration
order; do not put a data guard before the report it needs.

The [Failsafe documentation](https://maven.apache.org/surefire/maven-failsafe-plugin/)
explains why both goals matter. A focused fragment:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>${failsafe.version}</version>
  <executions>
    <execution>
      <goals><goal>integration-test</goal><goal>verify</goal></goals>
    </execution>
  </executions>
</plugin>
```

Use the project's test naming/includes and provider. For code modules where a
suite is mandatory, configure missing-test failure or equivalent count checks.
Do not force ITs into every module if integration tests deliberately live elsewhere.

## Inheritance and profiles

Inspect representative children with the wrapper's `help:effective-pom` and
`help:active-profiles`, using the same profiles as CI. Supply a project-resolved
help plugin version if it is not already managed. Compare effective executions
with build logs and reports for each expected module.

`pluginManagement` centralizes defaults for referenced plugins. Declare arbitrary
quality plugins in `build/plugins` with executions to schedule them. Check
inherited execution IDs, child overrides, `<inherited>false>`, skip properties,
aggregator-only goals and config file paths. A module listed in `<modules>` may
inherit from another parent; do not assume otherwise.

Apply source-specific plugins only in applicable modules, using shared managed
configuration with explicit module declarations when necessary. POM aggregators
and test-only modules need deliberate coverage/discovery treatment. Shared config
paths must resolve from both reactor and supported module-local invocations;
verify rather than relying on `${project.basedir}` to mean the reactor root.

Keep required gates active in an explicit required CI job. If using a quality
profile, document `./mvnw -B -ntp -Pquality verify` and execute that exact path.
Test supported JDK/profile combinations: JDK-activated tooling must not silently
disappear from all required jobs. Compatibility jobs may focus on runtime tests.

## Reproducibility and Enforcer

Generate and commit scripts/config with the official
[Maven Wrapper](https://maven.apache.org/tools/wrapper/), pin its distribution,
and use it locally and in CI. Pin build plugins/dependencies/BOMs and configurable
analysis engines independently. Review distribution checksums where supported.

[Enforcer](https://maven.apache.org/enforcer/maven-enforcer-plugin/) can constrain
tool versions and project dependencies. Choose rules intentionally:

- Convergence asks for consistent dependency versions across paths; upper-bound
  rules ask that resolved versions satisfy the relevant higher transitive versions.
  Neither automatically replaces the project's BOM strategy.
- Duplicate dependency declarations differ from duplicate classes in resolved
  artifacts; the latter may need an additional rule/provider.
- Dependency bytecode compatibility differs from the JDK that runs Maven.
  Check the chosen rule's scope, exclusions, multi-release JAR handling and release
  support before using it as proof of runtime compatibility.

Do not change dependency management merely to satisfy an unsuitable policy rule.
Make intentional exceptions explicit and prove the selected rules actually run.
