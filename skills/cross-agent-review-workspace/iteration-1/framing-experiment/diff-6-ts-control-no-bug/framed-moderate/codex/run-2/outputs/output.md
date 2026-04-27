**Review Scope:** `api/services/email.ts`, new `renderEmailTemplate(templateName, vars)` implementation  
**Process Used:** Closed-context structured code review using only the supplied package  
**Execution Context:** No shell commands, filesystem reads, or tests run  
**Integration Target:** Email template renderer loading HTML templates from `templates/email`  
**Governing Documents:** Supplied design / acceptance criteria  
**Reviewer:** Codex  
**Severity Scale:** Critical, High, Medium, Low as defined in request  
**Date:** 2026-04-26

**Findings**

**Critical**

No Critical findings.

**High**

**Finding 1: Path traversal can escape the email template directory**  
**Citation:** `api/services/email.ts:21`  
**Problem:** `templateName` is interpolated directly into a path with `path.join(TEMPLATE_DIR, `${templateName}.html`)`. A caller can pass values like `../admin/reset` or `../../some/path/file`, causing the resolved path to leave `templates/email`.  
**Why It Matters:** The acceptance criteria require loading from `templates/email/<templateName>.html`. This implementation can read other `.html` files outside that directory if `templateName` is caller-controlled, which is a significant security risk and violates the intended template boundary.  
**Source of Truth:** Design requirement: “Loads a template from `templates/email/<templateName>.html`.”  
**Proposed Fix:** Validate `templateName` against a strict allowlist such as `/^[a-zA-Z0-9_-]+$/`, or resolve the path and assert it remains inside `TEMPLATE_DIR` before reading.

**Medium**

No Medium findings.

**Low**

No Low findings.
