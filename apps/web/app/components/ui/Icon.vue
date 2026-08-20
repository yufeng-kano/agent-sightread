<script setup lang="ts">
/**
 * The app's glyphs, inlined.
 *
 * One 16px stroked set on a 16px grid (1.4 stroke, round caps and joins) so a Refresh in a
 * page header, a Copy in a table row, and a destination in the sidebar read as one family.
 * Inline rather than an icon package: a dozen glyphs do not justify a dependency, and a
 * remote sprite would be a render-blocking request for chrome that must paint immediately.
 *
 * Always decorative. An icon-only control carries its name in `UiButton`'s `label` (which
 * becomes both the accessible name and the tooltip) and a nav item in the word beside it,
 * never in the glyph — so this is unconditionally `aria-hidden`.
 */
defineProps<{
  name:
    | 'refresh'
    | 'copy'
    | 'check'
    | 'plus'
    | 'trash'
    | 'expand'
    | 'close'
    | 'sign-out'
    | 'menu'
    | 'dashboard'
    | 'keys'
    | 'jobs'
    | 'connect'
    | 'settings'
}>()
</script>

<template>
  <svg
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    stroke-width="1.4"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <!-- Refresh: an open circular arrow. The gap and the arrowhead are what distinguish it
         from the spinner it is replaced by while a refresh is in flight. -->
    <template v-if="name === 'refresh'">
      <path d="M13.5 8a5.5 5.5 0 11-1.61-3.89" />
      <path d="M13.5 2.5V5H11" />
    </template>

    <!-- Copy: two offset sheets. -->
    <template v-else-if="name === 'copy'">
      <rect x="5.75" y="5.75" width="8.5" height="8.5" rx="1.75" />
      <path d="M10.25 3.75A1.75 1.75 0 008.5 2H3.75A1.75 1.75 0 002 3.75V8.5c0 .966.784 1.75 1.75 1.75" />
    </template>

    <!-- Plus: create. -->
    <template v-else-if="name === 'plus'">
      <path d="M8 3v10M3 8h10" />
    </template>

    <!-- Trash: delete a stored value. Paired with a visible word wherever it destroys
         something the user would have to re-create. -->
    <template v-else-if="name === 'trash'">
      <path d="M2.75 4.5h10.5" />
      <path d="M6.5 7.25v4M9.5 7.25v4" />
      <path d="M4 4.5l.6 8.2a1 1 0 001 .8h4.8a1 1 0 001-.8l.6-8.2" />
      <path d="M6 4.5v-1a1 1 0 011-1h2a1 1 0 011 1v1" />
    </template>

    <!-- Expand: two outward corner arrows — opens a row's detail view. -->
    <template v-else-if="name === 'expand'">
      <path d="M9.5 2.5H13.5V6.5" />
      <path d="M13.5 2.5L9 7" />
      <path d="M6.5 13.5H2.5V9.5" />
      <path d="M2.5 13.5L7 9" />
    </template>

    <!-- Close: dismiss one thing. -->
    <template v-else-if="name === 'close'">
      <path d="M4 4l8 8M12 4l-8 8" />
    </template>

    <!-- Sign out: leave through the door. -->
    <template v-else-if="name === 'sign-out'">
      <path d="M6.25 13.5H3.75A1.25 1.25 0 012.5 12.25v-8.5A1.25 1.25 0 013.75 2.5h2.5" />
      <path d="M10.5 10.75L13.25 8l-2.75-2.75" />
      <path d="M13.25 8H6.25" />
    </template>

    <!-- Menu: opens the sidebar drawer below the shell breakpoint. -->
    <template v-else-if="name === 'menu'">
      <path d="M2 4h12M2 8h12M2 12h12" />
    </template>

    <!-- Dashboard: bars on a baseline — the page is cost and tokens over time. -->
    <template v-else-if="name === 'dashboard'">
      <path d="M2 13.5h12" />
      <path d="M4.25 13.5V8M8 13.5V3.5M11.75 13.5V6.25" />
    </template>

    <!-- Keys: a key, bit end first. -->
    <template v-else-if="name === 'keys'">
      <circle cx="5.25" cy="10.75" r="2.75" />
      <path d="M7.25 8.75L13 3M11 5l1.5 1.5M9.5 6.5L11 8" />
    </template>

    <!-- Jobs: a run of entries, each a marker beside its line. -->
    <template v-else-if="name === 'jobs'">
      <path d="M2.75 4h1.5M2.75 8h1.5M2.75 12h1.5" />
      <path d="M6.75 4h6.5M6.75 8h6.5M6.75 12h4" />
    </template>

    <!-- Connect: a plug, prongs up — the connector page. -->
    <template v-else-if="name === 'connect'">
      <path d="M5.5 2v3M10.5 2v3" />
      <path d="M3.75 5h8.5v2a4.25 4.25 0 01-8.5 0V5z" />
      <path d="M8 11.25V14" />
    </template>

    <!-- Settings: sliders rather than a gear — a gear's teeth turn to mush at 16px. -->
    <template v-else-if="name === 'settings'">
      <path d="M2.5 5.5h3.5M10 5.5h3.5" />
      <circle cx="8" cy="5.5" r="1.75" />
      <path d="M2.5 10.5h1.25M7.5 10.5h6" />
      <circle cx="5.5" cy="10.5" r="1.75" />
    </template>

    <!-- Check: the confirmation a copy swaps to. -->
    <template v-else>
      <path d="M3 8.5l3.25 3.25L13 5" />
    </template>
  </svg>
</template>
