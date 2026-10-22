import { existsSync, readFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { $fetch, fetch, setup } from '@nuxt/test-utils/e2e'

const auditFile = join(mkdtempSync(join(tmpdir(), 'fixture-nuxt-')), 'audit.log')
process.env.AUDIT_FILE = auditFile

describe('contract', async () => {
  await setup({ rootDir: fileURLToPath(new URL('..', import.meta.url)), server: true })

  it('orders 42 returns total', async () => {
    const body = await $fetch<{ id: string; total: number }>('/orders/42')
    expect(body.id).toBe('42')
    expect(typeof body.total).toBe('number')
  })

  it('orders 404 returns not found', async () => {
    expect((await fetch('/orders/404')).status).toBe(404)
  })

  it('orders boom returns 500', async () => {
    expect((await fetch('/orders/boom')).status).toBe(500)
  })

  it('pricing returns price', async () => {
    const body = await $fetch<{ id: string; price: number }>('/pricing/7')
    expect(body.id).toBe('7')
    expect(typeof body.price).toBe('number')
  })

  it('audit job runs', async () => {
    await $fetch('/orders/43')
    const deadline = Date.now() + 10000
    while (Date.now() < deadline) {
      if (existsSync(auditFile) && readFileSync(auditFile, 'utf8').split('\n').includes('43')) return
      await new Promise((r) => setTimeout(r, 100))
    }
    throw new Error('audit task did not record order 43')
  })
})
