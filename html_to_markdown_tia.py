from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

TITLE_BODY_RE = re.compile(
    r'<td class="title">(.*?)</td>.*?<div id="nstext">(.*?)</div><br><hr>',
    re.DOTALL,
)


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


class AssetManager:
    def __init__(self, output_md: Path) -> None:
        self.output_md = output_md
        self.asset_dir = output_md.with_name(f"{output_md.stem}_assets")
        self.image_index = 0
        self.saved: dict[str, str] = {}

    def save_data_uri(self, data_uri: str) -> str:
        if data_uri in self.saved:
            return self.saved[data_uri]
        match = re.match(r"data:(image/[^;]+);base64,(.*)", data_uri, re.DOTALL)
        if not match:
            return data_uri
        mime_type, payload = match.groups()
        ext = mimetypes.guess_extension(mime_type) or ".bin"
        if ext == ".jpe":
            ext = ".jpg"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.image_index += 1
        file_name = f"image_{self.image_index:03d}{ext}"
        file_path = self.asset_dir / file_name
        file_path.write_bytes(base64.b64decode(payload))
        rel_path = self.asset_dir.name + "/" + file_name
        self.saved[data_uri] = rel_path
        return rel_path


def normalize_code(code: str) -> str:
    code = html.unescape(code)
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    code = code.replace("\xa0", " ")
    lines = code.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(line.rstrip() for line in lines)


def inline_to_md(node: Tag | NavigableString, assets: AssetManager) -> str:
    if isinstance(node, NavigableString):
        return str(node)

    name = node.name.lower()
    if name == "br":
        return "\n"
    if name == "a":
        href = node.get("href", "")
        content = "".join(inline_to_md(c, assets) for c in node.children).strip()
        label = clean_text(content) or href
        return f"[{label}]({href})" if href else label
    if name in {"b", "strong"}:
        return f"**{clean_text(''.join(inline_to_md(c, assets) for c in node.children))}**"
    if name in {"i", "em"}:
        return f"*{clean_text(''.join(inline_to_md(c, assets) for c in node.children))}*"
    if name == "img":
        src = node.get("src") or ""
        alt = node.get("alt") or ""
        if src.startswith("data:image/"):
            src = assets.save_data_uri(src)
        return f"![{alt}]({src})" if src else alt
    return "".join(inline_to_md(c, assets) for c in node.children)


def render_list(tag: Tag, assets: AssetManager, level: int = 0) -> str:
    ordered = tag.name.lower() == "ol"
    lines: list[str] = []
    index = 1
    for li in tag.find_all("li", recursive=False):
        bullet = f"{index}." if ordered else "-"
        index += 1
        prefix = "  " * level + bullet + " "
        cont = "  " * (level + 1)

        texts: list[str] = []
        nested: list[str] = []
        for child in li.children:
            if isinstance(child, NavigableString):
                text = clean_text(str(child))
                if text:
                    texts.append(text)
                continue
            if not isinstance(child, Tag):
                continue
            child_name = child.name.lower()
            if child_name in {"ul", "ol"}:
                nested.append(render_list(child, assets, level + 1))
            elif child_name == "table" and "safety" in set(child.get("class", [])):
                nested.append(render_safety_table(child))
            else:
                text = clean_text("".join(inline_to_md(c, assets) for c in child.children))
                if text:
                    texts.append(text)
        item_text = "\n\n".join(texts).strip()
        if item_text:
            sublines = item_text.splitlines()
            lines.append(prefix + sublines[0])
            for extra in sublines[1:]:
                lines.append(cont + extra)
        else:
            lines.append(prefix.rstrip())
        for block in nested:
            if block:
                lines.append(block)
    return "\n".join(lines).rstrip()


def render_safety_table(table: Tag) -> str:
    lines = [clean_text(line) for line in table.get_text("\n", strip=True).split("\n")]
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


def render_regular_table(table: Tag, assets: AssetManager) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        row = [clean_text("".join(inline_to_md(c, assets) for c in cell.children)) for cell in cells]
        rows.append(row)
    if not rows:
        return ""
    col_count = max(len(r) for r in rows)
    rows = [r + [""] * (col_count - len(r)) for r in rows]
    if len(rows) == 1:
        return "| " + " | ".join(rows[0]) + " |"
    header = rows[0]
    sep = ["---"] * col_count
    body = rows[1:]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_div(div: Tag, assets: AssetManager) -> str:
    pieces: list[str] = []
    for child in div.children:
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name in {"p", "ul", "ol", "table", "div", "img"}:
            rendered = render_block(child, assets)
            if rendered:
                pieces.append(rendered)
    # Remove adjacent duplicates caused by wrapper duplication.
    result: list[str] = []
    for p in pieces:
        if not result or result[-1] != p:
            result.append(p)
    return "\n\n".join(result)


def render_block(tag: Tag, assets: AssetManager) -> str:
    name = tag.name.lower()
    if name == "a":
        return ""
    if name == "p":
        cls = set(tag.get("class", []))
        text = normalize_code("".join(inline_to_md(c, assets) for c in tag.children))
        if not text:
            return ""
        if "BlocktitleFirst" in cls or "Blocktitle" in cls:
            return f"## {text}"
        if "p_table_l_code" in cls or "table_sourcecode" in cls:
            return f"```csharp\n{text}\n```"
        if "p_table_title" in cls:
            return ""
        return text
    if name in {"ul", "ol"}:
        return render_list(tag, assets)
    if name == "table":
        classes = set(tag.get("class", []))
        if "table_sourcecode" in classes:
            code = normalize_code(tag.get_text("\n", strip=False))
            return f"```csharp\n{code}\n```" if code else ""
        if "safety" in classes:
            return render_safety_table(tag)
        return render_regular_table(tag, assets)
    if name == "div":
        return render_div(tag, assets)
    if name == "img":
        src = tag.get("src") or ""
        alt = tag.get("alt") or ""
        if src.startswith("data:image/"):
            src = assets.save_data_uri(src)
        return f"![{alt}]({src})" if src else alt
    return ""


def extract_sections(source_html: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_title, raw_body in TITLE_BODY_RE.findall(source_html):
        title = clean_text(re.sub(r"<.*?>", " ", raw_title, flags=re.DOTALL))
        preview = clean_text(re.sub(r"<.*?>", " ", raw_body, flags=re.DOTALL))[:500]
        key = (title, preview)
        if title and key not in seen:
            seen.add(key)
            sections.append((title, raw_body))
    return sections


def section_to_markdown(title: str, raw_body: str, assets: AssetManager, anchor: str) -> str:
    soup = BeautifulSoup(raw_body, "html.parser")
    blocks: list[str] = [f'<a id="{anchor}"></a>', f"# {title}"]
    for child in soup.contents:
        if isinstance(child, Tag):
            rendered = render_block(child, assets)
            if rendered:
                blocks.append(rendered)
    text = "\n\n".join(blocks)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def convert_html_to_markdown(input_html: Path, output_md: Path) -> None:
    source = input_html.read_text(encoding="utf-8", errors="ignore")
    sections = extract_sections(source)
    assets = AssetManager(output_md)

    slug_counts: dict[str, int] = {}
    section_info: list[tuple[str, str, str]] = []
    for title, body in sections:
        base = make_slug(title)
        slug_counts[base] = slug_counts.get(base, 0) + 1
        slug = base if slug_counts[base] == 1 else f"{base}-{slug_counts[base]}"
        section_info.append((title, body, slug))

    out: list[str] = []
    out.append(f"# Converted from {input_html.name}")
    out.append("")
    out.append(
        "This Markdown was generated from a Siemens Fluid Topics HTML snapshot. "
        "It preserves extracted documentation topics and converts headings, lists, notes, "
        "tables, links, images, and source code blocks into Markdown where practical."
    )
    out.append("")
    out.append("## Extracted topics")
    out.append("")
    for title, _, slug in section_info:
        out.append(f"- [{title}](#{slug})")
    out.append("")

    for title, body, slug in section_info:
        out.append(section_to_markdown(title, body, assets, slug))
        out.append("")

    md_text = "\n".join(out).strip() + "\n"
    output_md.write_text(md_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Siemens TIA Fluid Topics HTML snapshot to Markdown.")
    parser.add_argument("input_html", help="Input HTML file")
    parser.add_argument("output_md", help="Output Markdown file")
    args = parser.parse_args()
    convert_html_to_markdown(Path(args.input_html), Path(args.output_md))


if __name__ == "__main__":
    main()
