"""Live discovery and fixed-target measurements. Run with: pytest -m live -s"""
import contextlib
import hashlib
import json
import re
from pathlib import Path

import pytest

from siemens_docs_mcp import tools
from siemens_docs_mcp.catalog import Catalog, Resolved
from siemens_docs_mcp.client import FluidtopicsClient
from siemens_docs_mcp.server import DEFAULT_HOSTS, DEFAULT_LOCALE, DEFAULT_MIN_INTERVAL
from siemens_docs_mcp.toc import find_path, iter_pages

QUERIES = {"docs.tia.siemens.cloud": "TIA Portal Openness", "docs.industrial-operations-x.siemens.cloud": "OPC UA"}
MANIFEST = Path(__file__).with_name("fixtures") / "reference_live_targets.json"
BASELINE_IDENTITIES = {
    "docs.tia.siemens.cloud": {
        "map": "Rc0LxW522mLHDCX_sejL~A", "topic": "HZ7f9jFVFVga52ac6WpeDA",
        "search_docs": "8f03d02f6037e83dedb93002085f2f9b63109837d549e80af321ecd01db65377",
        "get_toc": "8bd9ab838c4a6d3f227e8c5fd5a97ae30f961ac619c24b4357668a36dfa9e4a2",
        "read_page": "9f876c2816f0d39145b19472e4728bc3b76c9e36df045ec3975f0221230434e7",
        "list_publications": "8f901a524a58af3135b192a7484345ee2eea12143890da9cd68c0cea9092ce85",
    },
    "docs.industrial-operations-x.siemens.cloud": {
        "map": "Li4yDQJF3SPIB5lKtTioBA", "topic": "DtlGcMzx28Bz2Y_H4~x5TA",
        "search_docs": "1819ac7fa4107d41314e7120668c3bba7ab4973322a6b2b3e1584c7a5b545b71",
        "get_toc": "80ac1c90cebd40be45dfb69763b56e42259915c0689a7f1b88df9d98606dc9b0",
        "read_page": "7c27cc5669e41f8849356a85743a182ff0723ce4bf2573b0898e1b5a307de21c",
        "list_publications": "7cb079950d987e194d98a64368199a8621e5e593cbc170f809d4fe4121ea3ff6",
    },
}


def _addresses(output):
    """Tool address fields only; page-body links are outside the reference contract."""
    lines = output.splitlines()
    if output.startswith("> Publication:"):
        candidates = [line.removeprefix("> Source: ") for line in output.split("\n\n", 1)[0].splitlines()
                      if line.startswith("> Source: ")]
    elif output.startswith(("Found ", "Showing ")):
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
    assert _addresses(
        'Showing 1 results for "q" in "Ch" — Pub (V21); checked 300 of 900 publication results, more may exist:\n'
        "1. **Hit**\n   Breadcrumb\n   Excerpt\n   tia:Map/Topic"
    ) == ["tia:Map/Topic"]
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
    baseline = BASELINE_IDENTITIES[host]
    calls = [
        ("search_docs", {"query": target["query"], "host": host, "locale": DEFAULT_LOCALE}),
        ("get_toc", {"url": target["publication_url"], "depth": 1}),
        ("read_page", {"url": target["topic_url"]}),
        ("list_publications", {"host": host, "locale": DEFAULT_LOCALE}),
    ]
    with client:
        for index, (tool_name, kwargs) in enumerate(calls):
            if tool_name == "list_publications":
                publication = cat.resolve(target["publication_url"])
                assert publication.map_id == baseline["map"]
                kwargs["title_contains"] = cat.maps(host)[publication.map_id].title
            fingerprints = {}
            effective_nodes = {}
            for reference_format in ("url", "compact"):
                requests.clear()
                output = getattr(tools, tool_name)(cat, **kwargs, reference_format=reference_format)
                request_count = len(requests)
                assert output.strip()
                addresses = _addresses(output)
                identities = set()
                for address in addresses:
                    resolved = cat.resolve(address)
                    content_id = resolved.content_id or ""
                    # The baseline publication URL and compact root-topic reference address the same TOC row.
                    if tool_name == "get_toc" and content_id == cat.toc(host, resolved.map_id).content_id:
                        content_id = ""
                    identities.add((resolved.host, resolved.map_id, content_id))
                identities = sorted(identities)
                assert identities
                effective_nodes[reference_format] = sorted({
                    (h, map_id, content_id or cat.toc(h, map_id).content_id)
                    for h, map_id, content_id in identities
                }) if tool_name == "search_docs" else identities
                if tool_name == "read_page":
                    expected = cat.resolve(target["topic_url"])
                    assert (expected.map_id, expected.content_id) == (baseline["map"], baseline["topic"])
                    assert (host, baseline["map"], baseline["topic"]) in identities
                    assert "> Source:" in output
                elif tool_name in ("get_toc", "list_publications"):
                    assert (host, baseline["map"], "") in identities
                fingerprint = hashlib.sha256(json.dumps(
                    identities, separators=(",", ":"), ensure_ascii=True,
                ).encode()).hexdigest()
                fingerprints[reference_format] = fingerprint
                baseline_match = fingerprint == baseline[tool_name]
                print("MEASUREMENT " + json.dumps({
                    "host": host, "target": target, "tool": tool_name, "format": reference_format,
                    "chars": len(output), "identities": identities, "identity_sha256": fingerprint,
                    "baseline_identity_match": baseline_match, "raw_identity_difference_from_baseline": not baseline_match,
                    "compact_fallback_urls": [address for address in addresses if address.startswith("https://")]
                    if reference_format == "compact" else [],
                    "unavailable_references": output.count("(reference unavailable)"),
                    "http_attempts": request_count,
                    "conditions": "fresh catalog/client" if index == 0 and reference_format == "url"
                    else "same catalog/client; metadata/TOC caches may be warm",
                    "kwargs": kwargs, "min_interval": DEFAULT_MIN_INTERVAL,
                }))
                if tool_name != "search_docs":
                    assert baseline_match, f"Pinned {tool_name} identity drift on {host}"
            print("COMPARISON " + json.dumps({
                "host": host, "tool": tool_name,
                "paired_identity_match": fingerprints["compact"] == fingerprints["url"],
                "effective_node_match": effective_nodes["compact"] == effective_nodes["url"],
                "baseline_identity_match": all(value == baseline[tool_name] for value in fingerprints.values()),
            }))


def _found(output):
    match = re.match(r"Found (\d+) results", output)
    assert match, output[:300]
    return int(match.group(1))


@pytest.mark.live
@pytest.mark.parametrize("host", DEFAULT_HOSTS)
def test_scoped_search_stays_in_scope(host):
    """Publication scope is applied upstream (an ignored filter would not shrink the count); topic scope locally."""
    targets = json.loads(MANIFEST.read_text(encoding="utf-8"))["targets"]
    target = next((entry for entry in targets if entry["host"] == host), None)
    if target is None:
        pytest.skip(f"No pinned target for {host}")
    client = FluidtopicsClient(host, DEFAULT_MIN_INTERVAL)
    cat = Catalog([host], lambda h: client)
    with client:
        publication = cat.resolve(target["publication_url"])
        pub_ref = cat.compact_ref(Resolved(host, publication.map_id, None))
        unscoped = tools.search_docs(cat, target["query"], host, DEFAULT_LOCALE)
        scoped = tools.search_docs(cat, target["query"], None, None, limit=50, scope=pub_ref)
        addresses = _addresses(scoped)
        assert addresses, scoped[:300]
        assert {cat.resolve(a).map_id for a in addresses} == {publication.map_id}
        assert _found(scoped) < _found(unscoped)

        topic = cat.resolve(target["topic_url"])
        assert topic.map_id == publication.map_id
        chapter = find_path(cat.toc(host, publication.map_id), topic.content_id)[1]
        inside = {page.content_id for page in iter_pages(chapter)}
        chapter_ref = cat.compact_ref(Resolved(host, publication.map_id, chapter.content_id))
        in_chapter = tools.search_docs(cat, target["query"], None, None, scope=chapter_ref)
        chapter_addresses = _addresses(in_chapter)
        assert chapter_addresses, in_chapter[:300]
        assert all(cat.resolve(a).content_id in inside for a in chapter_addresses)
        print("SCOPED " + json.dumps({
            "host": host, "query": target["query"], "chapter": chapter.title,
            "unscoped_total": _found(unscoped), "publication_total": _found(scoped),
            "chapter_header": in_chapter.splitlines()[0],
            "chars": {"unscoped_10": len(unscoped), "chapter_10": len(in_chapter)},
        }, ensure_ascii=False))


READING_MANIFEST = Path(__file__).with_name("fixtures") / "reading_live_targets.json"


@pytest.mark.live
def test_reading_measurements():
    """Print read_page sizes for fixed pages, one catalog/client per host."""
    pages = json.loads(READING_MANIFEST.read_text(encoding="utf-8"))["pages"]
    clients = {host: FluidtopicsClient(host, DEFAULT_MIN_INTERVAL) for host in DEFAULT_HOSTS}
    cat = Catalog(list(DEFAULT_HOSTS), lambda h: clients[h])
    with contextlib.ExitStack() as stack:
        for client in clients.values():
            stack.enter_context(client)
        for page in pages:
            for reference_format in ("compact", "url"):
                output = tools.read_page(cat, page["url"], reference_format=reference_format)
                assert "> Source:" in output
                print("MEASUREMENT " + json.dumps({
                    "label": page["label"], "mode": "full", "format": reference_format, "chars": len(output),
                    "min_interval": DEFAULT_MIN_INTERVAL,
                }))
