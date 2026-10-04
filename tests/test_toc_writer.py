"""Offline regression checks for TOC parsing and output paths."""
from pathlib import Path

from scraper.toc import iter_pages, parse_toc
from scraper.writer import resolve_output_paths

BASE = "/r/en-us/v21/doc"


def _node(title: str, url: str, children: list | None = None) -> dict:
    return {"tocId": url, "contentId": url, "title": title, "prettyUrl": BASE + url, "children": children or []}


def test_output_paths() -> None:
    root = _node("Doc", "")
    root["pageToc"] = [
        _node("Export/import", "/export/import", [_node("Exporting", "/export/import/exporting")]),
        _node("V15", "/v15"),
        _node("V15.1", "/v15.1"),
        _node("Dup", "/dup"),
        _node("Dup", "/dup"),
    ]
    pages = list(iter_pages(parse_toc({"paginatedToc": [root]})))
    rel = [p.relative_to("out").as_posix() for p in resolve_output_paths(pages, Path("out"))]
    assert rel == [
        "index.md",
        "export_import.md",
        "export_import/exporting.md",
        "v15.md",
        "v15.1.md",
        "dup.md",
        "dup-2.md",
    ], rel
