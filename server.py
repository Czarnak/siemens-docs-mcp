"""MCP server exposing Fluid Topics documentation tools (stdio)."""
from __future__ import annotations

import logging
import math
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from scraper import tools
from scraper.catalog import Catalog, CatalogError
from scraper.client import FluidtopicsClient, FluidtopicsError

log = logging.getLogger(__name__)

DEFAULT_HOSTS = ("docs.tia.siemens.cloud", "docs.industrial-operations-x.siemens.cloud")
DEFAULT_LOCALE = "en-US"
DEFAULT_MIN_INTERVAL = 0.3

_URL_DOC = "Reader URLs from any search result, TOC line or page link are valid input."
_FILTER_DOC = (
    "`product` (e.g. 'STEP 7', 'WinCC Unified', 'SIMATIC AX') and `version` (e.g. 'V21', '6.1') "
    "are matched against the catalog; call list_publications to see valid values."
)


@dataclass(frozen=True)
class Settings:
    hosts: tuple[str, ...]
    locale: str
    min_interval: float


def load_settings(env: Mapping[str, str]) -> Settings:
    extra = (h.strip().lower() for h in env.get("SIEMENS_DOCS_HOSTS", "").split(","))
    hosts = tuple(dict.fromkeys([*DEFAULT_HOSTS, *(h for h in extra if h)]))
    raw = env.get("SIEMENS_DOCS_MIN_INTERVAL", str(DEFAULT_MIN_INTERVAL))
    try:
        interval = float(raw)
    except ValueError:
        raise ValueError(f"SIEMENS_DOCS_MIN_INTERVAL must be a number, got {raw!r}") from None
    if not (math.isfinite(interval) and interval >= 0):
        raise ValueError(f"SIEMENS_DOCS_MIN_INTERVAL must be >= 0, got {raw!r}")
    return Settings(hosts, env.get("SIEMENS_DOCS_LOCALE", DEFAULT_LOCALE), interval)


@contextmanager
def _tool_errors() -> Iterator[None]:
    """Map expected failures to ToolError so the message reaches the agent without a traceback."""
    try:
        yield
    except (CatalogError, FluidtopicsError, ValueError) as exc:
        raise ToolError(str(exc)) from None
    except Exception as exc:  # API shape drift etc.: name the failure instead of a bare "Error executing tool"
        log.exception("Unexpected tool failure")
        raise ToolError(f"Unexpected error ({type(exc).__name__}): {exc}") from None


def build_server(catalog: Catalog, settings: Settings) -> MCPServer:
    hosts_doc = f"Allowed hosts: {', '.join(settings.hosts)} (default: {settings.hosts[0]})."
    server = MCPServer("siemens-docs-mcp")

    @server.tool(description=(
        f"""Full-text search of Siemens documentation. Returns a numbered Markdown list (1-50 hits via `limit`):
        title, publication + version, breadcrumb, excerpt and reader URL, with the total hit count.
        Pass a result's reader URL to read_page or get_toc. {_FILTER_DOC} {hosts_doc}"""
    ))
    def search_docs(
        query: str,
        host: str | None = None,
        product: str | None = None,
        version: str | None = None,
        locale: str | None = None,
        limit: int = 10,
    ) -> str:
        with _tool_errors():
            return tools.search_docs(
                catalog, query, host or settings.hosts[0], locale or settings.locale, product, version, limit
            )

    @server.tool(description=(
        f"""Read one documentation page as Markdown, with a header (publication, version, breadcrumb, source URL).
        If the page is longer than `max_chars`, the end says how to continue with a larger `offset`.
        {_URL_DOC} {hosts_doc}"""
    ))
    def read_page(url: str, offset: int = 0, max_chars: int = 20000) -> str:
        with _tool_errors():
            return tools.read_page(catalog, url, offset, max_chars)

    @server.tool(description=(
        f"""Show the table of contents (1-6 levels via `depth`) of the publication, or of the subtree under the
        topic, in `url`: an indented outline, one line per node with title and reader URL.
        {_URL_DOC} {hosts_doc}"""
    ))
    def get_toc(url: str, depth: int = 2) -> str:
        with _tool_errors():
            return tools.get_toc(catalog, url, depth)

    @server.tool(description=(
        f"""List documentation publications (up to 50 rows): title, product, version, locale and reader URL.
        Use it to discover valid `product` and `version` values; reader URLs are valid input to read_page and
        get_toc. {_FILTER_DOC} {hosts_doc}"""
    ))
    def list_publications(
        host: str | None = None,
        product: str | None = None,
        version: str | None = None,
        locale: str | None = None,
        title_contains: str | None = None,
    ) -> str:
        with _tool_errors():
            return tools.list_publications(
                catalog, host or settings.hosts[0], locale or settings.locale, product, version, title_contains
            )

    return server


def main() -> None:
    settings = load_settings(os.environ)
    catalog = Catalog(settings.hosts, lambda h: FluidtopicsClient(h, settings.min_interval))
    build_server(catalog, settings).run()


if __name__ == "__main__":
    main()
