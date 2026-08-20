<script setup lang="ts">
import { getJobResult, listJobs, type JobResult, type JobStatus, type JobSummary } from '~/lib/api'
import { formatDateTime } from '~/lib/format'
import type { TableColumn } from '~/lib/table'

definePageMeta({ middleware: 'authed' })

const JOB_LIMIT = 50

const { t, locale } = useI18n()
useHead(() => ({ title: t('jobs.headTitle') }))

const { data, pending, errorMessage, refresh } = useAuthedData(() => listJobs(JOB_LIMIT))
const { resolve } = useApiError()

/** The row whose result is open. The JSON is a document, so it gets a dialog rather than a
    row that grows to twenty lines and pushes every other job off the screen. */
const openJob = ref<JobSummary | null>(null)
const loadingResultId = ref<string | null>(null)
const results = reactive(new Map<string, JobResult>())
const resultErrors = reactive(new Map<string, string>())

/** Never color alone: each tone ships with the status word beside it. Running is
    informational, not a warning — a job in flight is not a problem. */
const STATUS_TONE: Record<JobStatus, 'neutral' | 'info' | 'ok' | 'danger'> = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'ok',
  failed: 'danger',
}

const columns = computed<TableColumn<JobSummary>[]>(() => [
  { key: 'file', header: t('jobs.columnFile') },
  { key: 'status', header: t('jobs.columnStatus') },
  { key: 'model', header: t('jobs.columnModel') },
  { key: 'pages', header: t('jobs.columnPages'), numeric: true, width: '90px' },
  { key: 'created', header: t('jobs.columnCreated'), hideOnMobile: true },
  { key: 'result', header: '', srHeader: t('jobs.result'), align: 'end', width: '56px' },
])

async function showResult(job: JobSummary) {
  openJob.value = job
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
  <div class="page">
    <UiPageHeader :title="t('jobs.headTitle')">
      <template #meta>
        <span class="period">{{ t('jobs.recent', { limit: JOB_LIMIT }) }}</span>
      </template>
      <template #actions>
        <UiButton
          variant="ghost"
          icon-only
          :label="t('common.refresh')"
          :loading="pending"
          @click="refresh"
        >
          <template #icon><UiIcon name="refresh" /></template>
        </UiButton>
      </template>
    </UiPageHeader>

    <div class="stack">
      <UiBanner v-if="errorMessage" tone="error">{{ errorMessage }}</UiBanner>

      <!--
        One card filling the region, rows scrolling inside it under a sticky header, so the
        page itself never grows past the viewport. It carries no head: the page header
        already names this collection and says how much of it is here ("Last 50 jobs"), and a
        bar above the table would be that sentence again.

        A failed refresh keeps the rows it already has — the banner above says what went
        wrong, and blanking the page on top of that helps nobody.
      -->
      <UiCard v-if="data || !errorMessage" class="list" fill flush>
        <UiSkeleton v-if="!data" :rows="5" />

        <UiEmptyState
          v-else-if="!data.jobs.length"
          :title="t('jobs.empty')"
          :body="t('jobs.emptyBody')"
        />

        <UiDataTable
          v-else
          :columns="columns"
          :rows="data.jobs"
          :row-key="(job) => job.job_id"
          :caption="t('jobs.headTitle')"
        >
          <template #cell-file="{ row }">
            <span class="filename" :title="row.filename">{{ row.filename }}</span>
          </template>
          <template #cell-status="{ row }">
            <UiStatusDot :tone="STATUS_TONE[row.status]" :label="t(`jobs.status.${row.status}`)" />
          </template>
          <template #cell-model="{ row }">
            <span class="mono">{{ row.model }}</span>
          </template>
          <template #cell-pages="{ row }">
            {{ row.page_count ? `${row.pages_done}/${row.page_count}` : row.pages_done }}
          </template>
          <template #cell-created="{ row }">{{ formatDateTime(row.created_at, locale) }}</template>
          <template #cell-result="{ row }">
            <UiButton
              variant="ghost"
              size="sm"
              icon-only
              :label="t('jobs.showResultFor', { name: row.filename })"
              @click="showResult(row)"
            >
              <template #icon><UiIcon name="expand" /></template>
            </UiButton>
          </template>
        </UiDataTable>
      </UiCard>
    </div>

    <UiModal v-if="openJob" :title="openJob.filename" size="md" @close="openJob = null">
      <div class="detail">
        <UiBanner v-if="openJob.error" tone="error">{{ openJob.error }}</UiBanner>

        <UiSkeleton v-if="loadingResultId === openJob.job_id" :rows="4" />
        <UiBanner v-else-if="resultErrors.get(openJob.job_id)" tone="error">
          {{ resultErrors.get(openJob.job_id) }}
        </UiBanner>
        <pre v-else-if="results.get(openJob.job_id)" class="result mono">{{
          JSON.stringify(results.get(openJob.job_id), null, 2)
        }}</pre>
      </div>
    </UiModal>
  </div>
</template>

<style scoped>
/* Fills the content region exactly, which is what gives the card a bounded box to scroll its
   rows inside of instead of growing the page. The shell's flex column supplies the height,
   so there is no viewport arithmetic to keep in sync here. No gap: UiPageHeader carries its
   own bottom margin. */
.page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  flex: 1;
  min-height: 0;
}

.list {
  flex: 1;
  min-height: 0;
}

.period {
  color: var(--muted);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.filename {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail {
  display: grid;
  gap: var(--space-3);
}

/* The result is a document to read. It scrolls sideways on its own — a JSON line must not
   be re-wrapped into something that no longer matches the file — but its *vertical* scroll
   is the dialog body's, so the dialog never shows two stacked scrollbars for one document. */
.result {
  margin: 0;
  overflow-x: auto;
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  line-height: 1.6;
  white-space: pre;
}
</style>
