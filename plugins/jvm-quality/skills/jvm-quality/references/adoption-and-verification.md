# Adoption and verification

Use this during audits, setup, adoption, or quality-policy changes. Record the
project's decisions alongside its build instructions; this skill supplies no
universal runtime, style, percentage, vulnerability cutoff or tool release.

## Establish the policy

Inventory each module: languages, packaging, production/test roots, generated
outputs, unit/integration/child-JVM suites, supported runtimes, and required CI
jobs. Separate declared configuration from observed execution. For each gate
record its command, applicable modules, selected rules/thresholds, exclusions,
failure behavior, and evidence location.

For existing projects, measure a clean baseline before changing floors. Agree
module floors and a plan for improving debt; preserve effective compatible
tooling. Avoid blanket formatting churn or sweeping new suppressions. New
projects can start with stricter agreed standards; do not invent a universal
coverage number or treat high coverage as a substitute for useful assertions.

Record exception scope, reason, owner and review/expiry date. Changes to floors,
suppression baselines or exclusion boundaries are policy changes, not build
repairs. Obtain the authority required by the project before making them.

## Coverage evidence

| Module condition | Required treatment |
|---|---|
| Production code with tests | Enforce explicit module line/branch floors and fresh expected data |
| Production code without tests | Report missing tests; fail when project policy requires tests/coverage |
| No production code, such as an aggregator | Explicitly mark coverage inapplicable; still run applicable hygiene checks |
| Test-only module | Verify discovery and intended coverage relationship to production modules |
| Production code without branch counters | Enforce line floor; document branch inapplicability without division by zero |
| Generated code | Exclude only identified generated outputs with a reason; retain handwritten boundaries |

Check both raw execution data and the analyzed population: a nonempty file can
contain only agent metadata or unrelated classes. Require expected production
classes and nonzero applicable counters, and validate executed suite counts.
Reset data before required suites or build cleanly in disposable CI so previous
test runs cannot satisfy the current gate. Removing instrumentation must fail
even after a previous successful run.

For combined unit/integration coverage, prove each suite contributes by checking
code exercised only by that suite. For separate floors, name both data sets and
their checks. An aggregate HTML/XML report alone enforces nothing; retain module
checks or explicitly map cross-module tests into equivalent module enforcement.

## Prove gates rather than trusting reports

In isolated temporary copies, run the complete documented command after:

1. Introducing a formatting violation; require failure and unchanged source bytes.
2. Introducing a selected analyzer finding; require its diagnostic and nonzero exit.
3. Failing an integration test; require final verification failure after teardown.
4. Leaving a production branch untested; require that module's threshold failure.
5. Removing instrumentation or skipping required tests; require missing/current-data
   or discovery failure, including an incremental run after a previous green build.

Do not interpret an unrelated dependency-download or compiler error as proof the
intended gate works. Restore each mutation, run a clean positive case and retain
commands, exit codes, suite counts and relevant diagnostics. Check multi-module
execution and required-profile CI activation separately.

## Dependency vulnerabilities and runtime compatibility

Define the scanner, cadence, required job, severity/failure policy, data freshness
expectation and outage behavior. Distinguish a successful scan with no findings
from a skipped scan or unavailable database. Reviewed exceptions identify the
dependency/finding, justification, owner and review date. Do not bake a specific
CVSS cutoff into a reusable skill. See the official
[Dependency-Check Maven guidance](https://dependency-check.github.io/DependencyCheck/dependency-check-maven/)
for one implementation; equivalent existing scanners can satisfy the policy.

Test the application on its supported runtime, including dependencies. Compilation
targets do not validate every dependency or reflective/runtime path. Keep build
JDK requirements for analyzers separate from application runtime requirements.

## Adoption instruction for local agents

Once the skills are available through the agent's supported discovery mechanism,
add an applicable instruction to the consuming project's shared guidance:

> For JVM changes, apply `jvm-quality`, the relevant `java-practices` and/or
> `kotlin-practices`, and `maven-practices` when the project uses Maven. Follow
> the repository's pinned tooling and canonical verification command. Tooling
> upgrades require an explicit setup/upgrade task.

Adapt names only if the installed discovery mechanism namespaces them. Confirm
availability instead of assuming skill installation means automatic application.
