<script setup lang="ts">
/**
 * Language choice, in both shells.
 *
 * Each option is written in its own language, so it is legible whichever catalog is
 * currently loaded — a translated list would name 繁體中文 "Chinese" to someone who cannot
 * read the rest of the page. They stay real links (the locale lives in the URL), so the
 * choice is bookmarkable and works without JavaScript on the prerendered landing.
 */
const { t, locale, locales } = useI18n()
const switchLocalePath = useSwitchLocalePath()
</script>

<template>
  <nav class="locales" :aria-label="t('nav.language')">
    <NuxtLink
      v-for="option in locales"
      :key="option.code"
      class="locale"
      :class="{ active: option.code === locale }"
      :to="switchLocalePath(option.code)"
      :aria-current="option.code === locale ? 'true' : undefined"
    >
      {{ option.name }}
    </NuxtLink>
  </nav>
</template>

<style scoped>
.locales {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.locale {
  display: inline-flex;
  align-items: center;
  height: calc(var(--control-height) - 10px);
  padding: 0 var(--space-2);
  border-radius: var(--radius-xs);
  color: var(--muted);
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
  white-space: nowrap;
  transition:
    background var(--duration-fast) var(--ease),
    color var(--duration-fast) var(--ease);
}

.locale:hover:not(.active) {
  background: var(--hover);
  color: var(--text);
}

/* The current locale is a fill *and* a step up in tone — the fill alone is a couple of
   percent of luminance and reads as noise without it. */
.locale.active {
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow);
}
</style>
