/** Locale-aware display formatting. The locale comes from the i18n catalog in use. */

export function formatDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

/**
 * `YYYY-MM-DD` day buckets from `GET /api/usage`. Rendered in UTC because that is the
 * timezone the backend grouped them in — a local-timezone render would shift labels.
 */
export function formatDay(day: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(
    new Date(`${day}T00:00:00Z`),
  )
}

/** Costs are OpenRouter's USD amounts and are often fractions of a cent. */
export function formatCost(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value)
}

export function formatCount(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value)
}
