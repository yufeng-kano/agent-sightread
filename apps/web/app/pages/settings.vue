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

/**
 * One choice, not two: a parsing default is a model *and* the format it is prompted for,
 * so the dropdown lists preset profiles (which pair them) plus at most one custom model.
 * Encoded as `profile:<id>` / `model:<id>` / '' so the `<select>` can carry either kind.
 */
const selection = ref('')
/** The custom entry the dropdown shows — the stored default, or one just picked. */
const customModel = ref<string | null>(null)
const defaultsPending = ref(false)
const defaultsError = ref<string | null>(null)
const defaultsMessage = ref<string | null>(null)

const addingCustom = ref(false)
const customChoice = ref('')

watch(
  () => auth.me.value?.settings,
  (settings) => {
    const profile = settings?.default_profile
    const model = settings?.default_model
    selection.value = profile ? `profile:${profile}` : model ? `model:${model}` : ''
    if (model) {
      customModel.value = model
    }
  },
  { immediate: true },
)

const customOptionLabel = computed(() => {
  if (!customModel.value) {
    return ''
  }
  const entry = catalog.value?.models.find((model) => model.id === customModel.value)
  return entry ? modelLabel(entry) : customModel.value
})

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

/** Saves on selection, reverting the dropdown when the server refuses — a picker whose
    display disagrees with the stored default would be lying. */
async function applySelection(value: string) {
  const previous = selection.value
  selection.value = value
  defaultsPending.value = true
  defaultsError.value = null
  defaultsMessage.value = null
  try {
    await putSettings({
      default_model: value.startsWith('model:') ? value.slice('model:'.length) : null,
      default_profile: value.startsWith('profile:') ? value.slice('profile:'.length) : null,
    })
    defaultsMessage.value = t('settings.saved')
    await auth.refresh()
  } catch (error) {
    selection.value = previous
    defaultsError.value = await resolve(error)
  } finally {
    defaultsPending.value = false
  }
}

function openCustom() {
  customChoice.value = customModel.value ?? ''
  addingCustom.value = true
}

async function submitCustom() {
  const choice = customChoice.value
  if (!choice || defaultsPending.value) {
    return
  }
  customModel.value = choice
  addingCustom.value = false
  await applySelection(`model:${choice}`)
}
</script>

<template>
  <div class="page">
    <UiPageHeader :title="t('settings.headTitle')" />

    <div class="stack">
      <UiCard :title="t('settings.openrouterTitle')">
        <div class="section">
          <!-- Only the stored state is worth a line. Absence explains itself: the field is
               empty and asks to be filled. -->
          <p v-if="openrouterKey?.present && openrouterKey.updated_at" class="state">
            {{
              t('settings.openrouterStored', {
                masked: openrouterKey.masked,
                updated: formatDateTime(openrouterKey.updated_at, locale),
              })
            }}
          </p>

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

          <!-- One dropdown, saved as it changes: each recommended entry is a model *and*
               the bbox format it is prompted for; "custom" is any image-input model on the
               default prompts. -->
          <div v-else class="control-row">
            <UiField v-slot="{ id }" class="grow" :label="t('settings.defaultLabel')">
              <UiSelect
                :id="id"
                :model-value="selection"
                :disabled="defaultsPending"
                @update:model-value="applySelection"
              >
                <option value="">{{ t('common.notSet') }}</option>
                <optgroup :label="t('settings.recommendedGroup')">
                  <option
                    v-for="profile in catalog.profiles"
                    :key="profile.id"
                    :value="`profile:${profile.id}`"
                    :disabled="!profile.available"
                  >
                    {{
                      profile.available
                        ? `${profile.name} · ${profile.model}`
                        : t('settings.profileUnavailable', { name: profile.name })
                    }}
                  </option>
                </optgroup>
                <optgroup v-if="customModel" :label="t('settings.customGroup')">
                  <option :value="`model:${customModel}`">{{ customOptionLabel }}</option>
                </optgroup>
              </UiSelect>
            </UiField>

            <UiButton :disabled="defaultsPending" @click="openCustom">
              <template #icon><UiIcon name="plus" /></template>
              {{ t('settings.addCustom') }}
            </UiButton>
          </div>

          <UiBanner v-if="defaultsError" tone="error">{{ defaultsError }}</UiBanner>
          <UiBanner v-else-if="defaultsMessage" tone="ok">{{ defaultsMessage }}</UiBanner>
        </div>
      </UiCard>
    </div>

    <UiModal v-if="addingCustom" :title="t('settings.customTitle')" @close="addingCustom = false">
      <form id="custom-model" class="custom-form" @submit.prevent="submitCustom">
        <UiField v-slot="{ id }" :label="t('settings.customModelLabel')">
          <UiSelect :id="id" v-model="customChoice">
            <option value="" disabled>{{ t('common.notSet') }}</option>
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
        <p class="custom-note">{{ t('settings.customNote') }}</p>
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="defaultsPending" @click="addingCustom = false">
          {{ t('common.cancel') }}
        </UiButton>
        <UiButton
          variant="primary"
          type="submit"
          form="custom-model"
          :disabled="!customChoice"
        >
          {{ t('settings.customUse') }}
        </UiButton>
      </template>
    </UiModal>

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

.custom-form {
  display: grid;
  gap: var(--space-3);
}

.custom-note {
  color: var(--muted);
  font-size: var(--text-sm);
  max-width: 60ch;
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
