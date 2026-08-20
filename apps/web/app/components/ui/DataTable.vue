<!--
  The one place table markup lives.

  Three things a page's own `<table>` reliably gets wrong, all handled here:

  1. Sticky header — the column names stay while the body scrolls inside its card, which is
     what lets a long table live in a bounded region instead of growing the page.
  2. Alignment — numeric columns are centered with tabular numerals, header and cells
     together, declared once per column rather than re-specified per cell.
  3. Mobile — below 768px each row becomes a card of label/value pairs. Horizontal scroll on
     a phone hides exactly the columns that matter, so that is not the fallback.

  Cells render through a per-column slot named `cell-<key>`, falling back to the column's
  `value()`.
-->
<script setup lang="ts" generic="Row">
import type { TableColumn } from '~/lib/table'

defineProps<{
  columns: TableColumn<Row>[]
  rows: Row[]
  rowKey: (row: Row) => string
  /** Accessible caption. Visually hidden — the card head carries the visible title. */
  caption: string
}>()

defineSlots<Record<string, (props: { row: Row }) => unknown>>()
</script>

<template>
  <table class="table">
    <caption class="sr-only">{{ caption }}</caption>
    <thead>
      <tr>
        <th
          v-for="column in columns"
          :key="column.key"
          scope="col"
          :class="{ numeric: column.numeric, end: column.align === 'end', 'hide-mobile': column.hideOnMobile }"
          :style="column.width ? { width: column.width } : undefined"
        >
          <span v-if="!column.header && column.srHeader" class="sr-only">{{ column.srHeader }}</span>
          <template v-else>{{ column.header }}</template>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="rowKey(row)">
        <td
          v-for="column in columns"
          :key="column.key"
          :class="{
            numeric: column.numeric,
            end: column.align === 'end',
            'hide-mobile': column.hideOnMobile,
          }"
          :data-label="column.header || column.srHeader"
        >
          <slot :name="`cell-${column.key}`" :row="row">{{ column.value?.(row) ?? '' }}</slot>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: var(--text-sm);
}

.table th {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 36px;
  padding: 0 var(--space-4);
  text-align: left;
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--muted);
  white-space: nowrap;
  /* Opaque, not translucent: rows scrolling under a semi-transparent header smear into the
     labels. */
  background: var(--surface-2);
  /* An inset shadow, not `border-bottom`: a sticky cell's border scrolls away independently
     of the cell itself, leaving the header floating unruled. */
  box-shadow: inset 0 -1px 0 var(--border);
}

.table td {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
  color: var(--text-secondary);
}

.table tbody tr:last-child td {
  border-bottom: none;
}

.table tbody tr:hover td {
  background: var(--surface-2);
}

/*
 * Column alignment, applied to the header and its cells as one. Written as `.table th` /
 * `.table td` rather than a bare `.numeric`, because `.table th`'s `text-align: left` sits
 * at a higher specificity and would otherwise win — leaving every numeric header
 * left-aligned over centered figures.
 *
 * Numbers are centered on the column rather than pushed to its edge: a header like COST is
 * far narrower than the track it names, and pushing the figures to the far edge strands
 * them a column's width from the word. Tabular numerals keep them a scannable block.
 */
.table th.numeric,
.table td.numeric {
  text-align: center;
  font-variant-numeric: tabular-nums;
}

/* A control column: the header sits over the control rather than at the far edge. */
.table th.end,
.table td.end {
  text-align: right;
}

/* Mobile: one card per row, each cell labelled by its column header. */
@media (max-width: 768px) {
  .table,
  .table tbody,
  .table tr,
  .table td {
    display: block;
    width: auto;
  }

  .table thead {
    display: none;
  }

  .table tbody tr {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border);
  }

  .table tbody tr:last-child {
    border-bottom: none;
  }

  .table td {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-1) 0;
    border-bottom: none;
    text-align: left;
  }

  .table tbody tr:hover td {
    background: transparent;
  }

  .table td::before {
    content: attr(data-label);
    flex-shrink: 0;
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--faint);
  }

  /* The first cell is the row's identity — it reads as a heading, not a labelled field. */
  .table td:first-child {
    display: block;
    margin-bottom: var(--space-2);
    font-weight: var(--weight-medium);
    color: var(--text);
  }

  .table td:first-child::before {
    display: none;
  }

  .table td.numeric {
    text-align: right;
  }

  /* The row is a card here, so an action reads as its last field rather than something
     pinned to a column edge that no longer exists. */
  .table td.end {
    text-align: left;
  }

  .table td.hide-mobile {
    display: none;
  }
}
</style>
