<script setup lang="ts">
import {
  deleteOpenRouterKey,
  listModels,
  listProfiles,
  putOpenRouterKey,
  putSettings,
} from '~/lib/api'
import { formatDateTime } from '~/lib/format'
import { modelLabel, sortModelsRecommendedFirst } from '~/lib/models'

definePageMeta({ middleware: 'authed' })

const { t, locale } = useI18n()
useHead(() => ({ title: t('settings.headTitle') }))

const auth = useAuth()
const { resolve } = useApiError()

const { data: catalog, errorMessage: catalogError } = useAuthedData(async () => {
  const [models, profiles] = await Promise.all([listModels(), listProfiles()])
  return { models: sortModelsRecommendedFirst(models.data), profiles: profiles.data }
})

const recommendedModels = computed(() => catalog.value?.models.filter((model) => model.recommended) ?? [])
const otherModels = computed(() => catalog.value?.models.filter((model) => !model.recommended) ?? [])

const openrouterKey = computed(() => auth.me.value?.openrouter_key ?? null)
const keyInput = ref('')
const keyPending = ref(false)
const keyError = ref<string | null>(null)
const keyMessage = ref<string | null>(null)

const defaultModel = ref('')
const defaultProfile = ref('')
const defaultsPending = ref(false)
const defaultsError = ref<string | null>(null)
const defaultsMessage = ref<string | null>(null)

watch(
  () => auth.me.value?.settings,
  (settings) => {
    defaultModel.value = settings?.default_model ?? ''
    defaultProfile.value = settings?.default_profile ?? ''
  },
  { immediate: true },
)

async function saveOpenRouterKey() {
  const candidate = keyInput.value.trim()
  if (!candidate || keyPending.value) {
    return
  }
  keyPending.value = true
  keyError.value = null
  keyMessage.value = null
  try {
    await putOpenRouterKey(candidate)
    keyInput.value = ''
    keyMessage.value = t('settings.openrouterSaved')
    await auth.refresh()
  } catch (error) {
    keyError.value = await resolve(error)
  } finally {
    keyPending.value = false
  }
}

async function removeOpenRouterKey() {
  if (!window.confirm(t('settings.openrouterDeleteConfirm'))) {
    return
  }
  keyPending.value = true
  keyError.value = null
  keyMessage.value = null
  try {
    await deleteOpenRouterKey()
    await auth.refresh()
  } catch (error) {
    keyError.value = await resolve(error)
  } finally {
    keyPending.value = false
  }
}

async function saveDefaults() {
  defaultsPending.value = true
  defaultsError.value = null
  defaultsMessage.value = null
  try {
    await putSettings({
      default_model: defaultModel.value || null,
      default_profile: defaultProfile.value || null,
    })
    defaultsMessage.value = t('settings.saved')
    await auth.refresh()
  } catch (error) {
    defaultsError.value = await resolve(error)
  } finally {
    defaultsPending.value = false
  }
}
</script>

<template>
  <main class="page">
    <section>
      <h2 class="section-head">{{ t('settings.openrouterTitle') }}</h2>

      <p v-if="openrouterKey?.present && openrouterKey.updated_at">
        {{
          t('settings.openrouterStored', {
            masked: openrouterKey.masked,
            updated: formatDateTime(openrouterKey.updated_at, locale),
          })
        }}
      </p>
      <p v-else class="muted">{{ t('settings.openrouterMissing') }}</p>

      <form class="row" @submit.prevent="saveOpenRouterKey">
        <div class="field">
          <label for="openrouter-key">{{ t('settings.openrouterLabel') }}</label>
          <input
            id="openrouter-key"
            v-model="keyInput"
            type="password"
            autocomplete="off"
            spellcheck="false"
            required
          >
        </div>
        <button class="primary submit" type="submit" :disabled="keyPending || !keyInput.trim()">
          {{ t('common.save') }}
        </button>
        <button
          v-if="openrouterKey?.present"
          class="icon danger submit"
          type="button"
          :disabled="keyPending"
          :title="t('settings.openrouterDelete')"
          :aria-label="t('settings.openrouterDelete')"
          @click="removeOpenRouterKey"
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
      </form>

      <p v-if="keyError" class="error">{{ keyError }}</p>
      <p v-else-if="keyMessage" class="muted">{{ keyMessage }}</p>
    </section>

    <section>
      <h2 class="section-head">{{ t('settings.defaultsTitle') }}</h2>

      <p v-if="catalogError" class="error">{{ catalogError }}</p>
      <p v-else-if="!catalog" class="muted">{{ t('common.loading') }}</p>

      <form v-else class="row" @submit.prevent="saveDefaults">
        <div class="field">
          <label for="default-model">{{ t('settings.defaultModel') }}</label>
          <select id="default-model" v-model="defaultModel">
            <option value="">{{ t('common.notSet') }}</option>
            <optgroup v-if="recommendedModels.length" :label="t('settings.recommendedGroup')">
              <option v-for="model in recommendedModels" :key="model.id" :value="model.id">
                {{ modelLabel(model) }}
              </option>
            </optgroup>
            <optgroup v-if="otherModels.length" :label="t('settings.otherModelsGroup')">
              <option v-for="model in otherModels" :key="model.id" :value="model.id">
                {{ modelLabel(model) }}
              </option>
            </optgroup>
          </select>
        </div>

        <div class="field">
          <label for="default-profile">{{ t('settings.defaultProfile') }}</label>
          <select id="default-profile" v-model="defaultProfile">
            <option value="">{{ t('common.notSet') }}</option>
            <option
              v-for="profile in catalog.profiles"
              :key="profile.id"
              :value="profile.id"
              :disabled="!profile.available"
            >
              {{
                profile.available
                  ? profile.name
                  : t('settings.profileUnavailable', { name: profile.name })
              }}
            </option>
          </select>
        </div>

        <button class="primary submit" type="submit" :disabled="defaultsPending">
          {{ t('common.save') }}
        </button>
      </form>

      <p v-if="defaultsError" class="error">{{ defaultsError }}</p>
      <p v-else-if="defaultsMessage" class="muted">{{ defaultsMessage }}</p>
    </section>
  </main>
</template>

<style scoped>
.submit {
  align-self: end;
}
</style>
