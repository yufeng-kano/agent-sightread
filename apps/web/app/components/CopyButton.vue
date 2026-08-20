<script setup lang="ts">
const props = defineProps<{ text: string }>()

const { t } = useI18n()
const copied = ref(false)
let resetTimer: ReturnType<typeof setTimeout> | undefined

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
  } catch {
    // Clipboard access can be denied (insecure context, permissions); the value stays
    // selectable on the page, so there is nothing to report.
    return
  }
  copied.value = true
  clearTimeout(resetTimer)
  resetTimer = setTimeout(() => {
    copied.value = false
  }, 1500)
}

onUnmounted(() => clearTimeout(resetTimer))
</script>

<template>
  <button
    class="icon"
    type="button"
    :title="copied ? t('common.copied') : t('common.copy')"
    :aria-label="copied ? t('common.copied') : t('common.copy')"
    @click="copy"
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
      <polyline v-if="copied" points="4 12.5 9.5 18 20 6.5" />
      <template v-else>
        <rect x="9" y="9" width="11" height="11" rx="2" />
        <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
      </template>
    </svg>
  </button>
</template>
