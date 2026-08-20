<script setup lang="ts">
defineProps<{ busy?: boolean }>()
defineEmits<{ click: [] }>()

const { t } = useI18n()
</script>

<template>
  <button
    class="icon"
    type="button"
    :disabled="busy"
    :title="t('common.refresh')"
    :aria-label="t('common.refresh')"
    @click="$emit('click')"
  >
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      stroke-width="1.7"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M20 12a8 8 0 1 1-2.34-5.66" />
      <polyline points="20 4 20 9 15 9" />
    </svg>
  </button>
</template>
