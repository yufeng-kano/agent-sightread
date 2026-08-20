import { defineConfig } from 'vitest/config'

// Only framework-free modules are unit tested: the API client and the display
// transforms (docs/testing.md § Frontend). No browser, no Nuxt runtime.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['app/**/*.test.ts'],
  },
})
