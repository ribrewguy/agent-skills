**Review Scope:** `api/services/email.ts` new `renderEmailTemplate(templateName, vars)` implementation  
**Process Used:** Static review of the supplied package only  
**Execution Context:** Closed-context evaluation; no shell commands, filesystem reads, or test execution  
**Integration Target:** Email template renderer service  
**Governing Documents:** Design / Acceptance criteria in review package  
**Reviewer:** Codex  
**Severity Scale:** Critical, High, Medium, Low as defined in review instructions  
**Date:** 2026-04-26  

## Critical Findings

None.

## High Findings

### `api/services/email.ts:21` - `templateName` permits path traversal outside `templates/email`

**Problem:** `templatePath` is built with `path.join(TEMPLATE_DIR, `${templateName}.html`)` without validating that `templateName` is a safe template identifier. A value like `../shared/layout` can resolve outside `templates/email`.

**Why it matters:** The acceptance criteria says templates must be loaded from `templates/email/<templateName>.html`. As written, callers can escape that directory and read other `.html` files available to the process. If `templateName` is user-controlled or indirectly influenced by request data, this is a significant file disclosure risk.

**Source of truth:** Design / Acceptance criteria: “Loads a template from `templates/email/<templateName>.html`.”

**Proposed fix:** Restrict `templateName` to a safe basename pattern, for example:

```ts
if (!/^[a-zA-Z0-9_-]+$/.test(templateName)) {
  throw new Error(`Invalid template name: ${templateName}`)
}
```

Optionally also resolve and enforce containment:

```ts
const templatePath = path.resolve(TEMPLATE_DIR, `${templateName}.html`)
if (!templatePath.startsWith(`${path.resolve(TEMPLATE_DIR)}${path.sep}`)) {
  throw new Error(`Invalid template name: ${templateName}`)
}
```

## Medium Findings

### `api/services/email.ts:6` - Unsupported `{{...}}` placeholders are silently left unrendered

**Problem:** `VAR_PATTERN` only matches identifiers shaped like `[a-zA-Z_][a-zA-Z0-9_]*`. A template containing `{{user-name}}`, `{{ user.email }}`, or another malformed placeholder is returned with that placeholder intact rather than throwing.

**Why it matters:** The acceptance criteria says the renderer throws if the template references a variable not in `vars`. Silent leftover placeholders can produce broken outbound email while tests still pass for simple identifiers.

**Source of truth:** Design / Acceptance criteria: “Throws if the template references a variable not in `vars`.”

**Proposed fix:** After replacement, detect any remaining `{{...}}` blocks and throw a clear error, or explicitly validate all placeholders before replacing:

```ts
const unresolved = rendered.match(/\{\{[^}]+\}\}/)
if (unresolved) {
  throw new Error(`Template ${templateName} contains invalid or unresolved variable ${unresolved[0]}`)
}
```

## Low Findings

None.
