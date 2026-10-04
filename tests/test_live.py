"""Live smoke tests against the real hosts. Run with: pytest -m live"""
import pytest

from scraper import tools
from scraper.catalog import Catalog
from scraper.client import FluidtopicsClient
from server import DEFAULT_HOSTS, DEFAULT_LOCALE, DEFAULT_MIN_INTERVAL

QUERIES = {"docs.tia.siemens.cloud": "export block", "docs.industrial-operations-x.siemens.cloud": "OPC UA"}


@pytest.mark.live
@pytest.mark.parametrize("host", DEFAULT_HOSTS)
def test_search_read_toc_roundtrip(host):
    cat = Catalog(DEFAULT_HOSTS, lambda h: FluidtopicsClient(h, DEFAULT_MIN_INTERVAL))
    hits = tools.search_docs(cat, QUERIES[host], host, DEFAULT_LOCALE)
    urls = [ln.strip() for ln in hits.splitlines() if ln.strip().startswith("https://")]
    assert urls, hits
    assert "> Source:" in tools.read_page(cat, urls[0])
    assert tools.get_toc(cat, urls[0], depth=1).strip()
