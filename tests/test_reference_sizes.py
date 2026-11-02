"""Characterization and measurements of tool-generated documentation references."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from siemens_docs_mcp import tools
from tests.conftest import TIA_HOST, make_hit

FIXTURES = Path(__file__).with_name("fixtures")


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
        actual = getattr(tools, tool_name)(catalog, **kwargs)
        assert actual == recorded[case]["output"], case
        assert len(actual) == recorded[case]["chars"], case


def test_reference_case_addresses_roundtrip(catalog, reference_cases):
    for tool_name, kwargs in reference_cases.values():
        output = getattr(tools, tool_name)(catalog, **kwargs)
        for line in output.splitlines():
            if "https://" not in line:
                continue
            url = "https://" + line.split("https://", 1)[1]
            assert "> Source:" in tools.read_page(catalog, url)
            assert tools.get_toc(catalog, url).strip()


def test_long_path_toc_baseline(catalog, long_reference_toc):
    url, expected_ids = long_reference_toc
    output = tools.get_toc(catalog, url, depth=1)
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
