import pytest

from scraper.catalog import CatalogError, Resolved
from scraper.tools import get_toc, list_publications, read_page, search_docs
from tests.conftest import (
    IOX_HOST,
    TIA_HOST,
    make_big_toc,
    make_hit,
    make_map,
    make_search_response,
)


def test_search_docs_formats_hits(catalog, fake_tia):
    fake_tia.search_response = make_search_response(
        [
            make_hit(
                title="Create block",
                metadata=[{"key": "tia:SoftwareVersionFilter", "values": ["V21"]}],
            ),
            {"entries": [{"type": "MAP"}]},  # no topic: skipped
        ],
        total=42,
    )
    out = search_docs(catalog, "block", TIA_HOST, "en-us", limit=5)
    assert out.splitlines()[0] == f'Found 42 results for "block" on {TIA_HOST}. Showing 1:'
    assert "1. **Create block** — STEP 7 Basic (V21)" in out
    assert "   Chapter 1 > Section" in out
    assert "   Some text" in out and "<b>" not in out
    assert "   https://docs.tia.siemens.cloud/r/en-us/v21/doc/page" in out
    call = fake_tia.search_calls[0]
    assert call["locale"] == "en-US" and call["filters"] is None
    assert call["page"] == 1 and call["per_page"] == 5


def test_search_docs_omits_version_when_missing(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()])
    out = search_docs(catalog, "q", TIA_HOST, "en-US")
    assert "**Hit** — STEP 7 Basic\n" in out


def test_search_docs_canonicalizes_filters(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()])
    search_docs(catalog, "q", TIA_HOST, "en-US", product="step 7", version="v21")
    assert fake_tia.search_calls[0]["filters"] == [
        {"key": "Product", "values": ["STEP 7"]},
        {"key": "tia:SoftwareVersionFilter", "values": ["V21"]},
    ]


def test_search_docs_version_filter_key_for_iox(catalog, fake_iox):
    fake_iox.search_response = make_search_response([make_hit()])
    search_docs(catalog, "q", IOX_HOST, "en-US", version="6.1")
    assert fake_iox.search_calls[0]["filters"] == [{"key": "SoftwareVersion", "values": ["6.1"]}]


@pytest.mark.parametrize("limit", [0, 51])
def test_search_docs_limit_bounds(catalog, fake_tia, limit):
    with pytest.raises(ValueError, match="1-50"):
        search_docs(catalog, "q", TIA_HOST, "en-US", limit=limit)
    assert fake_tia.search_calls == []


def test_search_docs_no_results(catalog, fake_tia):
    fake_tia.search_response = make_search_response([], total=0)
    assert search_docs(catalog, "zzz", TIA_HOST, "en-US") == f'No results for "zzz" on {TIA_HOST}.'


def test_list_publications_filters_and_cap(catalog, fake_tia):
    fake_tia.maps = [make_map(f"m{i:02d}", f"Doc {i:02d}", pretty=f"en-us/v21/d{i}") for i in range(60)]
    out = list_publications(catalog, TIA_HOST, "en-us", product="step 7")
    lines = out.splitlines()
    assert len(lines) == 51
    assert lines[0] == f"- **Doc 00** — STEP 7 V21 [en-US] https://{TIA_HOST}/r/en-us/v21/d0"
    assert lines[-1] == "Showing 50 of 60 — narrow your filters."


def test_list_publications_small_has_no_footer(catalog):
    out = list_publications(catalog, TIA_HOST, "en-US", version="v20")
    assert out == f"- **STEP 7 Basic V20** — STEP 7 V20 [en-US] https://{TIA_HOST}/r/en-us/v20/doc"


def test_list_publications_none(catalog):
    out = list_publications(catalog, TIA_HOST, "en-US", title_contains="nonexistent")
    assert out == f"No publications match these filters on {TIA_HOST}."


# --- read_page / get_toc ---------------------------------------------------

P1_URL = f"https://{TIA_HOST}/r/en-us/v21/doc/chapter-1/page-1"
ROOT_URL = f"https://{TIA_HOST}/r/tia2"


def test_read_page_header_and_body(catalog):
    out = read_page(catalog, P1_URL)
    lines = out.splitlines()
    assert lines[0] == "> Publication: STEP 7 Basic (V21) [en-US]"
    assert lines[1] == "> Path: STEP 7 Basic > Chapter 1 > Page 1"
    assert lines[2] == f"> Source: {P1_URL}"
    assert lines[3] == ""
    assert lines[4] == "# Page 1"
    assert "Hello" in out and "truncated" not in out


def test_read_page_map_root_reads_root_topic(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-root")] = "<p>Welcome</p>"
    out = read_page(catalog, ROOT_URL)
    assert "> Path: STEP 7 Basic\n" in out
    assert f"> Source: https://{TIA_HOST}/r/en-us/v21/doc\n" in out
    assert "# STEP 7 Basic" in out and "Welcome" in out


def test_read_page_truncates_with_offset_hint(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = "<p>" + "abcdefghij " * 400 + "</p>"
    first = read_page(catalog, P1_URL, max_chars=1000)
    assert first.endswith("[truncated — call again with offset=1000]")
    second = read_page(catalog, P1_URL, offset=1000, max_chars=1000)
    assert "offset=2000" in second
    body = first.split("\n\n", 1)[1]
    assert "offset=1000" in body


def test_read_page_last_chunk_has_no_footer(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = "<p>short</p>"
    assert "truncated" not in read_page(catalog, P1_URL, max_chars=1000)


def test_read_page_offset_past_end(catalog):
    with pytest.raises(ValueError, match="length"):
        read_page(catalog, P1_URL, offset=10_000)


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"max_chars": 999}, {"max_chars": 100_001}])
def test_read_page_param_bounds(catalog, fake_tia, kwargs):
    with pytest.raises(ValueError):
        read_page(catalog, "not even a url", **kwargs)
    assert fake_tia.get_pages_calls == []


def test_read_page_empty_content(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = "   "
    out = read_page(catalog, P1_URL)
    assert out.endswith("*No content available.*\n")


def test_read_page_untitled_topic_not_in_toc(catalog, fake_tia):
    fake_tia.contents[("tia2", "ghost")] = "<p>Orphan</p>"
    out = read_page(catalog, f"https://{TIA_HOST}/r/tia2/ghost")
    assert "> Path: STEP 7 Basic\n" in out
    assert f"> Source: https://{TIA_HOST}/r/tia2/ghost\n" in out
    assert "# (untitled topic)" in out and "Orphan" in out


def test_read_page_missing_map_is_catalog_error(catalog, fake_tia, monkeypatch):
    monkeypatch.setattr(catalog, "maps", lambda host: {})
    monkeypatch.setattr(
        catalog, "resolve", lambda url: Resolved(TIA_HOST, "gone", "x")
    )
    with pytest.raises(CatalogError):
        read_page(catalog, P1_URL)


def test_get_toc_depth(catalog):
    full = get_toc(catalog, ROOT_URL, depth=2)
    assert full.splitlines() == [
        f"- STEP 7 Basic — https://{TIA_HOST}/r/en-us/v21/doc",
        f"  - Chapter 1 — https://{TIA_HOST}/r/en-us/v21/doc/chapter-1",
        f"    - Page 1 — {P1_URL}",
    ]
    shallow = get_toc(catalog, ROOT_URL, depth=1)
    assert "Chapter 1" in shallow and "Page 1" not in shallow


@pytest.mark.parametrize("depth", [0, 7])
def test_get_toc_depth_bounds(catalog, depth):
    with pytest.raises(ValueError, match="1-6"):
        get_toc(catalog, ROOT_URL, depth=depth)


def test_get_toc_subtree_from_topic_url(catalog):
    out = get_toc(catalog, f"https://{TIA_HOST}/r/en-us/v21/doc/chapter-1", depth=1)
    assert out.splitlines()[0].startswith("- Chapter 1 — ")
    assert out.splitlines()[1].startswith("  - Page 1 — ")


def test_get_toc_topic_not_in_toc(catalog):
    with pytest.raises(CatalogError, match="search_docs"):
        get_toc(catalog, f"https://{TIA_HOST}/r/tia2/ghost")


def test_get_toc_line_cap(catalog, fake_tia):
    fake_tia.maps = [make_map("big", "Big", pretty="en-us/big")]
    fake_tia.pages["big"] = make_big_toc(599)
    out = get_toc(catalog, f"https://{TIA_HOST}/r/big", depth=6)
    lines = out.splitlines()
    assert len(lines) == 501
    assert lines[-1] == "… truncated at 500 lines — use a deeper URL or a smaller depth."


IOX_PUB = f"https://{IOX_HOST}/r/en-us/edge/guide"


def test_get_toc_multi_root_labels_publication(catalog):
    out = get_toc(catalog, IOX_PUB, depth=1)
    assert out.splitlines()[0] == f"- Edge Guide — {IOX_PUB}"
    assert "- Intro — " in out and "- Setup — " in out


def test_read_page_multi_root_topic_path_has_no_empty_segment(catalog):
    out = read_page(catalog, f"{IOX_PUB}/intro/a")
    assert "> Path: Edge Guide > Intro > Intro A" in out


def test_read_page_multi_root_bare_url(catalog):
    out = read_page(catalog, IOX_PUB)
    assert "> Path: Edge Guide > Intro" in out.splitlines()
