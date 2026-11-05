"""Recorded output of the converter before the block refactor; any change here is an exporter regression."""
import json
from pathlib import Path

import pytest

from siemens_docs_mcp.converter import html_to_markdown

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "converter_golden.json").read_text("utf-8"))


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_converter_matches_recorded_output(case):
    entry = GOLDEN[case]
    assert html_to_markdown(entry["html"], entry["title"]) == entry["markdown"]
