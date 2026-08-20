/**
 * Loading state for one authenticated read, shared by every control-plane page: fetch on
 * mount, keep the last good data, and route failures through `useApiError`.
 */
export function useAuthedData<T>(load: () => Promise<T>) {
  const { resolve } = useApiError()
  const data = shallowRef<T | null>(null)
  const pending = ref(false)
  const errorMessage = ref<string | null>(null)

  async function refresh(): Promise<void> {
    pending.value = true
    errorMessage.value = null
    try {
      data.value = await load()
    } catch (error) {
      errorMessage.value = await resolve(error)
    } finally {
      pending.value = false
    }
  }

  onMounted(refresh)

  return { data, pending, errorMessage, refresh }
}
