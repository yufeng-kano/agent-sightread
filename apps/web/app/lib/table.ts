/**
 * The column contract `UiDataTable` renders (see the component for what it does with each
 * field). It lives here rather than in the SFC because a Vue component that both exports a
 * type and uses `<script setup>` needs a second, plain `<script>` block for the export —
 * and importing a type out of an auto-imported component is a seam nothing else in this app
 * has.
 */
export interface TableColumn<Row> {
  key: string
  /** Visible column header. Blank for an action column, which needs `srHeader` instead. */
  header: string
  /** Centered under its header, with tabular numerals. */
  numeric?: boolean
  /** Right-aligns header and cells without the numeric treatment — for a control column. */
  align?: 'end'
  /** Plain-text value; also the mobile card's value when the page gives no slot. */
  value?: (row: Row) => string
  /** Dropped from the mobile cards — for a column that only adds noise there. */
  hideOnMobile?: boolean
  /**
   * Track width. An action column needs one: without it the column takes the table's
   * leftover width and its control ends up a long way from the row it acts on.
   */
  width?: string
  /**
   * Accessible name for a column whose `header` is intentionally blank. A blank `<th>` is an
   * unnamed column to a screen reader reading the table's structure, so the name is
   * rendered visually hidden rather than omitted.
   */
  srHeader?: string
}
