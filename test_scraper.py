"""Offline regression checks. Run: python test_scraper.py"""
from pathlib import Path

from scraper.converter import html_to_markdown
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


def test_code_table_is_not_double_spaced() -> None:
    html = (
        '<table class="table_sourcecode"><thead><tr><th><p class="table_sourcecode">'
        '<a href="x"><img alt="Copies the following program code to clipboard."></a></p></th></tr></thead>'
        "<tbody><tr><td>\n"
        '  <p class="p_table_l_code">var a = 1;</p>\n'
        '  <p class="p_table_l_code">&nbsp;&nbsp;{</p>\n'
        '  <p class="p_table_l_code">&nbsp;</p>\n'
        '  <p class="p_table_l_code">&nbsp;&nbsp;}</p>\n'
        "</td></tr></tbody></table>"
    )
    md = html_to_markdown(html, "T")
    assert "```csharp\nvar a = 1;\n  {\n\n  }\n```" in md, md


if __name__ == "__main__":
    test_output_paths()
    test_code_table_is_not_double_spaced()
    print("OK")
