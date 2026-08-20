<script setup lang="ts">
/**
 * The public shell — the landing page only.
 *
 * It shares every token with the signed-in app but not its frame: this is a document to be
 * read top to bottom, so it scrolls as one, with a quiet bar above it.
 *
 * The bar deliberately carries no sign-in control. The page has exactly one thing to ask of
 * a visitor, the hero states it in words, and a second identical button 80px above it would
 * be the same action twice on one screen.
 */
const localePath = useLocalePath()
</script>

<template>
  <div class="public">
    <header class="topbar">
      <div class="topbar-inner">
        <AppBrand :to="localePath('/')" />
        <LocaleSwitch />
      </div>
    </header>

    <slot />
  </div>
</template>

<style scoped>
.public {
  min-height: 100dvh;
  background: var(--bg);
}

.topbar {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.topbar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-height: var(--header-height);
  max-width: 56rem;
  margin: 0 auto;
  padding: var(--space-2) var(--space-5);
}

@media (max-width: 640px) {
  .topbar-inner {
    padding: var(--space-2) var(--space-4);
  }
}
</style>
