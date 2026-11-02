"""Exact Markdown contracts for renderers given prepared values."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from siemens_docs_mcp.catalog import Catalog, MapInfo
from siemens_docs_mcp.client import FluidtopicsClient
from siemens_docs_mcp.rendering import (
    SearchHit,
    render_page,
    render_publications,
    render_search,
    render_toc,
)


def publication(title="Manual", version="V21"):
    return MapInfo("m", title, "en-US", "STEP 7", version, "", "", "", "")


def test_render_search_exact_spacing_and_missing_version():
    hits = [
        SearchHit("Hit", "Manual", "V21", ("A", "B"), "Some text", "https://example.test/r/m/c"),
        SearchHit("Timer", "Manual", "", (), "Start on-delay timer", "https://example.test/r/m/d"),
    ]
    assert render_search("q", "example.test", 42, hits) == (
        'Found 42 results for "q" on example.test. Showing 2:\n'
        '1. **Hit** — Manual (V21)\n   A > B\n   Some text\n   https://example.test/r/m/c\n'
        '2. **Timer** — Manual\n   \n   Start on-delay timer\n   https://example.test/r/m/d'
    )


def test_search_hit_is_frozen():
    hit = SearchHit("Hit", "Manual", "", (), "", "ref")
    with pytest.raises(FrozenInstanceError):
        hit.title = "Changed"


def test_render_empty_results():
    assert render_search("q", "example.test", 0, []) == 'No results for "q" on example.test.'
    assert render_publications("example.test", [], 0, 50) == (
        "No publications match these filters on example.test."
    )
    assert render_toc([], False, 500) == ""


def test_render_publications_cap_and_missing_version():
    rows = [(publication(version=""), "https://example.test/r/m")]
    line = "- **Manual** — STEP 7  [en-US] https://example.test/r/m"
    assert render_publications("example.test", rows, 1, 1) == line
    assert render_publications("example.test", rows, 2, 1) == (
        line + "\nShowing 1 of 2 — narrow your filters."
    )


def test_render_page_provenance_and_pagination():
    assert render_page(publication(), ["Manual", "A", "B"], "https://example.test/r/m/c", "body\n") == (
        "> Publication: Manual (V21) [en-US]\n> Path: Manual > A > B\n"
        "> Source: https://example.test/r/m/c\n\nbody\n"
    )
    chunk = "body\n\n[truncated — call again with offset=1000]"
    assert render_page(publication(version=""), [], "ref", chunk) == (
        "> Publication: Manual () [en-US]\n> Path: \n> Source: ref\n\n" + chunk
    )


def test_render_toc_indentation_and_explicit_cap():
    rows = [(0, "Manual", "https://example.test/r/m"), (1, "A", "https://example.test/r/m/c")]
    outline = "- Manual — https://example.test/r/m\n  - A — https://example.test/r/m/c"
    assert render_toc(rows, False, 2) == outline
    assert render_toc(rows, True, 2) == (
        outline + "\n… truncated at 2 lines — use a deeper reference or a smaller depth."
    )


@pytest.mark.parametrize("prefix", ["tia", "iox"])
def test_renderers_match_search_page_and_toc_goldens(prefix):
    recorded = json.loads((Path(__file__).with_name("fixtures") / "reference_outputs.json").read_text(encoding="utf-8"))
    if prefix == "tia":
        host, title, version, topic = "docs.tia.siemens.cloud", "STEP 7 Basic", "V21", "Page 1"
        url = f"https://{host}/r/en-us/v21/doc"
        path = [title, "Chapter 1", topic]
        rows = [(0, title, url), (1, "Chapter 1", url + "/chapter-1"), (2, topic, url + "/chapter-1/page-1")]
        total, chunk = 42, "# Page 1\n\n# Page 1\n\nHello\n"
    else:
        host, title, version, topic = "docs.industrial-operations-x.siemens.cloud", "Edge Guide", "6.1", "Intro"
        url = f"https://{host}/r/en-us/edge/guide"
        path = [title, topic]
        rows = [(0, title, url), (1, topic, url + "/intro"), (2, "Intro A", url + "/intro/a"), (1, "Setup", url + "/setup")]
        total, chunk = 3, "# Intro\n\n# Intro\n"
    source = rows[2 if prefix == "tia" else 1][2]
    hit = SearchHit(topic, title, version, tuple(path[:-1]), "Some text", source)
    assert render_search("reference", host, total, [hit]) == recorded[f"{prefix}_search"]["output"]
    assert render_page(publication(title, version), path, source, chunk) == recorded[f"{prefix}_read"]["output"]
    assert render_toc(rows, False, 500) == recorded[f"{prefix}_toc"]["output"]


@pytest.mark.parametrize("prefix", ["tia", "iox"])
def test_render_publications_matches_goldens(prefix):
    recorded = json.loads((Path(__file__).with_name("fixtures") / "reference_outputs.json").read_text(encoding="utf-8"))
    if prefix == "tia":
        host = "docs.tia.siemens.cloud"
        values = [
            ("Openness API", "TIA Portal Openness", "V21", "en-us/v21/openness"),
            ("STEP 7 Basic", "STEP 7", "V21", "en-us/v21/doc"),
            ("STEP 7 Basic Extra", "STEP 7", "V21", "en-us/v21/doc-extra"),
            ("STEP 7 Basic V20", "STEP 7", "V20", "en-us/v20/doc"),
        ]
    else:
        host = "docs.industrial-operations-x.siemens.cloud"
        values = [
            ("Edge Admin", "Industrial Edge", "6.0", "en-us/edge/admin"),
            ("Edge Guide", "Industrial Edge", "6.1", "en-us/edge/guide"),
        ]
    rows = [
        (MapInfo("m", title, "en-US", product, version, "", "", "", ""), f"https://{host}/r/{path}")
        for title, product, version, path in values
    ]
    assert render_publications(host, rows, len(rows), 50) == recorded[f"{prefix}_list"]["output"]


def test_renderer_does_not_access_catalog(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Rendering must not retrieve data")

    for name in ("client", "maps", "toc", "resolve", "map_url", "reader_url"):
        monkeypatch.setattr(Catalog, name, forbidden)
    with patch.object(FluidtopicsClient, "_request", forbidden):
        assert render_search("q", "host", 1, [SearchHit("Hit", "Manual", "", (), "", "ref")])
        assert render_publications("host", [(publication(), "ref")], 1, 50)
        assert render_page(publication(), ["Manual"], "ref", "body")
        assert render_toc([(0, "Manual", "ref")], False, 500)
