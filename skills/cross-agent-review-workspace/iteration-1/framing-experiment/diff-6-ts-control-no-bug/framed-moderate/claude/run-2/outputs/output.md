**Review Scope:** New `renderEmailTemplate(templateName, vars)` function added at the end of `api/services/email.ts`, plus its 6 accompanying unit tests (tests not shown in the package, only described).

**Process Used:** Static review of the single TypeScript change presented in the package. Each line of the new function was traced against the stated acceptance criteria (load template, substitute `{{var}}`, HTML-escape values, throw on missing template, throw on missing variable, return rendered string). Variable-pattern regex, escape function, error handling branches, and path construction were each evaluated for correctness, security, and edge-case behavior.

**Execution Context:** Single-pass code review in a closed context; no execution of code, no test runs, no access to surrounding repository (e.g. `tsconfig.json`, build output layout, other call sites of `renderEmailTemplate`, or the actual unit-test file).

**Integration Target:** `api/services/email.ts` in what appears to be a Node.js/TypeScript backend service. Templates are expected to live on disk under `templates/email/<name>.html` resolved relative to the compiled module's `__dirname`.

**Governing Documents:** The "Design / Acceptance criteria" section of the package (lines 7-21) is treated as the source of truth for required behavior. The severity rubric in the "Review instructions" section (lines 77-84) is used for grading.

**Reviewer:** Claude (Opus 4.7, 1M context), acting as cross-agent reviewer in run-2 of the framed-moderate framing experiment for diff-6-ts-control-no-bug.

**Severity Scale:**
- Critical: production data corruption, arbitrary code execution, privilege escalation, or similar.
- High: significant security risk, resource leak under common load, silent data inconsistency, design requirement violated.
- Medium: incorrect behavior on some inputs, unclear error handling, performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

**Date:** 2026-04-26

## Findings

### Critical

_None._

### High

**1. `templateName` is interpolated directly into a filesystem path with no validation — path traversal / arbitrary file read.**

- File: `api/services/email.ts:48` (and indirectly `:44-47` where `templateName: string` is accepted untyped/unvalidated).
- Problem: `path.join(TEMPLATE_DIR, \`${templateName}.html\`)` will happily resolve `../`, absolute paths on POSIX (since `path.join` does not treat a leading `/` as absolute the way `path.resolve` does, but `..` segments still escape `TEMPLATE_DIR`), and NUL bytes are not stripped. A caller (or upstream HTTP handler) that passes user-controlled input such as `../../../../etc/passwd%00` or `../config/secrets` can read any file the Node process can read, with the suffix `.html` appended. Even without traversal, names like `../../package` would resolve to `<repo>/package.html` outside the templates directory.
- Why it matters: Email-template rendering is frequently wired to product surfaces where the template name is selected by request data (campaign id, notification type, locale segment). One careless `renderEmailTemplate(req.body.template, …)` and this becomes an arbitrary-file disclosure primitive. The design says "Loads a template from `templates/email/<templateName>.html`" — i.e. the contract is that the file lives _inside_ that directory, which the implementation does not enforce.
- Source-of-truth reference: Design line 14 ("Loads a template from `templates/email/<templateName>.html`.") implies confinement to that directory.
- Proposed fix: Validate `templateName` against an allowlist regex before joining (e.g. `if (!/^[a-zA-Z0-9_-]+$/.test(templateName)) throw new Error(...)`), and additionally verify after `path.resolve` that the resolved path still starts with `path.resolve(TEMPLATE_DIR) + path.sep`. Reject NUL bytes explicitly.

### Medium

**2. `TEMPLATE_DIR` is resolved relative to `__dirname`, which breaks under ESM and after a build-output relocation.**

- File: `api/services/email.ts:31` — `const TEMPLATE_DIR = path.join(__dirname, '../../templates/email')`.
- Problem: `__dirname` is a CommonJS-only global. If this file is ever compiled to ESM (`"module": "ES2022"`, `"type": "module"`, or `tsc` with `--module nodenext`), `__dirname` is undefined and the module will throw at import time. Additionally, the relative `'../../templates/email'` hardcodes an assumption about how many levels deep the compiled file ends up (e.g. `dist/api/services/email.js` vs `dist/services/email.js` vs running TS directly via `ts-node` from `src/`). A change in `outDir` or moving the file changes which directory it points at, silently.
- Why it matters: The function will appear to work in tests run from the source tree but throw "Template not found" in production once the build layout shifts. Since the same `ENOENT` is converted to a friendly "Template not found" error, the misconfiguration will be misdiagnosed as a missing template rather than a wrong directory.
- Source-of-truth reference: Design line 14 (template location) — implementation must actually resolve to that location.
- Proposed fix: Resolve from a known anchor: e.g. `path.join(process.cwd(), 'templates/email')`, or inject `TEMPLATE_DIR` via configuration, or for ESM use `fileURLToPath(new URL('../../templates/email', import.meta.url))`. At minimum, document the expected build layout.

**3. Variable-substitution callback throws synchronously from inside `String.prototype.replace`, which is fine but the resulting error loses positional context.**

- File: `api/services/email.ts:60-67`.
- Problem: When a `{{missing}}` placeholder is encountered, the thrown error message names the variable but not the offset within the template, nor the surrounding context. For multi-variable templates with the same placeholder repeated, it is not obvious which occurrence triggered the failure (it will always be the first, but the message does not say so). More importantly, if `vars[varName]` is `undefined` _but_ the property exists (e.g. `{ name: undefined }`), `hasOwnProperty` returns true and the function will render the literal string `"undefined"`, which is almost certainly not intended.
- Why it matters: The acceptance criterion says "Throws if the template references a variable not in `vars`." A property explicitly set to `undefined` _is_ in `vars` by the `hasOwnProperty` definition, so the function will silently emit `undefined` into the email body. Users will receive emails reading "Hello undefined,". This is a Medium-severity correctness gap rather than High because it requires the caller to pass an explicit `undefined`, but it is easy to do (`{ name: user.firstName }` where `firstName` is optional).
- Source-of-truth reference: Design line 18 ("Throws if the template references a variable not in `vars`.") — debatable whether this covers `undefined` values, but the safer interpretation is to also reject them.
- Proposed fix: Either (a) treat `vars[varName] === undefined` as missing and throw the same error, or (b) document explicitly that `undefined` values render as the empty string and `null` as `"null"` (current behavior renders `"undefined"` and `"null"` respectively). Option (a) matches the principle of least surprise.

**4. Variable-name regex `[a-zA-Z_][a-zA-Z0-9_]*` silently ignores placeholders that use dotted paths, hyphens, or unicode identifiers.**

- File: `api/services/email.ts:33`.
- Problem: A template containing `{{user.name}}`, `{{first-name}}`, or `{{ホスト}}` will not match `VAR_PATTERN`, so those placeholders are emitted verbatim into the rendered HTML. There is no warning, no error — the email goes out with literal `{{user.name}}` in it. The design does not require dotted paths, but it also does not say "any unmatched `{{…}}` is left as-is silently"; a template author who mistypes `{{ user-name }}` will not be told.
- Why it matters: Silent passthrough of `{{…}}`-looking text in customer-facing emails is the kind of bug that ships and is only caught when a customer screenshots it. The current behavior mixes "throw on missing variable" (loud) with "don't even recognize this placeholder" (silent), which is inconsistent.
- Source-of-truth reference: Design lines 15-16 ("occurrences of `{{var}}` are replaced…") and 18 ("Throws if the template references a variable not in `vars`.") — together imply that anything looking like `{{…}}` should be handled, not silently passed through.
- Proposed fix: Either widen the regex to a more permissive `\{\{\s*([^}\s][^}]*?)\s*\}\}` and validate the captured name inside the callback (throwing on invalid names), or add a second pass that scans for unmatched `{{…}}` patterns after substitution and throws.

### Low

**5. `escapeHtml` escapes single quotes as `&#39;` rather than `&#x27;` and does not escape backticks.**

- File: `api/services/email.ts:35-42`.
- Problem: `&#39;` is valid HTML5 but `&#x27;` is the OWASP-recommended form and is more widely supported in legacy renderers. Backticks (`` ` ``) are not in the escape set; in some contexts (notably IE-era HTML attribute parsing) backticks can be used to break out of attribute values. For email HTML this is mostly academic — email clients are not browsers — but the function name implies a general-purpose escaper.
- Why it matters: Minor robustness/style issue. Does not affect the acceptance criteria.
- Source-of-truth reference: General secure-coding hygiene; not enumerated in the design.
- Proposed fix: Switch to `&#x27;` and add `` `:`&#96;` `` to the chain, or pull in a vetted escaper (`he`, `lodash.escape`).

**6. `escapeHtml(value: unknown)` uses `String(value)`, which calls `toString()` on objects and produces `[object Object]`.**

- File: `api/services/email.ts:35-36`.
- Problem: Passing `vars: { user: { name: 'Ada' } }` and a template containing `{{user}}` will render `[object Object]`. The design does not require nested-object support, but a stricter type than `Record<string, unknown>` (e.g. `Record<string, string | number | boolean | null>`) would catch the misuse at compile time. As written, the type allows anything.
- Why it matters: Style / type-safety nit. The function does what it says, but the input contract is looser than the implementation can faithfully serve.
- Source-of-truth reference: Design line 16 ("`vars[var]` (HTML-escaped)") — does not specify object handling.
- Proposed fix: Tighten the parameter type to `Record<string, string | number | boolean | null | undefined>`, or detect non-primitive values in `escapeHtml` and throw.

**7. The `'utf8'` encoding string is fine but `'utf-8'` is the IANA-canonical spelling; minor style nit.**

- File: `api/services/email.ts:52`.
- Problem: Both work in Node, but project style guides commonly prefer one. No behavioral impact.
- Why it matters: Pure style.
- Source-of-truth reference: N/A.
- Proposed fix: Optional — align with whatever the rest of `api/services/` uses.

**8. No caching of templates; every render re-reads the file from disk.**

- File: `api/services/email.ts:50-58`.
- Problem: For a service that sends many emails, this is N disk reads. Templates are typically immutable per deploy. Not a defect — the design did not ask for caching — but worth noting for follow-up.
- Why it matters: Performance, only under load. Below Medium because the design is silent on this.
- Source-of-truth reference: N/A.
- Proposed fix: Add an in-memory `Map<string, string>` cache keyed by `templateName`, optionally with an env-flag escape hatch for local development.
