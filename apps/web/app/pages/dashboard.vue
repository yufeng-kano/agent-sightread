<script setup lang="ts">
import { getUsage } from '~/lib/api'
import { formatCost, formatCount, formatDay } from '~/lib/format'
import { summarizeUsage } from '~/lib/usage'

definePageMeta({ middleware: 'authed' })

const USAGE_DAYS = 30

const { t, locale } = useI18n()
useHead(() => ({ title: t('dashboard.headTitle') }))

const { data, pending, errorMessage, refresh } = useAuthedData(() => getUsage(USAGE_DAYS))
const summary = computed(() => (data.value ? summarizeUsage(data.value) : null))
</script>

<template>
  <main class="page">
    <section>
      <div class="section-head">
        <h2>{{ t('dashboard.period', { days: USAGE_DAYS }) }}</h2>
        <RefreshButton :busy="pending" @click="refresh" />
      </div>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <p v-else-if="!summary" class="muted">{{ t('common.loading') }}</p>
      <p v-else-if="summary.isEmpty" class="empty">{{ t('dashboard.empty') }}</p>
      <div v-else class="totals">
        <div>
          <div class="muted">{{ t('dashboard.totalCost') }}</div>
          <div class="total-value">{{ formatCost(summary.totalCost, locale) }}</div>
        </div>
        <div>
          <div class="muted">{{ t('dashboard.totalPromptTokens') }}</div>
          <div class="total-value">{{ formatCount(summary.totalPromptTokens, locale) }}</div>
        </div>
        <div>
          <div class="muted">{{ t('dashboard.totalCompletionTokens') }}</div>
          <div class="total-value">{{ formatCount(summary.totalCompletionTokens, locale) }}</div>
        </div>
      </div>
    </section>

    <section v-if="summary && summary.days.length">
      <h2 class="section-head">{{ t('dashboard.perDay') }}</h2>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ t('dashboard.columnDate') }}</th>
              <th class="bar-cell" />
              <th class="numeric">{{ t('dashboard.columnCost') }}</th>
              <th class="numeric">{{ t('dashboard.columnPrompt') }}</th>
              <th class="numeric">{{ t('dashboard.columnCompletion') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in summary.days" :key="row.label">
              <td>{{ formatDay(row.label, locale) }}</td>
              <td class="bar-cell">
                <span class="bar" :style="{ width: `${row.costShare * 100}%` }" />
              </td>
              <td class="numeric">{{ formatCost(row.cost, locale) }}</td>
              <td class="numeric">{{ formatCount(row.promptTokens, locale) }}</td>
              <td class="numeric">{{ formatCount(row.completionTokens, locale) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="summary && summary.models.length">
      <h2 class="section-head">{{ t('dashboard.perModel') }}</h2>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ t('dashboard.columnModel') }}</th>
              <th class="bar-cell" />
              <th class="numeric">{{ t('dashboard.columnCost') }}</th>
              <th class="numeric">{{ t('dashboard.columnPrompt') }}</th>
              <th class="numeric">{{ t('dashboard.columnCompletion') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in summary.models" :key="row.label">
              <td class="mono">{{ row.label }}</td>
              <td class="bar-cell">
                <span class="bar" :style="{ width: `${row.costShare * 100}%` }" />
              </td>
              <td class="numeric">{{ formatCost(row.cost, locale) }}</td>
              <td class="numeric">{{ formatCount(row.promptTokens, locale) }}</td>
              <td class="numeric">{{ formatCount(row.completionTokens, locale) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
