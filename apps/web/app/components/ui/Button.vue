<script setup lang="ts">
/**
 * The app's only button.
 *
 * Renders as `<button>`, or as `<a>` / `<NuxtLink>` when given `href` / `to` — a link that
 * looks like a button is still a link, and must keep middle-click and "open in new tab".
 * `href` stays same-tab: the one place we use it is the server-redirect sign-in flow.
 *
 * `loading` shows a spinner *in place of* the icon and disables the control, so a pending
 * action can never be fired twice; the label stays put so the button does not resize
 * mid-press.
 *
 * Every size is driven by `--control-height` (or a fixed step off it), so a button beside
 * an input is the same box — see docs/web.md § Rules.
 */
const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
    size?: 'sm' | 'md'
    /** Square button with an icon and no visible label — `label` becomes its accessible name. */
    iconOnly?: boolean
    loading?: boolean
    disabled?: boolean
    /**
     * Accessible name. Required when `iconOnly`, where it is also the tooltip. On a
     * labelled button it *overrides* the visible text for assistive tech — for a control
     * whose words repeat down a list ("Revoke" on every row) and need the subject spelled
     * out. It must still contain the visible label, per WCAG 2.5.3: a voice-control user
     * says what they can see.
     */
    label?: string
    href?: string
    to?: string
    type?: 'button' | 'submit'
  }>(),
  // The three optional strings are spelled out as `undefined` because that is how
  // `vue/require-default-prop` is satisfied for a type-only declaration: absent is the
  // default, and saying so keeps the lint output free of noise to read past.
  { variant: 'secondary', size: 'md', type: 'button', label: undefined, href: undefined, to: undefined },
)

// Resolved once at setup: `resolveComponent` is only valid here or in render, not inside a
// getter that may run later.
const NuxtLinkComponent = resolveComponent('NuxtLink')

const isDisabled = computed(() => props.disabled || props.loading)
const tag = computed(() => (props.to ? NuxtLinkComponent : props.href ? 'a' : 'button'))

/**
 * A disabled *link* has no native equivalent, so it is downgraded to an inert anchor with
 * `aria-disabled` rather than shipping a clickable control that looks dead.
 */
const bindings = computed(() => {
  if (props.to) {
    return isDisabled.value ? { role: 'link', 'aria-disabled': 'true' } : { to: props.to }
  }
  if (props.href) {
    return isDisabled.value ? { role: 'link', 'aria-disabled': 'true' } : { href: props.href }
  }
  return { type: props.type, disabled: isDisabled.value }
})
</script>

<template>
  <component
    :is="tag"
    class="btn"
    :class="[`btn-${variant}`, `btn-${size}`, { 'btn-icon': iconOnly, 'is-loading': loading }]"
    :aria-label="label"
    :title="iconOnly ? label : undefined"
    :aria-busy="loading ? 'true' : undefined"
    v-bind="bindings"
  >
    <UiSpinner v-if="loading" class="btn-spinner" />
    <slot v-else name="icon" />
    <span v-if="!iconOnly" class="btn-label"><slot /></span>
  </component>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-weight: var(--weight-medium);
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease),
    border-color var(--duration-fast) var(--ease),
    color var(--duration-fast) var(--ease);
}

.btn-md {
  height: var(--control-height);
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
}

.btn-sm {
  height: calc(var(--control-height) - 6px);
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
}

.btn-icon {
  padding: 0;
  aspect-ratio: 1;
}

.btn-icon.btn-md {
  width: var(--control-height);
}

.btn-icon.btn-sm {
  width: calc(var(--control-height) - 6px);
}

.btn:disabled,
.btn[aria-disabled='true'] {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

/* Loading keeps full opacity — the spinner already says "busy", and dimming on top of it
   reads as broken rather than pending. */
.btn.is-loading {
  opacity: 1;
  cursor: progress;
}

.btn-primary {
  background: var(--accent);
  color: var(--accent-fg);
}

.btn-primary:hover {
  background: var(--accent-hover);
}

.btn-secondary {
  background: var(--surface);
  color: var(--text);
  border-color: var(--border-strong);
}

.btn-secondary:hover {
  background: var(--surface-2);
  border-color: var(--faint);
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}

.btn-ghost:hover {
  background: var(--hover);
  color: var(--text);
}

.btn-danger {
  background: var(--surface);
  color: var(--danger);
  border-color: var(--danger-border);
}

.btn-danger:hover {
  background: var(--danger-bg);
}

.btn-spinner {
  flex-shrink: 0;
}

.btn :deep(svg) {
  flex-shrink: 0;
  width: 15px;
  height: 15px;
}

.btn-sm :deep(svg) {
  width: 14px;
  height: 14px;
}
</style>
