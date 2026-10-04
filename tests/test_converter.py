"""Offline regression checks for HTML to Markdown conversion."""
from pathlib import Path

from scraper.content import _clean_html
from scraper.converter import html_to_markdown

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


def test_unknown_inline_only_tag_not_dropped() -> None:
    md = html_to_markdown("<dl><dt>Term</dt><dd>Definition</dd></dl><pre>x = 1\ny = 2</pre>", "T")
    assert "Term" in md and "Definition" in md
    assert "x = 1\ny = 2" in md
