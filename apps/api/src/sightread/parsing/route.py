"""Per-page routing: text layer or vision (docs/parsing.md § Per-page routing).

A page takes the free `text_layer` path only when its text layer is real (enough words),
simple (a single column) and plain (no table grid, little mathematics). Everything else —
scans, two-column papers, table- or formula-heavy pages — goes to the vision model.

The thresholds are deliberately explicit and passed as one object so they can be tuned
without touching the logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .poppler import PageText, Word

TEXT_LAYER = "text_layer"
VISION = "vision"


@dataclass(frozen=True)
class RoutingThresholds:
    # Fewer real words than this and the page is a scan, a cover or a full-page figure.
    min_words: int = 40
    # Where a column gutter may sit, as a fraction of page width, and how wide it must be.
    gutter_band: tuple[float, float] = (0.35, 0.65)
    min_gutter_width: float = 0.05
    # Each side of a gutter must hold at least this share of the page's words.
    min_column_share: float = 0.2
    # A horizontal gap at least this wide (fraction of page width) separates table cells.
    cell_gap: float = 0.04
    # A line with this many cells looks tabular; this share of such lines means a table.
    table_min_cells: int = 3
    table_line_share: float = 0.3
    # Share of words carrying mathematical notation that forces the vision path.
    math_word_share: float = 0.05
    # Vertical tolerance for putting two words on the same line, as a share of line height.
    line_overlap: float = 0.5


DEFAULT_THRESHOLDS = RoutingThresholds()

MATH_CHARACTERS = frozenset("∑∏∫√∞≈≠≤≥±×÷∂∇∈∉⊂⊆∀∃∧∨⇒⇔→↦αβγδεθλμνξπρστφχψω")

# Sampling step for the gutter scan, as a fraction of page width.
_GUTTER_STEP = 0.005


@dataclass(frozen=True)
class RouteDecision:
    method: str
    # Short machine-readable reason; useful in tests and logs, never document content.
    reason: str


def group_lines(
    words: tuple[Word, ...], overlap: float = DEFAULT_THRESHOLDS.line_overlap
) -> list[list[Word]]:
    """Group words into visual lines, top to bottom, each line left to right."""
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda item: (item.y_min, item.x_min)):
        current = lines[-1] if lines else None
        if current is not None:
            reference = current[0]
            height = max(reference.y_max - reference.y_min, 1.0)
            if abs(word.y_min - reference.y_min) <= height * overlap:
                current.append(word)
                continue
        lines.append([word])
    for line in lines:
        line.sort(key=lambda item: item.x_min)
    return lines


def _has_column_gutter(page: PageText, thresholds: RoutingThresholds) -> bool:
    """True when a vertical band with no words splits the page into two populated columns."""
    if page.width_pt <= 0:
        return False
    spans = [(word.x_min / page.width_pt, word.x_max / page.width_pt) for word in page.words]
    band_start, band_end = thresholds.gutter_band

    gutter_run = 0.0
    position = band_start
    while position <= band_end:
        occupied = any(start <= position <= end for start, end in spans)
        gutter_run = 0.0 if occupied else gutter_run + _GUTTER_STEP
        if gutter_run >= thresholds.min_gutter_width:
            split = position - gutter_run / 2
            left = sum(1 for _, end in spans if end <= split)
            right = sum(1 for start, _ in spans if start >= split)
            share = thresholds.min_column_share * len(spans)
            if left >= share and right >= share:
                return True
            gutter_run = 0.0
        position += _GUTTER_STEP
    return False


def _looks_tabular(page: PageText, thresholds: RoutingThresholds) -> bool:
    """True when many lines break into three or more widely separated cells."""
    lines = group_lines(page.words, thresholds.line_overlap)
    if not lines or page.width_pt <= 0:
        return False
    gap = thresholds.cell_gap * page.width_pt

    tabular = 0
    for line in lines:
        cells = 1
        for previous, word in zip(line, line[1:], strict=False):
            if word.x_min - previous.x_max >= gap:
                cells += 1
        if cells >= thresholds.table_min_cells:
            tabular += 1
    return tabular / len(lines) >= thresholds.table_line_share


def route_page(page: PageText, thresholds: RoutingThresholds = DEFAULT_THRESHOLDS) -> RouteDecision:
    """Decide how one page is converted. Vision is the safe default for anything unusual."""
    if len(page.words) < thresholds.min_words:
        return RouteDecision(VISION, "thin_text_layer")
    if _has_column_gutter(page, thresholds):
        return RouteDecision(VISION, "multi_column")
    if _looks_tabular(page, thresholds):
        return RouteDecision(VISION, "tabular")

    math_words = sum(1 for word in page.words if MATH_CHARACTERS & set(word.text))
    if math_words / len(page.words) >= thresholds.math_word_share:
        return RouteDecision(VISION, "math_dense")
    return RouteDecision(TEXT_LAYER, "simple_text_layer")
