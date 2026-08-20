<script setup lang="ts">
import { createKey, listKeys, revokeKey, type CreatedApiKey } from '~/lib/api'
import { formatDateTime } from '~/lib/format'

definePageMeta({ middleware: 'authed' })

const { t, locale } = useI18n()
useHead(() => ({ title: t('keys.headTitle') }))

const { data, pending, errorMessage, refresh } = useAuthedData(() => listKeys())
const { resolve } = useApiError()

const newKeyName = ref('')
const creating = ref(false)
const mutationError = ref<string | null>(null)
const createdKey = ref<CreatedApiKey | null>(null)
const revokingId = ref<number | null>(null)

// The connector URL is this deployment's own origin; Caddy routes /mcp to the API.
const mcpUrl = ref('https://<host>/mcp')
onMounted(() => {
  mcpUrl.value = `${window.location.origin}/mcp`
})

async function submitCreate() {
  const name = newKeyName.value.trim()
  if (!name || creating.value) {
    return
  }
  creating.value = true
  mutationError.value = null
  try {
    createdKey.value = await createKey(name)
    newKeyName.value = ''
    await refresh()
  } catch (error) {
    mutationError.value = await resolve(error)
  } finally {
    creating.value = false
  }
}

async function revoke(id: number, name: string) {
  if (!window.confirm(t('keys.revokeConfirm', { name }))) {
    return
  }
  revokingId.value = id
  mutationError.value = null
  try {
    await revokeKey(id)
    if (createdKey.value?.id === id) {
      createdKey.value = null
    }
    await refresh()
  } catch (error) {
    mutationError.value = await resolve(error)
  } finally {
    revokingId.value = null
  }
}
</script>

<template>
  <main class="page">
    <section>
      <div class="section-head">
        <h2>{{ t('keys.listTitle') }}</h2>
        <RefreshButton :busy="pending" @click="refresh" />
      </div>

      <form class="row" @submit.prevent="submitCreate">
        <div class="field">
          <label for="key-name">{{ t('keys.nameLabel') }}</label>
          <input id="key-name" v-model="newKeyName" type="text" maxlength="255" required>
        </div>
        <button class="primary submit" type="submit" :disabled="creating || !newKeyName.trim()">
          {{ t('keys.create') }}
        </button>
      </form>

      <div v-if="createdKey" class="notice notice-warning">
        <div class="row created">
          <code class="mono">{{ createdKey.key }}</code>
          <CopyButton :text="createdKey.key" />
        </div>
        <p>{{ t('keys.createdWarning') }}</p>
      </div>

      <p class="muted">{{ t('keys.usageNote') }}</p>

      <p v-if="mutationError" class="error">{{ mutationError }}</p>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <p v-else-if="!data" class="muted">{{ t('common.loading') }}</p>
      <p v-else-if="!data.keys.length" class="empty">{{ t('keys.empty') }}</p>
      <div v-else class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ t('keys.columnName') }}</th>
              <th>{{ t('keys.columnPrefix') }}</th>
              <th>{{ t('keys.columnCreated') }}</th>
              <th>{{ t('keys.columnLastUsed') }}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in data.keys" :key="key.id">
              <td>{{ key.name }}</td>
              <td class="mono">{{ key.prefix }}</td>
              <td>{{ formatDateTime(key.created_at, locale) }}</td>
              <td>
                <span v-if="key.last_used_at">{{ formatDateTime(key.last_used_at, locale) }}</span>
                <span v-else class="muted">{{ t('common.never') }}</span>
              </td>
              <td class="numeric">
                <button
                  class="icon danger"
                  type="button"
                  :disabled="revokingId === key.id"
                  :title="t('keys.revoke')"
                  :aria-label="t('keys.revoke')"
                  @click="revoke(key.id, key.name)"
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
                    <path d="M4 7h16" />
                    <path d="M10 11v6M14 11v6" />
                    <path d="M6 7l1 13h10l1-13" />
                    <path d="M9 7V4h6v3" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section>
      <div class="section-head">
        <h2>{{ t('keys.mcpTitle') }}</h2>
        <CopyButton :text="mcpUrl" />
      </div>
      <pre>{{ mcpUrl }}</pre>
      <p class="muted">{{ t('keys.mcpBody') }}</p>
    </section>
  </main>
</template>

<style scoped>
.submit {
  align-self: end;
}

.created code {
  overflow-wrap: anywhere;
}

.created {
  align-items: center;
}
</style>
