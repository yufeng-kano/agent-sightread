/**
 * Reads the session once at app init. Deliberately not awaited: the prerendered landing
 * hydrates against its signed-out markup and updates when `GET /api/me` answers, while
 * route middleware awaits the very same in-flight request.
 */
export default defineNuxtPlugin(() => {
  void useAuth().ensureLoaded()
})
