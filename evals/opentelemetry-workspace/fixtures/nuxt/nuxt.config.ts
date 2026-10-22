export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  nitro: {
    preset: 'node-server',
    experimental: { tasks: true },
  },
})
