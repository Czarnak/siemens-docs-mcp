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

import html as html_module
import re

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from markdownify import markdownify

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def html_to_markdown(html: str, title: str) -> str:
    """Convert an HTML string to a Markdown document.

    Args:
        html:  Cleaned HTML content (output of :func:`siemens_docs_mcp.content.fetch_html`).
        title: Page title — prepended as an H1 heading.

    Returns:
        Complete Markdown string beginning with an H1 title heading.
    """
    if not html.strip():
        return f"# {title}\n\n*No content available.*\n"

    soup = BeautifulSoup(html, "html.parser")
    blocks: list[str] = []

    for child in soup.contents:
        if isinstance(child, Tag):
            rendered = _render_block(child)
            if rendered:
                blocks.append(rendered)

    body = _post_process("\n\n".join(blocks))
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

def _inline_to_md(node: Tag | NavigableString) -> str:
    """Recursively render an inline node to Markdown text."""
    if isinstance(node, NavigableString):
        return str(node)

    name = node.name.lower()

    if name == "br":
        return "\n"
    if name == "a":
        href = node.get("href", "")
        content = "".join(_inline_to_md(c) for c in node.children).strip()
        label = _clean_text(content) or href
        return f"[{label}]({href})" if href else label
    if name in {"b", "strong"}:
        inner = _clean_text("".join(_inline_to_md(c) for c in node.children))
        return f"**{inner}**" if inner else ""
    if name in {"i", "em"}:
        inner = _clean_text("".join(_inline_to_md(c) for c in node.children))
        return f"*{inner}*" if inner else ""
    if name == "code":
        inner = _clean_text("".join(_inline_to_md(c) for c in node.children))
        return f"`{inner}`" if inner else ""
    if name == "img":
        src = node.get("src") or ""
        alt = node.get("alt") or ""
        # Skip embedded data URIs (text-only output)
        if src.startswith("data:image/"):
            return alt or ""
        return f"![{alt}]({src})" if src else alt
    # Fallthrough: render children
    return "".join(_inline_to_md(c) for c in node.children)


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

# ATX heading levels for h1–h6
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _render_block(tag: Tag) -> str:
    """Render a single block-level HTML tag to Markdown."""
    name = tag.name.lower()

    # --- Headings (h1–h6) ---
    if name in _HEADING_TAGS:
        level = int(name[1])
        text = _clean_text("".join(_inline_to_md(c) for c in tag.children))
        return f"{'#' * level} {text}" if text else ""

    # --- Paragraphs ---
    if name == "p":
        cls = set(tag.get("class", []))
        text = _normalize_code("".join(_inline_to_md(c) for c in tag.children))
        if not text:
            return ""
        # Siemens section-title classes → H2
        if "BlocktitleFirst" in cls or "Blocktitle" in cls:
            return f"## {_clean_text(text)}"
        # Siemens inline code paragraph classes → fenced code block
        if "p_table_l_code" in cls or "table_sourcecode" in cls:
            return f"```\n{text}\n```"
        # Table-title paragraphs carry no useful prose — skip
        if "p_table_title" in cls:
            return ""
        return _clean_text(text)

    # --- Lists ---
    if name in {"ul", "ol"}:
        return _render_list(tag, level=0)

    # --- Tables ---
    if name == "table":
        classes = set(tag.get("class", []))
        if "table_sourcecode" in classes:
            # One <p> per code line; get_text("\n") would also emit the
            # whitespace between them, double-spacing every line.
            code_lines = [p.get_text() for p in tag.find_all("p", class_="p_table_l_code")]
            raw = "\n".join(code_lines) if code_lines else tag.get_text("\n", strip=False)
            code = _normalize_code(raw)
            return f"```\n{code}\n```" if code else ""
        if "safety" in classes:
            return _render_safety_table(tag)
        return _render_regular_table(tag)

    # --- Divs ---
    if name == "div":
        if "admonition" in tag.get("class", []):
            return _render_admonition(tag)
        return _render_div(tag)

    # --- Preformatted code ---
    if name == "pre":
        code = _normalize_code(tag.get_text())
        return f"```\n{code}\n```" if code else ""

    # --- Standalone images ---
    if name == "img":
        src = tag.get("src") or ""
        alt = tag.get("alt") or ""
        if src.startswith("data:image/"):
            return alt or ""
        return f"![{alt}]({src})" if src else alt

    # --- Ignored structural/chrome tags ---
    if name in {"script", "style", "head", "nav", "button", "form"}:
        return ""

    # --- Unknown tag: try to render children ---
    pieces = []
    for child in tag.children:
        if isinstance(child, Tag):
            rendered = _render_block(child)
            if rendered:
                pieces.append(rendered)
    if pieces:
        return "\n\n".join(pieces)
    # Inline-only unknown tag (dl, details, ...): keep its text via markdownify.
    if tag.get_text(strip=True):
        return markdownify(str(tag), heading_style="ATX").strip()
    return ""


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


def _render_list(tag: Tag, level: int) -> str:
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
                run.append(_inline_to_md(child))
                continue
            if not isinstance(child, Tag):
                continue
            _flush_run(run, texts)
            child_name = child.name.lower()
            if child_name in {"ul", "ol"}:
                nested.append(_render_list(child, level + 1))
            elif child_name == "table" and "safety" in set(child.get("class", [])):
                nested.append(_render_safety_table(child))
            else:
                text = _clean_text("".join(_inline_to_md(c) for c in child.children))
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


def _render_regular_table(table: Tag) -> str:
    """Render a standard HTML table as a GFM Markdown table."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        row = [
            _clean_text("".join(_inline_to_md(c) for c in cell.children))
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

def _render_admonition(div: Tag) -> str:
    """Render a MkDocs-style admonition div as a labelled Markdown blockquote."""
    title = div.find(class_="admonition-title")
    if title is not None:
        label = _clean_text(title.get_text())
    else:
        others = [c for c in div.get("class", []) if c != "admonition"]
        label = others[0].capitalize() if others else "Note"

    body = [
        r
        for child in div.children
        if isinstance(child, Tag) and child is not title
        if (r := _render_block(child))
    ]
    if not body:
        return f"> **{label}:**"
    lines = "\n\n".join(body).split("\n")
    out = [f"> **{label}:** {lines[0]}"]
    out.extend(f"> {ln}".rstrip() for ln in lines[1:])
    return "\n".join(out)


def _render_div(div: Tag) -> str:
    """Render a <div> by visiting its block-level children."""
    pieces: list[str] = []
    for child in div.children:
        if not isinstance(child, Tag):
            continue
        rendered = _render_block(child)
        if rendered:
            pieces.append(rendered)

    # Remove adjacent duplicates (wrapper divs sometimes duplicate content)
    result: list[str] = []
    for piece in pieces:
        if not result or result[-1] != piece:
            result.append(piece)

    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _post_process(md: str) -> str:
    """Collapse excessive blank lines and strip trailing whitespace."""
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

    return "\n".join(result).strip()