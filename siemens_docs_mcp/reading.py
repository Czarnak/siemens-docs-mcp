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


# --- chunking ----------------------------------------------------------------

_FENCE = "```"


@dataclass(frozen=True)
class Chunk:
    text: str  # ends with "\n" only when it reaches the end of the view
    next_offset: int | None  # view position of the first character not returned; None when done


def _line_starts(text: str) -> list[int]:
    return [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]


def _frame(block: Block, rel: int, budget: int) -> tuple[int, str, str, list[int], bool]:
    """(rel, prefix, suffix, line starts, is_code) for a piece of ``block`` starting at ``rel``.

    A code piece is fenced on both ends: its opening fence line is always the prefix (so a piece that
    starts at the block's beginning reuses it), and a piece that stops early gets a closing fence. A table
    piece starting after the header repeats the header when the header and one row fit.
    """
    text = block.text
    starts = _line_starts(text)
    is_code = block.kind == "code" and text.startswith(_FENCE) and len(starts) > 2
    prefix = ""
    if is_code:
        prefix = text[: starts[1]]
        rel = max(rel, starts[1])
    elif block.kind == "table" and len(starts) > 3 and rel >= starts[2]:
        next_line_end = text.find("\n", rel)
        row = text[rel: len(text) if next_line_end == -1 else next_line_end]
        if starts[2] + len(row) <= budget:
            prefix = text[: starts[2]]
    return rel, prefix, ("\n" + _FENCE if is_code else ""), starts, is_code


def _split_at_lines(block: Block, rel: int, budget: int, final_extra: int) -> tuple[str, int] | None:
    """The rest of the block, or its longest prefix ending at a line boundary, within ``budget``."""
    text = block.text
    rel, prefix, suffix, starts, is_code = _frame(block, rel, budget)
    remainder = text[rel:]
    if len(prefix) + len(remainder) + final_extra <= budget:
        return prefix + remainder, len(text)
    room = budget - len(prefix) - len(suffix)
    # A code piece must leave more than the closing fence for the next piece.
    candidates = [b for b in starts if b > rel and not (is_code and b == starts[-1])]
    fitting = [b for b in candidates if (b - 1) - rel <= room]
    if not fitting:
        return None
    cut = fitting[-1]
    return prefix + text[rel: cut - 1] + suffix, cut


def _split_in_line(block: Block, rel: int, budget: int, final_extra: int) -> tuple[str, int] | None:
    """Last resort for a line longer than any chunk: cut at its last space, else at the budget."""
    text = block.text
    rel, prefix, suffix, starts, is_code = _frame(block, rel, budget)
    room = budget - len(prefix) - len(suffix)
    if room <= 0:
        return None
    line_end = text.find("\n", rel)
    line_end = len(text) if line_end == -1 else line_end
    limit = min(rel + room, line_end)
    if limit == len(text) and final_extra:
        limit -= 1  # leave room for the view's final newline
    if is_code and limit == line_end and line_end + 1 == starts[-1]:
        limit -= 1  # never leave only the closing fence for the next piece
    if limit <= rel:
        return None
    space = text.rfind(" ", rel + 1, limit + 1)
    cut = space if space != -1 else limit
    return prefix + text[rel:cut] + suffix, cut + 1 if space != -1 else cut


def _split(block: Block, rel: int, budget: int, final_extra: int, max_chars: int) -> tuple[str, int] | None:
    """The largest valid piece of ``block`` from ``rel`` within ``budget``: (piece, next rel), or None.

    None means "start the next chunk here": a fresh chunk can take this part at a line boundary. Only a
    line that no chunk could hold is cut inside the line. Synthetic fence/header lines count toward the
    budget but not toward offsets.
    """
    piece = _split_at_lines(block, rel, budget, final_extra)
    if piece is not None:
        return piece
    if budget < max_chars and _split_at_lines(block, rel, max_chars, final_extra) is not None:
        return None
    return _split_in_line(block, rel, budget, final_extra)


def _resume_point(block: Block, rel: int, max_chars: int, final_extra: int) -> int:
    """Where to start inside a block that ``rel`` points into.

    A block that fits in one chunk is always read whole. In a larger block, go back to the start of the
    line when a chunk can hold it from there; otherwise (a line split mid-way on purpose) stay at ``rel``.
    """
    text = block.text
    if len(text) + final_extra <= max_chars:
        return 0
    line_start = text.rfind("\n", 0, rel) + 1
    return line_start if _split_at_lines(block, line_start, max_chars, final_extra) is not None else rel


def chunk_view(blocks: Sequence[Block], offset: int, max_chars: int) -> Chunk:
    """One chunk of the view, from ``offset``, at most ``max_chars``, cut only between blocks.

    A block larger than ``max_chars`` is split at a line (or table row); a single line longer than the
    budget is split at its last space, and only without one is it cut at the budget.
    """
    total = len(view_text(blocks))
    if offset >= total > 0:
        raise ValueError(f"offset {offset} is past the end of this page (length {total}).")
    if not blocks:
        return Chunk("", None)
    starts = []
    pos = 0
    for block in blocks:
        starts.append(pos)
        pos += len(block.text) + 2

    # Locate the start block; an offset in a separator moves to the next block, the final "\n" to the last.
    index = next(
        (i for i, b in enumerate(blocks) if offset < starts[i] + len(b.text) + (1 if i == len(blocks) - 1 else 2)),
        len(blocks) - 1,
    )
    rel = max(0, offset - starts[index])
    if rel >= len(blocks[index].text):  # in the separator after this block
        index, rel = (index + 1, 0) if index + 1 < len(blocks) else (index, 0)
    else:
        rel = _resume_point(blocks[index], rel, max_chars, 1 if index == len(blocks) - 1 else 0)

    parts: list[str] = []
    used = 0
    while index < len(blocks):
        block = blocks[index]
        sep = 2 if parts else 0
        final_extra = 1 if index == len(blocks) - 1 else 0
        if rel == 0 and used + sep + len(block.text) + final_extra <= max_chars:
            parts.append(block.text)
            used += sep + len(block.text)
            index += 1
            continue
        if rel == 0 and len(block.text) + final_extra <= max_chars:
            break  # fits in a chunk of its own: start the next chunk with it
        piece = _split(block, rel, max_chars - used - sep, final_extra, max_chars)
        if piece is None:
            break
        text, rel = piece
        parts.append(text)
        used += sep + len(text)
        if rel < len(block.text):
            break
        index, rel = index + 1, 0

    if not parts:  # cannot happen with max_chars >= 1000; guard against an endless continuation loop
        raise ValueError(f"max_chars {max_chars} is too small to make progress at offset {offset}.")
    if index >= len(blocks):
        return Chunk("\n\n".join(parts) + "\n", None)
    return Chunk("\n\n".join(parts), starts[index] + rel)
