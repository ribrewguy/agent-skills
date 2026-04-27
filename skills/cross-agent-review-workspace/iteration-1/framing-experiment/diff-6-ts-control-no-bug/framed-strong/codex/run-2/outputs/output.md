Review Scope: `api/services/email.ts` new `renderEmailTemplate(templateName, vars)` implementation  
Process Used: Static review of provided patch package only; no tools or filesystem access used  
Execution Context: Closed-context evaluation  
Integration Target: Email template rendering service  
Governing Documents: Design / acceptance criteria in package  
Reviewer: Codex  
Severity Scale: Critical, High, Medium, Low as defined in request  
Date: April 27, 2026

**High Findings**

**H1: `templateName` allows path traversal outside `templates/email`**  
Citation: `api/services/email.ts:21`

Problem statement: `templatePath` is built with `path.join(TEMPLATE_DIR, `${templateName}.html`)` without validating that `templateName` is a simple template identifier. A value like `../admin/reset` or `../../some/path/file` can resolve outside `templates/email`.

Why it matters: The design requires loading from `templates/email/<templateName>.html`. Without path-segment validation, callers can select files outside that directory if `templateName` is user-influenced. That is a significant security risk and violates the intended template boundary.

Source-of-truth reference: Acceptance criteria: “Loads a template from `templates/email/<templateName>.html`.”

Proposed fix: Reject names containing path separators, `..`, absolute paths, or unexpected characters before constructing the path. For example:

```ts
const TEMPLATE_NAME_PATTERN = /^[a-zA-Z0-9_-]+$/

if (!TEMPLATE_NAME_PATTERN.test(templateName)) {
  throw new Error(`Invalid template name: ${templateName}`)
}
```

Then build the path as currently done, or additionally verify `path.resolve(templatePath).startsWith(path.resolve(TEMPLATE_DIR) + path.sep)`.

**Medium Findings**

None.

**Low Findings**

None.

**Critical Findings**

None.
