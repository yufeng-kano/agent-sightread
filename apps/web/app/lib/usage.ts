import type { UsageResponse } from './api'

export interface UsageRow {
  /** A date (`YYYY-MM-DD`) for the per-day table, a model id for the per-model table. */
  label: string
  cost: number
  promptTokens: number
  completionTokens: number
  /** 0..1 — this row's cost against the largest cost in the same table, for the inline bar. */
  costShare: number
}

export interface UsageSummary {
  totalCost: number
  totalPromptTokens: number
  totalCompletionTokens: number
  days: UsageRow[]
  models: UsageRow[]
  isEmpty: boolean
}

/**
 * Display transform for `GET /api/usage`: totals, plus per-row bar shares. Days come back
 * from the backend oldest first and are flipped here so the newest is on top, matching the
 * job history.
 */
export function summarizeUsage(usage: UsageResponse): UsageSummary {
  const days = withCostShares(
    usage.per_day.map((entry) => ({
      label: entry.date,
      cost: entry.cost,
      promptTokens: entry.prompt_tokens,
      completionTokens: entry.completion_tokens,
      costShare: 0,
    })),
  ).reverse()

  const models = withCostShares(
    usage.per_model.map((entry) => ({
      label: entry.model,
      cost: entry.cost,
      promptTokens: entry.prompt_tokens,
      completionTokens: entry.completion_tokens,
      costShare: 0,
    })),
  ).sort((left, right) => right.cost - left.cost)

  return {
    totalCost: sum(usage.per_day.map((entry) => entry.cost)),
    totalPromptTokens: sum(usage.per_day.map((entry) => entry.prompt_tokens)),
    totalCompletionTokens: sum(usage.per_day.map((entry) => entry.completion_tokens)),
    days,
    models,
    isEmpty: usage.per_day.length === 0 && usage.per_model.length === 0,
  }
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

function withCostShares(rows: UsageRow[]): UsageRow[] {
  const largest = Math.max(0, ...rows.map((row) => row.cost))
  return rows.map((row) => ({ ...row, costShare: largest > 0 ? row.cost / largest : 0 }))
}
