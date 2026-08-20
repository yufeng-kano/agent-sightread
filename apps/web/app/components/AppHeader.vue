<script setup lang="ts">
const { t, locale, locales } = useI18n()
const localePath = useLocalePath()
const switchLocalePath = useSwitchLocalePath()
const auth = useAuth()

async function signOut() {
  await auth.signOut()
  await navigateTo(localePath('/'))
}
</script>

<template>
  <header class="site-header">
    <div class="page">
      <NuxtLink class="brand" :to="localePath('/')">{{ t('app.name') }}</NuxtLink>

      <nav v-if="auth.signedIn.value">
        <NuxtLink :to="localePath('/dashboard')">{{ t('nav.dashboard') }}</NuxtLink>
        <NuxtLink :to="localePath('/keys')">{{ t('nav.keys') }}</NuxtLink>
        <NuxtLink :to="localePath('/jobs')">{{ t('nav.jobs') }}</NuxtLink>
        <NuxtLink :to="localePath('/settings')">{{ t('nav.settings') }}</NuxtLink>
      </nav>

      <ul class="locales" :aria-label="t('nav.language')">
        <li v-for="option in locales" :key="option.code">
          <span v-if="option.code === locale" aria-current="true">{{ option.name }}</span>
          <NuxtLink v-else :to="switchLocalePath(option.code)">{{ option.name }}</NuxtLink>
        </li>
      </ul>

      <template v-if="auth.signedIn.value">
        <span class="muted account">{{ auth.me.value?.user.email }}</span>
        <button
          class="icon"
          type="button"
          :title="t('nav.signOut')"
          :aria-label="t('nav.signOut')"
          @click="signOut"
        >
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3" />
            <path d="M16 16l4-4-4-4" />
            <path d="M20 12H10" />
          </svg>
        </button>
      </template>
      <a v-else class="signin" href="/api/auth/login">{{ t('nav.signIn') }}</a>
    </div>
  </header>
</template>

<style scoped>
.locales {
  display: flex;
  gap: 0.6rem;
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 0.9rem;
}

.locales a {
  color: var(--muted);
  text-decoration: none;
}

.locales a:hover {
  color: var(--fg);
}

.account {
  font-size: 0.9rem;
}

.signin {
  text-decoration: none;
  font-size: 0.95rem;
}
</style>
