---
title: maven-practices
parent: Skills
nav_order: 10
---

# maven-practices

Reproducible Maven builds and effective lifecycle enforcement across modules, profiles and test JVMs.

## Key opinions

- Use the committed Maven Wrapper and project-owned plugin/engine pins.
- Prove inherited checks execute; pluginManagement and aggregate reports alone are insufficient.
- Run Surefire and both Failsafe goals through verify; preserve existing JVM arguments when adding coverage.
- Fail on missing coverage data and keep normal formatting checks nonmutating.

## Workflows

Audit an existing setup, configure requested missing gates, or follow the configured
standards during ordinary development. Setup preserves compatible existing choices;
audit alone does not authorize policy changes.

## Install

```sh
/plugin marketplace add ribrewguy/agent-skills
/plugin install maven-practices@ribrewguy-skills
```

For other local agents, use the [canonical-home pattern](../concepts/canonical-home):
point `~/.agents/skills/maven-practices` at
`plugins/maven-practices/skills/maven-practices` in your clone, then use your agent's
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

- [Canonical SKILL.md](https://github.com/ribrewguy/agent-skills/blob/main/plugins/maven-practices/skills/maven-practices/SKILL.md)
- [Behavioral eval cases](https://github.com/ribrewguy/agent-skills/blob/main/plugins/maven-practices/skills/maven-practices/evals/evals.json)
- [Family verification](../evals/jvm-quality)
