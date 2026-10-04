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

### Step 1 — Find the `map_id`

1. Open the target documentation URL in Chrome.
2. Open DevTools → **Network** tab → filter by **`khub`**.
3. Reload the page and look for a request matching: `/api/khub/maps/{MAP_ID}/pages`
4. Copy the `MAP_ID` value.

### Step 2 — Create a config file

```yaml
# configs/my_new_docs.yaml

name: my_new_docs

base_url: "https://docs.example.com/r/en/my-documentation"
api_base: "https://docs.example.com"
map_id:   "your-map-id-here"

output_dir: "output/my_new_docs"
```

### Step 3 — Run

```bash
python main.py configs/my_new_docs.yaml --dry-run   # verify pages found
python main.py configs/my_new_docs.yaml             # scrape
```

> **Note:** This tool currently supports Fluidtopics-based documentation portals only. Other platforms (MadCap Flare, Paligo, etc.) would require a different adapter.

---

## Configuration reference

| Key          | Required | Description                                                        |
|--------------|----------|--------------------------------------------------------------------|
| `name`       | No       | Human-readable label shown in log output.                          |
| `base_url`   | Yes      | Full URL of the documentation root page.                           |
| `api_base`   | Yes      | Root URL of the Fluidtopics instance (no trailing slash).          |
| `map_id`     | Yes      | Fluidtopics map identifier (see "Adding a new site" above).        |
| `output_dir` | Yes      | Directory where Markdown files will be written.                    |

---

## Included configs

| Config file                          | Documentation                        | Version |
|--------------------------------------|--------------------------------------|---------|
| `siemens_tia_openness_v21.yaml`      | Siemens TIA Portal Openness API      | v21     |

---

*Created with Claude AI*
