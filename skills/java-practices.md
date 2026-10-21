---
title: java-practices
parent: Skills
nav_order: 11
---

# java-practices

Bloch-inspired Java design: immutability, defensive boundaries, small APIs, value contracts and composition, alongside compiler, formatter and analyzer practices.

## Key opinions

- Favor immutable values with owned mutable components; records and unmodifiable wrappers alone do not establish immutability.
- Validate retained state and preserve invariants on failure, while keeping purposeful mutation and existing API contracts.
- Prefer small APIs and composition; keep value equality, hashing, ordering and exact amounts consistent.
- Set an explicit Java release/API target and a selected failing compiler-warning policy.
- Choose one formatter and make Checkstyle agree with its output, including test sources.
- Use complementary analyzers with clear rule ownership and verified build-JDK compatibility.
- Preserve effective existing tools; avoid unrelated upgrades and formatting churn.

## Workflows

Audit an existing setup, configure requested missing gates, or follow the configured
standards during ordinary development. Setup preserves compatible existing choices;
audit alone does not authorize policy changes.

## Install

```sh
/plugin marketplace add ribrewguy/agent-skills
/plugin install java-practices@ribrewguy-skills
```

For other local agents, use the [canonical-home pattern](../concepts/canonical-home):
point `~/.agents/skills/java-practices` at
`plugins/java-practices/skills/java-practices` in your clone, then use your agent's
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

- [Canonical SKILL.md](https://github.com/ribrewguy/agent-skills/blob/main/plugins/java-practices/skills/java-practices/SKILL.md)
- [Behavioral eval cases](https://github.com/ribrewguy/agent-skills/blob/main/plugins/java-practices/skills/java-practices/evals/evals.json)
- [Java design behavior evaluation](../evals/java-practices)
- [Family tooling verification](../evals/jvm-quality)
