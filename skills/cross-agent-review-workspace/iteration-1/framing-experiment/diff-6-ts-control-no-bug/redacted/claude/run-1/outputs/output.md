**Review Scope:** `renderEmailTemplate` function added to `api/services/email.ts` per the supplied design / acceptance criteria.

**Process Used:** Cold structured code review of the supplied diff. Re-derived correctness against the design statement; no compilation, linting, or test execution performed (no environment provided). Findings derived from static analysis of the single changed file.

**Execution Context:** Closed-context review; only the redacted package was read. No surrounding repo, no `tsconfig.json`, no test files, no `templates/email/` directory contents available.

**Integration Target:** `api/services/email.ts` — adds an exported async function used presumably by upstream callers (mailer, transactional pipeline). Reads from the `templates/email/` directory at runtime via `fs/promises`.

**Governing Documents:** Design / Acceptance criteria block in the package (lines 25-37): `renderEmailTemplate(templateName, vars)` contract, mandatory throws for missing template / missing variable, HTML escaping of substituted values, and 6 named unit tests.

**Reviewer:** Cross-vendor second-pass reviewer (Claude).

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

_None identified._

### High

**1. Path traversal: `templateName` is concatenated into a filesystem path with no validation.**
- File:line — `api/services/email.ts:64`
- Problem — `path.join(TEMPLATE_DIR, ${templateName}.html)` accepts any string the caller supplies. A `templateName` of `../../etc/passwd\0` (older Node) or `../../config/secrets` will resolve outside `TEMPLATE_DIR`. Even an absolute path passed as `templateName` will silently be treated by `path.join` as part of the join, but a value that begins with `..` segments will escape the templates directory entirely.
- Why it matters — If `templateName` ever flows from a request parameter, configuration, database row, or any non-hardcoded source, an attacker can read arbitrary files the Node process can access (HTML rendered back to them, or surfaced in error messages / logs / outbound emails). This is a classic LFI vector. The design does not say `templateName` is trusted; production email-template selectors are commonly driven by data (e.g., `welcome`, `password_reset`, picked from a campaign row).
- Source-of-truth reference — Design lines 30 ("Loads a template from `templates/email/<templateName>.html`") implies confinement to that directory; the implementation does not enforce it. OWASP ASVS V12.3 (file path injection).
- Proposed fix — Validate `templateName` against an allowlist regex (e.g., `/^[a-zA-Z0-9_-]+$/`) before constructing the path, OR resolve the final path and assert `path.resolve(templatePath).startsWith(path.resolve(TEMPLATE_DIR) + path.sep)`. Reject otherwise with a thrown error that does not echo the input verbatim.

**2. Throwing inside `String.prototype.replace`'s replacer is correct but loses the partially-rendered context; more importantly, the design's "throws if missing variable" requirement is satisfied only on the first encounter — fine — but the error message echoes user-controlled data unsanitized.**
- File:line — `api/services/email.ts:78-80`
- Problem — The thrown `Error` interpolates `templateName` and `varName` directly. If `templateName` ever comes from untrusted input, error logs / error-tracking pipelines / API error responses can be poisoned with attacker-controlled content (log forging via embedded newlines, ANSI escapes in terminal log viewers, or HTML if surfaced in a web error page). Less severe than #1 but related.
- Why it matters — Defense-in-depth; if #1 is fixed by allowlist this becomes moot, but if path traversal protection is added by `path.resolve` only, untrusted strings still reach the message.
- Source-of-truth reference — Design line 34 ("Throws if the template references a variable not in `vars`") — does not require echoing the variable name, but it is reasonable to keep it; just sanitize it.
- Proposed fix — Strip control characters from `templateName` and `varName` before interpolation (`.replace(/[\x00-\x1f\x7f]/g, '?')`), or rely on the allowlist proposed in #1.

### Medium

**3. `vars[varName]` lookup uses bracket access on a `Record<string, unknown>` without `Object.create(null)` protection — `__proto__`, `constructor`, `toString` collisions.**
- File:line — `api/services/email.ts:77, 82`
- Problem — `Object.prototype.hasOwnProperty.call(vars, varName)` correctly guards against inherited prototype properties, so `{{toString}}` will throw "not in vars" — good. However, if a caller passes a `vars` object that *does* have a key like `__proto__` (legitimately, via `vars['__proto__'] = 'x'`) the lookup `vars[varName]` returns the prototype object, not the string `'x'` — `String({})` produces `"[object Object]"` which then gets HTML-escaped and rendered. This is an edge case but counter-intuitive.
- Why it matters — Silent rendering of `[object Object]` into emails for callers that build `vars` from a JSON body. Not a security flaw given the `hasOwnProperty` guard, but a correctness footgun.
- Source-of-truth reference — Design line 31-32 ("Substitutes variables: occurrences of `{{var}}` are replaced with `vars[var]`").
- Proposed fix — Use `Reflect.get(vars, varName)` after the `hasOwnProperty` check, or normalize with `vars = { ...incomingVars }` (loses the issue because spread doesn't copy `__proto__` as own).

**4. `escapeHtml` does not escape backtick, equals sign, or forward slash; `String(value)` on `null` / `undefined` / symbol can mis-render or throw.**
- File:line — `api/services/email.ts:51-58`
- Problem — Two sub-issues:
  (a) `String(symbolValue)` throws `TypeError: Cannot convert a Symbol value to a string`. If a caller passes `vars = { x: Symbol('y') }`, the call crashes with a stack-trace error rather than a domain error.
  (b) `null` becomes the literal `"null"` and `undefined` becomes `"undefined"` in the rendered HTML. The design says "replaced with `vars[var]` (HTML-escaped)" — silent stringification of nullish values is almost never intended for a transactional email.
  (c) The escape set is OWASP-minimal but does not handle backtick (matters for some attribute contexts) or `=` / `/` (matters for unquoted attribute injection). For body-only HTML the current set is sufficient, but the function is named generically and the design does not constrain context.
- Why it matters — A welcome email rendering "Hello, undefined" is a real production embarrassment and a frequent source of bug reports. The Symbol crash is a DoS-style failure mode for any code path that forwards user-shaped data.
- Source-of-truth reference — Design line 32 ("HTML-escaped") — under-specifies, but standard practice is to reject or coerce `null`/`undefined` explicitly.
- Proposed fix — At top of `escapeHtml`, handle nullish explicitly (throw, or substitute `''`); reject Symbols with a typed error. Document the substitution policy.

**5. `fs.readFile` errors other than ENOENT are re-thrown raw — EACCES, EISDIR, EMFILE leak filesystem details.**
- File:line — `api/services/email.ts:69-74`
- Problem — Only `ENOENT` is mapped to a domain error. `EACCES` (permissions), `EISDIR` (someone made `templates/email/welcome.html` a directory), `EMFILE` (file-descriptor exhaustion under load) all surface as raw Node errors with absolute paths in the message. This breaks abstraction and complicates upstream error handling.
- Why it matters — Operational hygiene; absolute paths in error messages reach client-facing surfaces in some web frameworks. Also makes upstream `try/catch` brittle (callers must distinguish "template not found" from "I/O error" — currently they must inspect `err.message`).
- Source-of-truth reference — Design line 33 ("Throws if the template file is missing") — only specifies the ENOENT case; other I/O errors should be wrapped consistently.
- Proposed fix — Wrap non-ENOENT errors in a typed error (e.g., `class TemplateIOError extends Error`) with the templateName but not the absolute path.

**6. No template caching — every render re-reads from disk.**
- File:line — `api/services/email.ts:68`
- Problem — Each call to `renderEmailTemplate` performs a fresh `fs.readFile`. Email templates change rarely (deploy-time); reading them on every send wastes I/O and increases latency, especially on cold-cache filesystems or networked storage (EFS, etc.).
- Why it matters — Performance under load. The design does not require caching, so this is not a strict violation, but it is a foreseeable performance issue. In a high-throughput mailer this becomes the bottleneck.
- Source-of-truth reference — Design lines 25-37 — silent on caching, so this is a design-implies-not-required issue. Severity Medium because the design says "performance degradation" qualifies.
- Proposed fix — Add a process-local `Map<string, string>` cache keyed by templateName (with optional TTL or filesystem-mtime check). Document cache-invalidation strategy.

**7. The compiled regex `/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g` does not match dotted paths, hyphens, or numeric-prefixed keys, but the design says "occurrences of `{{var}}` are replaced with `vars[var]`" — there is no contract on what `var` may contain.**
- File:line — `api/services/email.ts:49`
- Problem — A template containing `{{user.name}}` or `{{1st_name}}` will be left untouched (regex does not match, so no substitution and no "missing variable" error fires). This silently emits the literal `{{user.name}}` in the output email — exactly the scenario the design's "throw on missing variable" rule was meant to prevent.
- Why it matters — Silent rendering of un-substituted placeholders to end users is a real and embarrassing failure mode. The "throw on missing variable" guarantee is weakened — it only fires for variables whose name happens to match the implementation's narrower regex.
- Source-of-truth reference — Design line 34 ("Throws if the template references a variable not in `vars`"). The implementation only enforces this for variable names matching `[a-zA-Z_][a-zA-Z0-9_]*`.
- Proposed fix — Either (a) document the allowed identifier grammar and add a second-pass scan that rejects any `{{...}}` in the output, OR (b) broaden the regex to capture any `{{...}}` and validate the captured name separately, throwing on malformed names.

**8. `__dirname` is used at module load time — breaks under ESM and bundlers.**
- File:line — `api/services/email.ts:47`
- Problem — `path.join(__dirname, '../../templates/email')` only works if the file is compiled as CommonJS. Under native ESM (`"type": "module"`), `__dirname` is `undefined` and the module crashes at import time. Bundlers (esbuild, webpack) often inline or polyfill this, but not always — a Vite SSR build, for example, will fail.
- Why it matters — Future-proofing; depending on the project's TS config / bundler, this can be a deploy-time failure. The package gives no tsconfig, so this depends on the integration target.
- Source-of-truth reference — N/A in design. This is a portability concern.
- Proposed fix — Use `import.meta.url` + `fileURLToPath` for ESM, or accept `TEMPLATE_DIR` as an injected dependency / environment variable.

### Low

**9. `Promise<string>` return is correct, but the `.replace` callback throws synchronously inside an async function — error surfaces as a rejected promise (good), but stack traces are lossy because `.replace` does not preserve async context.**
- File:line — `api/services/email.ts:76-83`
- Problem — When the missing-variable error is thrown inside the replacer, the resulting stack trace points into V8's `String.prototype.replace` internals rather than the call site. This is a minor debugging nuisance.
- Why it matters — DX, not correctness.
- Source-of-truth reference — N/A.
- Proposed fix — Pre-scan the template with `template.matchAll(VAR_PATTERN)`, validate all variable presences first, then perform substitution. This also enables a useful "all missing variables in one error" message rather than fail-fast on the first.

**10. `vars` typed as `Record<string, unknown>` — caller cannot get IDE help, and `unknown` permits values that crash `escapeHtml` (Symbols, see #4).**
- File:line — `api/services/email.ts:62`
- Problem — `Record<string, unknown>` is permissive but offers no compile-time protection.
- Why it matters — Style / type safety.
- Source-of-truth reference — N/A.
- Proposed fix — Consider `Record<string, string | number | boolean | null | undefined>` or accept a generic `T extends Record<string, ...>` and have the caller's variable set inferred.

**11. Test coverage stated as "6 unit tests" — no tests are included in the diff.**
- File:line — `api/services/email.ts` (entire file) — no companion `email.test.ts` provided in the package.
- Problem — Cannot verify the 6 acceptance tests exist (happy path, missing template, missing variable, HTML escaping of values, no-vars template, multi-variable template). The reviewer was instructed to re-derive quality claims; the diff supplies no tests.
- Why it matters — The acceptance criterion "6 unit tests cover ..." (design line 36-37) is unverifiable from the package. Treat as missing unless the test file is in a separate diff.
- Source-of-truth reference — Design line 36-37.
- Proposed fix — Provide / link the test file in the review package, or add it to the diff.

**12. `templates/email/` directory not shown — cannot confirm at least one template exists, nor that file extensions / encodings match the implementation's `utf8` assumption.**
- File:line — `api/services/email.ts:68`
- Problem — Implementation hard-codes `utf8`. If templates are authored in a different encoding (UTF-16 BOM, Windows-1252) they will be mis-decoded silently.
- Why it matters — Edge case; modern editors default to UTF-8, but designers using legacy tooling occasionally produce BOM-prefixed files. A leading BOM in the template will appear as `﻿` at the start of the rendered email and may confuse some MUAs.
- Source-of-truth reference — N/A.
- Proposed fix — Strip a leading BOM if present, or document the encoding requirement.
