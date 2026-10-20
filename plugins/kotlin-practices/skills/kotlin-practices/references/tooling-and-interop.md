# Kotlin tooling and mixed builds

Use during setup/upgrades or integration audits. Keep concrete tool release pins
in the consuming project; links below are discovery points, not promises that
their default page describes a stable release.

## Target and mixed compilation

Read [Kotlin compiler options](https://kotlinlang.org/docs/compiler-reference.html)
and the selected compiler's supported JVM options. Align JVM targets with Java
and constrain API availability with a supported release option or appropriate
compiler JDK. Test a call to a platform API above the intended runtime; bytecode
target alone is insufficient. Verify third-party dependencies and runtime paths.

The [Kotlin Maven configuration guide](https://kotlinlang.org/docs/maven-configure-project.html)
describes extensions and explicit execution wiring. Choose the method supported
by the pinned compiler; avoid combining snippets from incompatible releases.
For explicit wiring, make Kotlin compile first with Kotlin and Java source roots
visible, then compile Java against Kotlin output. Mirror this for test sources.
Disable/rebind default Java executions when necessary so they cannot run early.
Inspect effective configuration and logs; a successful compile can hide sources
that were never included. Test references in both directions and discover tests
written in both languages.

## ktlint and editor agreement

Resolve stable ktlint using [official releases](https://github.com/ktlint/ktlint/releases)
and consult [integrations](https://ktlint.github.io/ktlint/latest/install/integrations/).
Verify coordinates, main class and supported CLI flags against the selected
release; latest docs may show a new namespace or preview API. Track adapter and
engine versions independently. Spotless or a dedicated plugin is useful when it
supports the selected engine; a separately resolved CLI can address adapter lag.

When using Spotless, explicitly configure the ktlint engine and make its
EditorConfig overrides agree with the checked-in `.editorconfig`. Choose the
project's code style explicitly if adapter defaults differ. For CLI integration,
use an isolated tooling classpath instead of mixing the CLI's Kotlin libraries
with application dependencies. Propagate its nonzero exit.

Do not copy an integration that invokes `--format` during compile into normal
verification. Bind check mode to the required lifecycle; provide a separate
format command. Verify source/test patterns, generated exclusions and invocation
from the supported working directory. IDE and CI must use the same policy.

## detekt

Use detekt's [CLI](https://detekt.dev/docs/gettingstarted/cli/) or its documented
[Maven Ant integration](https://detekt.dev/docs/gettingstarted/mavenanttask/),
checking documentation for the selected stable release. An external process with
failure propagation can isolate tooling dependencies from the application.
Curate non-formatting rules and configure failure thresholds; do not let a report
or a tolerated issue count masquerade as enforcement.

[Type resolution](https://detekt.dev/docs/gettingstarted/type-resolution/)
requires the appropriate compilation classpath and target/JDK information.
Include compiled output and dependencies, and test classpaths for test analysis.
Keep tool-runtime dependencies separate from the analyzed classpath. Verify a
type-dependent finding where such rules are enabled. If the stable analyzer
cannot understand the project's compiler syntax/metadata, disclose the limitation
and choose a supported scoped solution; do not silently switch to previews or
claim syntax-only analysis provides full resolution.

## Coverage selection

JaCoCo can cover Kotlin bytecode; verify filtering of compiler-generated constructs
in the selected release. Kover is an alternative where its verified integration
satisfies the project. The [Kover Maven guide](https://kotlin.github.io/kotlinx-kover/maven-plugin/)
documents Maven-specific suite/agent limitations; check those before choosing it
for integration or child-JVM coverage. Do not assume its Gradle feature set or
combine JaCoCo and Kover instrumentation by default.

Prove Kotlin production classes contribute to the report, test names are
discovered, and removing a branch test or instrumentation fails the module gate.
For Maven, let `maven-practices` handle lifecycle/agent/data wiring. Kotlin-only
modules should not inherit Java source analyzers just because their output is
JVM bytecode; review bytecode-tool signal deliberately in mixed modules.
