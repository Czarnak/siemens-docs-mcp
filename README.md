# docs-scraper

A CLI tool that converts Fluidtopics-based documentation portals into a structured tree of Markdown files — one file per page, folders mirroring the navigation hierarchy.

Built to solve the problem of documentation portals (e.g. Siemens TIA Portal) that only offer low-quality PDF exports or JavaScript-rendered web views, making the content difficult to search, reference, or feed to AI tools.

---

## How it works

Fluidtopics (the platform behind `docs.tia.siemens.cloud` and similar portals) exposes a REST API that the browser SPA uses internally. This tool calls that API directly:

1. **Fetch TOC** — `GET /api/khub/maps/{mapId}/pages` returns the full navigation tree with titles and URLs.
2. **Fetch content** — `GET /api/khub/maps/{mapId}/topics/{contentId}/content` returns raw HTML per page.
3. **Convert** — HTML is converted to Markdown using [markdownify](https://github.com/matthewwithanm/python-markdownify).
4. **Write** — Files are written to disk following the URL hierarchy.

No browser automation is required.

---

## Installation

```bash
git clone https://github.com/your-org/docs-scraper.git
cd docs-scraper
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
# development (pytest, ruff, pip-audit; needs pip >= 25.1):
pip install -e . --group dev
```

Requires Python 3.11+.

---

## Usage

```bash
# Scrape everything
python main.py configs/siemens_tia_openness_v21.yaml

# Preview pages without writing files
python main.py configs/siemens_tia_openness_v21.yaml --dry-run

# Scrape a single page (for testing output quality)
python main.py configs/siemens_tia_openness_v21.yaml --page cybersecurity-information

# Override the output directory
python main.py configs/siemens_tia_openness_v21.yaml --output /tmp/docs

# Verbose logging
python main.py configs/siemens_tia_openness_v21.yaml --verbose
```

Output is written to the directory defined in the config (default: `output/siemens_tia_openness_v21/`).

---

## Output structure

The folder structure mirrors the documentation URL hierarchy:

```
output/siemens_tia_openness_v21/
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

---

## Adding a new documentation site

Create a config with any reader URL of the publication (a topic URL exports the whole publication):

```yaml
# configs/my_new_docs.yaml
name: my_new_docs
url: "https://docs.example.com/r/en/my-documentation"
output_dir: "output/my_new_docs"
```

```bash
python main.py configs/my_new_docs.yaml --dry-run   # verify pages found
python main.py configs/my_new_docs.yaml             # scrape
```

The legacy form (`api_base` + `map_id` + `output_dir`) still works; if both forms are present, `url` wins.

> **Note:** This tool currently supports Fluidtopics-based documentation portals only. Other platforms (MadCap Flare, Paligo, etc.) would require a different adapter.

---

## Configuration reference

| Key          | Required | Description                                                                 |
|--------------|----------|-----------------------------------------------------------------------------|
| `name`       | No       | Human-readable label shown in log output.                                   |
| `url`        | Yes*     | Any reader URL of the publication (resolved to its map automatically).      |
| `api_base`   | Yes*     | Legacy: root URL of the Fluidtopics instance (use with `map_id`).           |
| `map_id`     | Yes*     | Legacy: Fluidtopics map identifier (use with `api_base`).                   |
| `output_dir` | Yes      | Directory where Markdown files will be written.                             |

\* Either `url`, or `api_base` + `map_id`.

---

## MCP server

The same package ships an MCP server (stdio) that lets an AI assistant search and read Siemens documentation on demand.

```bash
pip install -e .          # installs the `siemens-docs-mcp` console script
claude mcp add siemens-docs -- <repo>/.venv/Scripts/siemens-docs-mcp
# Linux/macOS: <repo>/.venv/bin/siemens-docs-mcp
```

Tools:

| Tool                | Purpose                                                                   |
|---------------------|---------------------------------------------------------------------------|
| `search_docs`       | Full-text search (filter by `product`, `version`, `locale`, `host`).      |
| `read_page`         | Read one page as Markdown; page through long pages with `offset`.         |
| `get_toc`           | Table of contents of a publication or of the subtree under a topic URL.   |
| `list_publications` | List publications; discover valid `product` / `version` values.           |

Environment variables:

| Variable                     | Default  | Meaning                                                          |
|------------------------------|----------|------------------------------------------------------------------|
| `SIEMENS_DOCS_HOSTS`         | (none)   | Comma-separated extra hosts, appended to the built-in two (`docs.tia.siemens.cloud`, `docs.industrial-operations-x.siemens.cloud`). |
| `SIEMENS_DOCS_LOCALE`        | `en-US`  | Default locale for search and listings.                          |
| `SIEMENS_DOCS_MIN_INTERVAL`  | `0.3`    | Minimum seconds between requests to a host.                      |

The publication catalog and TOCs are cached in memory (not on disk), so the first call per host takes a few seconds.

Live smoke tests against the real hosts: `python -m pytest -m live`.

---

## Included configs

| Config file                          | Documentation                        | Version |
|--------------------------------------|--------------------------------------|---------|
| `siemens_tia_openness_v21.yaml`      | Siemens TIA Portal Openness API      | v21     |

---

*Created with Claude AI*
