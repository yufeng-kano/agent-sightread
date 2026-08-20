<script setup lang="ts">
/**
 * The signed-in frame.
 *
 * A fixed frame, not a scrolling document: the top bar stays put while only the content
 * region scrolls. That is what keeps each page's own controls — its sticky `UiPageHeader` —
 * reachable at any scroll depth.
 *
 * Four destinations, so the nav is a row of words in the bar rather than kano-proxy's
 * sidebar: a 248px column would spend a quarter of the width naming four things, and a
 * drawer would hide them behind a press. Below 640px the nav drops to its own scrollable
 * row inside the same bar, so every destination stays one tap away without a drawer to
 * trap focus in.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const auth = useAuth()

const NAV = [
  { to: '/dashboard', label: 'nav.dashboard' },
  { to: '/keys', label: 'nav.keys' },
  { to: '/jobs', label: 'nav.jobs' },
  { to: '/settings', label: 'nav.settings' },
] as const

/** The signed-in identity: the name when Google sent one, the address otherwise. */
const account = computed(() => auth.me.value?.user.name?.trim() || auth.me.value?.user.email || '')

async function signOut() {
  await auth.signOut()
  await navigateTo(localePath('/'))
}
</script>

<template>
  <div class="shell">
    <a class="skip-link" href="#content">{{ t('app.skipToContent') }}</a>

    <header class="topbar">
      <div class="topbar-inner">
        <AppBrand :to="localePath('/dashboard')" />

        <nav class="nav" :aria-label="t('nav.primary')">
          <NuxtLink
            v-for="item in NAV"
            :key="item.to"
            class="nav-item"
            :to="localePath(item.to)"
            active-class="active"
          >
            {{ t(item.label) }}
          </NuxtLink>
        </nav>

        <div class="topbar-end">
          <LocaleSwitch />
          <span v-if="account" class="account" :title="account">{{ account }}</span>
          <UiButton variant="ghost" icon-only :label="t('nav.signOut')" @click="signOut">
            <template #icon><UiIcon name="sign-out" /></template>
          </UiButton>
        </div>
      </div>
    </header>

    <main id="content" class="content" tabindex="-1">
      <div class="content-inner">
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  /* The frame owns the viewport: the document behind it never scrolls, which is what keeps
     the bar put and gives each page's sticky header something to stick to. */
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
}

.skip-link {
  position: absolute;
  top: var(--space-2);
  left: var(--space-2);
  z-index: 80;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--accent-fg);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  transform: translateY(-200%);
}

.skip-link:focus {
  transform: none;
}

/* --- Top bar ------------------------------------------------------------- */

.topbar {
  flex-shrink: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

/* Same cap and gutter as the content column below, so the brand sits on the same left edge
   as the page header and the cards. */
.topbar-inner {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  height: var(--header-height);
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 0 var(--space-4);
}

.nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-width: 0;
  margin-right: auto;
  overflow-x: auto;
  scrollbar-width: none;
}

.nav::-webkit-scrollbar {
  display: none;
}

.nav-item {
  display: inline-flex;
  align-items: center;
  height: var(--control-height);
  padding: 0 var(--space-3);
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: var(--text-sm);
  white-space: nowrap;
  transition:
    background var(--duration-fast) var(--ease),
    color var(--duration-fast) var(--ease);
}

.nav-item:hover {
  background: var(--hover);
  color: var(--text);
}

/* Active is a filled pill *and* a step up in weight — the fill on its own is a couple of
   percent of luminance and reads as noise without the weight. */
.nav-item.active {
  background: var(--hover);
  color: var(--text);
  font-weight: var(--weight-medium);
}

.topbar-end {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.account {
  max-width: 22ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: var(--text-xs);
}

/* --- Content ------------------------------------------------------------- */

/* The one scrolling element in the signed-in app. `min-height: 0` is what lets it actually
   shrink inside the flex parent — without it the region grows and the scrollbar never
   appears. The gutter is reserved permanently: pages differ in height, and without it the
   content column would slide sideways by the scrollbar's width on every navigation between
   one that scrolls and one that does not. */
.content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

/**
 * The page metrics are published as inherited custom properties rather than only applied as
 * padding: `UiPageHeader` cancels the top and the gutter with negative margins so its blur
 * reaches the region's edges, and a second hardcoded copy would silently disagree the first
 * time only one of them changed.
 *
 * `min-height: 100%` plus a flex column is what lets a page fill the region exactly — a page
 * that bounds its own table (Jobs) sets `flex: 1; min-height: 0` on its root and needs no
 * viewport arithmetic of its own.
 */
.content-inner {
  --page-gutter: var(--space-4);
  --page-top: var(--space-6);
  /* The safe-area inset lives inside this value so every consumer stays correct without
     knowing about it. */
  --page-bottom: calc(var(--space-10) + env(safe-area-inset-bottom, 0px));

  display: flex;
  flex-direction: column;
  min-height: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: var(--page-top) var(--page-gutter) var(--page-bottom);
}

/* --- Responsive ----------------------------------------------------------- */

@media (max-width: 860px) {
  /* The address is the least load-bearing thing in the bar: the shell already only renders
     for a signed-in user, and the sign-out control is right beside it. */
  .account {
    display: none;
  }
}

@media (max-width: 640px) {
  /* The nav takes its own row rather than being pushed into a drawer — four words fit, and
     a drawer would cost a press plus a focus trap to reach what is one tap away here. */
  .topbar-inner {
    height: auto;
    flex-wrap: wrap;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
  }

  .nav {
    order: 3;
    flex-basis: 100%;
    margin-right: 0;
  }

  .topbar-end {
    margin-left: auto;
  }

  .content-inner {
    --page-gutter: var(--space-3);
    --page-top: var(--space-4);
    --page-bottom: calc(var(--space-8) + env(safe-area-inset-bottom, 0px));
  }
}
</style>
