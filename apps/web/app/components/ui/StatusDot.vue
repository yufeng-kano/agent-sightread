<script setup lang="ts">
/**
 * Status indicator. The dot is never alone — it always ships with its label, because
 * color-only status fails both colorblind users and screen readers.
 *
 * `info` is the in-progress tone: a running job is not a warning, so it stays out of the
 * ok/warn/danger hue family.
 */
withDefaults(
  defineProps<{
    tone?: 'ok' | 'warn' | 'danger' | 'info' | 'neutral'
    label: string
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span class="status" :class="tone">
    <span class="dot" aria-hidden="true" />
    <span class="label">{{ label }}</span>
  </span>
</template>

<style scoped>
.status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: var(--radius-full);
  background: var(--standby);
}

.label {
  color: var(--text-secondary);
  white-space: nowrap;
}

.ok .dot {
  background: var(--ok);
  box-shadow: var(--ok-ring);
}

.warn .dot {
  background: var(--warn);
}

.danger .dot {
  background: var(--danger);
}

.info .dot {
  background: var(--info);
}

.danger .label {
  color: var(--danger);
}
</style>
