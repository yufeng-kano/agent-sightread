<script setup lang="ts">
/**
 * Native `<select>` in the app's control skin — same box as `UiTextInput` and any button on
 * its row, driven by `--control-height`.
 *
 * The options are a slot rather than a prop: the model picker groups its options, and a
 * prop-driven list would have to re-invent `<optgroup>` and per-option `disabled` to say
 * the same thing the platform already says.
 */
defineProps<{
  modelValue: string
  id?: string
  describedBy?: string
  disabled?: boolean
}>()

defineEmits<{ 'update:modelValue': [string] }>()
</script>

<template>
  <select
    :id="id"
    class="control"
    :value="modelValue"
    :disabled="disabled"
    :aria-describedby="describedBy"
    @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <slot />
  </select>
</template>

<style scoped>
.control {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  height: var(--control-height);
  padding: 0 var(--space-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font-size: var(--text-sm);
  outline: none;
  cursor: pointer;
  transition:
    border-color var(--duration-fast) var(--ease),
    box-shadow var(--duration-fast) var(--ease);
}

.control:focus {
  border-color: var(--ring-border);
  box-shadow: var(--ring);
  outline: none;
}

.control:disabled {
  background: var(--surface-2);
  color: var(--muted);
  cursor: not-allowed;
}

@media (pointer: coarse) {
  .control {
    font-size: var(--text-md);
  }
}
</style>
