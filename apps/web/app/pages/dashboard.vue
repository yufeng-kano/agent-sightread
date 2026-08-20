<script setup lang="ts">
import { getUsage } from '~/lib/api'
import { formatCost, formatCount, formatDay } from '~/lib/format'
import type { TableColumn } from '~/lib/table'
import { summarizeUsage, type UsageRow } from '~/lib/usage'

definePageMeta({ middleware: 'authed' })

const USAGE_DAYS = 30

const { t, locale } = useI18n()
useHead(() => ({ title: t('dashboard.headTitle') }))

const { data, pending, errorMessage, refresh } = useAuthedData(() => getUsage(USAGE_DAYS))
const summary = computed(() => (data.value ? summarizeUsage(data.value) : null))

/**
 * The two tables differ only in what their first column identifies, so they share one column
 * set built here. The bar column carries no visible header — it ranks the cost column beside
 * it — but keeps an accessible name, since a blank `<th>` is an unnamed column to a screen
 * reader reading the table's structure.
 */
function usageColumns(firstHeader: string): TableColumn<UsageRow>[] {
  return [
    { key: 'label', header: firstHeader },
    { key: 'share', header: '', srHeader: t('dashboard.columnShare'), width: '20%', hideOnMobile: true },
    { key: 'cost', header: t('dashboard.columnCost'), numeric: true },
    { key: 'prompt', header: t('dashboard.columnPrompt'), numeric: true },
    { key: 'completion', header: t('dashboard.columnCompletion'), numeric: true },
  ]
}

const dayColumns = computed(() => usageColumns(t('dashboard.columnDate')))
const modelColumns = computed(() => usageColumns(t('dashboard.columnModel')))
</script>

<template>
  <div class="page">
    <UiPageHeader :title="t('dashboard.headTitle')">
      <template #meta>
        <span class="period">{{ t('dashboard.period', { days: USAGE_DAYS }) }}</span>
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
      <!-- A failed refresh keeps the figures it already has: the banner says what went
           wrong, and blanking the page on top of that helps nobody. -->
      <UiBanner v-if="errorMessage" tone="error">{{ errorMessage }}</UiBanner>

      <UiCard v-if="!summary && !errorMessage" flush>
        <UiSkeleton :rows="4" />
      </UiCard>

      <UiCard v-else-if="summary?.isEmpty" flush>
        <UiEmptyState :title="t('dashboard.empty')" :body="t('dashboard.emptyBody')" />
      </UiCard>

      <template v-else-if="summary">
        <!-- Three figures on the page's own surface, divided by a rule. Boxing each of them
             would make the page a tray of tiles and say nothing the label does not. -->
        <dl class="totals">
          <div class="total">
            <dt>{{ t('dashboard.totalCost') }}</dt>
            <dd class="tabular">{{ formatCost(summary.totalCost, locale) }}</dd>
          </div>
          <div class="total">
            <dt>{{ t('dashboard.totalPromptTokens') }}</dt>
            <dd class="tabular">{{ formatCount(summary.totalPromptTokens, locale) }}</dd>
          </div>
          <div class="total">
            <dt>{{ t('dashboard.totalCompletionTokens') }}</dt>
            <dd class="tabular">{{ formatCount(summary.totalCompletionTokens, locale) }}</dd>
          </div>
        </dl>

        <!-- Two independent collections, so two cards, each bounding and scrolling its own
             rows: one scrollbar dragging both would make the reader scroll past the days to
             reach the models. -->
        <UiCard
          v-if="summary.days.length"
          :title="t('dashboard.perDay')"
          flush
          body-max="var(--group-max)"
        >
          <UiDataTable
            :columns="dayColumns"
            :rows="summary.days"
            :row-key="(row) => row.label"
            :caption="t('dashboard.perDay')"
          >
            <template #cell-label="{ row }">{{ formatDay(row.label, locale) }}</template>
            <template #cell-share="{ row }">
              <UiUsageBar :share="row.costShare" :label="formatDay(row.label, locale)" />
            </template>
            <template #cell-cost="{ row }">{{ formatCost(row.cost, locale) }}</template>
            <template #cell-prompt="{ row }">{{ formatCount(row.promptTokens, locale) }}</template>
            <template #cell-completion="{ row }">
              {{ formatCount(row.completionTokens, locale) }}
            </template>
          </UiDataTable>
        </UiCard>

        <UiCard
          v-if="summary.models.length"
          :title="t('dashboard.perModel')"
          flush
          body-max="var(--group-max)"
        >
          <UiDataTable
            :columns="modelColumns"
            :rows="summary.models"
            :row-key="(row) => row.label"
            :caption="t('dashboard.perModel')"
          >
            <template #cell-label="{ row }">
              <span class="mono">{{ row.label }}</span>
            </template>
            <template #cell-share="{ row }">
              <UiUsageBar :share="row.costShare" :label="row.label" />
            </template>
            <template #cell-cost="{ row }">{{ formatCost(row.cost, locale) }}</template>
            <template #cell-prompt="{ row }">{{ formatCount(row.promptTokens, locale) }}</template>
            <template #cell-completion="{ row }">
              {{ formatCount(row.completionTokens, locale) }}
            </template>
          </UiDataTable>
        </UiCard>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* No gap on the page itself: UiPageHeader carries its own bottom margin, and a second
   spacer under it would double the distance on every page. */
.page {
  display: flex;
  flex-direction: column;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* The range these figures cover — a fact about the data, not a line explaining the page. */
.period {
  color: var(--muted);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.totals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: var(--space-5);
  margin: 0;
  padding-bottom: var(--space-5);
  border-bottom: 1px solid var(--border);
}

.total dt {
  color: var(--muted);
  font-size: var(--text-xs);
}

.total dd {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-tight);
}
</style>
