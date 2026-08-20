"""Markdown assembly and the `sightread://` figure placeholder contract (docs/api.md).

Two shapes arrive here:

- vision pages, where the model returns markdown already carrying placeholders, and
- text-layer pages, where the words come from Poppler and the figure boxes come from a
  separate detection call, so the placeholders are appended in reading order.

Both end up with document-wide figure ids, page numbers we trust (ours, not the model's)
and bounding boxes validated against the 0-1000 coordinate space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .poppler import PageText
from .route import group_lines

BBOX_MAX = 1000

# A placeholder as emitted by the model or by us: ![anything](sightread://p3/10,20,30,40).
PLACEHOLDER_RE = re.compile(
    r"!\[[^\]\n]*\]\(\s*sightread://p(?P<page>\d+)/"
    r"(?P<ymin>-?\d+)\s*,\s*(?P<xmin>-?\d+)\s*,\s*(?P<ymax>-?\d+)\s*,\s*(?P<xmax>-?\d+)\s*\)"
)

# Paragraph break when the top-to-top step between two text lines exceeds this multiple of
# the line height (ordinary leading lands near 1.3).
PARAGRAPH_GAP_RATIO = 1.8


@dataclass(frozen=True)
class FigureBox:
    """A detected figure before it gets a document-wide id."""

    bbox: tuple[int, int, int, int]
    caption: str = ""


@dataclass
class PageMarkdown:
    page: int
    markdown: str
    # Figures detected separately from the text (the text-layer path); appended in order.
    figures: list[FigureBox] = field(default_factory=list)


@dataclass
class AssembledDocument:
    markdown: str
    figures: list[dict]
    # Placeholders the model emitted with an unusable box; counted, never guessed at.
    dropped_figures: int


def clean_bbox(values: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    """Clamp a `[ymin, xmin, ymax, xmax]` box to 0-1000, or reject it as unusable."""
    y_min, x_min, y_max, x_max = (max(0, min(BBOX_MAX, int(value))) for value in values)
    if y_max <= y_min or x_max <= x_min:
        return None
    return y_min, x_min, y_max, x_max


def placeholder(figure_id: str, page: int, bbox: tuple[int, int, int, int]) -> str:
    y_min, x_min, y_max, x_max = bbox
    return f"![{figure_id}](sightread://p{page}/{y_min},{x_min},{y_max},{x_max})"


def text_layer_markdown(page: PageText) -> str:
    """Turn Poppler word boxes into paragraphs; verbatim text, no interpretation."""
    blocks: list[str] = []
    previous_top: float | None = None
    for line in group_lines(page.words):
        height = max(line[0].y_max - line[0].y_min, 1.0)
        if previous_top is not None and line[0].y_min - previous_top > height * PARAGRAPH_GAP_RATIO:
            blocks.append("")
        blocks.append(" ".join(word.text for word in line))
        previous_top = line[0].y_min
    return "\n".join(blocks).strip()


def _caption_after(text: str, end: int) -> str:
    """The caption a placeholder claims: the first non-empty line after its own line."""
    _, _, remainder = text[end:].partition("\n")
    for line in remainder.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return "" if PLACEHOLDER_RE.search(stripped) else stripped
    return ""


def assemble(pages: list[PageMarkdown]) -> AssembledDocument:
    """Join pages into one document with document-wide figure ids."""
    figures: list[dict] = []
    dropped = 0
    bodies: list[str] = []

    for page in pages:
        parts: list[str] = []
        cursor = 0
        for match in PLACEHOLDER_RE.finditer(page.markdown):
            parts.append(page.markdown[cursor : match.start()])
            cursor = match.end()
            bbox = clean_bbox(
                (
                    int(match.group("ymin")),
                    int(match.group("xmin")),
                    int(match.group("ymax")),
                    int(match.group("xmax")),
                )
            )
            if bbox is None:
                dropped += 1
                continue
            figure_id = f"fig{len(figures) + 1}"
            # The page number is ours: a model that mislabels the page must not corrupt
            # the coordinate contract.
            figures.append(
                {
                    "id": figure_id,
                    "page": page.page,
                    "bbox": list(bbox),
                    "caption": _caption_after(page.markdown, match.end()),
                }
            )
            parts.append(placeholder(figure_id, page.page, bbox))
        parts.append(page.markdown[cursor:])

        body = "".join(parts).strip()
        for detected in page.figures:
            bbox = clean_bbox(detected.bbox)
            if bbox is None:
                dropped += 1
                continue
            figure_id = f"fig{len(figures) + 1}"
            figures.append(
                {
                    "id": figure_id,
                    "page": page.page,
                    "bbox": list(bbox),
                    "caption": detected.caption,
                }
            )
            body = (
                f"{body}\n\n{placeholder(figure_id, page.page, bbox)}\n{detected.caption}".strip()
            )
        if body:
            bodies.append(body)

    return AssembledDocument(markdown="\n\n".join(bodies), figures=figures, dropped_figures=dropped)
