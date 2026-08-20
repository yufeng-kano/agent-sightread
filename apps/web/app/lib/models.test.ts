import { describe, expect, it } from 'vitest'
import type { ModelEntry } from './api'
import { modelLabel, sortModelsRecommendedFirst } from './models'

function model(id: string, name: string | null, recommended: boolean): ModelEntry {
  return { id, name, context_length: null, pricing: null, recommended }
}

describe('sortModelsRecommendedFirst', () => {
  it('puts recommended models first and sorts each group by label', () => {
    const catalog = [
      model('vendor/zeta', 'Zeta', false),
      model('vendor/alpha', 'Alpha', false),
      model('vendor/omega', 'Omega', true),
      model('vendor/beta', 'Beta', true),
    ]

    expect(sortModelsRecommendedFirst(catalog).map((entry) => entry.id)).toEqual([
      'vendor/beta',
      'vendor/omega',
      'vendor/alpha',
      'vendor/zeta',
    ])
  })

  it('sorts by id when the catalog has no display name', () => {
    const catalog = [model('vendor/b', null, false), model('vendor/a', null, false)]

    expect(sortModelsRecommendedFirst(catalog).map((entry) => entry.id)).toEqual([
      'vendor/a',
      'vendor/b',
    ])
  })

  it('leaves the input array untouched', () => {
    const catalog = [model('vendor/a', 'A', false), model('vendor/b', 'B', true)]

    sortModelsRecommendedFirst(catalog)

    expect(catalog.map((entry) => entry.id)).toEqual(['vendor/a', 'vendor/b'])
  })
})

describe('modelLabel', () => {
  it('falls back to the id when the name is missing or blank', () => {
    expect(modelLabel(model('vendor/a', '  ', false))).toBe('vendor/a')
    expect(modelLabel(model('vendor/a', 'Alpha', false))).toBe('Alpha')
  })
})
