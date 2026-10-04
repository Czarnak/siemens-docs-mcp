import pytest

from scraper.tools import list_publications, search_docs
from tests.conftest import IOX_HOST, TIA_HOST, make_hit, make_map, make_search_response


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
