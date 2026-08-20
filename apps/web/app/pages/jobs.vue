<script setup lang="ts">
import { getJobResult, listJobs, type JobResult, type JobSummary } from '~/lib/api'
import { formatDateTime } from '~/lib/format'

definePageMeta({ middleware: 'authed' })

const JOB_LIMIT = 50

const { t, locale } = useI18n()
useHead(() => ({ title: t('jobs.headTitle') }))

const { data, pending, errorMessage, refresh } = useAuthedData(() => listJobs(JOB_LIMIT))
const { resolve } = useApiError()

const expandedJobId = ref<string | null>(null)
const loadingResultId = ref<string | null>(null)
const results = reactive(new Map<string, JobResult>())
const resultErrors = reactive(new Map<string, string>())

async function toggleResult(job: JobSummary) {
  if (expandedJobId.value === job.job_id) {
    expandedJobId.value = null
    return
  }
  expandedJobId.value = job.job_id
  if (results.has(job.job_id)) {
    return
  }
  loadingResultId.value = job.job_id
  resultErrors.delete(job.job_id)
  try {
    results.set(job.job_id, await getJobResult(job.job_id))
  } catch (error) {
    resultErrors.set(job.job_id, await resolve(error))
  } finally {
    loadingResultId.value = null
  }
}
</script>

<template>
  <main class="page">
    <section>
      <div class="section-head">
        <h2>{{ t('jobs.recent', { limit: JOB_LIMIT }) }}</h2>
        <RefreshButton :busy="pending" @click="refresh" />
      </div>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <p v-else-if="!data" class="muted">{{ t('common.loading') }}</p>
      <p v-else-if="!data.jobs.length" class="empty">{{ t('jobs.empty') }}</p>
      <div v-else class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ t('jobs.columnFile') }}</th>
              <th>{{ t('jobs.columnStatus') }}</th>
              <th>{{ t('jobs.columnModel') }}</th>
              <th class="numeric">{{ t('jobs.columnPages') }}</th>
              <th>{{ t('jobs.columnCreated') }}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <template v-for="job in data.jobs" :key="job.job_id">
              <tr>
                <td>{{ job.filename }}</td>
                <td :class="`status-${job.status}`">{{ t(`jobs.status.${job.status}`) }}</td>
                <td class="mono">{{ job.model }}</td>
                <td class="numeric">{{ job.page_count ? `${job.pages_done}/${job.page_count}` : job.pages_done }}</td>
                <td>{{ formatDateTime(job.created_at, locale) }}</td>
                <td class="numeric">
                  <button class="link" type="button" @click="toggleResult(job)">
                    {{ expandedJobId === job.job_id ? t('jobs.hideResult') : t('jobs.showResult') }}
                  </button>
                </td>
              </tr>
              <tr v-if="expandedJobId === job.job_id">
                <td colspan="6">
                  <p v-if="job.error" class="error">{{ job.error }}</p>
                  <p v-if="loadingResultId === job.job_id" class="muted">{{ t('common.loading') }}</p>
                  <p v-else-if="resultErrors.get(job.job_id)" class="error">
                    {{ resultErrors.get(job.job_id) }}
                  </p>
                  <pre v-else-if="results.get(job.job_id)" class="result-json">{{
                    JSON.stringify(results.get(job.job_id), null, 2)
                  }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
