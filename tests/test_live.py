"""Live discovery and fixed-target measurements. Run with: pytest -m live -s"""
import json
import re
from pathlib import Path

import pytest

from siemens_docs_mcp import tools
from siemens_docs_mcp.catalog import Catalog
from siemens_docs_mcp.client import FluidtopicsClient
from siemens_docs_mcp.server import DEFAULT_HOSTS, DEFAULT_LOCALE, DEFAULT_MIN_INTERVAL

QUERIES = {"docs.tia.siemens.cloud": "TIA Portal Openness", "docs.industrial-operations-x.siemens.cloud": "OPC UA"}
MANIFEST = Path(__file__).with_name("fixtures") / "reference_live_targets.json"


def _addresses(output):
    """Tool address fields only; page-body links are outside the reference contract."""
    lines = output.splitlines()
    if output.startswith("> Publication:"):
        candidates = [line.removeprefix("> Source: ") for line in output.split("\n\n", 1)[0].splitlines()
                      if line.startswith("> Source: ")]
    elif output.startswith("Found "):
        candidates = [line.strip() for line in lines[4::4]]
    else:
        candidates = [line.rsplit(" ", 1)[-1] for line in lines if line.lstrip().startswith("- ")]
    return [value for value in candidates if re.fullmatch(r"https://\S+|[\w.-]+:[\w~.-]+(?:/[\w~.-]+)?", value)]


def test_addresses_accept_both_formats_and_ignore_body_links():
    assert _addresses(
        "Found 2 results:\n1. **Hit**\n   Breadcrumb\n   Example tia:NotAnAddress\n   tia:Map/Topic\n"
        "2. **Hit**\n   Breadcrumb\n   Excerpt\n   https://example.com/r/m/t"
    ) == [
        "tia:Map/Topic", "https://example.com/r/m/t",
    ]
    assert _addresses("- Pub — Product V21 [en-US] iox:Map") == ["iox:Map"]
    assert _addresses("- Topic — docs.example.com:Map/Topic") == ["docs.example.com:Map/Topic"]
    assert _addresses(
        "> Publication: Pub\n> Path: Topic\n> Source: tia:Map/Topic\n\nhttps://example.com/r/body/link"
    ) == ["tia:Map/Topic"]


@pytest.mark.live
@pytest.mark.parametrize("host", DEFAULT_HOSTS)
def test_search_read_toc_roundtrip(host):
    client = FluidtopicsClient(host, DEFAULT_MIN_INTERVAL)
    cat = Catalog([host], lambda h: client)
    with client:
        hits = tools.search_docs(cat, QUERIES[host], host, DEFAULT_LOCALE)
        urls = _addresses(hits)
        assert urls, hits
        page = tools.read_page(cat, urls[0])
        assert "> Source:" in page
        assert tools.get_toc(cat, urls[0], depth=1).strip()
        target = cat.resolve(urls[0])
        info = cat.maps(host)[target.map_id]
        if host == "docs.tia.siemens.cloud":
            assert "openness" in (info.title + " " + info.product).lower(), page[:300]
        print("DISCOVERED " + json.dumps({
            "host": host, "query": QUERIES[host],
            "publication_url": cat.map_url(host, target.map_id), "topic_url": cat.id_url(target),
        }))


@pytest.mark.live
@pytest.mark.parametrize("host", DEFAULT_HOSTS)
def test_fixed_target_measurements(host, monkeypatch):
    targets = json.loads(MANIFEST.read_text(encoding="utf-8"))["targets"]
    target = next((entry for entry in targets if entry["host"] == host), None)
    if target is None:
        pytest.skip(f"No pinned baseline target for {host}; discovery gap recorded in evidence")
    client = FluidtopicsClient(host, DEFAULT_MIN_INTERVAL)
    send = client._send
    requests = []

    def record_send(method, path, **kwargs):
        requests.append((method, path))
        return send(method, path, **kwargs)

    monkeypatch.setattr(client, "_send", record_send)
    cat = Catalog([host], lambda h: client)
    calls = [
        ("search_docs", {"query": target["query"], "host": host, "locale": DEFAULT_LOCALE}),
        ("get_toc", {"url": target["publication_url"], "depth": 1}),
        ("read_page", {"url": target["topic_url"]}),
    ]
    with client:
        for index, (tool_name, kwargs) in enumerate(calls):
            requests.clear()
            output = getattr(tools, tool_name)(cat, **kwargs, reference_format="url")
            request_count = len(requests)
            assert output.strip()
            identities = sorted({(r.host, r.map_id, r.content_id or "")
                                 for url in _addresses(output) for r in [cat.resolve(url)]})
            assert identities
            if tool_name == "read_page":
                expected = cat.resolve(target["topic_url"])
                assert (expected.host, expected.map_id, expected.content_id) in identities
                assert "> Source:" in output
            elif tool_name == "get_toc":
                expected = cat.resolve(target["publication_url"])
                assert (expected.host, expected.map_id, "") in identities
            print("MEASUREMENT " + json.dumps({
                "host": host, "target": target, "tool": tool_name, "format": "url",
                "chars": len(output), "identities": identities, "http_attempts": request_count,
                "conditions": "fresh catalog/client" if index == 0 else "same catalog/client; metadata/TOC caches may be warm",
                "min_interval": DEFAULT_MIN_INTERVAL,
            }))
        info = cat.maps(host)[cat.resolve(target["publication_url"]).map_id]
        requests.clear()
        output = tools.list_publications(cat, host, DEFAULT_LOCALE, title_contains=info.title, reference_format="url")
        request_count = len(requests)
        identities = sorted({(r.host, r.map_id, r.content_id or "")
                             for url in _addresses(output) for r in [cat.resolve(url)]})
        assert (host, info.id, "") in identities
        print("MEASUREMENT " + json.dumps({
            "host": host, "target": target["publication_url"], "tool": "list_publications", "format": "url",
            "chars": len(output), "identities": identities, "http_attempts": request_count,
            "conditions": "same catalog/client; metadata warm; title_contains=" + info.title,
            "min_interval": DEFAULT_MIN_INTERVAL,
        }))
