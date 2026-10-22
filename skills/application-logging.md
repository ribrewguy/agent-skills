---
title: application-logging
parent: Skills
nav_order: 13
---

# application-logging

For adding or reviewing logging in any server code. It decides what an application logs, at which level, in which shape, and which values never appear. It stands alone: a project with no OpenTelemetry still gets the console appender, the field rules, and the level rules.

## What makes this skill distinct

- **Two appenders with different jobs.** A single-line console appender for humans (with a `LOG_FORMAT=json` switch for platforms that scrape stdout), and an OpenTelemetry appender for the pipeline. The same log call feeds both; neither replaces the other.
- **Fields are arguments, never interpolated.** The message is a stable sentence; values travel as structured key-value fields, so they survive as attributes on the OpenTelemetry record.
- **One exception, logged once.** The boundary that handles it logs it; layers that rethrow stay silent; layers that swallow log at `WARN` or higher with the reason.
- **Level meanings are defined, not implied.** `ERROR` means a request or job failed and someone may need to act; `INFO` is one business-relevant state change per unit of work.
- **A never-log denylist with a review-failure rule.** Credentials, tokens, session IDs, request bodies, card numbers, personal data beyond an opaque user ID. Any new field named `password`, `token`, `secret`, `authorization`, or `cookie` fails review.
- **Reviewer-grade output.** Findings come back severity-tagged and compose with [structured-code-review](structured-code-review).

## What it covers

- Level meanings and the one-event-per-record rule
- Field naming that follows OpenTelemetry semantic conventions (`user.id`, `http.route`, `error.type`)
- Request-scoped context set once in a filter or middleware (MDC on the JVM, a child logger in pino)
- Logback configuration with both appenders and a Spring Boot profile switch (JVM reference)
- pino setup with a dev pretty-printer, JSON in production, and Nitro integration (Node reference)
- Red flags and common rationalizations, plus a verification checklist

## Install

Inside Claude Code:

```
/plugin marketplace add ribrewguy/agent-skills
/plugin install application-logging@ribrewguy-skills
```

For other tools, see [Install](../install).

## Composes with

- **[opentelemetry](opentelemetry)**: when both are loaded, this skill governs the content of a record and `opentelemetry` governs its transport and correlation fields.
- **[structured-code-review](structured-code-review)**: formats review findings.

## Source

- **[Full SKILL.md on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/application-logging/skills/application-logging/SKILL.md)**: the canonical reference loaded by AI tools.
- **[Eval set on GitHub](https://github.com/ribrewguy/agent-skills/blob/main/plugins/application-logging/skills/application-logging/evals/evals.json)**: the three test cases for the skill.
