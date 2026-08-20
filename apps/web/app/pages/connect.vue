<script setup lang="ts">
definePageMeta({ middleware: 'authed' })

const { t } = useI18n()
useHead(() => ({ title: t('connect.headTitle') }))

// The connector URL is this deployment's own origin; Caddy routes /mcp to the API.
const mcpUrl = ref('https://<host>/mcp')
onMounted(() => {
  mcpUrl.value = `${window.location.origin}/mcp`
})
</script>

<template>
  <div class="page">
    <UiPageHeader :title="t('connect.headTitle')" />

    <UiCard :title="t('connect.mcpTitle')">
      <div class="connect">
        <UiCopyField :value="mcpUrl" />
        <!-- The one sentence that matters: the connector authorizes over OAuth, so there is
             no key to paste — which is exactly why it does not live on the keys page. -->
        <p class="note">{{ t('connect.mcpBody') }}</p>
      </div>
    </UiCard>
  </div>
</template>

<style scoped>
/* Same measure as Settings: a form page, not a table page. No gap on the page itself —
   UiPageHeader carries its own bottom margin. */
.page {
  display: flex;
  flex-direction: column;
  max-width: 56rem;
  width: 100%;
}

.connect {
  display: grid;
  gap: var(--space-3);
}

.note {
  color: var(--muted);
  font-size: var(--text-sm);
  max-width: 72ch;
}
</style>
