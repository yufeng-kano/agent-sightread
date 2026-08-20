<script setup lang="ts">
/**
 * A short word or figure from a closed set — a count beside a card title.
 *
 * `white-space: nowrap` is deliberate, and it is also the limit: anything open-ended or
 * long would clip mid-word with its own border sliced through it, so a long value is plain
 * text in a tone colour instead.
 */
withDefaults(defineProps<{ tone?: 'neutral' | 'ok' | 'warn' | 'danger' }>(), { tone: 'neutral' })
</script>

<template>
  <span class="badge" :class="tone"><slot /></span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
  padding: 2px var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-full);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  font-variant-numeric: tabular-nums;
  line-height: 1.5;
  white-space: nowrap;
}

.neutral {
  background: var(--hover);
  color: var(--muted);
}

.ok {
  background: var(--ok-bg);
  border-color: var(--ok-border);
  color: var(--ok);
}

.warn {
  background: var(--warn-bg);
  border-color: var(--warn-border);
  color: var(--warn);
}

.danger {
  background: var(--danger-bg);
  border-color: var(--danger-border);
  color: var(--danger);
}
</style>
