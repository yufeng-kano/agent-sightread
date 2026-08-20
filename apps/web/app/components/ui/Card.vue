<script setup lang="ts">
/**
 * The surface a block of content sits on.
 *
 * A card bounds a scroll region or a genuinely separate dataset. It is never the page's
 * skeleton and it never nests: structure comes from the grid, from spacing, rules and
 * headings (docs/web.md § Stack — design restraint).
 *
 * `flush` drops the body padding for content that manages its own (a table). `fill` makes
 * the card consume its parent's height, which is what lets the body scroll internally
 * instead of growing the page.
 *
 * There is no subtitle prop: a card whose contents are self-evident carries no line
 * explaining itself.
 */
defineProps<{
  title?: string
  flush?: boolean
  fill?: boolean
  /** Caps the body's height so a long list scrolls inside the card rather than as the page. */
  bodyMax?: string
}>()

defineSlots<{
  default: () => unknown
  /** Beside the title: identity metadata about this card's dataset (a row count). */
  heading?: () => unknown
  /** Right side of the head — this section's own controls. */
  actions?: () => unknown
  /** Below the head, outside the padded body: a form row, a filter. */
  toolbar?: () => unknown
}>()
</script>

<template>
  <section class="card" :class="{ fill }">
    <header v-if="title || $slots.heading || $slots.actions" class="card-head">
      <!-- Kept even when the card has no title: it is what `space-between` places the
           actions against. -->
      <div class="card-heading">
        <h2 v-if="title" class="card-title">{{ title }}</h2>
        <slot name="heading" />
      </div>
      <div v-if="$slots.actions" class="card-actions">
        <slot name="actions" />
      </div>
    </header>

    <div v-if="$slots.toolbar" class="card-toolbar">
      <slot name="toolbar" />
    </div>

    <div class="card-body" :class="{ flush }" :style="bodyMax ? { maxHeight: bodyMax } : undefined">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

/* Consumes its parent's height so .card-body has a bounded box to scroll within. Only
   bounds anything if the parent is itself bounded — `min-height: 0` is what lets the card
   shrink below its content once that holds. */
.card.fill {
  height: 100%;
  min-height: 0;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border);
}

/* A row, so the `heading` slot's metadata sits on the title's baseline instead of stacking
   under it as the subtitle it deliberately is not. */
.card-heading {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.card-title {
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.card-toolbar {
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--border);
}

.card-body {
  min-height: 0;
  padding: var(--space-5);
  overflow: auto;
}

/*
 * A flush body reaches the card's edge, so it also reaches the card's corners — and a
 * child's background paints *over* the parent's rounded one (a table's sticky header is
 * opaque by necessity). The body therefore carries the radius itself, on whichever ends it
 * actually reaches, and clips to it. One pixel smaller than the card's: the border sits
 * outside this box, and matching it exactly leaves a hairline showing through the curve.
 */
.card-body.flush {
  padding: 0;
}

.card-body.flush:first-child {
  border-radius: calc(var(--radius) - 1px) calc(var(--radius) - 1px) 0 0;
}

.card-body.flush:last-child {
  border-radius: 0 0 calc(var(--radius) - 1px) calc(var(--radius) - 1px);
}

/* Both ends — the card is nothing but its body. Needs its own rule: the two above would
   otherwise cancel each other's corners out. */
.card-body.flush:first-child:last-child {
  border-radius: calc(var(--radius) - 1px);
}

/* In a filling card the body is the scroll region. */
.card.fill .card-body {
  flex: 1;
}

@media (max-width: 640px) {
  .card-head {
    padding: var(--space-3) var(--space-4);
  }

  .card-toolbar,
  .card-body {
    padding: var(--space-4);
  }

  .card-body.flush {
    padding: 0;
  }
}
</style>
