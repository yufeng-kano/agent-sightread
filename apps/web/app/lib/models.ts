import type { ModelEntry } from './api'

/** OpenRouter's `name` is optional; the id is always there and is what the API expects. */
export function modelLabel(model: ModelEntry): string {
  return model.name?.trim() || model.id
}

/**
 * Recommended models first — those a preset profile currently resolves to — then the rest
 * of the catalog alphabetically, so the tested choices are at the top of the select
 * (docs/web.md § Pages).
 */
export function sortModelsRecommendedFirst(models: ModelEntry[]): ModelEntry[] {
  return [...models].sort((left, right) => {
    if (left.recommended !== right.recommended) {
      return left.recommended ? -1 : 1
    }
    return modelLabel(left).localeCompare(modelLabel(right))
  })
}
