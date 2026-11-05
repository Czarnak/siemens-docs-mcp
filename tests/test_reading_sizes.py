"""Character ceilings for read_page modes on the Openness-like fixture (measured +5%, see evidence doc)."""
import math

import pytest

from siemens_docs_mcp.tools import read_page
from tests.test_tools import OPENNESS_HTML

# Measured on 2026-11-05 with tests/fixtures/html/openness_page.html as tia2-p1.
MEASURED = {
    "full_compact": 1039,
    "full_url": 1115,
    "outline": 405,
    "section": 536,
    "code": 536,
    "code_section": 536,
}
CALLS = {
    "full_compact": {},
    "full_url": {"reference_format": "url"},
    "outline": {"mode": "outline"},
    "section": {"section": "Program code"},
    "code": {"mode": "code"},
    "code_section": {"mode": "code", "section": "Program code"},
}


@pytest.fixture
def sizes(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = OPENNESS_HTML
    return {name: len(read_page(catalog, "tia:tia2/tia2-p1", **kwargs)) for name, kwargs in CALLS.items()}


@pytest.mark.parametrize("name", sorted(CALLS))
def test_reading_output_ceiling(sizes, name):
    assert sizes[name] <= math.ceil(MEASURED[name] * 1.05), (name, sizes[name])


def test_reading_modes_are_smaller(sizes):
    assert sizes["full_compact"] < sizes["full_url"]
    for name in ("outline", "section", "code", "code_section"):
        assert sizes[name] < sizes["full_compact"], name
