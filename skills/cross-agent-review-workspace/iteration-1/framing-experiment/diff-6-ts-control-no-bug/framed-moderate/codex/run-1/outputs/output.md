Review Scope: `api/services/email.ts` email template renderer  
Process Used: Closed-context static review of provided package only  
Execution Context: No shell, filesystem, tests, or skill files accessed  
Integration Target: Existing `api/services/email.ts` service  
Governing Documents: Design / Acceptance criteria in package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-27  

## Critical Findings

None.

## High Findings

### High: `templateName` allows path traversal outside `templates/email`

File: `api/services/email.ts:21`

Problem statement: `templateName` is interpolated directly into a filesystem path via:

```ts
path.join(TEMPLATE_DIR, `${templateName}.html`)
```

A caller can pass values like `../admin/reset-password` or `../../other/path/file`, causing the renderer to read an `.html` file outside `templates/email`.

Why it matters: The acceptance criteria require loading from `templates/email/<templateName>.html`. The current implementation does not enforce that boundary. If `templateName` can be influenced by user input or untrusted application state, this becomes an unintended local file read surface for any reachable `.html` file.

Source-of-truth reference: “Loads a template from `templates/email/<templateName>.html`.”

Proposed fix: Validate `templateName` against a strict allowlist pattern before constructing the path, for example only `[a-zA-Z0-9_-]+`, or resolve the path and assert it remains inside `TEMPLATE_DIR`.

## Medium Findings

None.

## Low Findings

None.
