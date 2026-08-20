<script setup lang="ts">
const localeHead = useLocaleHead({ seo: true })

useHead(() => ({
  htmlAttrs: { lang: localeHead.value.htmlAttrs?.lang },
  link: [...(localeHead.value.link || [])],
  meta: [...(localeHead.value.meta || [])],
}))
</script>

<template>
  <AppHeader />
  <NuxtPage />
</template>
