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
const confirmingDelete = ref(false)

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
  keyPending.value = true
  keyError.value = null
  keyMessage.value = null
  try {
    await deleteOpenRouterKey()
    confirmingDelete.value = false
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
  <div class="page">
    <UiPageHeader :title="t('settings.headTitle')" />

    <div class="stack">
      <UiCard :title="t('settings.openrouterTitle')">
        <div class="section">
          <!-- The stored state, in the tone it deserves: a missing key is why parsing would
               fail, so it is written in the warning tone rather than boxed in a banner that
               would still be there after the user fixed it. -->
          <p v-if="openrouterKey?.present && openrouterKey.updated_at" class="state">
            {{
              t('settings.openrouterStored', {
                masked: openrouterKey.masked,
                updated: formatDateTime(openrouterKey.updated_at, locale),
              })
            }}
          </p>
          <p v-else class="state missing">{{ t('settings.openrouterMissing') }}</p>

          <form class="control-row" @submit.prevent="saveOpenRouterKey">
            <UiField v-slot="{ id }" class="grow" :label="t('settings.openrouterLabel')">
              <UiTextInput
                :id="id"
                v-model="keyInput"
                type="password"
                autocomplete="off"
                required
              />
            </UiField>
            <UiButton
              variant="primary"
              type="submit"
              :loading="keyPending"
              :disabled="!keyInput.trim()"
            >
              {{ t('common.save') }}
            </UiButton>
            <!-- Keeps its word: it destroys a credential the user has to fetch from OpenRouter
                 again, which is not something a bare glyph should be able to do. -->
            <UiButton
              v-if="openrouterKey?.present"
              variant="danger"
              :disabled="keyPending"
              @click="confirmingDelete = true"
            >
              <template #icon><UiIcon name="trash" /></template>
              {{ t('settings.openrouterDelete') }}
            </UiButton>
          </form>

          <UiBanner v-if="keyError" tone="error">{{ keyError }}</UiBanner>
          <UiBanner v-else-if="keyMessage" tone="ok">{{ keyMessage }}</UiBanner>
        </div>
      </UiCard>

      <UiCard :title="t('settings.defaultsTitle')">
        <div class="section">
          <UiBanner v-if="catalogError" tone="error">{{ catalogError }}</UiBanner>
          <UiSkeleton v-else-if="!catalog" :rows="2" />

          <form v-else class="control-row" @submit.prevent="saveDefaults">
            <UiField v-slot="{ id }" class="grow" :label="t('settings.defaultModel')">
              <UiSelect :id="id" v-model="defaultModel">
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
              </UiSelect>
            </UiField>

            <UiField v-slot="{ id }" class="grow" :label="t('settings.defaultProfile')">
              <UiSelect :id="id" v-model="defaultProfile">
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
              </UiSelect>
            </UiField>

            <UiButton variant="primary" type="submit" :loading="defaultsPending">
              {{ t('common.save') }}
            </UiButton>
          </form>

          <UiBanner v-if="defaultsError" tone="error">{{ defaultsError }}</UiBanner>
          <UiBanner v-else-if="defaultsMessage" tone="ok">{{ defaultsMessage }}</UiBanner>
        </div>
      </UiCard>
    </div>

    <UiConfirmDialog
      v-if="confirmingDelete"
      :title="t('settings.openrouterDelete')"
      :message="t('settings.openrouterDeleteConfirm')"
      :confirm-label="t('common.delete')"
      :pending="keyPending"
      @confirm="removeOpenRouterKey"
      @cancel="confirmingDelete = false"
    />
  </div>
</template>

<style scoped>
/* No gap on the page itself: UiPageHeader carries its own bottom margin. Forms also read
   better in a column than stretched across a desktop's full width — the tables on the other
   pages are what --content-max is for. */
.page {
  display: flex;
  flex-direction: column;
  max-width: 56rem;
  width: 100%;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.section {
  display: grid;
  gap: var(--space-4);
}

.state {
  color: var(--text-secondary);
  max-width: 72ch;
}

.state.missing {
  color: var(--warn);
}

/*
 * One row of controls that are all the same height: the fields' labels sit above them, so
 * the row aligns on its baseline edge and the buttons meet the bottom of the inputs. Every
 * control's height comes from --control-height, so nothing here re-states a pixel value.
 */
.control-row {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.grow {
  flex: 1 1 18rem;
  min-width: 0;
}
</style>
