"""Characterization and measurements of tool-generated documentation references."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from bs4 import BeautifulSoup

from siemens_docs_mcp import tools
from tests.conftest import IOX_HOST, TIA_HOST, make_hit, make_map, make_node, make_toc
from tests.test_live import _addresses

FIXTURES = Path(__file__).with_name("fixtures")

EXPECTED_IDENTITIES = {
    "tia_search": [("tia2", "tia2-p1")],
    "tia_list": [("tia1", ""), ("tia2", ""), ("tia3", ""), ("tia4", "")],
    "tia_read": [("tia2", "tia2-p1")],
    "tia_toc": [("tia2", "tia2-root"), ("tia2", "tia2-ch1"), ("tia2", "tia2-p1")],
    "iox_search": [("iox1", "iox1-p1")],
    "iox_list": [("iox2", ""), ("iox1", "")],
    "iox_read": [("iox1", "iox1-p1")],
    "iox_toc": [("iox1", ""), ("iox1", "iox1-p1"), ("iox1", "iox1-p1a"), ("iox1", "iox1-p2")],
}


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_reference_output_budgets(catalog, reference_cases, reference_format):
    recorded = json.loads((FIXTURES / "reference_outputs.json").read_text(encoding="utf-8"))
    for case, (tool_name, kwargs) in reference_cases.items():
        baseline = recorded[case]
        actual = getattr(tools, tool_name)(catalog, **kwargs, reference_format=reference_format)
        assert len(actual) <= baseline["max_chars"][reference_format], (case, reference_format, len(actual))
        addresses = _addresses(actual)
        assert len(addresses) == len(EXPECTED_IDENTITIES[case]), case
        host = TIA_HOST if case.startswith("tia_") else IOX_HOST
        identities = []
        for address in addresses:
            target = catalog.resolve(address)
            assert target.host == host
            content_id = target.content_id or ""
            if case.endswith("_toc") and not content_id:
                content_id = catalog.toc(host, target.map_id).content_id
            identities.append((target.map_id, content_id))
        assert identities == EXPECTED_IDENTITIES[case], case
        # Keep every title, metadata field, excerpt and body byte from the golden output.
        expected_content = baseline["output"]
        for address in _addresses(expected_content):
            expected_content = expected_content.replace(address, "<reference>", 1)
        for address in addresses:
            actual = actual.replace(address, "<reference>", 1)
        assert actual == expected_content, case


def test_search_fixture_identity_is_configurable():
    topic = make_hit(map_id="iox1", content_id="iox1-p1")["entries"][0]["topic"]
    assert (topic["mapId"], topic["contentId"]) == ("iox1", "iox1-p1")
    assert "contentId" not in make_hit(content_id=None)["entries"][0]["topic"]
    assert "mapId" not in make_hit(map_id=None)["entries"][0]["topic"]


def test_content_calls_are_recorded(fake_tia):
    fake_tia.get_content("tia2", "tia2-p1")
    assert fake_tia.get_content_calls == [("tia2", "tia2-p1")]


def test_missing_content_calls_are_recorded(fake_tia):
    with pytest.raises(KeyError):
        fake_tia.get_content("tia2", "missing")
    assert fake_tia.get_content_calls == [("tia2", "missing")]


def test_legacy_output_baselines(catalog, reference_cases):
    recorded = json.loads((FIXTURES / "reference_outputs.json").read_text(encoding="utf-8"))
    assert set(recorded) == set(reference_cases)
    assert len(reference_cases) == 8
    for case, (tool_name, kwargs) in reference_cases.items():
        actual = getattr(tools, tool_name)(catalog, **kwargs, reference_format="url")
        assert actual == recorded[case]["output"], case
        assert len(actual) == recorded[case]["chars"], case


@pytest.mark.parametrize("reference_format", ["compact", "url"])
@pytest.mark.parametrize("prefix,host", [("tia", TIA_HOST), ("iox", IOX_HOST)])
def test_reference_case_addresses_roundtrip(catalog, reference_cases, reference_format, prefix, host):
    for case, (tool_name, kwargs) in reference_cases.items():
        if not case.startswith(prefix + "_"):
            continue
        output = getattr(tools, tool_name)(catalog, **kwargs, reference_format=reference_format)
        addresses = _addresses(output)
        assert addresses, case
        for address in addresses:
            target = catalog.resolve(address)
            assert target.host == host
            assert address.startswith(prefix + ":" if reference_format == "compact" else f"https://{host}/r/")
            publication = catalog.maps(host)[target.map_id]
            page = tools.read_page(catalog, address, reference_format=reference_format)
            assert f"> Publication: {publication.title} ({publication.version}) [{publication.locale}]" in page
            assert page.split("\n\n", 1)[1].strip()
            source = catalog.resolve(_addresses(page)[0])
            root = catalog.toc(host, target.map_id)
            expected_content = target.content_id or root.content_id or root.children[0].content_id
            expected_html = catalog.client(host).contents[(target.map_id, expected_content)]
            expected_text = BeautifulSoup(expected_html, "html.parser").get_text("\n").splitlines()
            assert all(text in page.split("\n\n", 1)[1] for text in expected_text if text.strip())
            source_content = source.content_id or root.content_id or root.children[0].content_id
            assert (source.host, source.map_id, source_content) == (host, target.map_id, expected_content)
            toc = tools.get_toc(catalog, address, reference_format=reference_format)
            first = catalog.resolve(_addresses(toc)[0])
            assert (first.host, first.map_id) == (host, target.map_id)
            assert (first.content_id or root.content_id or None) == (target.content_id or root.content_id or None)


def test_long_path_toc_baseline(catalog, long_reference_toc):
    url, expected_ids = long_reference_toc
    output = tools.get_toc(catalog, url, depth=1, reference_format="url")
    lines = output.splitlines()
    assert len(lines) == 301
    assert len(output) == 77868
    resolved_ids = []
    for index, line in enumerate(lines):
        address = line.split(" — ", 1)[1]
        if index:
            assert len(urlsplit(address).path) >= 160
        target = catalog.resolve(address)
        assert (target.host, target.map_id) == (TIA_HOST, "long-reference")
        resolved_ids.append(target.content_id or catalog.toc(target.host, target.map_id).content_id)
    assert resolved_ids == expected_ids


def test_long_toc_compact_is_smaller(catalog, long_reference_toc):
    url, expected_ids = long_reference_toc
    compact = tools.get_toc(catalog, url, depth=1)
    url_output = tools.get_toc(catalog, url, depth=1, reference_format="url")
    assert len(compact) < len(url_output)
    addressed = []
    for output in (compact, url_output):
        assert len(output.splitlines()) == 301
        identities = set()
        for address in _addresses(output):
            target = catalog.resolve(address)
            assert (target.host, target.map_id) == (TIA_HOST, "long-reference")
            identities.add(target.content_id or catalog.toc(target.host, target.map_id).content_id)
        addressed.append(identities)
    assert addressed[0] == addressed[1] == set(expected_ids)
    assert [line.split(" — ")[0] for line in compact.splitlines()] == [
        line.split(" — ")[0] for line in url_output.splitlines()
    ]


@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_reference_toc_preserves_500_line_cap(catalog, fake_tia, reference_format):
    pretty = "en-us/v21/big"
    fake_tia.maps.append(make_map("big", "Big", pretty=pretty))
    fake_tia.pages["big"] = make_toc("big-root", "Big", f"/r/{pretty}", [
        make_node(f"bt{i}", f"big-p{i}", f"Topic {i}", f"/r/{pretty}/t{i}") for i in range(600)
    ])
    output = tools.get_toc(catalog, "tia:big", depth=1, reference_format=reference_format)
    addresses = _addresses(output)
    assert len(addresses) == 500
    assert len(output.splitlines()) == 501
    assert output.splitlines()[-1] == "… truncated at 500 lines — use a deeper reference or a smaller depth."
    identities = []
    for address in addresses:
        target = catalog.resolve(address)
        assert (target.host, target.map_id) == (TIA_HOST, "big")
        identities.append(target.content_id or catalog.toc(target.host, target.map_id).content_id)
    assert identities == ["big-root"] + [f"big-p{i}" for i in range(499)]
