Review Scope: `api/services/email.ts` new `renderEmailTemplate` implementation  
Process Used: Static review from provided package only; no files or commands accessed  
Execution Context: Closed-context evaluation  
Integration Target: Email template renderer service  
Governing Documents: Design / Acceptance criteria in package  
Reviewer: Codex second-pass reviewer  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: 2026-04-26

**High Findings**

**High: Template name allows path traversal outside `templates/email`**  
Citation: `api/services/email.ts:21`

Problem statement: `path.join(TEMPLATE_DIR, `${templateName}.html`)` accepts raw `templateName`. A caller can pass values like `../admin/reset` or absolute/path-like inputs to read files outside `templates/email`, depending on the resolved path and filesystem layout.

Why it matters: The acceptance criteria require loading from `templates/email/<templateName>.html`. This implementation does not enforce that boundary, creating a significant file disclosure risk and violating the template directory constraint.

Source-of-truth reference: “Loads a template from `templates/email/<templateName>.html`.”

Proposed fix: Reject template names containing path separators, `..`, absolute paths, or unexpected characters. Resolve the final path and assert it remains inside the resolved template directory before reading.

**Medium Findings**

**Medium: Unsupported placeholder names are silently left unrendered instead of failing**  
Citation: `api/services/email.ts:6`, `api/services/email.ts:33`

Problem statement: `VAR_PATTERN` only matches placeholders whose names fit `[a-zA-Z_][a-zA-Z0-9_]*`. A template containing `{{user-name}}`, `{{ user.email }}`, `{{1}}`, or another placeholder-like reference will remain in the output unchanged and will not trigger the missing-variable error.

Why it matters: The design says template variable references must be substituted, and missing referenced variables must throw. Silent pass-through creates incorrect rendered HTML and can leak raw template syntax into emails.

Source-of-truth reference: “Substitutes variables: occurrences of `{{var}}` are replaced with `vars[var]`” and “Throws if the template references a variable not in `vars`.”

Proposed fix: First scan for all `{{ ... }}` tokens, trim the inner name, and either support arbitrary `Record<string, unknown>` keys or explicitly throw for invalid placeholder syntax. Do not leave placeholder-shaped content silently unchanged.

**Low Findings**

None.
