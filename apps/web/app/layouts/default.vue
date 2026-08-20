<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'

/**
 * The signed-in frame.
 *
 * A fixed grid, not a scrolling document: the sidebar stays put while only the content
 * region scrolls. That is what keeps each page's own controls — its sticky `UiPageHeader` —
 * reachable at any scroll depth.
 *
 * Below 1080px the sidebar becomes a drawer behind a menu button in a mobile bar. No icon
 * rail and no bottom tab bar: the labels are doing the work, and a tab bar would spend the
 * scarcest axis on a phone.
 */
const { t, locale, locales } = useI18n()
const route = useRoute()
const localePath = useLocalePath()
const switchLocalePath = useSwitchLocalePath()
const auth = useAuth()

const NAV = [
  { icon: 'dashboard', to: '/dashboard', label: 'nav.dashboard' },
  { icon: 'jobs', to: '/jobs', label: 'nav.jobs' },
  { icon: 'keys', to: '/keys', label: 'nav.keys' },
  { icon: 'connect', to: '/connect', label: 'nav.connect' },
  { icon: 'settings', to: '/settings', label: 'nav.settings' },
] as const

/** The signed-in identity: the name when Google sent one, the address otherwise. */
const account = computed(() => auth.me.value?.user.name?.trim() || auth.me.value?.user.email || '')
/** The avatar glyph: the backend sends no picture, so the identity's first letter stands in. */
const initial = computed(() => (account.value[0] ?? '?').toUpperCase())

/** The popover over the account row: language choice and sign-out live here. */
const accountMenu = ref(false)
const foot = ref<HTMLElement | null>(null)
const accountButton = ref<HTMLElement | null>(null)

function onDocumentClick(event: MouseEvent) {
  if (accountMenu.value && foot.value && !foot.value.contains(event.target as Node)) {
    accountMenu.value = false
  }
}

const sidebar = ref<HTMLElement | null>(null)
/** A ref on a component yields its instance; `UiButton` with neither `to` nor `href` roots
 *  a real `<button>`, which is the element focus has to return to. */
const menuButton = ref<ComponentPublicInstance | null>(null)
const drawerOpen = ref(false)

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Matches the 1080px breakpoint in this component's own stylesheet. */
function isDrawerLayout(): boolean {
  return typeof matchMedia !== 'undefined' && matchMedia('(max-width: 1080px)').matches
}

// A destination the user just picked is behind the drawer they picked it from. The account
// menu closes too: a locale link re-navigates the same page.
watch(() => route.path, () => {
  drawerOpen.value = false
  accountMenu.value = false
})

/**
 * Open, the drawer covers the page behind a scrim — that makes it modal, and modal surfaces
 * owe the same three things a dialog does: focus moves in, Tab stays in, and focus returns
 * to the trigger on close. Without the trap, Tab walks invisibly through the page beneath.
 */
watch(drawerOpen, async (open) => {
  if (!isDrawerLayout()) return
  if (!open) {
    ;(menuButton.value?.$el as HTMLElement | undefined)?.focus()
    return
  }
  await nextTick()
  sidebar.value?.querySelector<HTMLElement>(FOCUSABLE)?.focus()
})

function onKeydown(event: KeyboardEvent) {
  // The account popover closes before the drawer does: it is the topmost open surface.
  if (event.key === 'Escape' && accountMenu.value) {
    accountMenu.value = false
    accountButton.value?.focus()
    return
  }

  // `drawerOpen` only means anything below the breakpoint — above it the sidebar is a static
  // column, and trapping focus in it would strand the user in the nav. The flag can be left
  // true by a resize, so check the layout rather than trusting it alone.
  if (!drawerOpen.value || !isDrawerLayout()) return

  if (event.key === 'Escape') {
    drawerOpen.value = false
    return
  }
  if (event.key !== 'Tab' || !sidebar.value) return

  const items = [...sidebar.value.querySelectorAll<HTMLElement>(FOCUSABLE)]
  if (!items.length) return
  const first = items[0]!
  const last = items[items.length - 1]!
  const active = document.activeElement

  // Also catches focus already outside the drawer — a click on the scrim, say — pulling it
  // back rather than letting Tab continue through the page behind.
  if (event.shiftKey && (active === first || !sidebar.value.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || !sidebar.value.contains(active))) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocumentClick)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocumentClick)
})

async function signOut() {
  await auth.signOut()
  await navigateTo(localePath('/'))
}
</script>

<template>
  <div class="shell">
    <a class="skip-link" href="#content">{{ t('app.skipToContent') }}</a>

    <!-- Under the drawer and above the content; clicking it closes. -->
    <div v-if="drawerOpen" class="scrim" @click="drawerOpen = false" />

    <aside ref="sidebar" class="sidebar" :class="{ open: drawerOpen }">
      <div class="sidebar-head">
        <AppBrand :to="localePath('/dashboard')" />
        <UiButton
          class="drawer-close"
          variant="ghost"
          icon-only
          :label="t('nav.closeMenu')"
          @click="drawerOpen = false"
        >
          <template #icon><UiIcon name="close" /></template>
        </UiButton>
      </div>

      <nav class="nav" :aria-label="t('nav.primary')">
        <NuxtLink
          v-for="item in NAV"
          :key="item.to"
          class="nav-item"
          :to="localePath(item.to)"
          active-class="active"
        >
          <UiIcon :name="item.icon" />
          <span class="nav-label">{{ t(item.label) }}</span>
        </NuxtLink>
      </nav>

      <div ref="foot" class="sidebar-foot">
        <div v-if="accountMenu" id="account-menu" class="account-menu" role="menu">
          <!-- Each locale in its own language, so it is legible whichever catalog is
               loaded. Real links: the locale lives in the URL. -->
          <NuxtLink
            v-for="option in locales"
            :key="option.code"
            class="menu-item"
            role="menuitem"
            :to="switchLocalePath(option.code)"
            :aria-current="option.code === locale ? 'true' : undefined"
            @click="accountMenu = false"
          >
            <span class="menu-label">{{ option.name }}</span>
            <UiIcon v-if="option.code === locale" name="check" />
          </NuxtLink>
          <div class="menu-rule" role="separator" />
          <button type="button" class="menu-item" role="menuitem" @click="signOut">
            <span class="menu-label">{{ t('nav.signOut') }}</span>
            <UiIcon name="sign-out" />
          </button>
        </div>

        <button
          ref="accountButton"
          type="button"
          class="account"
          aria-haspopup="menu"
          aria-controls="account-menu"
          :aria-expanded="accountMenu ? 'true' : 'false'"
          :title="account || undefined"
          @click="accountMenu = !accountMenu"
        >
          <span class="avatar" aria-hidden="true">{{ initial }}</span>
          <!-- Rendered even while `GET /api/me` is still in flight: the label is the row's
               only flexible track, and dropping it would slide the gear across the foot the
               moment the identity arrives. -->
          <span class="account-label">{{ account }}</span>
          <UiIcon name="settings" class="account-gear" />
        </button>
      </div>
    </aside>

    <div class="frame">
      <header class="mobile-bar">
        <UiButton
          ref="menuButton"
          variant="ghost"
          icon-only
          :label="t('nav.openMenu')"
          :aria-expanded="drawerOpen ? 'true' : 'false'"
          @click="drawerOpen = true"
        >
          <template #icon><UiIcon name="menu" /></template>
        </UiButton>
        <AppBrand :to="localePath('/dashboard')" />
      </header>

      <main id="content" class="content" tabindex="-1">
        <div class="content-inner">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  /* The frame owns the viewport: the document behind it never scrolls, which is what keeps
     the sidebar put and gives each page's sticky header something to stick to. */
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

/* --- Sidebar -------------------------------------------------------------- */

.sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  height: var(--header-height);
  padding: 0 var(--space-2);
  margin-bottom: var(--space-2);
}

/* The close control only exists once the sidebar is a drawer. Qualified by its parent so it
   outranks `UiButton`'s own `display` without depending on stylesheet order. */
.sidebar-head .drawer-close {
  display: none;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow-y: auto;
  /* As a drawer this sits over the content region; scrolling it to its end must not chain
     through to the page behind. */
  overscroll-behavior: contain;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  /* The shared control height, so the nav grows with the rest of the app's targets on a
     coarse pointer rather than needing a breakpoint of its own. */
  height: var(--control-height);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: var(--text-sm);
  overflow: hidden;
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

.nav-item :deep(svg) {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  pointer-events: none;
}

.nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Pinned to the bottom, divided by a rule: the session's own row, anchoring the popover
   that holds everything about the session rather than a destination. */
.sidebar-foot {
  position: relative;
  margin-top: auto;
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
}

.account {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  min-width: 0;
  height: var(--control-height);
  padding: 0 var(--space-2);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease);
}

.account:hover,
.account[aria-expanded='true'] {
  background: var(--hover);
}

.avatar {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--surface-2);
  color: var(--muted);
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
}

.account-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-xs);
}

.account .account-gear {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  color: var(--muted);
}

/* Pops above its anchor — the foot is the lowest thing in the viewport, so upward is the
   only direction with room. Width matches the row it belongs to. */
.account-menu {
  position: absolute;
  bottom: calc(100% + var(--space-1));
  left: 0;
  right: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: calc(var(--control-height) - 4px);
  padding: 0 var(--space-2);
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease),
    color var(--duration-fast) var(--ease);
}

.menu-item:hover {
  background: var(--hover);
  color: var(--text);
}

.menu-item :deep(svg) {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-left: auto;
}

.menu-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-rule {
  height: 1px;
  margin: var(--space-1) var(--space-2);
  background: var(--border);
}

/* --- Content -------------------------------------------------------------- */

.frame {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.mobile-bar {
  display: none;
}

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

@media (max-width: 1080px) {
  .shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .scrim {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: var(--overlay);
    overscroll-behavior: contain;
    animation: fade var(--duration) var(--ease-enter);
  }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 50;
    width: var(--sidebar-width);
    transform: translateX(-100%);
    box-shadow: var(--shadow-lg);
    /* Off-screen *and* inert: a translated-away drawer is still focusable, so Tab would walk
       into a menu nobody can see. `visibility` fixes that, but it is not interpolable —
       applied plainly it would snap to hidden on the first frame and eat the slide-out.
       Hence the `0s` step delayed by the transform's own duration on close, undelayed on
       open. */
    visibility: hidden;
    transition:
      transform var(--duration) var(--ease-exit),
      visibility 0s linear var(--duration);
  }

  .sidebar.open {
    transform: none;
    visibility: visible;
    transition:
      transform var(--duration-slow) var(--ease-enter),
      visibility 0s;
  }

  .sidebar-head .drawer-close {
    display: inline-flex;
  }

  .mobile-bar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--header-height);
    flex-shrink: 0;
    padding: 0 var(--space-3);
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }

  @keyframes fade {
    from {
      opacity: 0;
    }
  }
}

@media (max-width: 640px) {
  .content-inner {
    --page-gutter: var(--space-3);
    --page-top: var(--space-4);
    --page-bottom: calc(var(--space-8) + env(safe-area-inset-bottom, 0px));
  }
}
</style>
