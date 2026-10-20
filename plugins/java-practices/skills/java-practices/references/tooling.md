# Java tool selection and integration

Use during setup/upgrades and audits. Resolve current stable compatible releases
from the official sources below, pin in the project, and consult release-specific
documentation. Existing effective tooling takes precedence over a gratuitous
migration to the suggested stack.

## Compilation and formatter agreement

[Compiler release configuration](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
shows how javac constrains language, bytecode and platform APIs together. Use the
project's selected target and selected warnings with failure enabled. Third-party
dependency bytecode still needs separate compatibility checks.

[Spotless Maven](https://github.com/diffplug/spotless/tree/main/plugin-maven)
supports separate check/apply goals and formatter engine configuration.
[google-java-format](https://github.com/google/google-java-format) documents its
runtime/compiler-internals requirements. Keep integration and formatter pins
separate in the project. Limit source patterns to applicable Java production/test
roots and justified generation exclusions.

[Checkstyle check](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html)
is a failing build goal; configure test sources explicitly where required and
select effective severity/failure settings. A supplied style configuration can
contain advisory warnings that the plugin does not fail on by default. Check
severity thresholds, not just `failOnViolation`.

Do not assume a formatter's advertised style and an entire Checkstyle preset are
mutually consistent. Start with project conventions and a focused ruleset; format
representative production/test code including imports, Javadoc and long lines,
then run the style check. Reconcile any incompatible rule with a documented owner
instead of repeatedly reformatting or broadly suppressing files.

## Complementary analyzers

[Error Prone installation](https://errorprone.info/docs/installation) documents
compiler setup, current build-JDK requirements, processor paths and exports/opens.
Run on a supported compiler JDK while retaining the project's release target.
Keep existing annotation processors when adding its processor path. In-process
javac needs access in the build JVM; forked javac needs its own JVM arguments.
Promote selected checks to errors and verify an actual finding fails.

[SpotBugs check](https://spotbugs.github.io/spotbugs-maven-plugin/check-mojo.html)
must enforce selected findings, not only emit XML. Match parser/bytecode support
to the compiled classes and add [FindSecBugs](https://find-sec-bugs.github.io/)
for selected security patterns. Identify exact detector/engine pins in project
configuration; prefer scoped source suppressions with justifications over broad
class/package filters. Coverage policy and dependency vulnerability scans remain
separate concerns.

[PMD Maven usage](https://maven.apache.org/plugins/maven-pmd-plugin/usage.html)
distinguishes reports from build checks. Curate a version-compatible ruleset and
bind `check` and, when adopted, `cpd-check`. Assign ownership of overlapping rules,
configure production/test treatment, and calibrate duplication thresholds to real
project patterns rather than importing every rule.

## Useful probes

In disposable fixtures, introduce separately a forbidden platform API, a selected
compiler warning, formatter drift in a test, a selected Checkstyle violation and
one finding per adopted analyzer. Verify the canonical project gate returns
nonzero with the expected diagnostic. Restore changes between probes; one early
formatter error must not mask whether later analyzers work. Record the actual
JDK, source roots, test discovery and any unsupported analyzer combinations.
