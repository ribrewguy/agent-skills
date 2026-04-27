Review Scope: `api/services/email.ts`, new `renderEmailTemplate` implementation  
Process Used: Static review of provided patch only  
Execution Context: Closed-context review; no filesystem or commands used  
Integration Target: Email template renderer service  
Governing Documents: Acceptance criteria in review package  
Reviewer: Codex  
Severity Scale: Critical / High / Medium / Low as provided  
Date: 2026-04-27

## Critical Findings

None.

## High Findings

### `api/services/email.ts:24` - `templateName` permits path traversal outside `templates/email`

Problem statement: `templateName` is interpolated directly into a filename and passed through `path.join`, so values like `../admin/reset` or `../../some/path/file` can escape `templates/email` as long as the target ends in `.html`.

Why it matters: The acceptance criteria specifically require loading from `templates/email/<templateName>.html`. This implementation can read unintended HTML files elsewhere in the project or filesystem-relative tree, which is a significant security boundary issue if `templateName` is influenced by user input or tenant-controlled configuration.

Source-of-truth reference: “Loads a template from `templates/email/<templateName>.html`.”

Proposed fix: Validate `templateName` against a strict allowlist such as `/^[a-zA-Z0-9_-]+$/`, or resolve the final path and assert it remains inside `TEMPLATE_DIR` before reading.

## Medium Findings

None.

## Low Findings

None.
