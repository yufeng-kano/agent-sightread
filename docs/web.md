# Web (Nuxt control plane)

The web app is a **pure control plane**: configure, issue, observe. It never uploads, previews, or renders documents — the data plane is API/MCP only.

## Stack

Nuxt (latest stable) + TypeScript + `@nuxtjs/i18n` (en, zh-TW; en is the source catalog), pnpm. No heavy UI framework — hand-rolled primitives, design restraint in the kano-proxy spirit: one surface, icons over restated copy, no decorative cards.

## Pages

| Page | Rendering | Content |
|------|-----------|---------|
| `/` sign-in | **prerendered, public** (en + `/zh-TW`, hreflang) — still the SEO surface: meta tags, OG. Sitemap deferred: needs the public origin (`i18n.baseUrl`), configure when a host exists | kano-proxy-style login page: dark brand panel (dark in both themes) with the mark and a one-line pitch; sign-in panel with the Google button (official mark + prescribed colors) and, when available, the dev sign-in. No marketing copy, no API how-to — curl/MCP instructions live on `/keys`. A signed-in visitor is redirected to `/dashboard` (which is how the OAuth callback's redirect to `web_url` lands in the app) |
| `/dashboard` | client-side, authed | usage: cost + tokens per day and per model (`GET /api/usage`) |
| `/keys` | client-side, authed | API key list/create/revoke; plaintext shown once; REST usage (curl with `Authorization: Bearer`) |
| `/connect` | client-side, authed | Claude MCP connector: endpoint URL + the one sentence that matters (OAuth, no key to paste) |
| `/settings` | client-side, authed | OpenRouter key (masked, save validates upstream); parsing default as **one** dropdown of preset profiles (model + bbox format pairs from `GET /v1/profiles`) plus an "add custom model" dialog picking any image-input model from `GET /v1/models` (runs default prompts, `profile: null`); selection saves on change |
| `/jobs` | client-side, authed | parse history: filename, status, model, pages, expandable raw result JSON (per-job cost not exposed yet — usage aggregates only) |

## Design system (as built)

- Tokens in `app/assets/css/main.css`, ported from kano-proxy's zinc system: surface ramp, three-step secondary text, monochrome accent inverting between themes, status colors with paired `-bg`/`-border`, spacing/radius/type/motion scales. Every color is defined in both `:root` theme blocks; nothing outside them names a color. One `--control-height` drives Button/TextInput/Select (40px on coarse pointers).
- One layout, `default`: the signed-in fixed frame following kano-proxy's AppShell — a left sidebar (brand head, icon+label nav for dashboard/jobs/keys/connect/settings, foot with an account row: avatar initial + name opening a popover with the language links and sign-out), a fixed grid where only the content region scrolls, and below 1080px the sidebar becomes a focus-trapped drawer behind a header menu button. The sign-in page is full-bleed two-column and owns its own frame (`layout: false`), sharing tokens only; the locale switch component appears only there.
- Shared primitives live in `app/components/ui/`: DataTable (the only table markup, sticky headers, <768px card fallback), Modal, Button, TextInput, Select, CopyField, UsageBar, status dot+word. Icon-only controls carry `label` (= aria-label + tooltip); destructive actions keep their visible word.
- Cards bound scroll regions; never page skeleton, never nested. Empty states say what would be here. A failed refresh keeps its data.
- Icons ship as three files in `public/`: `favicon.svg` (the source mark), `favicon.ico` (16/32/48, generated from it) and `apple-touch-icon.png` (180). All three are declared in `nuxt.config.ts`, and the FastAPI consent page declares them too. The `.ico` is not redundant: clients that do not take SVG — connector webviews among them — request `/favicon.ico`, and when that answers a blank placeholder they fall back to whatever icon they already hold for the parent domain.

## Rules

- Auth state via `GET /api/me`; unauthenticated → sign-in page; signed-in on `/` → `/dashboard` (locale-aware, client-side). Login is a plain link to `/api/auth/login` (server redirect flow, no client OAuth).
- The web app calls only `/api/*` (+ `GET /v1/models`, `GET /v1/profiles` which are safe reads). Session cookie, `credentials: include`, custom `X-Requested-With` header on mutations (CSRF pairing with SameSite=Lax).
- Frontend renders only what the backend returns — empty states are real states, never fabricated sample data.
- Uploads never pass through Nuxt/Node — there is no upload UI; `curl`/connector instructions live on `/keys`.
- i18n: every user-visible string goes through the catalog; en and zh-TW ship together.
