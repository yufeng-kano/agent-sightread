<script setup lang="ts">
/**
 * A read-only value with a copy button — the connector URL, a freshly issued API key.
 *
 * `emphasis` is for a value the user has to copy *now* because it will not be shown again:
 * it is the only place in the app where a value gets a stronger box than its neighbours,
 * and the tone comes from the block it sits in rather than from a colour of its own.
 */
defineProps<{
  value: string
  /** Only where the surrounding text does not already name the value. */
  label?: string
  emphasis?: boolean
}>()
</script>

<template>
  <div class="copy-field" :class="{ emphasis }">
    <span v-if="label" class="copy-label">{{ label }}</span>
    <code class="copy-value mono">{{ value }}</code>
    <UiCopyButton :text="value" variant="secondary" />
  </div>
</template>

<style scoped>
.copy-field {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
}

.copy-field.emphasis {
  background: var(--surface);
  border-color: var(--border-strong);
}

.copy-label {
  flex-shrink: 0;
  color: var(--muted);
  font-size: var(--text-xs);
}

.copy-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  font-size: var(--text-xs);
}

@media (max-width: 640px) {
  .copy-field {
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .copy-label {
    width: 100%;
  }

  .copy-value {
    /* Wrap rather than ellipsize on a phone: there is no hover to reveal the rest, and a
       truncated URL or key is useless. */
    flex: 1 1 100%;
    white-space: normal;
    overflow-wrap: anywhere;
  }
}
</style>
