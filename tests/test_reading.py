"""Pure reading views over converter blocks: sections, outline rows, code view, chunking."""
import pytest

from siemens_docs_mcp.converter import Block
from siemens_docs_mcp.reading import (
    Chunk,
    OutlineRow,
    chunk_view,
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


# --- chunking ------------------------------------------------------------------

def _all(blocks, max_chars, offset=0):
    """Every chunk from ``offset`` to the end, following the continuation offsets."""
    chunks = []
    while offset is not None:
        chunk = chunk_view(blocks, offset, max_chars)
        assert chunk.text and len(chunk.text) <= max_chars, (offset, len(chunk.text))
        chunks.append(chunk)
        assert chunk.next_offset is None or chunk.next_offset > offset
        offset = chunk.next_offset
    return chunks


def _tokens(text):
    """Content as a token sequence, ignoring whitespace and fence lines the splitter may add."""
    return " ".join(line for line in text.splitlines() if line.strip() != "```").split()


def test_whole_blocks_only():
    blocks = [p("a" * 600), p("b" * 600)]
    first = chunk_view(blocks, 0, 1000)
    assert first.text == "a" * 600 and first.next_offset == 602


def test_oversized_code_is_split_with_valid_fences():
    code = c("```\n" + "\n".join(f"line {i:03d}" for i in range(300)) + "\n```")
    chunks = _all([code], 1000)
    assert len(chunks) > 1
    for chunk in chunks:
        lines = chunk.text.rstrip("\n").split("\n")
        assert lines[0] == "```" and lines[-1] == "```" and len(lines) > 2
    seen = [ln for chunk in chunks for ln in chunk.text.split("\n") if ln.startswith("line ")]
    assert seen == [f"line {i:03d}" for i in range(300)]


def test_table_continuation_repeats_header():
    rows = "\n".join(f"| r{i} | {'v' * 40} |" for i in range(60))
    table = Block("table", "| h1 | h2 |\n| --- | --- |\n" + rows)
    chunks = _all([table], 1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.text.startswith("| h1 | h2 |\n| --- | --- |\n| r")
    seen = [ln for chunk in chunks for ln in chunk.text.split("\n") if ln.startswith("| r")]
    assert seen == rows.split("\n")


def test_long_paragraph_splits_at_space_and_progresses():
    para = p("word " * 1000)
    chunks = _all([para], 1000)
    assert all(not chunk.text.startswith(" ") for chunk in chunks)
    assert _tokens("".join(chunk.text + " " for chunk in chunks)) == _tokens(para.text)


def test_single_spaceless_line_hard_cut():
    chunk = chunk_view([p("x" * 2500)], 0, 1000)
    assert chunk.text == "x" * 1000 and chunk.next_offset == 1000
    assert chunk_view([p("x" * 2500)], 1000, 1000).text == "x" * 1000


def test_title_then_huge_paragraph_fills_first_chunk():
    chunk = chunk_view([h(1, "Page 1"), p("abcdefghij " * 400)], 0, 1000)
    assert chunk.text.startswith("# Page 1\n\nabcdefghij") and len(chunk.text) > 900


def test_offset_mid_block_snaps_back_and_separator_moves_forward():
    blocks = [p("a" * 300), p("b" * 300)]
    assert chunk_view(blocks, 450, 1000).text == "b" * 300 + "\n"
    assert chunk_view(blocks, 301, 1000).text == "b" * 300 + "\n"
    assert chunk_view(blocks, 150, 1000).text == view_text(blocks)


def test_offset_inside_oversized_block_resumes_at_line_start():
    code = c("```\n" + "\n".join(f"line {i:03d}" for i in range(300)) + "\n```")
    start = code.text.index("line 150")
    chunk = chunk_view([code], start + 3, 1000)
    assert chunk.text.startswith("```\nline 150\n")


def test_changed_max_chars_resumes_without_loss():
    blocks = [p(f"para {i} " + "z" * 200) for i in range(30)]
    first = chunk_view(blocks, 0, 3000)
    rest = _all(blocks, 1000, offset=first.next_offset)
    assert _tokens(first.text + "\n" + "\n".join(r.text for r in rest)) == _tokens(view_text(blocks))


def test_concatenation_reproduces_view():
    blocks = [h(1, "T"), p("x " * 900), c("```\n" + "y\n" * 800 + "```"), p("end")]
    chunks = _all(blocks, 1000)
    assert _tokens("\n".join(chunk.text for chunk in chunks)) == _tokens(view_text(blocks))
    assert chunks[-1].text.endswith("end\n")


def test_no_cut_inside_a_code_fence_between_blocks():
    blocks = [p("intro " * 100), c("```\n" + "k = 1;\n" * 60 + "```"), p("outro")]
    for chunk in _all(blocks, 1000):
        assert sum(ln.strip() == "```" for ln in chunk.text.split("\n")) % 2 == 0


def test_final_chunk_and_past_end():
    assert chunk_view([p("short")], 0, 1000) == Chunk("short\n", None)
    with pytest.raises(ValueError, match="length"):
        chunk_view([p("short")], 6, 1000)
