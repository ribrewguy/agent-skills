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
