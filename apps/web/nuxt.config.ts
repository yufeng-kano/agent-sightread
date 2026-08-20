// Nuxt control plane (docs/web.md). The app only ever uses relative URLs: in production
// Caddy routes /api/*, /v1/* to FastAPI and everything else here; in development the
// nitro dev proxy below reproduces that same-origin split so session cookies work.
export default defineNuxtConfig({
  modules: ['@nuxtjs/i18n', '@nuxt/eslint'],
  compatibilityDate: '2025-08-20',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],

  app: {
    head: {
      htmlAttrs: { lang: 'en' },
      meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
      // The .ico is not decoration: clients that do not take SVG (and connector webviews
      // that just fetch /favicon.ico) fall back to whatever icon they already hold for the
      // parent domain when this 404s or answers a blank placeholder.
      link: [
        { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' },
        { rel: 'icon', href: '/favicon.ico', sizes: '48x48' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
      ],
    },
  },

  i18n: {
    defaultLocale: 'en',
    strategy: 'prefix_except_default',
    // Locale lives in the URL, so no cookie or Accept-Language redirect guessing.
    detectBrowserLanguage: false,
    locales: [
      { code: 'en', language: 'en', name: 'English', file: 'en.ts' },
      { code: 'zh-TW', language: 'zh-TW', name: '繁體中文', file: 'zh-TW.ts' },
    ],
  },

  routeRules: {
    // The landing page is the SEO surface: prerendered HTML in both locales.
    '/': { prerender: true },
    '/zh-TW': { prerender: true },
    // Control-plane pages are per-user and session-authenticated: client-rendered only.
    '/dashboard': { ssr: false },
    '/keys': { ssr: false },
    '/settings': { ssr: false },
    '/jobs': { ssr: false },
    '/zh-TW/dashboard': { ssr: false },
    '/zh-TW/keys': { ssr: false },
    '/zh-TW/settings': { ssr: false },
    '/zh-TW/jobs': { ssr: false },
  },

  nitro: {
    devProxy: {
      '/api': { target: 'http://localhost:8000/api', changeOrigin: false },
      '/v1': { target: 'http://localhost:8000/v1', changeOrigin: false },
    },
  },
})
