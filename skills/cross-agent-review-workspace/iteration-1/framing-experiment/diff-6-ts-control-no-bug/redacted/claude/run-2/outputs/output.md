- **Review Scope**: `renderEmailTemplate` function added to `api/services/email.ts` per the design "Email template renderer".
- **Process Used**: Cold structured code review of the supplied diff against the stated acceptance criteria. Re-derived correctness by reading the implementation line-by-line; no tests were executed and no other files were consulted.
- **Execution Context**: Closed-context review; only the supplied package was read. No repository search, no test runs, no static analysis tooling.
- **Integration Target**: `api/services/email.ts` (a single new exported async function). Templates are expected at `templates/email/<templateName>.html` resolved relative to the compiled module's `__dirname`.
- **Governing Documents**: The "Design / Acceptance criteria" block embedded in the supplied package (Email template renderer spec, including 6 enumerated unit tests).
- **Reviewer**: Cross-vendor second-pass reviewer (Claude).
- **Severity Scale**: Critical = production data corruption / RCE / privilege escalation. High = significant security risk, resource leak under common load, silent data inconsistency, design requirement violated. Medium = incorrect behavior on some inputs, unclear error handling, performance degradation, missing validation implied by the design. Low = style, naming, nits.
- **Date**: 2026-04-26.

## Findings

### Critical

#### C1. Path traversal: `templateName` is concatenated into a filesystem path with no validation
- **Citation**: `api/services/email.ts:64` — `const templatePath = path.join(TEMPLATE_DIR, \`${templateName}.html\`)`
- **Problem**: `templateName` is an unvalidated string passed straight into `path.join`. A caller (or upstream input) supplying values like `../../../../etc/passwd\0` (older Node), `../../config/secrets`, or an absolute path on Windows (`C:\\Windows\\win.ini`) will escape `TEMPLATE_DIR`. `path.join` does not constrain results to a base directory; segments containing `..` are resolved normally. The function then `readFile`s the resulting path and returns its contents (after `{{var}}` substitution, which is a no-op for files that contain no template tokens) to the caller.
- **Why it matters**: If `templateName` is ever influenced by request data — which is the natural shape of an "email template renderer" service called from controllers — this is an arbitrary file read. Combined with the fact that the rendered string is typically emailed or returned to a user, it becomes information disclosure of any file the Node process can read (`.env`, private keys, `/etc/passwd`, source). The design lists "Throws if the template file is missing" but says nothing about constraining `templateName`; absent that check, the safe default must be enforced in code. This is a Critical issue because it can lead to disclosure of secrets and source.
- **Source-of-truth reference**: Design bullet "Loads a template from `templates/email/<templateName>.html`." This phrasing requires that the loaded file actually live under `templates/email/`; the implementation does not enforce that invariant.
- **Proposed fix**: Validate `templateName` against a strict allowlist regex (e.g. `/^[a-zA-Z0-9_-]+$/`) before use, AND verify after `path.join` + `path.resolve` that the result still starts with `path.resolve(TEMPLATE_DIR) + path.sep`. Reject otherwise with a non-leaky error. Example:
  ```ts
  if (!/^[a-zA-Z0-9_-]+$/.test(templateName)) {
    throw new Error(`Invalid template name: ${templateName}`)
  }
  const resolved = path.resolve(templatePath)
  const base = path.resolve(TEMPLATE_DIR) + path.sep
  if (!resolved.startsWith(base)) {
    throw new Error(`Invalid template name: ${templateName}`)
  }
  ```

### High

#### H1. Throwing inside `String.prototype.replace` callback yields confusing behavior and leaks partial work
- **Citation**: `api/services/email.ts:76-83`
- **Problem**: The replacement callback throws when a referenced variable is missing. `String.prototype.replace` does not document throw-from-callback as a supported termination path; in V8 it propagates, but it does so only after the *first* missing var is encountered, leaving later missing vars un-reported. The error message names the first offender only, and there is no aggregation. Worse, because `replace` evaluates lazily, the thrown error is not deterministic relative to the order of `vars` passed in — it is determined by the order tokens appear in the *template*, which is fine, but it precludes giving a complete diagnostic.
- **Why it matters**: The design says "Throws if the template references a variable not in `vars`." The behavior is technically met for the first missing var, but operationally this makes triage painful: editing the template to fix one missing var only surfaces the next one on the next render. For a templating system this is a recurring footgun.
- **Source-of-truth reference**: Design bullet "Throws if the template references a variable not in `vars`."
- **Proposed fix**: Pre-scan the template with `template.matchAll(VAR_PATTERN)` to collect all referenced names, diff against `Object.keys(vars)` (using `hasOwnProperty`), and throw a single error listing every missing variable before doing the substitution pass.

#### H2. Templates with extra (unused) variables are silently accepted — likely a spec mismatch
- **Citation**: `api/services/email.ts:60-84` (whole function)
- **Problem**: The design says "Throws if the template references a variable not in `vars`" but does not say what to do when `vars` contains keys the template never uses. The implementation silently ignores them. This is a "missing validation that the design implies" question: in many template systems, an unused variable is a strong signal of a caller bug (typo'd key, refactor stale).
- **Why it matters**: Silent acceptance of typo'd keys (e.g. `vars.userName` when the template uses `{{user_name}}`) means the renderer happily emits an email with the literal `{{user_name}}` — except the implementation throws on that case (good) — but the more common bug is `vars.usernme` and the template using `{{username}}` in two places where one was renamed. Without logging or strict-mode, drift between callers and templates accumulates undetected.
- **Source-of-truth reference**: Design bullets enumerate happy path, missing template, missing variable, HTML escaping, no-vars template, multi-variable template — none requires extra-vars detection. Flagging as High because the design's "missing variable" symmetry is broken by silently allowing the inverse; depending on intent this may be Medium.
- **Proposed fix**: Decide the policy explicitly. Either (a) document the asymmetry, or (b) add an opt-in `strict: true` mode that throws on unused keys.

### Medium

#### M1. `__dirname` is undefined under ESM — `TEMPLATE_DIR` resolution is build-system dependent
- **Citation**: `api/services/email.ts:47` — `const TEMPLATE_DIR = path.join(__dirname, '../../templates/email')`
- **Problem**: `__dirname` exists in CommonJS but is not defined in native ES modules. The TypeScript source gives no `tsconfig` clues either way; in many modern Node services this file would be compiled to ESM, in which case `__dirname` is a `ReferenceError` at module load. Even in CJS, the `'../../templates/email'` traversal assumes `__dirname` is two levels deep under `api/services/`, which is true for `src/api/services/` source layout but not for typical `dist/api/services/` build output unless templates are copied into `dist/`. The design says "Loads a template from `templates/email/<templateName>.html`" without specifying a base.
- **Why it matters**: The function may throw on import (ESM) or fail with `ENOENT` for every template (CJS with build that doesn't ship templates next to source) — a runtime regression that none of the prescribed unit tests catch unless the test harness happens to mirror production layout.
- **Source-of-truth reference**: Design bullet "Loads a template from `templates/email/<templateName>.html`." Implicit requirement: this must work at runtime in the target deployment.
- **Proposed fix**: Resolve `TEMPLATE_DIR` from a known anchor (e.g. `process.cwd()` plus a config value, or `path.resolve(import.meta.url, ...)` for ESM with a `fileURLToPath` shim). Document the assumed CWD/build layout. Add a startup check that `TEMPLATE_DIR` exists.

#### M2. `escapeHtml` is unsafe for attribute contexts and useless for non-string contexts
- **Citation**: `api/services/email.ts:51-58`
- **Problem**: The escaper handles `& < > " '` — sufficient for HTML text and double-quoted attribute values, but:
  - It does not escape backtick `` ` `` (problematic in IE attribute contexts and in `<style>`/`<script>` data-binding contexts).
  - Substituting into `<script>` or `<style>` blocks remains dangerous; HTML escaping does not neutralize JS strings. Email HTML rarely contains `<script>`, but `<style>` is common and a `</style><script>...` payload in a value would break out.
  - For URL contexts (e.g. `<a href="{{link}}">`), HTML-escaping a value that begins with `javascript:` does nothing; the design mentions "HTML-escaping" but URL contexts need URL-validation, not HTML escaping.
  - `String(value)` for `undefined` yields `"undefined"`, for `null` yields `"null"`, for objects yields `"[object Object]"`. The design says "occurrences of `{{var}}` are replaced with `vars[var]`" without specifying coercion semantics, so emitting `"[object Object]"` into a customer email is a surprising silent failure.
- **Why it matters**: Email templates often include links and styles; the escape function's protection is incomplete by today's standards. The coercion behavior bakes user-visible junk into outgoing mail without warning.
- **Source-of-truth reference**: Design bullets "Substitutes variables: occurrences of `{{var}}` are replaced with `vars[var]` (HTML-escaped)" and the "HTML escaping of values" unit test.
- **Proposed fix**: Either (a) restrict accepted value types to `string | number | boolean` (throw on others), or (b) document that values are stringified and only safe in HTML text/attribute contexts. Add backtick to the escape map. Document that `href`/`src` interpolation requires a separate URL validator.

#### M3. Tag regex permits leading/trailing whitespace but not other Mustache-like spacing; subtle parser drift
- **Citation**: `api/services/email.ts:49` — `/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g`
- **Problem**: The pattern matches `{{ foo }}` (good) but rejects `{{foo.bar}}` and `{{ foo-bar }}` and `{{foo}}` adjacent to other braces (`{{{foo}}}` will match the inner `{foo}` form ambiguously, leaving stray braces). Also, escaped/literal `{{` cannot be expressed — there is no escape syntax — so a template that legitimately needs `{{` in output (e.g. documentation about templating) cannot represent it.
- **Why it matters**: The acceptance criteria do not call out these cases, so this is implicit-design risk: the function will silently emit literal `{{foo.bar}}` text into emails when a developer writes a Mustache-style dotted path expecting nested lookup. No error fires; the template author thinks they templated something that they did not.
- **Source-of-truth reference**: Design bullet "Substitutes variables: occurrences of `{{var}}` are replaced with `vars[var]`."
- **Proposed fix**: Document the supported syntax explicitly in a comment. Optionally pre-scan for `{{` sequences that look like template tags but don't match the pattern, and warn or throw.

#### M4. No size limit on template file or on rendered output
- **Citation**: `api/services/email.ts:68` — `template = await fs.readFile(templatePath, 'utf8')`
- **Problem**: `fs.readFile` will load whatever the file contains into memory. If templates are committed assets this is generally fine, but if they are ever sourced from writable storage (deploy artifacts, mounted volumes), a giant file becomes an OOM/DOS vector. The design treats templates as static assets but the implementation does not enforce that.
- **Why it matters**: Defense-in-depth. With no cap, a misconfigured deploy that drops a 2 GB file at the template path will OOM the process on first render.
- **Source-of-truth reference**: General robustness; not explicitly in the design.
- **Proposed fix**: `fs.stat` first and reject above a sane bound (e.g. 1 MB), or use a streaming approach. Cache parsed templates to avoid re-reading on every call (currently every invocation hits disk).

#### M5. No template caching — every render hits the filesystem
- **Citation**: `api/services/email.ts:67-68`
- **Problem**: Each call performs an async disk read. For an email service under common load (e.g. signup confirmations, password resets), this is a needless syscall per render and a measurable latency floor.
- **Why it matters**: Performance degradation under load and unnecessary IO. Templates rarely change between deploys, so an in-process cache (or LRU) is the standard pattern.
- **Source-of-truth reference**: General performance hygiene; not in the design's bullet list, hence Medium.
- **Proposed fix**: Memoize `templateName -> string` reads in a `Map` (with optional invalidation hook for tests/dev mode). Be careful not to cache substitutions, only the raw template.

### Low

#### L1. Error messages echo `templateName` verbatim
- **Citation**: `api/services/email.ts:71, 79`
- **Problem**: The thrown errors include `templateName` and (in H1's case) the offending variable name. If `templateName` ever comes from user input and the error propagates to logs without scrubbing, it can pollute logs with attacker-controlled strings (log injection if the renderer is called in a path that logs to a structured sink without escaping). Minor.
- **Why it matters**: Operational hygiene; encourages safer logging. Compounds with C1.
- **Source-of-truth reference**: General secure-logging guidance.
- **Proposed fix**: Either restrict `templateName` (see C1) so untrusted strings cannot reach the message, or escape control characters in error messages.

#### L2. `Record<string, unknown>` for `vars` is loose; consider a stricter alias
- **Citation**: `api/services/email.ts:62`
- **Problem**: `unknown` puts the burden on `escapeHtml` to coerce sensibly. A typed alias like `type TemplateVar = string | number | boolean` plus `Record<string, TemplateVar>` would catch caller mistakes at compile time.
- **Why it matters**: Type-safety nit; reduces surprise stringification (M2).
- **Source-of-truth reference**: TypeScript style.
- **Proposed fix**: Tighten the type or document the contract.

#### L3. `import * as fs from 'fs/promises'` namespace style is inconsistent with typical Node 18+ guidance
- **Citation**: `api/services/email.ts:44`
- **Problem**: `fs/promises` is typically imported as `import { readFile } from 'fs/promises'` or `import fs from 'fs/promises'` (with `esModuleInterop`). Namespace imports work but produce a slightly larger bundle in some bundlers and read awkwardly. Pure nit.
- **Why it matters**: Style only.
- **Source-of-truth reference**: None.
- **Proposed fix**: `import { readFile } from 'fs/promises'`.

#### L4. The 6-test acceptance set under-specifies behavior the implementation has
- **Citation**: Design "6 unit tests cover happy path, missing template, missing variable, HTML escaping of values, no-vars template, and a multi-variable template."
- **Problem**: The list does not explicitly require tests for: variable appearing more than once (substituted in all positions?), whitespace inside `{{ var }}`, non-string values, path traversal rejection (see C1), or ESM/CJS path resolution (M1). A 6-test suite that mechanically covers the bullets will leave C1, H1, M1, M2, and M3 untested.
- **Why it matters**: This is what the review brief calls "failure modes that tests don't catch." Worth flagging in the test plan even though it's outside the implementation diff.
- **Source-of-truth reference**: Design's enumerated test list.
- **Proposed fix**: Expand the suite to cover at minimum: rejecting `..` in `templateName`, repeated tokens, whitespace-tolerant tokens, and a value that is `null`/`undefined`/an object.
