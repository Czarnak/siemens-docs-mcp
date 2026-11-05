"""Reading views over converter blocks: sections, outline rows, code-only views and chunking.

Everything here is pure (no I/O), so each reading mode is a small, separately testable filter over the
block list that ``converter.html_to_blocks`` produces.
"""
from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from siemens_docs_mcp.converter import Block

ReadMode = Literal["full", "outline", "code"]
READ_MODES: tuple[ReadMode, ...] = ("full", "outline", "code")

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKUP = re.compile(r"\*\*|\*|`")


@dataclass(frozen=True)
class Section:
    number: int  # 0 = the lead (blocks before the first heading)
    heading: Block | None  # None for the lead
    blocks: tuple[Block, ...]  # heading first, nested sections included


@dataclass(frozen=True)
class OutlineRow:
    number: int
    label: str  # heading text with # markers, "(before first heading)" or "(whole page)"
    chars: int
    code_blocks: int


def view_text(blocks: Sequence[Block]) -> str:
    """The text a view's blocks make: one blank line between blocks, a final newline ("" for no blocks)."""
    return "\n\n".join(b.text for b in blocks) + "\n" if blocks else ""


def _spans(blocks: Sequence[Block]) -> list[tuple[int, int, int]]:
    """(number, start, end) block-index ranges: the lead, then one per heading including nested headings."""
    spans = []
    first = next((i for i, b in enumerate(blocks) if b.kind == "heading"), len(blocks))
    if first > 0:
        spans.append((0, 0, first))
    number = 0
    for i, block in enumerate(blocks):
        if block.kind != "heading":
            continue
        number += 1
        # A section ends at the next heading of the same or a higher level (smaller or equal number).
        end = next(
            (j for j in range(i + 1, len(blocks)) if blocks[j].kind == "heading" and blocks[j].level <= block.level),
            len(blocks),
        )
        spans.append((number, i, end))
    return spans


def split_sections(blocks: Sequence[Block]) -> list[Section]:
    return [
        Section(number, blocks[start] if blocks[start].kind == "heading" else None, tuple(blocks[start:end]))
        for number, start, end in _spans(blocks)
    ]


def heading_match_text(block: Block) -> str:
    """A heading's plain text for matching: no # markers, link syntax or emphasis; whitespace collapsed."""
    text = block.text.lstrip("#")
    text = _LINK.sub(r"\1", text)
    text = _MARKUP.sub("", text)
    return " ".join(text.split())


def _row_label(blocks: Sequence[Block], heading: Block | None) -> str:
    if heading is not None:
        return heading.text
    return "(before first heading)" if any(b.kind == "heading" for b in blocks) else "(whole page)"


def outline_rows(blocks: Sequence[Block]) -> list[OutlineRow]:
    return [
        OutlineRow(
            s.number,
            _row_label(blocks, s.heading),
            len(view_text(s.blocks)),
            sum(b.kind == "code" for b in s.blocks),
        )
        for s in split_sections(blocks)
    ]


def _headings_list(blocks: Sequence[Block]) -> str:
    return "\n".join(f"{row.number}. {row.label}" for row in outline_rows(blocks))


def select_sections(blocks: Sequence[Block], section: int | str) -> list[Block]:
    """Blocks of the sections chosen by an outline number, or by heading text.

    Text matches a heading equal to it, or starting with it followed by ":" (case-insensitive), so
    "Program code" matches every "Program code: …" section. All matches are returned in document order;
    a match nested inside another match is returned once, as part of the outer one.
    """
    spans = _spans(blocks)
    if isinstance(section, int):
        chosen = [span for span in spans if span[0] == section]
        if not chosen:
            raise ValueError(f"No section number {section} on this page. Sections:\n{_headings_list(blocks)}")
    else:
        if not any(b.kind == "heading" for b in blocks):
            raise ValueError("This page has no headings; read it without section.")
        query = " ".join(section.split()).lower()
        chosen = []
        for span in spans:
            heading = blocks[span[1]]
            if heading.kind != "heading":
                continue
            text = heading_match_text(heading).lower()
            if text != query and not text.startswith(query + ":"):
                continue
            if chosen and span[1] < chosen[-1][2]:  # nested inside the previous match
                continue
            chosen.append(span)
        if not chosen:
            raise ValueError(_no_match_message(blocks, spans, section))
    return [b for _, start, end in chosen for b in blocks[start:end]]


def _no_match_message(blocks: Sequence[Block], spans: list[tuple[int, int, int]], section: str) -> str:
    labels = {
        heading_match_text(blocks[start]).lower(): f"{number}. {blocks[start].text}"
        for number, start, _ in spans
        if blocks[start].kind == "heading"
    }
    close = difflib.get_close_matches(section.lower(), list(labels), n=3)
    hint = f" Close matches: {'; '.join(labels[c] for c in close)}." if close else ""
    return f"No heading matches section {section!r}.{hint}\nSections:\n{_headings_list(blocks)}"


def code_view(blocks: Sequence[Block]) -> list[Block]:
    """Code blocks, each run preceded by its nearest heading (none for code before the first heading)."""
    out: list[Block] = []
    heading: Block | None = None
    emitted: Block | None = None
    for block in blocks:
        if block.kind == "heading":
            heading = block
        elif block.kind == "code":
            if heading is not None and heading is not emitted:
                out.append(heading)
                emitted = heading
            out.append(block)
    return out
