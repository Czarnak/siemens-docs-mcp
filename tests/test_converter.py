"""Offline regression checks for HTML to Markdown conversion."""
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from siemens_docs_mcp.content import _clean_html, _clean_soup, fetch_soup
from siemens_docs_mcp.converter import html_to_blocks, html_to_markdown
from tests.test_converter_golden import GOLDEN

FIX = Path(__file__).parent / "fixtures" / "html"


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
    assert "```\nvar a = 1;\n  {\n\n  }\n```" in md, md


def test_scl_code_has_no_language_tag() -> None:
    md = html_to_markdown(_clean_html(FIX.joinpath("tia_scl.html").read_text("utf-8")), "T")
    assert "```csharp" not in md
    assert "\n```\n" in md or md.count("```") >= 2


def test_admonition_becomes_blockquote() -> None:
    html = '<div class="admonition note"><p class="admonition-title">Note</p><p>Body text.</p></div>'
    assert "> **Note:** Body text." in html_to_markdown(html, "T")


def test_iox_fixture_admonition_rendered() -> None:
    md = html_to_markdown(_clean_html(FIX.joinpath("iox_admonition.html").read_text("utf-8")), "T")
    assert "> **" in md


def test_list_item_keeps_inline_markup() -> None:
    html = (
        '<ul><li><a href="https://h/access?ft:baseId=1">LAD (S7-1200)</a></li>'
        "<li>Use <b>TON</b> or <code>IEC_TIMER</code> here</li>"
        "<li><p>First para</p><p>Second <b>para</b></p></li></ul>"
    )
    md = html_to_markdown(html, "T")
    assert "- [LAD (S7-1200)](https://h/access?ft:baseId=1)\n" in md, md
    assert "- Use **TON** or `IEC_TIMER` here\n" in md, md
    assert "- First para\n\n  Second **para**" in md, md


def test_unknown_inline_only_tag_not_dropped() -> None:
    md = html_to_markdown("<dl><dt>Term</dt><dd>Definition</dd></dl><pre>x = 1\ny = 2</pre>", "T")
    assert "Term" in md and "Definition" in md
    assert "x = 1\ny = 2" in md


def test_blocks_kinds_and_levels() -> None:
    html = (
        '<div><p class="Blocktitle">Requirement</p><p>Text</p><h3>Deep</h3>'
        '<table class="table_sourcecode"><tr><td><p class="p_table_l_code">x();</p></td></tr></table>'
        '<table class="safety"><tr><td>Note</td><td>Careful</td></tr></table>'
        "<ul><li>a</li></ul><table><tr><td>h</td></tr><tr><td>v</td></tr></table></div>"
    )
    assert [(b.kind, b.level) for b in html_to_blocks(html)] == [
        ("heading", 2), ("paragraph", 0), ("heading", 3), ("code", 0),
        ("quote", 0), ("list", 0), ("table", 0),
    ]


def test_blocks_open_nested_divs_and_drop_adjacent_duplicates() -> None:
    blocks = html_to_blocks("<div><div><p>A</p><p>B</p></div><div><p>A</p><p>B</p></div></div>")
    assert [b.text for b in blocks] == ["A", "B"]


def test_blocks_empty_source() -> None:
    assert html_to_blocks("") == [] and html_to_blocks("  \n") == []


def test_html_to_markdown_is_blocks_joined() -> None:
    html = _clean_html(FIX.joinpath("openness_page.html").read_text("utf-8"))
    blocks = html_to_blocks(html)
    assert html_to_markdown(html, "T") == "# T\n\n" + "\n\n".join(b.text for b in blocks) + "\n"


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_soup_path_matches_string_path(case) -> None:
    entry = GOLDEN[case]
    soup = BeautifulSoup(entry["html"], "html.parser")
    _clean_soup(soup)
    assert html_to_markdown(soup, entry["title"]) == html_to_markdown(_clean_html(entry["html"]), entry["title"])


def test_link_hook_and_images_off() -> None:
    html = (
        '<p><a href="A">one</a> <a href="B">two</a> <a href="C"><img alt="" src="i.png"></a>'
        ' <img alt="Diagram" src="d.png"></p>'
    )
    md = html_to_markdown(html, "T", link=lambda h: {"A": "tia:m/a", "B": None}.get(h, h), images=False)
    assert "[one](tia:m/a) two" in md and "Diagram" in md
    assert "i.png" not in md and "d.png" not in md and "](C)" not in md


def test_image_inside_link_keeps_alt_as_label() -> None:
    md = html_to_markdown('<p><a href="A"><img alt="Wiring" src="w.png"></a></p>', "T", images=False)
    assert "[Wiring](A)" in md and "w.png" not in md


def test_link_hook_in_lists_and_tables() -> None:
    html = '<ul><li><a href="A">item</a></li></ul><table><tr><td><a href="A">cell</a></td></tr></table>'
    md = html_to_markdown(html, "T", link=lambda h: "tia:m/a")
    assert md.count("(tia:m/a)") == 2 and "(A)" not in md


def test_link_hook_reaches_markdownify_fallback() -> None:
    md = html_to_markdown(
        '<dl><dt><a href="A">term</a> <img alt="pic" src="p.png"></dt><dd>d</dd></dl>', "T",
        link=lambda h: "tia:m/a", images=False,
    )
    assert "tia:m/a" in md and "(A)" not in md and "p.png" not in md and "pic" in md


@pytest.mark.parametrize("html", [
    (
        '<table class="safety"><tr><td>Notice</td><td>Switch the <span class="operating-mode">RUN</span>'
        " CPU off first.</td></tr></table>"
    ),
    (
        '<table class="safety"><tr><td>Note</td><td>Do not stop the PLC <button>?</button> while downloading.'
        "</td></tr></table>"
    ),
    '<table class="table_sourcecode"><tr><td>var x = 1;<button>Copy</button>var y = 2;</td></tr></table>',
])
def test_chrome_removed_between_text_nodes_matches_string_path(html) -> None:
    """Removing chrome leaves adjacent text nodes; they must render as the reparsed string path does."""
    soup = BeautifulSoup(html, "html.parser")
    _clean_soup(soup)
    assert html_to_markdown(soup, "T") == html_to_markdown(_clean_html(html), "T")


def test_fetch_soup_merges_text_split_by_removed_chrome() -> None:
    class Client:
        def get_content(self, map_id, content_id):
            return '<table class="safety"><tr><td>Note</td><td>Stop the <button>x</button> PLC.</td></tr></table>'

    assert "> Stop the PLC.\n" in html_to_markdown(fetch_soup(Client(), "m", "c"), "T")
