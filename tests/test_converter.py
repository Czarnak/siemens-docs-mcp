"""Offline regression checks for HTML to Markdown conversion."""
from scraper.converter import html_to_markdown


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
