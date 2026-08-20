<script setup lang="ts">
/**
 * One row's share of the largest value in its column, as a bar.
 *
 * Unlike a quota meter the fill never escalates through amber to red: a bigger share of a
 * month's spend is not a worse state, it is just a bigger number. The figure it ranks is
 * always printed in the next column, so the bar is emphasis and never the only signal —
 * which is also why it carries an accessible name rather than a visible label.
 */
const props = defineProps<{
  /** 0..1, this row against the largest row in the same table. */
  share: number
  /** Accessible name — the row this bar belongs to. */
  label: string
}>()

const percent = computed(() => Math.round(Math.max(0, Math.min(1, props.share)) * 100))
</script>

<template>
  <div
    class="track"
    role="meter"
    :aria-valuenow="percent"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-label="label"
  >
    <div class="fill" :style="{ width: `${percent}%` }" />
  </div>
</template>

<style scoped>
.track {
  height: 5px;
  border-radius: var(--radius-full);
  background: var(--bar-track);
  overflow: hidden;
}

.fill {
  height: 100%;
  min-width: 1px;
  border-radius: var(--radius-full);
  background: var(--bar-fill);
  transition: width var(--duration-slow) var(--ease);
}
</style>
