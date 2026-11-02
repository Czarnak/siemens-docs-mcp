from urllib.parse import quote

import pytest

from siemens_docs_mcp.catalog import (
    Catalog,
    CatalogError,
    MapInfo,
    Resolved,
    validate_reference_format,
)
from siemens_docs_mcp.toc import find_path, parse_toc
from tests.conftest import (
    IOX_HOST,
    SHARED_PRETTY,
    TIA_HOST,
    FakeClient,
    make_map,
    make_node,
    make_toc,
)

TIA_DOC = f"https://{TIA_HOST}/r/en-us/v21/doc"


def test_compact_reference_contract(catalog, fake_tia, fake_iox):
    assert catalog.resolve(" TIA:tia2/tia2-p1 ") == Resolved(TIA_HOST, "tia2", "tia2-p1")
    assert catalog.resolve("iox:iox1").content_id is None
    assert catalog.compact_ref(Resolved(TIA_HOST, "Ab~.-_1", "Cd2")) == "tia:Ab~.-_1/Cd2"
    assert catalog.id_url(Resolved(IOX_HOST, "iox1", None)) == f"https://{IOX_HOST}/r/iox1"
    assert catalog.resolve("tia:tia2/arbitrary-topic") == Resolved(TIA_HOST, "tia2", "arbitrary-topic")
    assert fake_tia.get_pages_calls == fake_iox.get_pages_calls == []


@pytest.mark.parametrize("value", [
    "tia:", "tia:/c", "tia:m/", "tia:m/c/x", "tia:m//c", "tia:../c", "tia:m/.",
    "tia:m/%2F", "tia:m?x=1", "tia:m/c#h", "tia:ti a2/c", "tia:tia2/c d",
    "tia :tia2/c", "unknown:tia2/c", "evil.example:tia2/c", "tia:./c", "tia:m/..",
    "tia:m%2Fc", "tia:m/c?x=1", "tia:m#h", "tia:m\nc", "tia:m:c", "tia:m\\c",
])
def test_compact_syntax_rejected_before_fetch(catalog, fake_tia, fake_iox, value):
    def calls():
        return [
            (client.list_maps_calls, list(client.get_pages_calls),
             list(client.get_content_calls), list(client.search_calls))
            for client in (fake_tia, fake_iox)
        ]

    before = calls()
    with pytest.raises(CatalogError):
        catalog.resolve(value)
    assert calls() == before


@pytest.mark.parametrize("map_id, content_id", [
    ("Ab~.-_1", "Cd2"), ("门户", "żółć_2"), ("m", None),
])
def test_compact_identifier_grammar(catalog, fake_tia, map_id, content_id):
    fake_tia.maps.append(make_map(map_id, "Grammar"))
    suffix = "" if content_id is None else f"/{content_id}"
    target = Resolved(TIA_HOST, map_id, content_id)
    assert catalog.resolve(f"tia:{map_id}{suffix}") == target
    assert catalog.compact_ref(target) == f"tia:{map_id}{suffix}"
    assert fake_tia.get_pages_calls == []


def test_compact_unknown_publication_has_useful_error(catalog):
    with pytest.raises(CatalogError, match="search_docs.*list_publications"):
        catalog.resolve("tia:missing/topic")


def test_protocol_relative_reader_url_is_preserved(catalog):
    assert catalog.resolve("//docs.tia.siemens.cloud/r/tia2/tia2-p1") == Resolved(
        TIA_HOST, "tia2", "tia2-p1",
    )


def test_prefix_identity_survives_restart_and_host_order(fake_tia, fake_iox):
    for client in (fake_tia, fake_iox):
        client.maps.append(make_map("same-map", "Same IDs"))
    clients = {TIA_HOST: fake_tia, IOX_HOST: fake_iox}
    for hosts in ([TIA_HOST, IOX_HOST], [IOX_HOST, TIA_HOST]):
        fresh = Catalog(hosts, lambda host: clients[host])
        assert fresh.resolve("tia:same-map/same-topic") == Resolved(TIA_HOST, "same-map", "same-topic")
        assert fresh.resolve("iox:same-map/same-topic") == Resolved(IOX_HOST, "same-map", "same-topic")
    assert fake_tia.get_pages_calls == fake_iox.get_pages_calls == []


@pytest.mark.parametrize("host, prefix", [
    (TIA_HOST, "tia"), (IOX_HOST, "iox"), ("docs.example.com", "docs.example.com"),
])
def test_literal_host_roundtrip(host, prefix):
    client = FakeClient(host, [make_map("Ab1", "Literal host")])
    fresh = Catalog([host], lambda host: client)
    target = Resolved(host, "Ab1", "Cd2")
    assert fresh.resolve(f"{host.upper()}:Ab1/Cd2") == target
    assert fresh.compact_ref(target) == f"{prefix}:Ab1/Cd2"
    assert fresh.resolve(fresh.compact_ref(target)) == target


def test_compact_spelling_does_not_fetch(catalog, monkeypatch):
    def unexpected(*args):
        raise AssertionError("Spelling a known target must not fetch")

    monkeypatch.setattr(catalog, "_factory", unexpected)
    monkeypatch.setattr(catalog, "maps", unexpected)
    monkeypatch.setattr(catalog, "toc", unexpected)
    assert catalog.compact_ref(Resolved(TIA_HOST.upper(), "Ab~.-_1", "Cd2")) == "tia:Ab~.-_1/Cd2"
    assert catalog.compact_ref(Resolved(IOX_HOST, "iox1", None)) == "iox:iox1"
    assert catalog.id_url(Resolved(TIA_HOST.upper(), "legacy/map", "legacy topic")) == (
        f"https://{TIA_HOST}/r/legacy/map/legacy topic"
    )
    assert catalog.fallback_reader_url(f" https://{TIA_HOST}/r/pretty/path ") == (
        f"https://{TIA_HOST}/r/pretty/path"
    )


@pytest.mark.parametrize("target", [
    Resolved("evil.example", "m", "c"), Resolved(TIA_HOST, "", "c"),
    Resolved(TIA_HOST, "..", "c"), Resolved(TIA_HOST, "m/c", None),
    Resolved(TIA_HOST, "m", ""), Resolved(TIA_HOST, "m", "."),
    Resolved(TIA_HOST, "m", "%2F"), Resolved(TIA_HOST, "m", "c d"),
])
def test_compact_spelling_rejects_invalid_target(catalog, target):
    with pytest.raises(CatalogError):
        catalog.compact_ref(target)


def test_id_url_rejects_unknown_host(catalog):
    with pytest.raises(CatalogError):
        catalog.id_url(Resolved("evil.example", "m", "c"))


@pytest.mark.parametrize("value, expected", [
    (f" https://{TIA_HOST}/r/en-us/v21/doc ", f"https://{TIA_HOST}/r/en-us/v21/doc"),
    (f"https://{IOX_HOST}/r/iox1?x=1#h", f"https://{IOX_HOST}/r/iox1?x=1#h"),
    (f"https://{TIA_HOST.upper()}/r/m", f"https://{TIA_HOST.upper()}/r/m"),
    (None, None), (123, None), ({}, None), ("", None),
    ("https://evil.example/r/m", None), (f"https://{TIA_HOST}/r/", None),
    (f"https://{TIA_HOST}/r", None), (f"https://{TIA_HOST}/other", None),
    (f"https://user@{TIA_HOST}/r/m", None), (f"https://user:pass@{TIA_HOST}/r/m", None),
    (f"http://{TIA_HOST}/r/m", None), (f"ftp://{TIA_HOST}/r/m", None),
    (f"//{TIA_HOST}/r/m", None), ("https://[broken/r/m", None),
])
def test_upstream_url_fallback(catalog, fake_tia, fake_iox, value, expected):
    assert catalog.fallback_reader_url(value) == expected
    for client in (fake_tia, fake_iox):
        assert client.list_maps_calls == 0
        assert client.get_pages_calls == client.get_content_calls == client.search_calls == []


@pytest.mark.parametrize("value", ["compact", "url"])
def test_validate_reference_format_accepts_exact_values(value):
    assert validate_reference_format(value) == value


@pytest.mark.parametrize("value", ["URL", "Compact", " compact ", "", "json", None])
def test_validate_reference_format_rejects_other_values(value):
    with pytest.raises(ValueError, match="compact.*url"):
        validate_reference_format(value)


def test_maps_parsed_from_metadata(catalog):
    tia = catalog.maps(TIA_HOST)["tia2"]
    assert tia == MapInfo(
        id="tia2", title="STEP 7 Basic", locale="en-US", product="STEP 7", version="V21",
        version_key="tia:SoftwareVersionFilter", pretty_url="en-us/v21/doc",
        cluster_id="cluster-tia2", last_publication="2026-01-01",
    )
    iox = catalog.maps(IOX_HOST)["iox1"]
    assert (iox.version, iox.version_key) == ("6.1", "SoftwareVersion")


def test_maps_missing_metadata_is_empty_string(fake_tia):
    fake_tia.maps = [{"id": "x", "title": "T", "metadata": [{"key": "Product", "values": []}]}]
    info = Catalog([TIA_HOST], lambda h: fake_tia).maps(TIA_HOST)["x"]
    assert (info.product, info.version, info.version_key, info.locale) == ("", "", "", "")


def test_maps_cached_until_ttl(catalog_with_clock, fake_tia):
    cat = catalog_with_clock
    cat.maps(TIA_HOST)
    cat.maps(TIA_HOST)
    assert fake_tia.list_maps_calls == 1
    cat.clock_value += 86401
    cat.maps(TIA_HOST)
    assert fake_tia.list_maps_calls == 2


def test_toc_cached_until_ttl(catalog_with_clock, fake_tia):
    cat = catalog_with_clock
    cat.toc(TIA_HOST, "tia2")
    cat.toc(TIA_HOST, "tia2")
    assert fake_tia.get_pages_calls == ["tia2"]
    cat.clock_value += 86401
    cat.toc(TIA_HOST, "tia2")
    assert fake_tia.get_pages_calls == ["tia2", "tia2"]


def test_unknown_host_rejected(catalog):
    with pytest.raises(CatalogError) as e:
        catalog.client("evil.example")
    assert TIA_HOST in str(e.value) and IOX_HOST in str(e.value)


def test_client_lowercases_and_reuses(catalog, fake_tia):
    assert catalog.client(TIA_HOST.upper()) is fake_tia
    assert catalog.client(TIA_HOST) is fake_tia


def test_resolve_short_map_url(catalog):
    assert catalog.resolve(f"https://{TIA_HOST}/r/tia2") == Resolved(TIA_HOST, "tia2", None)


def test_resolve_short_topic_url(catalog, fake_tia):
    r = catalog.resolve(f"https://{TIA_HOST}/r/tia2/whatever")
    assert r == Resolved(TIA_HOST, "tia2", "whatever")
    assert fake_tia.get_pages_calls == []  # no TOC load


def test_resolve_pretty_map_url(catalog):
    assert catalog.resolve(TIA_DOC) == Resolved(TIA_HOST, "tia2", None)


def test_resolve_pretty_topic_url(catalog):
    r = catalog.resolve(f"{TIA_DOC}/chapter-1/page-1")
    assert r == Resolved(TIA_HOST, "tia2", "tia2-p1")


def test_resolve_longest_prefix_wins(catalog, fake_tia):
    assert catalog.resolve(f"{TIA_DOC}-extra") == Resolved(TIA_HOST, "tia3", None)
    fake_tia.pages["tia3"] = make_toc(
        "tia3-root", "Extra", "/r/en-us/v21/doc-extra",
        [make_node("e1", "tia3-p1", "P", "/r/en-us/v21/doc-extra/p")],
    )
    assert catalog.resolve(f"{TIA_DOC}-extra/p") == Resolved(TIA_HOST, "tia3", "tia3-p1")


@pytest.mark.parametrize(
    "url",
    [
        f"{TIA_DOC}/chapter-1/page-1?q=1",
        f"{TIA_DOC}/chapter-1/page-1#frag",
        f"{TIA_DOC}/chapter-1/page-1/",
        f"http://{TIA_HOST}/r/en-us/v21/doc/chapter-1/page-1",
        f"https://{TIA_HOST.upper()}/r/en-us/v21/doc/chapter-1/page-1",
    ],
)
def test_resolve_tolerates_url_noise(catalog, url):
    assert catalog.resolve(url) == Resolved(TIA_HOST, "tia2", "tia2-p1")


@pytest.mark.parametrize("path", ["/r/nope/nothing", "/other", "/r/en-us/v21/doc/missing-page"])
def test_resolve_unknown_path(catalog, path):
    with pytest.raises(CatalogError) as e:
        catalog.resolve(f"https://{TIA_HOST}{path}")
    assert "search_docs" in str(e.value) and "list_publications" in str(e.value)


def test_resolve_shared_pretty_url_walks_all_candidates(catalog, shared_pretty):
    base = f"https://{TIA_HOST}/r/{SHARED_PRETTY}"
    assert catalog.resolve(f"{base}/b-topic") == Resolved(TIA_HOST, "tia7", "tia7-p1")
    assert catalog.resolve(f"{base}/a-topic") == Resolved(TIA_HOST, "tia6", "tia6-p1")
    assert catalog.resolve(base) == Resolved(TIA_HOST, "tia6", None)


def test_resolve_falls_back_to_shorter_prefix(catalog, fake_tia):
    """A longer-prefix map whose TOC lacks the topic must not hide the shorter-prefix map that has it."""
    fake_tia.maps.append(make_map("tia9", "Chapter Map", pretty="en-us/v21/doc/chapter-1"))
    fake_tia.pages["tia9"] = make_toc("tia9-root", "Chapter Map", "/r/en-us/v21/doc/chapter-1")
    assert catalog.resolve(f"{TIA_DOC}/chapter-1/page-1") == Resolved(TIA_HOST, "tia2", "tia2-p1")


def test_reader_url_shared_pretty_uses_id_form(catalog, shared_pretty):
    for map_id in ("tia6", "tia7"):
        root = catalog.toc(TIA_HOST, map_id)
        assert catalog.reader_url(TIA_HOST, map_id, root) == f"https://{TIA_HOST}/r/{map_id}/{map_id}-root"
        child = root.children[0]
        assert catalog.reader_url(TIA_HOST, map_id, child) == f"https://{TIA_HOST}/r/{map_id}/{map_id}-p1"
        assert catalog.map_url(TIA_HOST, map_id) == f"https://{TIA_HOST}/r/{map_id}"
    assert catalog.map_url(TIA_HOST.upper(), "tia2") == f"https://{TIA_HOST}/r/en-us/v21/doc"


def test_map_url_without_pretty_uses_id(catalog, fake_tia):
    fake_tia.maps.append(make_map("tia8", "No Pretty", pretty=""))
    assert catalog.map_url(TIA_HOST, "tia8") == f"https://{TIA_HOST}/r/tia8"


def test_resolve_percent_encoded_unicode(catalog, fake_tia):
    fake_tia.maps.append(make_map("tia-zh", "门户", locale="zh-CN", pretty="zh-cn/v21/门户"))
    url = f"https://{TIA_HOST}/r/zh-cn/v21/{quote('门户')}"
    assert catalog.resolve(url) == Resolved(TIA_HOST, "tia-zh", None)


@pytest.mark.parametrize("content", ["..", ".", "..%2F..%2Fx", "x%3Fy", "a b"])
def test_resolve_rejects_unsafe_content_id(catalog, content):
    with pytest.raises(CatalogError, match="Could not resolve"):
        catalog.resolve(f"https://{TIA_HOST}/r/tia2/{content}")


def test_resolve_unknown_host(catalog):
    with pytest.raises(CatalogError, match=IOX_HOST):
        catalog.resolve("https://evil.example/r/tia2")


def test_canonical_product_case_insensitive(catalog):
    assert catalog.canonical(TIA_HOST, "product", "step 7") == "STEP 7"


def test_canonical_unknown_suggests_close(catalog):
    with pytest.raises(CatalogError, match="Close matches: .*STEP 7"):
        catalog.canonical(TIA_HOST, "product", "STEP7")


def test_canonical_unknown_lists_known_when_no_close(catalog):
    with pytest.raises(CatalogError, match="Valid values include: .*TIA Portal Openness"):
        catalog.canonical(TIA_HOST, "product", "zzzzzz")


def test_canonical_locale_case_insensitive(catalog):
    assert catalog.canonical(TIA_HOST, "locale", "en-us") == "en-US"


def test_canonical_version_uses_source_key(catalog):
    assert catalog.canonical_version(TIA_HOST, "v21") == ("tia:SoftwareVersionFilter", "V21")
    assert catalog.canonical_version(IOX_HOST, "6.1") == ("SoftwareVersion", "6.1")


def test_canonical_version_falls_back_to_second_key(fake_tia):
    # one map carries both keys; the filter key wins, SoftwareVersion still searchable
    both = make_map("b", "Both", version="V21")
    both["metadata"].append({"key": "SoftwareVersion", "values": ["21.0.1"]})
    fake_tia.maps = [both]
    cat = Catalog([TIA_HOST], lambda h: fake_tia)
    assert cat.canonical_version(TIA_HOST, "21.0.1") == ("SoftwareVersion", "21.0.1")
    assert cat.canonical_version(TIA_HOST, "v21") == ("tia:SoftwareVersionFilter", "V21")
    assert [m.id for m in cat.filter(TIA_HOST, version="21.0.1")] == ["b"]
    assert [m.id for m in cat.filter(TIA_HOST, version="v21")] == ["b"]


def test_filter_excludes_map_with_value_under_other_key(fake_tia):
    only_sw = make_map("s", "OnlySw", version="V21", version_key="SoftwareVersion")
    fake_tia.maps = [make_map("f", "Filt", version="V21"), only_sw]
    cat = Catalog([TIA_HOST], lambda h: fake_tia)
    assert [m.id for m in cat.filter(TIA_HOST, version="v21")] == ["f"]


def test_canonical_version_unknown(catalog):
    with pytest.raises(CatalogError, match="V21"):
        catalog.canonical_version(TIA_HOST, "V2")


def test_filter_combines_and_sorts(catalog):
    got = catalog.filter(TIA_HOST, product="step 7", version="v21", locale="en-us", title_contains="basic")
    assert [m.id for m in got] == ["tia2", "tia3"]
    assert [m.title for m in got] == sorted(m.title for m in got)
    assert [m.id for m in catalog.filter(TIA_HOST, version="v20")] == ["tia4"]
    assert len(catalog.filter(TIA_HOST)) == 5


def test_reader_url(catalog):
    root = catalog.toc(TIA_HOST, "tia2")
    assert catalog.reader_url(TIA_HOST, "tia2", root) == f"https://{TIA_HOST}/r/en-us/v21/doc"
    root.pretty_url = ""
    assert catalog.reader_url(TIA_HOST, "tia2", root) == f"https://{TIA_HOST}/r/tia2/tia2-root"


def test_find_path_returns_root_to_node():
    root = parse_toc(make_toc(
        "r", "R", "/r/x",
        [make_node("a", "ca", "A", "/r/x/a", [make_node("b", "cb", "B", "/r/x/a/b")])],
    ))
    assert [p.content_id for p in find_path(root, "cb")] == ["r", "ca", "cb"]
    assert [p.content_id for p in find_path(root, "r")] == ["r"]
    assert find_path(root, "zzz") is None
    # In-page links use the tocId (/r/{map}/{tocId}), not the contentId
    assert [p.content_id for p in find_path(root, "b")] == ["r", "ca", "cb"]


def test_concurrent_cold_loads_happen_once(fake_tia, fake_iox):
    import threading
    import time

    created: list[str] = []
    clients = {TIA_HOST: fake_tia, IOX_HOST: fake_iox}

    def factory(host):
        time.sleep(0.05)  # widen the race window
        created.append(host)
        return clients[host]

    orig = fake_tia.list_maps

    def slow_list_maps():
        time.sleep(0.05)
        return orig()

    fake_tia.list_maps = slow_list_maps
    cat = Catalog([TIA_HOST, IOX_HOST], factory)
    barrier = threading.Barrier(8)

    def work():
        barrier.wait()
        cat.client(TIA_HOST)
        cat.maps(TIA_HOST)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert created == [TIA_HOST]
    assert fake_tia.list_maps_calls == 1
