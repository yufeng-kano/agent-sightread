<script setup lang="ts">
import { devLogin, isDevLoginAvailable } from '~/lib/api'

const { t } = useI18n()
const localePath = useLocalePath()
const auth = useAuth()
const { resolve } = useApiError()

useSeoMeta({
  title: () => t('landing.seoTitle'),
  description: () => t('landing.seoDescription'),
  ogTitle: () => t('landing.seoTitle'),
  ogDescription: () => t('landing.seoDescription'),
  ogType: 'website',
  twitterCard: 'summary',
})

// Prerendered HTML cannot know the deployment's host, so the documented pattern is what
// ships in the markup and the real host replaces it once the page is running.
const host = ref('<host>')
const devLoginAvailable = ref(false)
const devLoginError = ref<string | null>(null)
const signingIn = ref(false)

const curlExample = computed(
  () =>
    `curl -X POST https://${host.value}/v1/parse \\\n` +
    `  -H "Authorization: Bearer sr_your_api_key" \\\n` +
    `  -F file=@document.pdf`,
)
const mcpUrl = computed(() => `https://${host.value}/mcp`)

onMounted(async () => {
  host.value = window.location.host
  await auth.ensureLoaded()
  if (!auth.signedIn.value) {
    devLoginAvailable.value = await isDevLoginAvailable()
  }
})

async function signInAsDeveloper() {
  signingIn.value = true
  devLoginError.value = null
  try {
    await devLogin()
    await auth.refresh()
    await navigateTo(localePath('/dashboard'))
  } catch (error) {
    devLoginError.value = await resolve(error)
  } finally {
    signingIn.value = false
  }
}
</script>

<template>
  <main class="page">
    <section>
      <h1>{{ t('landing.heroTitle') }}</h1>
      <p>{{ t('landing.heroBody') }}</p>
      <div class="row actions">
        <NuxtLink v-if="auth.signedIn.value" class="cta" :to="localePath('/dashboard')">
          {{ t('landing.openDashboard') }}
        </NuxtLink>
        <a v-else class="cta" href="/api/auth/login">{{ t('nav.signIn') }}</a>
        <button v-if="devLoginAvailable" type="button" :disabled="signingIn" @click="signInAsDeveloper">
          {{ t('landing.devSignIn') }}
        </button>
        <span v-if="devLoginAvailable" class="muted dev-note">{{ t('landing.devSignInNote') }}</span>
      </div>
      <p v-if="devLoginError" class="error">{{ devLoginError }}</p>
    </section>

    <section>
      <h2 class="section-head">{{ t('landing.howTitle') }}</h2>
      <ol>
        <li>{{ t('landing.step1') }}</li>
        <li>{{ t('landing.step2') }}</li>
        <li>{{ t('landing.step3') }}</li>
        <li>{{ t('landing.step4') }}</li>
      </ol>
    </section>

    <section>
      <div class="section-head">
        <h2>{{ t('landing.curlTitle') }}</h2>
        <CopyButton :text="curlExample" />
      </div>
      <pre>{{ curlExample }}</pre>
      <p class="muted">{{ t('landing.curlNote') }}</p>
    </section>

    <section>
      <div class="section-head">
        <h2>{{ t('landing.mcpTitle') }}</h2>
        <CopyButton :text="mcpUrl" />
      </div>
      <pre>{{ mcpUrl }}</pre>
      <p class="muted">{{ t('landing.mcpBody') }}</p>
    </section>

    <section>
      <h2 class="section-head">{{ t('landing.resultTitle') }}</h2>
      <p>{{ t('landing.resultBody') }}</p>
    </section>
  </main>
</template>

<style scoped>
h1 {
  max-width: 34ch;
}

p {
  max-width: 68ch;
}

.actions {
  align-items: center;
  margin-top: 0.5rem;
}

.cta {
  display: inline-flex;
  align-items: center;
  height: var(--control-height);
  padding: 0 0.9rem;
  border-radius: var(--radius);
  background: var(--accent);
  color: var(--accent-fg);
  font-weight: 500;
  text-decoration: none;
}

.dev-note {
  font-size: 0.9rem;
}

ol {
  margin: 0;
  padding-inline-start: 1.2rem;
  max-width: 68ch;
}
</style>
