<script setup lang="ts">
/**
 * "Are you sure?" for the two actions in this app that destroy something the user would have
 * to re-create: revoking an API key and deleting the stored OpenRouter key.
 *
 * A dialog rather than `window.confirm`: the native one cannot say which key, cannot be
 * styled to mark the action as destructive, and on some browsers is suppressed entirely.
 */
defineProps<{
  title: string
  message: string
  /** The destructive verb, e.g. "Revoke". Never a generic "OK". */
  confirmLabel: string
  pending?: boolean
}>()

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const { t } = useI18n()
</script>

<template>
  <UiModal :title="title" @close="emit('cancel')">
    <p class="message">{{ message }}</p>
    <template #footer>
      <UiButton variant="ghost" :disabled="pending" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </UiButton>
      <UiButton variant="danger" :loading="pending" @click="emit('confirm')">
        {{ confirmLabel }}
      </UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.message {
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
