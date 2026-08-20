"""Poppler wrappers and the routing heuristic, against real fixture documents.

Poppler is a real dependency of the test environment (docs/testing.md): these run actual
subprocesses, never mocks.
"""

from __future__ import annotations

import pytest
from PIL import Image

from sightread.parsing import poppler
from sightread.parsing.markdown import text_layer_markdown
from sightread.parsing.route import TEXT_LAYER, VISION, route_page


async def test_pdf_info_reports_pages_and_dimensions(documents, tmp_path) -> None:
    info = await poppler.pdf_info(documents["mixed_pdf"], cwd=tmp_path)

    assert info.page_count == 3
    assert len(info.page_sizes) == 3
    assert (round(info.page_size(1).width_pt), round(info.page_size(1).height_pt)) == (612, 792)
    # Out-of-range pages fall back rather than raising.
    assert info.page_size(99) == info.page_size(1)


async def test_pdf_info_rejects_a_corrupt_file(documents, tmp_path) -> None:
    with pytest.raises(poppler.PopplerError):
        await poppler.pdf_info(documents["corrupt_pdf"], cwd=tmp_path)


async def test_page_text_reads_the_text_layer(documents, tmp_path) -> None:
    page = await poppler.page_text(documents["text_pdf"], 1, cwd=tmp_path)

    assert page.page_no == 1
    assert round(page.width_pt) == 612
    assert len(page.words) > 100
    assert "quick" in {word.text for word in page.words}
    # Poppler reports a top-left origin, which is what the coordinate contract assumes.
    assert min(word.y_min for word in page.words) < page.height_pt / 2


async def test_scanned_page_has_no_text_layer(documents, tmp_path) -> None:
    page = await poppler.page_text(documents["scanned_pdf"], 1, cwd=tmp_path)
    assert page.words == ()


async def test_render_page_stays_within_the_long_edge_budget(documents, tmp_path) -> None:
    info = await poppler.pdf_info(documents["text_pdf"], cwd=tmp_path)
    rendered = await poppler.render_page(documents["text_pdf"], 1, info.page_size(1), cwd=tmp_path)

    assert rendered.parent == tmp_path
    with Image.open(rendered) as image:
        assert max(image.size) <= poppler.MAX_RENDER_LONG_EDGE_PX
        assert max(image.size) > poppler.MAX_RENDER_LONG_EDGE_PX * 0.9


async def test_a_child_that_overruns_its_timeout_is_killed(documents, tmp_path) -> None:
    info = await poppler.pdf_info(documents["text_pdf"], cwd=tmp_path)
    with pytest.raises(poppler.PopplerTimeout):
        await poppler.render_page(
            documents["text_pdf"], 1, info.page_size(1), cwd=tmp_path, timeout=0.0005
        )


def test_render_dpi_scales_with_page_size() -> None:
    letter_dpi = poppler.render_dpi(poppler.PageSize(612, 792))
    poster_dpi = poppler.render_dpi(poppler.PageSize(1728, 2592))

    assert poster_dpi < letter_dpi <= poppler.MAX_RENDER_DPI
    assert 792 / 72 * letter_dpi <= poppler.MAX_RENDER_LONG_EDGE_PX


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("text_pdf", TEXT_LAYER),
        ("scanned_pdf", VISION),
        ("two_column_pdf", VISION),
        ("table_pdf", VISION),
    ],
)
async def test_routing_heuristic(documents, tmp_path, document: str, expected: str) -> None:
    page = await poppler.page_text(documents[document], 1, cwd=tmp_path)
    assert route_page(page).method == expected


async def test_routing_reasons_are_specific(documents, tmp_path) -> None:
    scanned = await poppler.page_text(documents["scanned_pdf"], 1, cwd=tmp_path)
    columns = await poppler.page_text(documents["two_column_pdf"], 1, cwd=tmp_path)

    assert route_page(scanned).reason == "thin_text_layer"
    assert route_page(columns).reason == "multi_column"


async def test_math_dense_text_goes_to_vision(documents, tmp_path) -> None:
    page = await poppler.page_text(documents["text_pdf"], 1, cwd=tmp_path)
    words = list(page.words)
    # Replace a tenth of the words with notation; the threshold is 5%.
    for index in range(0, len(words), 10):
        words[index] = poppler.Word("∑x∈S", *[10.0, 10.0, 20.0, 20.0])
    mathematical = poppler.PageText(
        page_no=1, width_pt=page.width_pt, height_pt=page.height_pt, words=tuple(words)
    )

    assert route_page(mathematical).method == VISION
    assert route_page(mathematical).reason == "math_dense"


async def test_text_layer_markdown_reads_back_the_page(documents, tmp_path) -> None:
    page = await poppler.page_text(documents["text_pdf"], 1, cwd=tmp_path)
    markdown = text_layer_markdown(page)

    assert markdown.startswith("A Very Ordinary Report")
    assert "quick brown fox" in markdown
    assert "\n" in markdown
