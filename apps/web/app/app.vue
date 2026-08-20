<script setup lang="ts">
const localeHead = useLocaleHead({ seo: true })

useHead(() => ({
  htmlAttrs: { lang: localeHead.value.htmlAttrs?.lang },
  link: [...(localeHead.value.link || [])],
  meta: [...(localeHead.value.meta || [])],
}))
</script>

<template>
  <!-- Two shells: `layouts/default` is the signed-in fixed frame, `layouts/public` the
       landing's scrolling document (docs/web.md § Pages). -->
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>
