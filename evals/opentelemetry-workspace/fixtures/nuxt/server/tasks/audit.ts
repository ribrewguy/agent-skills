import { appendFileSync } from 'node:fs'

export const recorded: string[] = []

export default defineTask({
  meta: { name: 'audit', description: 'Record that an order was fetched' },
  run({ payload }) {
    const id = String(payload?.id)
    recorded.push(id)
    if (process.env.AUDIT_FILE) appendFileSync(process.env.AUDIT_FILE, `${id}\n`)
    return { result: 'recorded' }
  },
})
