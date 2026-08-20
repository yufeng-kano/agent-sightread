import { ApiRequestError } from '~/lib/api'

/**
 * One place that decides what a failed request means: an expired or missing session ends
 * the local session and sends the visitor back to the landing page (docs/web.md), an
 * offline failure gets our own wording, and anything else shows the backend's message from
 * the error envelope verbatim — it describes the actual problem better than we can.
 */
export function useApiError() {
  const { t } = useI18n()
  const auth = useAuth()
  const localePath = useLocalePath()

  async function resolve(error: unknown): Promise<string> {
    if (error instanceof ApiRequestError) {
      if (error.isUnauthorized) {
        auth.clearSession()
        await navigateTo(localePath('/'))
        return t('errors.signedOut')
      }
      if (error.isOffline) {
        return t('errors.network')
      }
      return error.message
    }
    return t('errors.unexpected')
  }

  return { resolve }
}
