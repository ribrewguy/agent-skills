---
title: kotlin-practices
parent: Skills
nav_order: 12
---

# kotlin-practices

Kotlin JVM targets, ktlint, detekt, coverage and reliable Java interoperability.

## Key opinions

- Constrain Java API availability as well as Kotlin JVM bytecode targets.
- Resolve current stable compatible ktlint at setup/upgrades; track adapter and engine pins separately.
- Align IDE formatting with .editorconfig and verify detekt type resolution for selected rules.
- Prove both-language compilation/test discovery and select one verified coverage implementation.

## Workflows

Audit an existing setup, configure requested missing gates, or follow the configured
standards during ordinary development. Setup preserves compatible existing choices;
audit alone does not authorize policy changes.

## Install

```sh
/plugin marketplace add ribrewguy/agent-skills
/plugin install kotlin-practices@ribrewguy-skills
```

For other local agents, use the [canonical-home pattern](../concepts/canonical-home):
point `~/.agents/skills/kotlin-practices` at
`plugins/kotlin-practices/skills/kotlin-practices` in your clone, then use your agent's
[installation instructions](../install/). Plugin namespacing varies by agent.

## Composition

Use `jvm-quality` with the applicable language skill(s) and `maven-practices`
for Maven projects. Mixed Java/Kotlin Maven builds use all four. Kotlin Gradle
projects use shared/Kotlin guidance with their existing Gradle integration.
Companion plugins are installed separately; no cross-plugin filesystem links
are required by the skill files.

Once installed, add an applicable JVM instruction to the consuming project's
shared agent guidance; see [adoption guidance](https://github.com/ribrewguy/agent-skills/blob/main/plugins/jvm-quality/skills/jvm-quality/references/adoption-and-verification.md).
Installation alone does not guarantee a skill is applied.

## Source and evaluation

- [Canonical SKILL.md](https://github.com/ribrewguy/agent-skills/blob/main/plugins/kotlin-practices/skills/kotlin-practices/SKILL.md)
- [Behavioral eval cases](https://github.com/ribrewguy/agent-skills/blob/main/plugins/kotlin-practices/skills/kotlin-practices/evals/evals.json)
- [Family verification](../evals/jvm-quality)
