"""Convert cleaned HTML to Markdown using a custom TIA-aware renderer.

This replaces a generic markdownify pass with a renderer that understands
Siemens/Fluidtopics-specific HTML patterns:

- Siemens CSS classes (BlocktitleFirst, Blocktitle, p_table_l_code,
  table_sourcecode, safety) are mapped to appropriate Markdown constructs.
- Safety/note/warning tables become Markdown blockquotes.
- Source-code tables and paragraphs become fenced code blocks (no language tag).
- Standard GFM tables are produced for regular data tables.
- Nested lists are handled correctly.
- HTML headings (h1–h6) are converted to ATX headings.

The renderer is intentionally text-only: embedded base64 images are not
extracted to disk (the tool was designed for text content).  External image
references are preserved as Markdown image links.
"""
from __future__ import annotations

import copy
import html as html_module
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from markdownify import markdownify

BlockKind = Literal["heading", "paragraph", "code", "table", "list", "quote", "other"]
# Maps an anchor href to a replacement href, or to None to keep only the link label.
LinkRewrite = Callable[[str], str | None]


@dataclass(frozen=True)
class Block:
    """One top-level piece of a page: finished Markdown plus what reading modes need to know about it."""

    kind: BlockKind
    text: str
    level: int = 0  # 1-6 for headings, 0 otherwise


@dataclass(frozen=True)
class _Options:
    """Rendering choices passed down explicitly (not module state) so concurrent reads cannot mix them."""

    link: LinkRewrite | None = None
    images: bool = True


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def html_to_blocks(
    source: BeautifulSoup | str, *, link: LinkRewrite | None = None, images: bool = True
) -> list[Block]:
    """Convert cleaned HTML (a parsed tree or a string) into Markdown blocks, without the page title."""
    if isinstance(source, str):
        if not source.strip():
            return []
        source = BeautifulSoup(source, "html.parser")
    opts = _Options(link, images)
    blocks: list[Block] = []
    for child in source.contents:
        if isinstance(child, Tag):
            blocks.extend(_render_block(child, opts))
    # Post-process per block, trimming only blank lines, then strip the start of the first block: joined
    # with one blank line, the blocks then equal the old single post-processing pass over the whole body.
    finished = [b for b in (Block(b.kind, _post_process(b.text), b.level) for b in blocks) if b.text]
    if finished and finished[0].text != finished[0].text.lstrip():
        first = finished[0]
        finished[0] = Block(first.kind, first.text.lstrip(), first.level)
    return [b for b in finished if b.text]


def html_to_markdown(
    source: BeautifulSoup | str, title: str, *, link: LinkRewrite | None = None, images: bool = True
) -> str:
    """Convert cleaned HTML to a Markdown document beginning with an H1 title heading (the exporter's format)."""
    if not str(source).strip():
        return f"# {title}\n\n*No content available.*\n"
    body = "\n\n".join(b.text for b in html_to_blocks(source, link=link, images=images))
    return f"# {title}\n\n{body}\n"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    text = html_module.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_code(code: str) -> str:
    """Unescape and strip leading/trailing blank lines from code text."""
    code = html_module.unescape(code)
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    code = code.replace("\xa0", " ")
    lines = code.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(line.rstrip() for line in lines)


# ---------------------------------------------------------------------------
# Inline rendering
# ---------------------------------------------------------------------------

def _inline_to_md(node: Tag | NavigableString, opts: _Options) -> str:
    """Recursively render an inline node to Markdown text."""
    if isinstance(node, NavigableString):
        return str(node)

    name = node.name.lower()

    if name == "br":
        return "\n"
    if name == "a":
        href = node.get("href", "")
        text = _clean_text("".join(_inline_to_md(c, opts) for c in node.children).strip())
        if href and opts.link is not None:
            href = opts.link(href)
            if href is None:  # the hook keeps only the label
                return text
        if not text and not opts.images:  # e.g. an image link whose image was dropped
            return ""
        label = text or href
        return f"[{label}]({href})" if href else label
    if name in {"b", "strong"}:
        inner = _clean_text("".join(_inline_to_md(c, opts) for c in node.children))
        return f"**{inner}**" if inner else ""
    if name in {"i", "em"}:
        inner = _clean_text("".join(_inline_to_md(c, opts) for c in node.children))
        return f"*{inner}*" if inner else ""
    if name == "code":
        inner = _clean_text("".join(_inline_to_md(c, opts) for c in node.children))
        return f"`{inner}`" if inner else ""
    if name == "img":
        return _render_img(node, opts)
    # Fallthrough: render children
    return "".join(_inline_to_md(c, opts) for c in node.children)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

# ATX heading levels for h1–h6
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _render_block(tag: Tag, opts: _Options) -> list[Block]:
    """Render one block-level HTML tag; containers yield their children's blocks."""
    name = tag.name.lower()

    # --- Headings (h1–h6) ---
    if name in _HEADING_TAGS:
        level = int(name[1])
        text = _clean_text("".join(_inline_to_md(c, opts) for c in tag.children))
        return [Block("heading", f"{'#' * level} {text}", level)] if text else []

    # --- Paragraphs ---
    if name == "p":
        cls = set(tag.get("class", []))
        text = _normalize_code("".join(_inline_to_md(c, opts) for c in tag.children))
        if not text:
            return []
        # Siemens section-title classes → H2
        if "BlocktitleFirst" in cls or "Blocktitle" in cls:
            return [Block("heading", f"## {_clean_text(text)}", 2)]
        # Siemens inline code paragraph classes → fenced code block
        if "p_table_l_code" in cls or "table_sourcecode" in cls:
            return [Block("code", f"```\n{text}\n```")]
        # Table-title paragraphs carry no useful prose — skip
        if "p_table_title" in cls:
            return []
        return [Block("paragraph", _clean_text(text))]

    # --- Lists ---
    if name in {"ul", "ol"}:
        return _block("list", _render_list(tag, 0, opts))

    # --- Tables ---
    if name == "table":
        classes = set(tag.get("class", []))
        if "table_sourcecode" in classes:
            # One <p> per code line; get_text("\n") would also emit the
            # whitespace between them, double-spacing every line.
            code_lines = [p.get_text() for p in tag.find_all("p", class_="p_table_l_code")]
            raw = "\n".join(code_lines) if code_lines else tag.get_text("\n", strip=False)
            code = _normalize_code(raw)
            return [Block("code", f"```\n{code}\n```")] if code else []
        if "safety" in classes:
            return _block("quote", _render_safety_table(tag))
        return _block("table", _render_regular_table(tag, opts))

    # --- Divs ---
    if name == "div":
        if "admonition" in tag.get("class", []):
            return _block("quote", _render_admonition(tag, opts))
        return _render_div(tag, opts)

    # --- Preformatted code ---
    if name == "pre":
        code = _normalize_code(tag.get_text())
        return [Block("code", f"```\n{code}\n```")] if code else []

    # --- Standalone images ---
    if name == "img":
        return _block("paragraph", _render_img(tag, opts))

    # --- Ignored structural/chrome tags ---
    if name in {"script", "style", "head", "nav", "button", "form"}:
        return []

    # --- Unknown tag: try to render children ---
    pieces = [b for child in tag.children if isinstance(child, Tag) for b in _render_block(child, opts)]
    if pieces:
        return pieces
    # Inline-only unknown tag (dl, details, ...): keep its text via markdownify.
    if tag.get_text(strip=True):
        return _block("other", _markdownify(tag, opts))
    return []


def _markdownify(tag: Tag, opts: _Options) -> str:
    """markdownify fallback with the same link and image choices, applied to a copy of the tag."""
    if opts.link is None and opts.images:
        return markdownify(str(tag), heading_style="ATX").strip()
    # Work on a copy inside a holder, so the tag itself (often the <a>) can also be rewritten or unwrapped.
    holder = BeautifulSoup("", "html.parser")
    holder.append(copy.copy(tag))  # bs4 copies the whole subtree, detached from the page
    if not opts.images:
        for img in holder.find_all("img"):
            img.replace_with(img.get("alt") or "")
        for a in holder.find_all("a"):
            if not a.get_text(strip=True):
                a.decompose()
    if opts.link is not None:
        for a in holder.find_all("a", href=True):
            href = opts.link(a["href"])
            if href is None:
                a.unwrap()
            else:
                a["href"] = href
    return markdownify(str(holder), heading_style="ATX").strip()


def _block(kind: BlockKind, text: str) -> list[Block]:
    return [Block(kind, text)] if text else []


def _render_img(tag: Tag, opts: _Options) -> str:
    src = tag.get("src") or ""
    alt = tag.get("alt") or ""
    # Skip embedded data URIs (text-only output); with images off every image is its alt text.
    if not opts.images or src.startswith("data:image/"):
        return alt
    return f"![{alt}]({src})" if src else alt


# ---------------------------------------------------------------------------
# List rendering
# ---------------------------------------------------------------------------

_INLINE_TAGS = {"a", "b", "strong", "i", "em", "code", "span", "img", "sub", "sup", "u", "br"}


def _flush_run(run: list[str], texts: list[str]) -> None:
    """Append the inline ``run`` to ``texts`` as one paragraph, then empty it."""
    text = _clean_text("".join(run))
    if text:
        texts.append(text)
    run.clear()


def _render_list(tag: Tag, level: int, opts: _Options) -> str:
    ordered = tag.name.lower() == "ol"
    lines: list[str] = []
    index = 1

    for li in tag.find_all("li", recursive=False):
        bullet = f"{index}." if ordered else "-"
        index += 1
        prefix = "  " * level + bullet + " "
        continuation = "  " * (level + 1)

        texts: list[str] = []
        nested: list[str] = []
        run: list[str] = []  # consecutive inline nodes, joined into one paragraph

        for child in li.children:
            if isinstance(child, NavigableString) or (isinstance(child, Tag) and child.name.lower() in _INLINE_TAGS):
                run.append(_inline_to_md(child, opts))
                continue
            if not isinstance(child, Tag):
                continue
            _flush_run(run, texts)
            child_name = child.name.lower()
            if child_name in {"ul", "ol"}:
                nested.append(_render_list(child, level + 1, opts))
            elif child_name == "table" and "safety" in set(child.get("class", [])):
                nested.append(_render_safety_table(child))
            else:
                text = _clean_text("".join(_inline_to_md(c, opts) for c in child.children))
                if text:
                    texts.append(text)
        _flush_run(run, texts)

        item_text = "\n\n".join(texts).strip()
        if item_text:
            sublines = item_text.splitlines()
            lines.append(prefix + sublines[0])
            for extra in sublines[1:]:
                lines.append(continuation + extra)
        else:
            lines.append(prefix.rstrip())

        for block in nested:
            if block:
                lines.append(block)

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _render_safety_table(table: Tag) -> str:
    """Render a Siemens safety/note/warning table as a Markdown blockquote."""
    lines = [_clean_text(line) for line in table.get_text("\n", strip=True).split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    label = lines[0].capitalize()
    if label.lower() in {"note", "warning", "caution", "notice", "danger"}:
        body = lines[1:]
        if not body:
            return f"> **{label}**"
        return "> **{}**\n>\n> {}".format(label, "\n> ".join(body))
    return "> " + "\n> ".join(lines)


def _render_regular_table(table: Tag, opts: _Options) -> str:
    """Render a standard HTML table as a GFM Markdown table."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        row = [
            _clean_text("".join(_inline_to_md(c, opts) for c in cell.children))
            for cell in cells
        ]
        rows.append(row)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    # Pad all rows to the same width
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    if len(rows) == 1:
        return "| " + " | ".join(rows[0]) + " |"

    header = rows[0]
    separator = ["---"] * col_count
    body_rows = rows[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body_rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Div rendering
# ---------------------------------------------------------------------------

def _render_admonition(div: Tag, opts: _Options) -> str:
    """Render a MkDocs-style admonition div as a labelled Markdown blockquote."""
    title = div.find(class_="admonition-title")
    if title is not None:
        label = _clean_text(title.get_text())
    else:
        others = [c for c in div.get("class", []) if c != "admonition"]
        label = others[0].capitalize() if others else "Note"

    body = [
        b.text
        for child in div.children
        if isinstance(child, Tag) and child is not title
        for b in _render_block(child, opts)
    ]
    if not body:
        return f"> **{label}:**"
    lines = "\n\n".join(body).split("\n")
    out = [f"> **{label}:** {lines[0]}"]
    out.extend(f"> {ln}".rstrip() for ln in lines[1:])
    return "\n".join(out)


def _render_div(div: Tag, opts: _Options) -> list[Block]:
    """Render a <div> by visiting its block-level children."""
    result: list[Block] = []
    previous: str | None = None
    for child in div.children:
        if not isinstance(child, Tag):
            continue
        blocks = _render_block(child, opts)
        if not blocks:
            continue
        # Remove adjacent duplicates (wrapper divs sometimes duplicate content), compared per child as before.
        joined = "\n\n".join(b.text for b in blocks)
        if joined != previous:
            result.extend(blocks)
        previous = joined
    return result


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _post_process(md: str) -> str:
    """Collapse excessive blank lines, strip trailing whitespace and surrounding blank lines."""
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in md.splitlines()]

    result: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 1:
                result.append(line)
        else:
            blank_run = 0
            result.append(line)

    return "\n".join(result).strip("\n")