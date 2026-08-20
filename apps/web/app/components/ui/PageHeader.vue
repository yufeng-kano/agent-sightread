<script setup lang="ts">
/**
 * The sticky top of every signed-in page: the title, and the controls the page is operated
 * by.
 *
 * Sticky is the point — Refresh and Create must be reachable at any scroll depth, so they
 * live here rather than in the content that scrolls away.
 *
 * The visible `h1` is the one thing here that repeats the shell's active nav item, and the
 * deliberate exception to the rule against restating the shell: it anchors the content
 * column, and a header row that is nothing but right-aligned controls reads as a floating
 * toolbar rather than as the top of a page. What is *not* here is a subtitle — the line
 * beneath the heading explaining what the page is was the redundancy.
 *
 * Chrome, not a surface: one compact row over a heavy frosted wash of the page background,
 * so a stuck header reads as the page frosting out under the controls.
 */
defineProps<{ title: string }>()

defineSlots<{
  /** Identity metadata beside the title — the range these figures cover. Not a subtitle. */
  meta?: () => unknown
  /** Primary and secondary actions, right-aligned on the title row. */
  actions?: () => unknown
}>()
</script>

<template>
  <header class="page-header">
    <div class="row">
      <div class="heading">
        <h1 class="title">{{ title }}</h1>
        <slot name="meta" />
      </div>
      <div v-if="$slots.actions" class="actions">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<style scoped>
/**
 * The frost spans the content region, not just the card column: cancelling the region's top
 * padding lets the blur reach the top edge once the header is stuck, and cancelling the
 * gutter lets the wash and the bottom rule run the region's full width. The same gutter
 * comes back as padding so the title and the actions stay on the card column.
 *
 * Both values are the shell's own, inherited rather than restated — two copies would
 * silently disagree at whichever breakpoint someone updated only one of them.
 */
.page-header {
  --top: var(--page-top, var(--space-6));
  --gutter: var(--page-gutter, var(--space-4));

  position: sticky;
  top: 0;
  z-index: 10;
  margin: calc(var(--top) * -1) calc(var(--gutter) * -1) var(--space-5);
  padding: var(--top) var(--gutter) 0;
  background: var(--topbar-bg);
  backdrop-filter: blur(var(--topbar-blur));
  -webkit-backdrop-filter: blur(var(--topbar-blur));
  border-bottom: 1px solid var(--border);
}

/*
 * Title and actions on one row: the header is a strip of chrome, and a second stacked text
 * row is what would make it read as a block.
 *
 * The control-height floor keeps the header the same height on a page whose only control is
 * absent, so navigating between pages does not shift the content under it.
 */
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
  min-height: var(--control-height);
  padding-bottom: var(--space-3);
}

.heading {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  min-width: 0;
}

.title {
  min-width: 0;
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
}

/*
 * Sized to its controls at every width, never widened to fill the line. The auto margin is
 * what keeps it right-aligned on a line it wraps onto: `space-between` puts a lone item at
 * the start, and a wrapped line is a line of one.
 */
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .page-header {
    margin-bottom: var(--space-4);
  }
}
</style>
