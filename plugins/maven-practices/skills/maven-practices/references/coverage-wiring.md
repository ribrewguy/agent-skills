# Coverage wiring

Use for Maven test instrumentation. Shared thresholds and exception policy belong
to `jvm-quality`; this reference implements them with JaCoCo. Resolve plugin
versions in the consuming project and inspect documentation for that release.

## Preserve arguments and distinguish suites

JaCoCo [prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html)
sets a property for the test JVM. A dedicated property avoids overwriting existing
`argLine` settings. This fragment illustrates one unit-test suite, not a complete
coverage configuration:

```xml
<properties>
  <coverage.unit.args></coverage.unit.args>
  <test.jvm.args></test.jvm.args>
</properties>
<!-- Under build/plugins; all version properties are project-owned pins. -->
<plugin>
  <groupId>org.jacoco</groupId>
  <artifactId>jacoco-maven-plugin</artifactId>
  <version>${jacoco.version}</version>
  <executions>
    <execution>
      <id>coverage-unit-agent</id>
      <goals><goal>prepare-agent</goal></goals>
      <configuration>
        <propertyName>coverage.unit.args</propertyName>
        <destFile>${project.build.directory}/coverage-unit.exec</destFile>
      </configuration>
    </execution>
  </executions>
</plugin>
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>${surefire.version}</version>
  <configuration>
    <argLine>@{coverage.unit.args} ${test.jvm.args}</argLine>
  </configuration>
</plugin>
```

Move existing test JVM flags/agents into the preserved project property or compose
with the actual existing properties; do not drop them while copying this fragment.
Late evaluation allows a property populated during the lifecycle to reach the
forked JVM; empty defaults avoid literal unresolved property tokens when the agent
is deliberately inactive. A required coverage guard must still reject an
unintentionally inactive agent. Check Surefire/Failsafe property behavior for the
selected versions and verify with a sentinel JVM property or existing agent.

Use a separate integration agent property/data path, with `prepare-agent-integration`
or an explicitly bound `prepare-agent`, and compose Failsafe's JVM arguments too.
Instrument child application JVMs explicitly when those are the coverage target;
Surefire's arguments do not automatically reach `ProcessBuilder` children.

## Data lifecycle and concurrency

1. Before suites, remove the intended raw data and report outputs or guarantee a
   clean isolated workspace. Normal incremental verification must also avoid
   accepting old data after tests/agents are disabled.
2. Ensure each fork/child has a safe output strategy. Use unique data files per
   concurrent writer and a deliberate merge/dump step. Append mode does not make
   concurrent writes to one file a safe general solution.
3. At verify, require each expected suite's nonempty raw data. Merge intended
   files or use suite-specific checks; never let a surviving unit file hide a
   missing required integration file.
4. Generate reports for the intended production class directories, then require
   expected classes and nonzero applicable counters. This catches files containing
   only agent session data, overbroad exclusions or the wrong analyzed module.
5. Execute explicit line/branch threshold checks for each production module.
   Check aggregate requirements separately if the project has them.

JaCoCo's [check goal](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
supports explicit counters/limits, but missing data can cause the goal to skip.
Neither setting a high floor nor generating an aggregate report repairs that.
See the project's [check implementation](https://github.com/jacoco/jacoco/blob/master/jacoco-maven-plugin/src/org/jacoco/maven/CheckMojo.java)
and confirm behavior in the resolved stable release; trunk documentation may be
ahead of it.

An additional bound guard can use Ant or a repository script. For example,
an Ant condition inside an already configured Maven Antrun `run` execution can
require one raw data file (repeat for each required suite):

```xml
<fail message="Required unit coverage data missing or empty">
  <condition>
    <not><and>
      <available file="${project.build.directory}/coverage-unit.exec"/>
      <length file="${project.build.directory}/coverage-unit.exec"
              length="0" when="greater"/>
    </and></not>
  </condition>
</fail>
```

File presence/size is only one guard. Also validate the report's module/class
population, suite discovery and relevant counters. Configure guards only in
modules/suites requiring coverage; use explicit reasons for other module types.

## Reactor and failure proof

`report-aggregate` collects data/classes according to its dependency relationships;
it does not automatically run module threshold checks. Confirm that cross-module
tests contribute to the intended production modules and that a poorly covered
module fails despite a healthy reactor total.

Prove unit-only and integration-only code is measured. Then, independently, fail
an IT, remove a branch assertion, remove unit instrumentation, remove integration
instrumentation, and rerun after a prior green build. Require the intended
diagnostic/nonzero exit rather than any failure. Confirm supported skip/debug
paths have resolved JVM arguments, while the full gate still rejects missing
required tests or coverage.
