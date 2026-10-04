"""Write scraped Markdown pages to the file system.

Output structure mirrors the documentation's URL hierarchy.
Given a base prettyUrl of ``/r/en-us/v21/doc-name`` and a page with
``prettyUrl`` of ``/r/en-us/v21/doc-name/basics/overview``, the output is:

    output_dir/
    └── basics/
        └── overview.md

The root page becomes ``index.md``.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .toc import TocPage

log = logging.getLogger(__name__)

# Characters that are unsafe or awkward in file/directory names on common OSes.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def resolve_output_path(page: TocPage, output_dir: Path) -> Path:
    """Compute the output file path for a page.

    Every TOC segment except the last becomes a directory; the last becomes
    the ``.md`` filename. Example: segments ``("basics", "overview")``
    → ``output_dir / "basics" / "overview.md"``.
    """
    if not page.segments:
        # This is the root / landing page of the documentation
        return output_dir / "index.md"

    path = output_dir.joinpath(*(_sanitize(s) for s in page.segments))
    # Append rather than with_suffix(): "v15.1" must not become "v15.md".
    return path.with_name(path.name + ".md")


def resolve_output_paths(pages: list[TocPage], output_dir: Path) -> list[Path]:
    """Resolve paths for all pages, suffixing ``-2``, ``-3``… on collisions.

    Fluidtopics occasionally gives two distinct topics the same prettyUrl.
    """
    seen: set[Path] = set()
    result: list[Path] = []
    for page in pages:
        base = path = resolve_output_path(page, output_dir)
        n = 1
        while path in seen:
            n += 1
            path = base.with_name(f"{base.stem}-{n}.md")
        seen.add(path)
        result.append(path)
    return result


def write_page(path: Path, content: str) -> None:
    """Write Markdown content to a file, creating parent directories as needed.

    Args:
        path:    Destination file path (should end in ``.md``).
        content: Markdown content string.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    log.debug("Written → %s", path)


def _sanitize(segment: str) -> str:
    """Replace filesystem-unsafe characters in a path segment with underscores."""
    cleaned = _UNSAFE.sub("_", segment)
    # Collapse multiple underscores that may result from substitution
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if cleaned and not cleaned.strip("."):  # ".", ".." would escape output_dir (or vanish on Windows)
        return "_"
    return cleaned or "_empty_"
