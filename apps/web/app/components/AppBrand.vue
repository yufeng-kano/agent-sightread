<script setup lang="ts">
/** The product mark and name, linking home — the same in both shells. */
defineProps<{ to: string }>()

const { t } = useI18n()
</script>

<template>
  <NuxtLink class="brand" :to="to">
    <span class="brand-mark" aria-hidden="true">sr</span>
    <span class="brand-name">{{ t('app.name') }}</span>
  </NuxtLink>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  flex-shrink: 0;
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-tight);
}

.brand-mark {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--accent-fg);
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
}

.brand-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
