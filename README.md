# Siemens Docs MCP

An MCP server that lets an AI assistant search and read Siemens documentation live — any publication on `docs.tia.siemens.cloud` (TIA Portal, STEP 7, WinCC Unified, Openness, …) and `docs.industrial-operations-x.siemens.cloud` (Industrial Operations X) — plus a CLI that exports a whole publication to a tree of Markdown files.

Built to solve the problem of documentation portals that only offer low-quality PDF exports or JavaScript-rendered web views, making the content difficult to search, reference, or feed to AI tools.

---

## Installation

### PyPI

```bash
pip install siemens-docs-mcp
```

This installs two commands: `siemens-docs-mcp` (the MCP server) and `siemens-docs-export` (the Markdown exporter). Requires Python 3.11+.

### From source

```bash
git clone https://github.com/Czarnak/siemens-docs-mcp
cd siemens-docs-mcp
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
# development (pytest, ruff, pip-audit; needs pip >= 25.1):
pip install -e . --group dev
```

---

## MCP server

The server speaks MCP over stdio. Register it with Claude Code:

```bash
# from PyPI, no manual install (needs uv)
claude mcp add siemens-docs -- uvx siemens-docs-mcp

# or an installed copy
claude mcp add siemens-docs -- siemens-docs-mcp
# from a source checkout: <repo>/.venv/Scripts/siemens-docs-mcp  (Linux/macOS: <repo>/.venv/bin/siemens-docs-mcp)
```

Pass settings with `-e`, e.g. `claude mcp add siemens-docs -e SIEMENS_DOCS_LOCALE=de-DE -- uvx siemens-docs-mcp`.

Tools:

| Tool                | Purpose                                                                   |
|---------------------|---------------------------------------------------------------------------|
| `search_docs`       | Full-text search (filter by `product`, `version`, `locale`, `host`).      |
| `read_page`         | Read one page as Markdown; page through long pages with `offset`.         |
| `get_toc`           | Table of contents of a publication or of the subtree under a topic URL.   |
| `list_publications` | List publications; discover valid `product` / `version` values.           |

Any reader URL returned by a tool (or copied from the browser) is valid input to `read_page` and `get_toc`.

Environment variables:

| Variable                     | Default  | Meaning                                                          |
|------------------------------|----------|------------------------------------------------------------------|
| `SIEMENS_DOCS_HOSTS`         | (none)   | Comma-separated extra hosts, appended to the built-in two (`docs.tia.siemens.cloud`, `docs.industrial-operations-x.siemens.cloud`). |
| `SIEMENS_DOCS_LOCALE`        | `en-US`  | Default locale for search and listings.                          |
| `SIEMENS_DOCS_MIN_INTERVAL`  | `0.3`    | Minimum seconds between requests to a host.                      |

The publication catalog and TOCs are cached in memory (not on disk), so the first call per host takes a few seconds.

---

## Markdown export (CLI)

Export a whole publication to Markdown — one file per page, folders mirroring the navigation hierarchy. Create a config with any reader URL of the publication (a topic URL exports the whole publication):

```yaml
# my_docs.yaml
name: tia_openness_v21
url: "https://docs.tia.siemens.cloud/r/en-us/v21/tia-portal-openness-api-for-automation-of-engineering-workflows"
output_dir: "output/tia_openness_v21"
```

```bash
# Preview pages without writing files
siemens-docs-export my_docs.yaml --dry-run

# Export everything
siemens-docs-export my_docs.yaml

# Export a single page (for testing output quality)
siemens-docs-export my_docs.yaml --page cybersecurity-information

# Override the output directory / verbose logging
siemens-docs-export my_docs.yaml --output /tmp/docs --verbose
```

A ready-made config lives in [`configs/`](https://github.com/Czarnak/siemens-docs-mcp/tree/main/configs) in the repository.

### Output structure

```
output/tia_openness_v21/
├── index.md                          ← root page
├── cybersecurity-information.md
├── what-s-new-in-tia-portal-openness.md
├── basics/
│   ├── basics.md
│   └── ...
├── tia-portal-openness-api/
│   ├── tia-portal-openness-object/
│   │   └── ...
│   └── ...
└── ...
```

### Configuration reference

| Key          | Required | Description                                                                 |
|--------------|----------|-----------------------------------------------------------------------------|
| `name`       | No       | Human-readable label shown in log output.                                   |
| `url`        | Yes*     | Any reader URL of the publication (resolved to its map automatically).      |
| `api_base`   | Yes*     | Legacy: root URL of the Fluidtopics instance (use with `map_id`).           |
| `map_id`     | Yes*     | Legacy: Fluidtopics map identifier (use with `api_base`).                   |
| `output_dir` | Yes      | Directory where Markdown files will be written.                             |

\* Either `url`, or `api_base` + `map_id`. If both are present, `url` wins.

---

## How it works

Fluidtopics (the platform behind both portals) exposes a REST API that the browser SPA uses internally. This package calls that API directly — no browser automation:

1. **Catalog** — `GET /api/khub/maps` lists every publication; reader URLs are resolved against it.
2. **Search** — `POST /api/khub/clustered-search` with product/version/locale filters.
3. **TOC** — `GET /api/khub/maps/{mapId}/pages` returns the navigation tree.
4. **Content** — `GET /api/khub/maps/{mapId}/topics/{contentId}/content` returns raw HTML, converted to Markdown with [markdownify](https://github.com/matthewwithanm/python-markdownify).

Requests are throttled per host and retried once on 401/403/429/5xx.

> **Note:** Only Fluidtopics-based portals are supported. Other platforms (MadCap Flare, Paligo, etc.) would need a different adapter.

---

## Development

```bash
python -m pytest -q          # offline tests
python -m pytest -m live -q  # live smoke tests against the real hosts
ruff check .
```

---

*Created with Claude AI*
