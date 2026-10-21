---
title: jvm-quality
parent: Skills
nav_order: 9
---

# jvm-quality

Shared JVM quality policy for tests, module coverage, runtime compatibility, exceptions and dependency vulnerability scanning.

## Key opinions

- Coverage is enforced per module, with current data and explicit treatment of empty modules.
- Build JDK, supported runtime, bytecode target and API compatibility are separate decisions.
- Existing projects adopt measured floors without broad exclusions or blanket formatting churn.
- Tool versions are resolved during setup/upgrades and pinned in consuming projects, never encoded in the skill.

## Workflows

Audit an existing setup, configure requested missing gates, or follow the configured
standards during ordinary development. Setup preserves compatible existing choices;
audit alone does not authorize policy changes.

## Install

```sh
/plugin marketplace add ribrewguy/agent-skills
/plugin install jvm-quality@ribrewguy-skills
```

For other local agents, use the [canonical-home pattern](../concepts/canonical-home):
point `~/.agents/skills/jvm-quality` at
`plugins/jvm-quality/skills/jvm-quality` in your clone, then use your agent's
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

- [Canonical SKILL.md](https://github.com/ribrewguy/agent-skills/blob/main/plugins/jvm-quality/skills/jvm-quality/SKILL.md)
- [Behavioral eval cases](https://github.com/ribrewguy/agent-skills/blob/main/plugins/jvm-quality/skills/jvm-quality/evals/evals.json)
- [Family verification](../evals/jvm-quality)
