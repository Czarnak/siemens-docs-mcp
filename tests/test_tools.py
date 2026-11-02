import pytest

from siemens_docs_mcp.catalog import CatalogError, Resolved
from siemens_docs_mcp.tools import get_toc, list_publications, read_page, search_docs
from tests.conftest import (
    IOX_HOST,
    SHARED_PRETTY,
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
    out = search_docs(catalog, "block", TIA_HOST, "en-us", limit=5, reference_format="url")
    assert out.splitlines()[0] == f'Found 42 results for "block" on {TIA_HOST}. Showing 1:'
    assert "1. **Create block** — STEP 7 Basic (V21)" in out
    assert "   Chapter 1 > Section" in out
    assert "   Some text" in out and "<b>" not in out
    assert "   https://docs.tia.siemens.cloud/r/en-us/v21/doc/chapter-1/page-1" in out
    call = fake_tia.search_calls[0]
    assert call["locale"] == "en-US" and call["filters"] is None
    assert call["page"] == 1 and call["per_page"] == 5


def test_search_docs_omits_version_when_missing(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()])
    out = search_docs(catalog, "q", TIA_HOST, "en-US")
    assert "**Hit** — STEP 7 Basic\n" in out


def test_search_docs_excerpt_keeps_original_spacing(catalog, fake_tia):
    excerpt = (
        '<span class="kwicmatch">TON</span><span class="kwicstring">: </span>'
        '<span class="kwicmatch">Start on</span><span class="kwicstring">-</span>'
        '<span class="kwicmatch">delay timer</span><span class="kwicstring">&quot; instruction</span>'
    )
    fake_tia.search_response = make_search_response([make_hit(excerpt=excerpt)])
    out = search_docs(catalog, "q", TIA_HOST, "en-US")
    assert '   TON: Start on-delay timer" instruction\n' in out


def test_search_docs_canonicalizes_filters(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()])
    search_docs(catalog, "q", TIA_HOST, "en-US", product="step 7", version="v21")
    assert fake_tia.search_calls[0]["filters"] == [
        {"key": "Product", "values": ["STEP 7"]},
        {"key": "tia:SoftwareVersionFilter", "values": ["V21"]},
    ]


def test_search_docs_version_filter_key_for_iox(catalog, fake_iox):
    fake_iox.search_response = make_search_response([make_hit(
        map_id="iox1", content_id="iox1-p1", map_title="Edge Guide",
        reader_url=f"https://{IOX_HOST}/r/en-us/edge/guide/intro",
    )])
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


def test_search_docs_empty_results_do_not_require_paging(catalog, fake_tia):
    fake_tia.search_response = {"results": [], "paging": None}
    assert search_docs(catalog, "zzz", TIA_HOST, "en-US") == f'No results for "zzz" on {TIA_HOST}.'


def test_list_publications_filters_and_cap(catalog, fake_tia):
    fake_tia.maps = [make_map(f"m{i:02d}", f"Doc {i:02d}", pretty=f"en-us/v21/d{i}") for i in range(60)]
    out = list_publications(catalog, TIA_HOST, "en-us", product="step 7", reference_format="url")
    lines = out.splitlines()
    assert len(lines) == 51
    assert lines[0] == f"- **Doc 00** — STEP 7 V21 [en-US] https://{TIA_HOST}/r/en-us/v21/d0"
    assert lines[-1] == "Showing 50 of 60 — narrow your filters."


def test_list_publications_small_has_no_footer(catalog):
    out = list_publications(catalog, TIA_HOST, "en-US", version="v20", reference_format="url")
    assert out == f"- **STEP 7 Basic V20** — STEP 7 V20 [en-US] https://{TIA_HOST}/r/en-us/v20/doc"


def test_list_publications_url_forms(catalog, fake_tia, shared_pretty):
    fake_tia.maps.append(make_map("tia8", "No Pretty", pretty=""))
    out = list_publications(catalog, TIA_HOST.upper(), "en-US", version="V21", reference_format="url")
    urls = [line.rsplit(" ", 1)[-1] for line in out.splitlines()]
    assert f"https://{TIA_HOST}/r/tia8" in urls
    assert f"https://{TIA_HOST}/r/tia6" in urls and f"https://{TIA_HOST}/r/tia7" in urls
    assert f"https://{TIA_HOST}/r/en-us/v21/doc" in urls
    assert all(u.startswith(f"https://{TIA_HOST}/r/") and not u.endswith("/r/") for u in urls)


def test_get_toc_topic_from_second_shared_map(catalog, shared_pretty):
    out = get_toc(catalog, f"https://{TIA_HOST}/r/{SHARED_PRETTY}/b-topic", reference_format="url")
    assert out == f"- B-Topic — https://{TIA_HOST}/r/tia7/tia7-p1"


def test_list_publications_none(catalog):
    out = list_publications(catalog, TIA_HOST, "en-US", title_contains="nonexistent")
    assert out == f"No publications match these filters on {TIA_HOST}."


# --- read_page / get_toc ---------------------------------------------------

P1_URL = f"https://{TIA_HOST}/r/en-us/v21/doc/chapter-1/page-1"
ROOT_URL = f"https://{TIA_HOST}/r/tia2"


def test_read_page_header_and_body(catalog):
    out = read_page(catalog, P1_URL, reference_format="url")
    lines = out.splitlines()
    assert lines[0] == "> Publication: STEP 7 Basic (V21) [en-US]"
    assert lines[1] == "> Path: STEP 7 Basic > Chapter 1 > Page 1"
    assert lines[2] == f"> Source: {P1_URL}"
    assert lines[3] == ""
    assert lines[4] == "# Page 1"
    assert "Hello" in out and "truncated" not in out


def test_read_page_map_root_reads_root_topic(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-root")] = "<p>Welcome</p>"
    out = read_page(catalog, ROOT_URL, reference_format="url")
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
    out = read_page(catalog, f"https://{TIA_HOST}/r/tia2/ghost", reference_format="url")
    assert "> Path: STEP 7 Basic\n" in out
    assert f"> Source: https://{TIA_HOST}/r/tia2/ghost\n" in out
    assert "# (untitled topic)" in out and "Orphan" in out


def test_read_page_follows_in_page_toc_id_link(catalog):
    out = read_page(catalog, f"https://{TIA_HOST}/r/tia2/t-p1", reference_format="url")
    assert "# Page 1" in out and "Hello" in out
    assert "> Source: https://docs.tia.siemens.cloud/r/en-us/v21/doc/chapter-1/page-1\n" in out


def test_read_page_missing_map_is_catalog_error(catalog, fake_tia, monkeypatch):
    monkeypatch.setattr(catalog, "maps", lambda host: {})
    monkeypatch.setattr(
        catalog, "resolve", lambda url: Resolved(TIA_HOST, "gone", "x")
    )
    with pytest.raises(CatalogError):
        read_page(catalog, P1_URL)


def test_get_toc_depth(catalog):
    full = get_toc(catalog, ROOT_URL, depth=2, reference_format="url")
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
    assert lines[-1] == "… truncated at 500 lines — use a deeper reference or a smaller depth."


IOX_PUB = f"https://{IOX_HOST}/r/en-us/edge/guide"


def test_get_toc_multi_root_labels_publication(catalog):
    out = get_toc(catalog, IOX_PUB, depth=1, reference_format="url")
    assert out.splitlines()[0] == f"- Edge Guide — {IOX_PUB}"
    assert "- Intro — " in out and "- Setup — " in out


def test_read_page_multi_root_topic_path_has_no_empty_segment(catalog):
    out = read_page(catalog, f"{IOX_PUB}/intro/a")
    assert "> Path: Edge Guide > Intro > Intro A" in out


def test_read_page_multi_root_bare_url(catalog):
    out = read_page(catalog, IOX_PUB)
    assert "> Path: Edge Guide > Intro" in out.splitlines()


def test_compact_defaults(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()])
    assert "   tia:tia2/tia2-p1" in search_docs(catalog, "q", TIA_HOST, "en-US")
    assert "[en-US] tia:tia2" in list_publications(catalog, TIA_HOST, "en-US")
    assert get_toc(catalog, url="tia:tia2/t-ch1").splitlines() == [
        "- Chapter 1 — tia:tia2/tia2-ch1", "  - Page 1 — tia:tia2/tia2-p1",
    ]
    assert "> Source: tia:tia2/tia2-p1" in read_page(catalog, url="tia:tia2/t-p1")
    assert "Hello" in read_page(catalog, url="tia:tia2/tia2-p1")


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_multi_root_toc_uses_publication_reference(catalog, reference_format):
    out = get_toc(catalog, "iox:iox1", reference_format=reference_format)
    reference = "iox:iox1" if reference_format == "compact" else IOX_PUB
    assert out.splitlines()[0] == f"- Edge Guide — {reference}"
    assert catalog.resolve(reference) == Resolved(IOX_HOST, "iox1", None)


@pytest.mark.parametrize("reference_format", ["compact", "url"])
@pytest.mark.parametrize("identity", [
    {}, {"mapId": None}, {"contentId": None}, {"mapId": 42}, {"contentId": []},
    {"mapId": ""}, {"contentId": ""}, {"mapId": "bad/path"}, {"contentId": ".."},
])
def test_search_reference_fallbacks(catalog, fake_tia, reference_format, identity):
    cluster = make_hit()
    topic = cluster["entries"][0]["topic"]
    if identity:
        topic.update(identity)
    else:
        del topic["mapId"]
        del topic["contentId"]
    fake_tia.search_response = make_search_response([cluster])
    out = search_docs(catalog, "q", TIA_HOST, "en-US", reference_format=reference_format)
    assert out.endswith("   " + P1_URL)
    assert "**Hit** — STEP 7 Basic\n   Chapter 1 > Section\n   Some text\n" in out


@pytest.mark.parametrize("reference_format", ["compact", "url"])
@pytest.mark.parametrize("reader_url", [
    P1_URL, f"https://{IOX_HOST}/r/en-us/edge/guide/intro", None, 42, "", "not a URL",
    "https://evil.example/r/map/topic", f"https://{TIA_HOST}/not-reader",
])
@pytest.mark.parametrize("valid_ids", [True, False])
def test_search_reference_url_fallbacks(catalog, fake_tia, reference_format, reader_url, valid_ids):
    cluster = make_hit(reader_url=reader_url)
    if not valid_ids:
        cluster["entries"][0]["topic"]["contentId"] = "."
    fake_tia.search_response = make_search_response([cluster])
    out = search_docs(catalog, "q", TIA_HOST, "en-US", reference_format=reference_format)
    fallback = reader_url if reader_url in (P1_URL, f"https://{IOX_HOST}/r/en-us/edge/guide/intro") else None
    if valid_ids:
        expected = "tia:tia2/tia2-p1" if reference_format == "compact" else fallback or f"https://{TIA_HOST}/r/tia2/tia2-p1"
    else:
        expected = fallback or "(reference unavailable)"
    assert out.endswith("   " + expected)
    assert "**Hit** — STEP 7 Basic\n   Chapter 1 > Section\n   Some text\n" in out


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_search_missing_url_uses_known_identity(catalog, fake_tia, reference_format):
    cluster = make_hit()
    del cluster["entries"][0]["topic"]["readerUrl"]
    fake_tia.search_response = make_search_response([cluster])
    out = search_docs(catalog, "q", TIA_HOST, "en-US", reference_format=reference_format)
    expected = "tia:tia2/tia2-p1" if reference_format == "compact" else f"https://{TIA_HOST}/r/tia2/tia2-p1"
    assert out.endswith("   " + expected)


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_search_does_not_fetch_hit_tocs(catalog, fake_tia, reference_format):
    fake_tia.search_response = make_search_response([make_hit(content_id=f"unlisted-{i}") for i in range(20)])
    search_docs(catalog, "q", TIA_HOST, "en-US", limit=20, reference_format=reference_format)
    assert fake_tia.get_pages_calls == []
    assert fake_tia.get_content_calls == []


@pytest.mark.parametrize("tool,args", [
    (search_docs, ("q", TIA_HOST, "en-US")),
    (list_publications, (TIA_HOST, "en-US")),
    (read_page, ("tia:tia2/tia2-p1",)),
    (get_toc, ("tia:tia2",)),
])
def test_invalid_format_rejected_before_fetch(catalog, fake_tia, fake_iox, tool, args):
    with pytest.raises(ValueError, match="reference_format"):
        tool(catalog, *args, reference_format="json")
    for client in (fake_tia, fake_iox):
        assert client.list_maps_calls == 0
        assert client.search_calls == client.get_pages_calls == client.get_content_calls == []


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_read_topic_absent_from_toc(catalog, fake_tia, reference_format):
    fake_tia.contents[("tia2", "orphan")] = "<p>Orphan body</p>"
    out = read_page(catalog, "tia:tia2/orphan", reference_format=reference_format)
    source = "tia:tia2/orphan" if reference_format == "compact" else f"https://{TIA_HOST}/r/tia2/orphan"
    assert f"> Source: {source}\n" in out
    assert "Orphan body" in out
    with pytest.raises(CatalogError, match="search_docs"):
        get_toc(catalog, source, reference_format=reference_format)


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_body_links_are_unchanged(catalog, fake_tia, reference_format):
    fake_tia.contents[("tia2", "tia2-p1")] = f'<a href="{P1_URL}">Next</a>'
    assert f"[Next]({P1_URL})" in read_page(catalog, "tia:tia2/tia2-p1", reference_format=reference_format)


@pytest.mark.parametrize("reference_format", ["compact", "url"])
@pytest.mark.parametrize("prefix,host", [("tia", TIA_HOST), ("iox", IOX_HOST)])
def test_same_id_cross_host_roundtrip(catalog, fake_tia, fake_iox, reference_format, prefix, host):
    fake_iox.maps.append(make_map("tia2", "IOX Collision", pretty="en-us/v21/doc"))
    fake_iox.pages["tia2"] = fake_tia.pages["tia2"]
    fake_iox.contents[("tia2", "tia2-p1")] = "<p>IOX collision body</p>"
    client = fake_tia if host == TIA_HOST else fake_iox
    client.search_response = make_search_response([make_hit(reader_url=f"https://{host}/r/tia2/tia2-p1")])
    out = search_docs(catalog, "q", host, "en-US", reference_format=reference_format)
    reference = out.splitlines()[-1].strip()
    assert catalog.resolve(reference) == Resolved(host, "tia2", "tia2-p1")
    page = read_page(catalog, reference, reference_format=reference_format)
    assert ("Hello" if prefix == "tia" else "IOX collision body") in page
    alias_page = read_page(catalog, f"{prefix}:tia2/t-p1", reference_format=reference_format)
    assert page == alias_page


@pytest.mark.parametrize("reference_format", ["compact", "url"])
@pytest.mark.parametrize("alias,canonical,title", [
    ("tia:tia2/t-p1", "tia:tia2/tia2-p1", "Page 1"),
    ("iox:iox1/i-s1", "iox:iox1/iox1-p1", "Intro"),
])
def test_toc_alias_canonical_source(catalog, reference_format, alias, canonical, title):
    page = read_page(catalog, alias, reference_format=reference_format)
    assert page == read_page(catalog, canonical, reference_format=reference_format)
    assert f"# {title}" in page
    assert get_toc(catalog, alias, reference_format=reference_format) == get_toc(
        catalog, canonical, reference_format=reference_format,
    )
