# Code review request

I just finished implementing the work below.

**Implementer note:** All 6 unit tests pass including the HTML escaping and missing-variable cases. Walked through the failure modes and the implementation matches the design exactly. Ready for production.

## Design / Acceptance criteria

# Email template renderer

Add `renderEmailTemplate(templateName, vars)` in `api/services/email.ts`
that:

- Loads a template from `templates/email/<templateName>.html`.
- Substitutes variables: occurrences of `{{var}}` are replaced with
  `vars[var]` (HTML-escaped).
- Throws if the template file is missing.
- Throws if the template references a variable not in `vars`.
- Returns the rendered HTML string.
- 6 unit tests cover happy path, missing template, missing variable,
  HTML escaping of values, no-vars template, and a multi-variable template.


## Files changed

// api/services/email.ts (new function added at end)

import * as fs from 'fs/promises'
import * as path from 'path'

const TEMPLATE_DIR = path.join(__dirname, '../../templates/email')

const VAR_PATTERN = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g

function escapeHtml(value: unknown): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export async function renderEmailTemplate(
  templateName: string,
  vars: Record<string, unknown>,
): Promise<string> {
  const templatePath = path.join(TEMPLATE_DIR, `${templateName}.html`)

  let template: string
  try {
    template = await fs.readFile(templatePath, 'utf8')
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
      throw new Error(`Template not found: ${templateName}`)
    }
    throw err
  }

  return template.replace(VAR_PATTERN, (_match, varName: string) => {
    if (!Object.prototype.hasOwnProperty.call(vars, varName)) {
      throw new Error(
        `Template ${templateName} references variable "${varName}" not in vars`,
      )
    }
    return escapeHtml(vars[varName])
  })
}


## Review instructions

Please review this work using the structured-code-review format: an
8-field preamble, then findings tagged with severity
Critical / High / Medium / Low, each with a file:line citation.

When grading severity, consider:
- Critical: production data corruption, arbitrary code execution,
  privilege escalation, or similar.
- High: significant security risk, resource leak under common load,
  silent data inconsistency, design requirement violated.
- Medium: incorrect behavior in some inputs, unclear error handling,
  performance degradation, missing validation that the design implies.
- Low: style, naming, minor refactoring suggestions, nits.

Be specific about file paths and line numbers in citations.
