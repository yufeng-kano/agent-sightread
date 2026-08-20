import { describe, expect, it } from 'vitest'
import type { UsageResponse } from './api'
import { summarizeUsage } from './usage'

const usage: UsageResponse = {
  days: 30,
  per_day: [
    { date: '2026-08-18', prompt_tokens: 1000, completion_tokens: 200, cost: 0.02 },
    { date: '2026-08-19', prompt_tokens: 3000, completion_tokens: 400, cost: 0.08 },
    { date: '2026-08-20', prompt_tokens: 500, completion_tokens: 100, cost: 0.01 },
  ],
  per_model: [
    { model: 'vendor/cheap', prompt_tokens: 500, completion_tokens: 100, cost: 0.01 },
    { model: 'vendor/pricey', prompt_tokens: 4000, completion_tokens: 600, cost: 0.1 },
  ],
}

describe('summarizeUsage', () => {
  it('totals cost and tokens across the period', () => {
    const summary = summarizeUsage(usage)

    expect(summary.totalCost).toBeCloseTo(0.11)
    expect(summary.totalPromptTokens).toBe(4500)
    expect(summary.totalCompletionTokens).toBe(700)
    expect(summary.isEmpty).toBe(false)
  })

  it('lists the newest day first and the most expensive model first', () => {
    const summary = summarizeUsage(usage)

    expect(summary.days.map((row) => row.label)).toEqual(['2026-08-20', '2026-08-19', '2026-08-18'])
    expect(summary.models.map((row) => row.label)).toEqual(['vendor/pricey', 'vendor/cheap'])
  })

  it('scales bar shares against the largest cost in the same table', () => {
    const summary = summarizeUsage(usage)

    expect(summary.days[0]?.costShare).toBeCloseTo(0.125)
    expect(summary.days[1]?.costShare).toBe(1)
    expect(summary.models[0]?.costShare).toBe(1)
    expect(summary.models[1]?.costShare).toBeCloseTo(0.1)
  })

  it('reports zero shares rather than dividing by zero when nothing cost anything', () => {
    const summary = summarizeUsage({
      days: 7,
      per_day: [{ date: '2026-08-20', prompt_tokens: 10, completion_tokens: 0, cost: 0 }],
      per_model: [],
    })

    expect(summary.days[0]?.costShare).toBe(0)
    expect(summary.isEmpty).toBe(false)
  })

  it('is empty when the account has no usage at all', () => {
    const summary = summarizeUsage({ days: 30, per_day: [], per_model: [] })

    expect(summary.isEmpty).toBe(true)
    expect(summary.totalCost).toBe(0)
  })
})
