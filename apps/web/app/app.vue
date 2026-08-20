<script setup lang="ts">
const localeHead = useLocaleHead({ seo: true })

useHead(() => ({
  htmlAttrs: { lang: localeHead.value.htmlAttrs?.lang },
  link: [...(localeHead.value.link || [])],
  meta: [...(localeHead.value.meta || [])],
}))
</script>

<template>
  <!-- One shell: `layouts/default` is the signed-in fixed frame. The sign-in page is
       full-bleed and opts out with `layout: false` (docs/web.md § Design system). -->
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>
