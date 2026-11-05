"""search_docs with a publication or topic (subtree) scope."""
import pytest

from siemens_docs_mcp.catalog import CatalogError
from siemens_docs_mcp.client import FluidtopicsError
from siemens_docs_mcp.tools import search_docs
from tests.conftest import (
    IOX_HOST,
    TIA_HOST,
    make_hit,
    make_map,
    make_node,
    make_search_page,
    make_search_response,
    make_toc,
)

V21 = [{"key": "tia:SoftwareVersionFilter", "values": ["V21"]}]
TIA2_FILTER = [{"key": "ft:publicationId", "values": ["tia2"]}]
SC_FILTER = [{"key": "ft:publicationId", "values": ["sc"]}]


@pytest.fixture
def scoped_guide(fake_tia):
    """Map "sc": root > Chapter A (A1, A2) and Chapter B (B1)."""
    pretty = "/r/en-us/v21/scoped"
    fake_tia.maps.append(make_map("sc", "Scoped Guide", pretty=pretty[3:]))
    fake_tia.pages["sc"] = make_toc("sc-root", "Scoped Guide", pretty, [
        make_node("t-cha", "sc-cha", "Chapter A", f"{pretty}/a", [
            make_node("t-a1", "sc-a1", "A1", f"{pretty}/a/a1"),
            make_node("t-a2", "sc-a2", "A2", f"{pretty}/a/a2"),
        ]),
        make_node("t-chb", "sc-chb", "Chapter B", f"{pretty}/b", [
            make_node("t-b1", "sc-b1", "B1", f"{pretty}/b/b1"),
        ]),
    ])
    return fake_tia


def sc_hits(*content_ids: str) -> list[dict]:
    return [make_hit(title=c, map_title="Scoped Guide", map_id="sc", content_id=c) for c in content_ids]


def filler(n: int) -> list[dict]:
    """Publication hits outside Chapter A."""
    return sc_hits(*(["sc-b1"] * n))


# --- publication scope ---------------------------------------------------------------------------


def test_publication_scope_filters_upstream_and_derives_host_and_locale(catalog, fake_tia, fake_iox):
    fake_tia.search_response = make_search_response([make_hit()], total=1)
    search_docs(catalog, "block", None, None, scope="tia:tia2")
    assert fake_tia.search_calls == [
        {"query": "block", "locale": "en-US", "filters": TIA2_FILTER, "page": 1, "per_page": 10},
    ]
    assert fake_iox.search_calls == []


def test_publication_scope_uses_the_publications_locale(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit(map_id="tia5", content_id="x")], total=1)
    search_docs(catalog, "q", None, None, scope="tia:tia5")
    assert fake_tia.search_calls[0]["locale"] == "de-DE"


def test_publication_scope_output_names_scope_once(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit(title="Page 1", metadata=V21)], total=11)
    assert search_docs(catalog, "block", None, None, scope="tia:tia2") == (
        'Found 11 results for "block" in STEP 7 Basic (V21). Showing 1:\n'
        "1. **Page 1**\n"
        "   Chapter 1 > Section\n"
        "   Some text\n"
        "   tia:tia2/tia2-p1"
    )


def test_publication_scope_accepts_reader_url(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()], total=1)
    search_docs(catalog, "q", None, None, scope=f"https://{TIA_HOST}/r/en-us/v21/doc")
    assert fake_tia.search_calls[0]["filters"] == TIA2_FILTER


def test_publication_scope_no_results(catalog, fake_tia):
    fake_tia.search_response = make_search_response([], total=0)
    assert search_docs(catalog, "zzz", None, None, scope="tia:tia2") == 'No results for "zzz" in STEP 7 Basic (V21).'


def test_scoped_output_is_smaller_than_unscoped(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit(metadata=V21)] * 10, total=10)
    scoped = search_docs(catalog, "q", None, None, scope="tia:tia2")
    unscoped = search_docs(catalog, "q", TIA_HOST, "en-US")
    assert len(scoped) < len(unscoped)
    assert len(scoped) <= 730  # measured 2026-11-05; unscoped is 944


def test_scope_with_url_reference_format(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()], total=1)
    out = search_docs(catalog, "q", None, None, scope="tia:tia2", reference_format="url")
    assert out.endswith(f"   https://{TIA_HOST}/r/en-us/v21/doc/chapter-1/page-1")


# --- parameter checks ----------------------------------------------------------------------------


def test_matching_host_and_locale_are_accepted_case_insensitively(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()], total=1)
    search_docs(catalog, "q", TIA_HOST.upper(), "EN-us", scope="tia:tia2")
    assert fake_tia.search_calls[0]["locale"] == "en-US"


@pytest.mark.parametrize("kwargs,message", [
    ({"host": IOX_HOST}, "host"),
    ({"locale": "de-DE"}, "locale"),
    ({"product": "STEP 7"}, "product"),
    ({"version": "V21"}, "version"),
])
def test_conflicting_parameters_are_rejected_before_search(catalog, fake_tia, fake_iox, kwargs, message):
    args = {"host": None, "locale": None, **kwargs}
    with pytest.raises(ValueError, match=message):
        search_docs(catalog, "q", args.pop("host"), args.pop("locale"), scope="tia:tia2", **args)
    assert fake_tia.search_calls == fake_iox.search_calls == []


def test_empty_product_and_version_are_ignored_with_scope(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit()], total=1)
    search_docs(catalog, "q", None, None, product="", version="", scope="tia:tia2")
    assert fake_tia.search_calls[0]["filters"] == TIA2_FILTER


def test_invalid_scope_is_rejected(catalog, fake_tia):
    with pytest.raises(CatalogError):
        search_docs(catalog, "q", None, None, scope="tia:missing-map")
    assert fake_tia.search_calls == []


def test_unscoped_search_still_needs_host_and_locale(catalog):
    with pytest.raises(ValueError, match="host"):
        search_docs(catalog, "q", None, None)


# --- ignored upstream filter ---------------------------------------------------------------------


def test_hit_from_another_publication_is_an_error(catalog, fake_tia):
    fake_tia.search_response = make_search_response([make_hit(), make_hit(map_id="tia3", content_id="x")], total=2)
    with pytest.raises(FluidtopicsError, match="publication filter"):
        search_docs(catalog, "q", None, None, scope="tia:tia2")


def test_cluster_entry_from_scoped_publication_is_chosen(catalog, fake_tia):
    other = make_hit(title="Other", map_id="tia3", content_id="x")["entries"][0]
    cluster = make_hit(title="Mine")
    cluster["entries"].insert(0, other)
    fake_tia.search_response = make_search_response([cluster], total=1)
    out = search_docs(catalog, "q", None, None, scope="tia:tia2")
    assert "**Mine**" in out and "Other" not in out
    assert out.endswith("   tia:tia2/tia2-p1")


def test_subtree_scan_also_rejects_foreign_hits(catalog, scoped_guide):
    scoped_guide.search_response = make_search_response([make_hit(map_id="tia3", content_id="x")], total=1)
    with pytest.raises(FluidtopicsError, match="publication filter"):
        search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha")


# --- subtree scope -------------------------------------------------------------------------------


def test_subtree_keeps_only_hits_inside_the_topic(catalog, scoped_guide):
    scoped_guide.search_response = make_search_response(sc_hits("sc-a1", "sc-b1", "sc-a2", "sc-cha"))
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha")
    assert scoped_guide.search_calls == [
        {"query": "q", "locale": "en-US", "filters": SC_FILTER, "page": 1, "per_page": 100},
    ]
    assert out == (
        'Found 3 results for "q" in "Chapter A" — Scoped Guide (V21). Showing 3:\n'
        "1. **sc-a1**\n   Chapter 1 > Section\n   Some text\n   tia:sc/sc-a1\n"
        "2. **sc-a2**\n   Chapter 1 > Section\n   Some text\n   tia:sc/sc-a2\n"
        "3. **sc-cha**\n   Chapter 1 > Section\n   Some text\n   tia:sc/sc-cha"
    )


def test_subtree_accepts_toc_id(catalog, scoped_guide):
    scoped_guide.search_response = make_search_response(sc_hits("sc-a1", "sc-b1"))
    out = search_docs(catalog, "q", None, None, scope="tia:sc/t-cha")
    assert "tia:sc/sc-a1" in out and "sc-b1" not in out


def test_leaf_topic_scope(catalog, scoped_guide):
    scoped_guide.search_response = make_search_response(sc_hits("sc-a1", "sc-a2"))
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-a2")
    assert out.startswith('Found 1 results for "q" in "A2" — Scoped Guide (V21).')
    assert "tia:sc/sc-a2" in out and "sc-a1" not in out


def test_root_topic_scope_is_publication_scope(catalog, scoped_guide):
    scoped_guide.search_response = make_search_response(sc_hits("sc-a1", "sc-b1"), total=2)
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-root")
    assert scoped_guide.search_calls[0]["per_page"] == 10
    assert out.startswith('Found 2 results for "q" in Scoped Guide (V21).')
    assert "tia:sc/sc-b1" in out


def test_topic_outside_toc_is_rejected(catalog, scoped_guide):
    with pytest.raises(CatalogError, match="not in this publication's TOC"):
        search_docs(catalog, "q", None, None, scope="tia:sc/nope")
    assert scoped_guide.search_calls == []


def test_subtree_stops_when_limit_is_reached(catalog, scoped_guide):
    scoped_guide.search_pages = {1: make_search_page(sc_hits("sc-a1", "sc-a2") + filler(98), 250, 1, last=False)}
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha", limit=2)
    assert len(scoped_guide.search_calls) == 1
    assert out.splitlines()[0] == (
        'Showing 2 results for "q" in "Chapter A" — Scoped Guide (V21); '
        "checked 100 of 250 publication results, more may exist:"
    )


def test_subtree_reads_following_pages_until_the_last(catalog, scoped_guide):
    scoped_guide.search_pages = {
        1: make_search_page(sc_hits("sc-a1") + filler(99), 120, 1, last=False),
        2: make_search_page(filler(19) + sc_hits("sc-a2"), 120, 2, last=True),
    }
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha")
    assert [c["page"] for c in scoped_guide.search_calls] == [1, 2]
    assert out.startswith('Found 2 results for "q" in "Chapter A" — Scoped Guide (V21). Showing 2:')
    assert out.index("tia:sc/sc-a1") < out.index("tia:sc/sc-a2")


def test_subtree_count_is_exact_when_limit_is_hit_on_the_last_page(catalog, scoped_guide):
    scoped_guide.search_response = make_search_page(sc_hits("sc-a1", "sc-a2", "sc-cha"), 3, 1, last=True)
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha", limit=2)
    assert out.splitlines()[0] == 'Found 3 results for "q" in "Chapter A" — Scoped Guide (V21). Showing 2:'


def test_subtree_scan_stops_after_three_pages(catalog, scoped_guide):
    scoped_guide.search_pages = {
        1: make_search_page(sc_hits("sc-a1") + filler(99), 1000, 1, last=False),
        2: make_search_page(filler(100), 1000, 2, last=False),
        3: make_search_page(filler(100), 1000, 3, last=False),
        4: make_search_page(sc_hits("sc-a2") * 100, 1000, 4, last=False),
    }
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha")
    assert [c["page"] for c in scoped_guide.search_calls] == [1, 2, 3]
    assert out.splitlines()[0] == (
        'Showing 1 results for "q" in "Chapter A" — Scoped Guide (V21); '
        "checked 300 of 1000 publication results, more may exist:"
    )


def test_subtree_no_results_after_partial_scan(catalog, scoped_guide):
    scoped_guide.search_pages = {p: make_search_page(filler(100), 1000, p, last=False) for p in (1, 2, 3)}
    assert search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha") == (
        'No results for "q" in "Chapter A" — Scoped Guide (V21) among the first 300 of 1000 publication results. '
        "Try a narrower query or search the whole publication."
    )


def test_subtree_no_results_after_full_scan(catalog, scoped_guide):
    scoped_guide.search_response = make_search_page(filler(5), 5, 1, last=True)
    assert search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha") == (
        'No results for "q" in "Chapter A" — Scoped Guide (V21).'
    )


def test_subtree_scope_on_multi_section_toc(catalog, fake_iox):
    """iox1 has no root topic; a section is a normal subtree."""
    hits = [make_hit(title=c, map_id="iox1", content_id=c) for c in ("iox1-p1a", "iox1-p2")]
    fake_iox.search_response = make_search_response(hits)
    out = search_docs(catalog, "q", None, None, scope="iox:iox1/iox1-p1")
    assert out.startswith('Found 1 results for "q" in "Intro" — Edge Guide (6.1).')
    assert "iox:iox1/iox1-p1a" in out and "iox1-p2" not in out


def test_subtree_trusts_the_last_page_flag_over_totals(catalog, scoped_guide):
    """Results and clusters can be counted differently upstream; the flag still ends the scan."""
    scoped_guide.search_pages = {1: make_search_page(sc_hits("sc-a1") + filler(2), 150, 1, last=True)}
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha")
    assert len(scoped_guide.search_calls) == 1
    assert out.startswith('Found 1 results for "q" in "Chapter A" — Scoped Guide (V21). Showing 1:')


def test_subtree_scan_counts_clusters_not_results(catalog, scoped_guide):
    """Each cluster is one hit after scoping, so progress is measured against totalClustersCount."""
    def page(n: int) -> dict:
        data = make_search_page(filler(100), 900, n, last=False)
        data["paging"]["totalClustersCount"] = 800
        return data

    scoped_guide.search_pages = {n: page(n) for n in (1, 2, 3)}
    out = search_docs(catalog, "q", None, None, scope="tia:sc/sc-cha")
    assert "among the first 300 of 800 publication results" in out
