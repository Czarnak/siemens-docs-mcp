"""siemens-docs-export — CLI entry point.

Config: ``url`` (any reader URL of the publication) or legacy ``api_base`` + ``map_id``,
plus ``output_dir``.

Usage examples::

    # Scrape everything defined in a config
    siemens-docs-export configs/siemens_tia_openness_v21.yaml

    # Preview what pages would be scraped (no files written)
    siemens-docs-export configs/siemens_tia_openness_v21.yaml --dry-run

    # Scrape with verbose logging
    siemens-docs-export configs/siemens_tia_openness_v21.yaml --verbose

    # Override the output directory
    siemens-docs-export configs/siemens_tia_openness_v21.yaml --output /tmp/docs

    # Scrape only a specific page (useful for testing output quality)
    siemens-docs-export configs/siemens_tia_openness_v21.yaml --page cybersecurity-information
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import yaml

from siemens_docs_mcp.catalog import Catalog
from siemens_docs_mcp.client import FluidtopicsClient
from siemens_docs_mcp.content import fetch_html
from siemens_docs_mcp.converter import html_to_markdown
from siemens_docs_mcp.toc import TocPage, iter_pages, parse_toc
from siemens_docs_mcp.writer import resolve_output_paths, write_page

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _validate_config(config: dict) -> None:
    if not config.get("output_dir"):
        raise ValueError("Config is missing required key: 'output_dir'")
    if not (config.get("url") or (config.get("api_base") and config.get("map_id"))):
        raise ValueError("Config needs either url or api_base + map_id")


def _resolve_target(config: dict, catalog_factory: Callable[[str], Catalog]) -> tuple[str, str]:
    """Return ``(host, map_id)``; ``url`` wins over the legacy ``api_base`` + ``map_id``."""
    if url := config.get("url"):
        if config.get("api_base") or config.get("map_id"):
            log.info("Both 'url' and legacy api_base/map_id given — using 'url'")
        res = catalog_factory(urlparse(url).hostname).resolve(url)
        if res.content_id:
            log.warning("URL points at a single topic — the whole publication is exported")
        return res.host, res.map_id
    return urlparse(config["api_base"]).hostname, config["map_id"]


# ---------------------------------------------------------------------------
# Core scrape logic
# ---------------------------------------------------------------------------

def run(config: dict, dry_run: bool = False, output_override: str | None = None, page_filter: str | None = None) -> None:
    """Execute the scrape pipeline.

    Args:
        config:          Loaded YAML config dict.
        dry_run:         If True, list pages but write no files.
        output_override: Override the ``output_dir`` from config.
        page_filter:     If set, only scrape pages whose prettyUrl ends with this string.
    """
    _validate_config(config)

    catalogs: list[Catalog] = []

    def catalog_factory(host: str) -> Catalog:
        catalogs.append(Catalog([host], lambda h: FluidtopicsClient(h)))
        return catalogs[0]

    host, map_id = _resolve_target(config, catalog_factory)
    output_dir = Path(output_override or config["output_dir"])

    log.info("Config  : %s", config.get("name", "unnamed"))
    log.info("Host    : %s", host)
    log.info("Map ID  : %s", map_id)
    log.info("Output  : %s", output_dir)

    # Reuse the catalog's client (shared throttle) for the url form.
    with catalogs[0].client(host) if catalogs else FluidtopicsClient(host) as client:

        # ---- Step 1: fetch TOC ----
        log.info("Fetching TOC…")
        pages_response = client.get_pages(map_id)
        root: TocPage = parse_toc(pages_response)
        total = sum(1 for p in iter_pages(root) if p.content_id)
        log.info("TOC loaded — %d pages found", total)

        # ---- Step 2: apply page filter ----
        # Resolve paths over the full TOC so collision suffixes don't depend on --page.
        all_pages = [p for p in iter_pages(root) if p.content_id]  # skips the synthetic root
        targets = list(zip(all_pages, resolve_output_paths(all_pages, output_dir), strict=True))
        if page_filter:
            targets = [(p, path) for p, path in targets if p.pretty_url.endswith(page_filter)]
            if not targets:
                log.error(
                    "No pages matched filter '%s'. "
                    "Use --dry-run without --page to list all available prettyUrls.",
                    page_filter,
                )
                sys.exit(1)
            log.info("Filter applied — scraping %d matching page(s)", len(targets))

        # ---- Dry run: just list pages ----
        if dry_run:
            log.info("DRY RUN — pages that would be scraped:")
            for page, out_path in targets:
                indent = "  " * page.depth
                log.info("%s[%s] %s → %s", indent, page.content_id, page.title, out_path)
            return

        # ---- Step 3: fetch & write each page ----
        failed: list[str] = []
        for i, (page, out_path) in enumerate(targets, start=1):
            log.info("[%d/%d] %s", i, len(targets), page.title)
            try:
                html = fetch_html(client, map_id, page.content_id)
                markdown = html_to_markdown(html, page.title)
                write_page(out_path, markdown)
            except Exception as exc:  # noqa: BLE001
                log.error("  ✗ Failed: %s", exc)
                failed.append(page.title)

    # ---- Summary ----
    log.info("─" * 60)
    log.info("Done. Output written to: %s", output_dir.resolve())
    if failed:
        log.warning("%d page(s) failed:", len(failed))
        for title in failed:
            log.warning("  - %s", title)
    else:
        log.info("All pages scraped successfully.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="siemens-docs-export",
        description="Scrape Fluidtopics documentation sites to a Markdown folder tree.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Path to the YAML site configuration file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pages and their output paths without writing any files.",
    )
    parser.add_argument(
        "--output",
        metavar="DIR",
        help="Override the output_dir defined in the config.",
    )
    parser.add_argument(
        "--page",
        metavar="SUFFIX",
        help=(
            "Scrape only pages whose prettyUrl ends with SUFFIX. "
            "Useful for testing a single page. "
            "Example: --page cybersecurity-information"
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.config.exists():
        log.error("Config file not found: %s", args.config)
        sys.exit(1)

    config = _load_config(args.config)

    try:
        run(
            config,
            dry_run=args.dry_run,
            output_override=args.output,
            page_filter=args.page,
        )
    except ValueError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
