<script setup lang="ts">
import { devLogin, isDevLoginAvailable } from '~/lib/api'

definePageMeta({ layout: 'public' })

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

const steps = computed(() => [
  t('landing.step1'),
  t('landing.step2'),
  t('landing.step3'),
  t('landing.step4'),
])

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
  <main class="landing">
    <section class="hero">
      <h1>{{ t('landing.heroTitle') }}</h1>
      <p class="lede">{{ t('landing.heroBody') }}</p>

      <!-- The page's one call to action. The shell's bar carries none, so this is the only
           place it is asked. -->
      <div class="cta">
        <UiButton v-if="auth.signedIn.value" variant="primary" :to="localePath('/dashboard')">
          {{ t('landing.openDashboard') }}
        </UiButton>
        <UiButton v-else variant="primary" href="/api/auth/login">
          {{ t('nav.signIn') }}
        </UiButton>

        <template v-if="devLoginAvailable">
          <UiButton :loading="signingIn" @click="signInAsDeveloper">
            {{ t('landing.devSignIn') }}
          </UiButton>
          <span class="dev-note">{{ t('landing.devSignInNote') }}</span>
        </template>
      </div>

      <UiBanner v-if="devLoginError" tone="error">{{ devLoginError }}</UiBanner>
    </section>

    <section>
      <h2 class="section-head">{{ t('landing.howTitle') }}</h2>
      <ol class="steps">
        <li v-for="step in steps" :key="step">{{ step }}</li>
      </ol>
    </section>

    <section>
      <div class="section-head">
        <h2>{{ t('landing.curlTitle') }}</h2>
        <UiCopyButton :text="curlExample" />
      </div>
      <pre class="code mono">{{ curlExample }}</pre>
      <p class="note">{{ t('landing.curlNote') }}</p>
    </section>

    <section>
      <div class="section-head">
        <h2>{{ t('landing.mcpTitle') }}</h2>
        <UiCopyButton :text="mcpUrl" />
      </div>
      <pre class="code mono">{{ mcpUrl }}</pre>
      <p class="note">{{ t('landing.mcpBody') }}</p>
    </section>

    <section>
      <h2 class="section-head">{{ t('landing.resultTitle') }}</h2>
      <p class="body">{{ t('landing.resultBody') }}</p>
    </section>
  </main>
</template>

<style scoped>
/*
 * A reading measure, not the app's table width: this page is prose. It shares the app's
 * tokens and nothing else — no cards, no page header, no frame.
 */
.landing {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  max-width: 56rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-5) calc(var(--space-12) * 2);
}

section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.hero {
  gap: var(--space-5);
}

.hero h1 {
  max-width: 24ch;
  font-size: var(--text-2xl);
  letter-spacing: var(--tracking-tighter);
  line-height: 1.2;
}

.lede {
  max-width: 64ch;
  font-size: var(--text-md);
  line-height: 1.6;
  color: var(--text-secondary);
}

.cta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
}

/* Set to be read rather than shrunk and greyed: it is the one thing that explains why a
   second sign-in button is on the page at all. */
.dev-note {
  color: var(--muted);
  font-size: var(--text-sm);
}

/* A rule under the heading divides the sections — the plainest thing that carries the
   division, and the reason none of them needs a box. */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: var(--control-height);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.section-head h2 {
  font-size: var(--text-md);
}

.steps {
  display: grid;
  gap: var(--space-2);
  max-width: 64ch;
  margin: 0;
  padding-inline-start: 1.4em;
  color: var(--text-secondary);
}

.body {
  max-width: 64ch;
  color: var(--text-secondary);
  line-height: 1.6;
}

.note {
  max-width: 64ch;
  color: var(--muted);
  font-size: var(--text-sm);
  line-height: 1.6;
}

.code {
  margin: 0;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  line-height: 1.7;
  /* A command line must not be re-wrapped into something that no longer runs, so it scrolls
     in its own box rather than making the page scroll sideways. */
  overflow-x: auto;
  white-space: pre;
}

@media (max-width: 640px) {
  .landing {
    gap: var(--space-8);
    padding: var(--space-8) var(--space-4) var(--space-12);
  }

  .hero h1 {
    font-size: var(--text-xl);
  }
}
</style>
