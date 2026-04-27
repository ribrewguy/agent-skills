**Review Scope:** `api/services/email.ts` new `renderEmailTemplate(templateName, vars)` implementation  
**Process Used:** Closed-context second-pass code review from provided package only  
**Execution Context:** No commands run; no filesystem or skill files read  
**Integration Target:** Email template renderer design / acceptance criteria  
**Governing Documents:** Design / Acceptance criteria in review package  
**Reviewer:** Codex  
**Severity Scale:** Critical, High, Medium, Low as defined in package  
**Date:** 2026-04-26  

**Findings**

**High**

**H1: `templateName` allows path traversal outside `templates/email`**  
Citation: `api/services/email.ts:21`

Problem: `templatePath` is built with `path.join(TEMPLATE_DIR, `${templateName}.html`)` without validating that `templateName` is a simple template identifier. A caller can pass values such as `../admin/reset` or deeper traversal segments and cause the renderer to read `*.html` files outside `templates/email`.

Why it matters: The design specifically requires loading from `templates/email/<templateName>.html`. This implementation does not enforce that boundary. If `templateName` is user-influenced, this becomes a local file disclosure risk for any readable `.html` file reachable from the service process.

Source-of-truth reference: Design / Acceptance criteria: “Loads a template from `templates/email/<templateName>.html`.”

Proposed fix: Reject `templateName` values containing path separators, traversal segments, or absolute paths. For example, require `/^[a-zA-Z0-9_-]+$/`, then resolve the path and assert it remains inside `TEMPLATE_DIR`.

**Medium**

**M1: Template path depends on compiled file location, which may not match the project template directory**  
Citation: `api/services/email.ts:4`

Problem: `TEMPLATE_DIR` is derived from `__dirname`. In TypeScript projects, `__dirname` at runtime usually points to the compiled output directory, not necessarily the source `api/services` directory. Depending on the build layout, this may resolve to something like `dist/templates/email` or another unintended location instead of the repository’s `templates/email`.

Why it matters: The renderer can pass unit tests that mock or run under ts-node, then fail after compilation/deployment because templates are not copied to the computed location. That violates the “throws if missing” behavior in practice by making valid templates appear missing.

Source-of-truth reference: Design / Acceptance criteria: “Loads a template from `templates/email/<templateName>.html`” and “Throws if the template file is missing.”

Proposed fix: Anchor template loading to a known application root/configured template directory, or ensure the build copies templates to the runtime path and document that contract. Prefer an injected/configured base path for testability and deployment correctness.
