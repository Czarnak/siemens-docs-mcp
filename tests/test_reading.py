"""Pure reading views over converter blocks: sections, outline rows, code view, chunking."""
import pytest

from siemens_docs_mcp.converter import Block
from siemens_docs_mcp.reading import (
    OutlineRow,
    code_view,
    outline_rows,
    select_sections,
    split_sections,
    view_text,
)


def h(level: int, text: str) -> Block:
    return Block("heading", f"{'#' * level} {text}", level)


def p(text: str) -> Block:
    return Block("paragraph", text)


def c(text: str) -> Block:
    return Block("code", text)


PAGE = [
    p("lead"), h(2, "Requirement"), p("req"), h(2, "Program code: Compile one"), c("```\na();\n```"),
    h(3, "Detail"), p("d"), h(2, "Program code: Compile group"), c("```\nb();\n```"), h(2, "Results"),
]


def test_view_text() -> None:
    assert view_text([p("a"), p("b")]) == "a\n\nb\n"
    assert view_text([]) == ""


def test_sections_numbering_and_nesting() -> None:
    secs = split_sections(PAGE)
    assert [s.number for s in secs] == [0, 1, 2, 3, 4, 5]
    assert [b.text for b in secs[2].blocks] == ["## Program code: Compile one", "```\na();\n```", "### Detail", "d"]
    assert secs[0].heading is None and secs[1].heading == h(2, "Requirement")


def test_sections_without_lead_start_at_one() -> None:
    assert [s.number for s in split_sections(PAGE[1:])] == [1, 2, 3, 4, 5]


def test_select_by_prefix_returns_all_matches_in_order() -> None:
    texts = [b.text for b in select_sections(PAGE, "program code")]
    assert texts[0] == "## Program code: Compile one" and "## Program code: Compile group" in texts
    assert "## Results" not in texts and "## Requirement" not in texts


def test_select_exact_full_heading() -> None:
    assert select_sections(PAGE, "Program code: Compile group")[0].text == "## Program code: Compile group"


def test_select_by_number_and_lead() -> None:
    assert [b.text for b in select_sections(PAGE, 0)] == ["lead"]
    assert select_sections(PAGE, 3)[0].text == "### Detail"


def test_nested_match_returns_outer_once() -> None:
    blocks = [h(2, "Export"), p("x"), h(3, "Export: blocks"), p("y")]
    assert [b.text for b in select_sections(blocks, "export")] == ["## Export", "x", "### Export: blocks", "y"]


def test_partial_after_colon_does_not_match() -> None:
    with pytest.raises(ValueError, match=r"2\. ## Program code: Compile one"):
        select_sections(PAGE, "Program code: Compile")


def test_no_match_lists_close_matches_first() -> None:
    with pytest.raises(ValueError) as exc:
        select_sections(PAGE, "Requirment")
    message = str(exc.value)
    assert "Requirement" in message.split("\n")[0]


def test_markup_in_heading_matches_plain_text() -> None:
    blocks = [h(2, "**Properties** of `Safety` [telegrams](tia:m/t)"), p("x")]
    assert select_sections(blocks, "properties of safety telegrams")[1].text == "x"


def test_no_headings_and_bad_number() -> None:
    with pytest.raises(ValueError, match="no headings"):
        select_sections([p("x")], "Anything")
    with pytest.raises(ValueError):
        select_sections(PAGE, 9)
    with pytest.raises(ValueError):
        select_sections(PAGE[1:], 0)  # no lead → 0 is invalid


def test_code_view_groups_under_nearest_heading() -> None:
    blocks = [c("```\nlead();\n```"), h(2, "A"), c("```\n1\n```"), c("```\n2\n```"), h(2, "B"), p("x")]
    assert [b.text for b in code_view(blocks)] == ["```\nlead();\n```", "## A", "```\n1\n```", "```\n2\n```"]
    assert code_view([p("x")]) == []


def test_code_view_uses_innermost_heading_and_repeats_after_prose() -> None:
    blocks = [h(2, "A"), c("```\n1\n```"), p("prose"), c("```\n2\n```"), h(3, "A.1"), c("```\n3\n```")]
    assert [b.text for b in code_view(blocks)] == ["## A", "```\n1\n```", "```\n2\n```", "### A.1", "```\n3\n```"]


def test_outline_rows() -> None:
    rows = outline_rows(PAGE)
    assert rows[0] == OutlineRow(0, "(before first heading)", len("lead\n"), 0)
    assert rows[2].code_blocks == 1 and rows[2].label == "## Program code: Compile one"
    assert rows[2].chars == len(view_text(split_sections(PAGE)[2].blocks))
    assert outline_rows([p("x")]) == [OutlineRow(0, "(whole page)", 2, 0)]
    assert outline_rows([]) == []
