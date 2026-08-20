<script setup lang="ts">
/**
 * Text input. Pairs with `UiField`, which supplies `id` and `describedBy` through its slot
 * props. Height comes from `--control-height` so it matches any button on its row.
 */
withDefaults(
  defineProps<{
    modelValue: string
    id?: string
    type?: 'text' | 'password'
    placeholder?: string
    describedBy?: string
    invalid?: boolean
    disabled?: boolean
    required?: boolean
    maxlength?: number
    autocomplete?: string
    mono?: boolean
  }>(),
  {
    type: 'text',
    autocomplete: 'off',
    id: undefined,
    placeholder: undefined,
    describedBy: undefined,
    maxlength: undefined,
  },
)

defineEmits<{ 'update:modelValue': [string] }>()
</script>

<template>
  <input
    :id="id"
    class="control"
    :class="{ mono, invalid }"
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :required="required"
    :maxlength="maxlength"
    :autocomplete="autocomplete"
    :aria-describedby="describedBy"
    :aria-invalid="invalid || undefined"
    spellcheck="false"
    @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
  >
</template>

<style scoped>
.control {
  width: 100%;
  min-width: 0;
  height: var(--control-height);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font-size: var(--text-sm);
  outline: none;
  transition:
    border-color var(--duration-fast) var(--ease),
    box-shadow var(--duration-fast) var(--ease);
}

.control::placeholder {
  color: var(--faint);
}

.control:focus {
  /* The border plus ring already meet the focus-visibility bar, and the global outline
     would sit awkwardly outside a field's own ring. */
  border-color: var(--ring-border);
  box-shadow: var(--ring);
  outline: none;
}

.control:disabled {
  background: var(--surface-2);
  color: var(--muted);
  cursor: not-allowed;
}

.control.invalid {
  border-color: var(--danger-border);
}

.mono {
  font-family: var(--mono);
  font-size: var(--text-xs);
}

/* 16px stops iOS Safari zooming the viewport on focus. */
@media (pointer: coarse) {
  .control,
  .mono {
    font-size: var(--text-md);
  }
}
</style>
