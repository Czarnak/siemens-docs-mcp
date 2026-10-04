"""Shared fakes for catalog and tool tests. Extend these rather than defining new clients."""
from __future__ import annotations

import pytest

from scraper.catalog import Catalog

TIA_HOST = "docs.tia.siemens.cloud"
IOX_HOST = "docs.industrial-operations-x.siemens.cloud"


def make_map(
    id: str,
    title: str,
    locale: str = "en-US",
    product: str = "STEP 7",
    version: str = "V21",
    pretty: str = "en-us/v21/doc",
    version_key: str = "tia:SoftwareVersionFilter",
) -> dict:
    """Raw /api/khub/maps entry. Pass ``version_key=""`` or empty values to omit keys."""
    meta = [
        ("ft:locale", locale),
        ("Product", product),
        (version_key, version),
        ("ft:prettyUrl", pretty),
        ("ft:clusterId", f"cluster-{id}"),
        ("ft:lastPublication", "2026-01-01"),
    ]
    return {
        "id": id,
        "title": title,
        "metadata": [
            {"key": k, "values": [v] if v else []} for k, v in meta if k
        ],
    }


def make_node(toc_id: str, content_id: str, title: str, pretty: str, children: list[dict] | None = None) -> dict:
    return {
        "tocId": toc_id,
        "contentId": content_id,
        "title": title,
        "prettyUrl": pretty,
        "children": children or [],
    }


def make_toc(
    content_id: str = "root",
    title: str = "Doc",
    pretty: str = "/r/en-us/v21/doc",
    children: list[dict] | None = None,
) -> dict:
    """Raw /pages response: the root lists children under ``pageToc``, nodes under ``children``."""
    return {
        "paginatedToc": [
            {
                "tocId": f"toc-{content_id}",
                "contentId": content_id,
                "title": title,
                "prettyUrl": pretty,
                "pageToc": children or [],
            }
        ]
    }


class FakeClient:
    """Stands in for FluidtopicsClient; records calls for assertions."""

    def __init__(self, host: str, maps: list[dict] | None = None) -> None:
        self.host = host
        self.maps: list[dict] = maps or []
        self.pages: dict[str, dict] = {}
        self.contents: dict[tuple[str, str], str] = {}
        self.search_response: dict = {}
        self.search_calls: list[dict] = []
        self.list_maps_calls = 0
        self.get_pages_calls: list[str] = []

    def list_maps(self) -> list[dict]:
        self.list_maps_calls += 1
        return self.maps

    def get_pages(self, map_id: str) -> dict:
        self.get_pages_calls.append(map_id)
        return self.pages[map_id]

    def get_content(self, map_id: str, content_id: str) -> str:
        return self.contents[(map_id, content_id)]

    def search(self, query, locale, filters=None, page=1, per_page=10) -> dict:
        self.search_calls.append(
            {"query": query, "locale": locale, "filters": filters, "page": page, "per_page": per_page}
        )
        return self.search_response

    def close(self) -> None:
        pass


@pytest.fixture
def fake_tia() -> FakeClient:
    client = FakeClient(
        TIA_HOST,
        [
            make_map("tia1", "Openness API", product="TIA Portal Openness", pretty="en-us/v21/openness"),
            make_map("tia2", "STEP 7 Basic", pretty="en-us/v21/doc"),
            make_map("tia3", "STEP 7 Basic Extra", pretty="en-us/v21/doc-extra"),
            make_map("tia4", "STEP 7 Basic V20", version="V20", pretty="en-us/v20/doc"),
            make_map("tia5", "STEP 7 Deutsch", locale="de-DE", pretty="de-de/v21/doc"),
        ],
    )
    client.pages["tia2"] = make_toc(
        "tia2-root",
        "STEP 7 Basic",
        "/r/en-us/v21/doc",
        [
            make_node(
                "t-ch1",
                "tia2-ch1",
                "Chapter 1",
                "/r/en-us/v21/doc/chapter-1",
                [make_node("t-p1", "tia2-p1", "Page 1", "/r/en-us/v21/doc/chapter-1/page-1")],
            )
        ],
    )
    client.contents[("tia2", "tia2-p1")] = "<h1>Page 1</h1><p>Hello</p>"
    return client


SHARED_PRETTY = "en-us/v21/shared"


@pytest.fixture
def shared_pretty(fake_tia: FakeClient) -> FakeClient:
    """Adds tia6/tia7: two distinct maps sharing one ft:prettyUrl, each with its own TOC (live: TOOpenness)."""
    for map_id, title, topic in (("tia6", "Shared A", "a-topic"), ("tia7", "Shared B", "b-topic")):
        fake_tia.maps.append(make_map(map_id, title, pretty=SHARED_PRETTY))
        fake_tia.pages[map_id] = make_toc(
            f"{map_id}-root", title, f"/r/{SHARED_PRETTY}",
            [make_node(f"t-{map_id}", f"{map_id}-p1", topic.title(), f"/r/{SHARED_PRETTY}/{topic}")],
        )
    return fake_tia


@pytest.fixture
def fake_iox() -> FakeClient:
    client = FakeClient(
        IOX_HOST,
        [
            make_map(
                "iox1", "Edge Guide", product="Industrial Edge", version="6.1",
                version_key="SoftwareVersion", pretty="en-us/edge/guide",
            ),
            make_map(
                "iox2", "Edge Admin", product="Industrial Edge", version="6.0",
                version_key="SoftwareVersion", pretty="en-us/edge/admin",
            ),
        ],
    )
    # No root topic: each top-level section is its own paginatedToc entry.
    client.pages["iox1"] = {
        "paginatedToc": [
            make_node("i-s1", "iox1-p1", "Intro", "/r/en-us/edge/guide/intro",
                      [make_node("i-s1a", "iox1-p1a", "Intro A", "/r/en-us/edge/guide/intro/a")]),
            make_node("i-s2", "iox1-p2", "Setup", "/r/en-us/edge/guide/setup"),
        ]
    }
    client.contents[("iox1", "iox1-p1")] = "<h1>Intro</h1>"
    client.contents[("iox1", "iox1-p1a")] = "<h1>Intro A</h1>"
    return client


@pytest.fixture
def catalog(fake_tia: FakeClient, fake_iox: FakeClient) -> Catalog:
    clients = {TIA_HOST: fake_tia, IOX_HOST: fake_iox}
    return Catalog([TIA_HOST, IOX_HOST], lambda host: clients[host])


@pytest.fixture
def catalog_with_clock(fake_tia: FakeClient, fake_iox: FakeClient) -> Catalog:
    clients = {TIA_HOST: fake_tia, IOX_HOST: fake_iox}

    cat = Catalog([TIA_HOST, IOX_HOST], lambda host: clients[host], clock=lambda: cat.clock_value)
    cat.clock_value = 1000.0  # mutable fake clock; tests advance it
    return cat


def make_hit(
    title: str = "Hit",
    map_title: str = "STEP 7 Basic",
    breadcrumb: list[str] | None = None,
    excerpt: str = "<p>Some <b>text</b></p>",
    reader_url: str = "https://docs.tia.siemens.cloud/r/en-us/v21/doc/page",
    metadata: list[dict] | None = None,
) -> dict:
    """One search cluster whose first entry is a TOPIC."""
    return {
        "entries": [
            {
                "type": "TOPIC",
                "topic": {
                    "mapId": "tia2",
                    "contentId": "c1",
                    "title": title,
                    "mapTitle": map_title,
                    "breadcrumb": breadcrumb if breadcrumb is not None else ["Chapter 1", "Section"],
                    "htmlExcerpt": excerpt,
                    "readerUrl": reader_url,
                    "metadata": metadata if metadata is not None else [],
                },
            }
        ]
    }


def make_search_response(clusters: list[dict], total: int | None = None) -> dict:
    # Real API shape: totals live under "paging" (verified live 2026-10-04).
    total = len(clusters) if total is None else total
    return {"paging": {"currentPage": 1, "totalResultsCount": total}, "results": clusters}


def make_big_toc(n: int, content_id: str = "big-root") -> dict:
    """/pages response with ``n`` flat children under the root (n + 1 nodes)."""
    kids = [make_node(f"bt{i}", f"big-p{i}", f"Topic {i}", f"/r/big/t{i}") for i in range(n)]
    return make_toc(content_id, "Big", "/r/big", kids)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
