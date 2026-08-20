/** Control-plane pages are client-rendered; unauthenticated visitors go to the sign-in page. */
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) {
    return
  }
  const auth = useAuth()
  await auth.ensureLoaded()
  if (!auth.signedIn.value) {
    return navigateTo(useLocalePath()('/'))
  }
})
