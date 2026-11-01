# Contributing

Contributions are welcome. This project has two entry points built on one shared core: an MCP
server (`siemens-docs-mcp`) and a Markdown exporter (`siemens-docs-export`). The
[README](README.md) describes both; the sections below cover working on the code.

## Development setup

Python 3.11 or newer is required. Clone the repository, create a virtual environment, and install
the package with the dev dependency group (pytest, pytest-cov, ruff, pip-audit; this needs
pip 25.1 or newer):

```bash
git clone https://github.com/Czarnak/siemens-docs-mcp
cd siemens-docs-mcp
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e . --group dev
```

The repository also has a `uv.lock`; if you use [uv](https://docs.astral.sh/uv/), `uv sync` works
as well.

## Project layout

| Path | Covers |
| --- | --- |
| `siemens_docs_mcp/server.py`, `tools.py` | The MCP server and the four tools (`search_docs`, `read_page`, `get_toc`, `list_publications`) |
| `siemens_docs_mcp/cli.py`, `writer.py`, `configs/` | The `siemens-docs-export` command, its YAML config, and the Markdown file writer |
| `siemens_docs_mcp/converter.py`, `content.py` | HTML cleaning and HTML-to-Markdown conversion |
| `siemens_docs_mcp/client.py`, `catalog.py`, `toc.py` | The Fluid Topics HTTP client, the per-host publication catalog, and TOC parsing |
| `tests/` | pytest suite; HTML samples used by the converter tests live in `tests/fixtures/` |

## Making changes

- Branch from `main` and keep each change focused on a single feature or bug fix.
- Add or update tests for new or changed behavior. Tests run offline against fixtures and fakes;
  nothing in the default test run touches the network.
- If you change a tool's name, parameters, or output, or an environment variable or config key,
  update the matching table in the README in the same pull request.
- `README.md` is also the PyPI project description, where relative links do not resolve. Every
  link from the README to another file in the repository must be an absolute
  `https://github.com/Czarnak/siemens-docs-mcp/blob/main/...` URL.
- Keep exported Siemens documentation out of the repository. Test fixtures should be the smallest
  HTML snippet that reproduces the case.

## Testing

Run these before opening a pull request. They are the same checks CI runs:

```bash
ruff check .
python -m pytest -q
```

CI (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request against it:
lint, tests, `pip-audit` on the dependencies, and a smoke test of `siemens-docs-export --help`.
The release workflow additionally requires 80% line coverage:

```bash
python -m pytest -q --cov=siemens_docs_mcp --cov-report=term-missing --cov-fail-under=80
```

### Live tests

`tests/test_live.py` talks to the real documentation hosts. It is excluded from the default run,
so CI never depends on those sites being reachable. When you change the client, catalog, or
content handling, run it once yourself and say so in the pull request:

```bash
python -m pytest -m live
```

## Commit messages

Use conventional commit style:

- `feat:` – new feature
- `fix:` – bug fix
- `refactor:` – code restructuring without behavior change
- `perf:` – performance improvement
- `test:` – test-only changes
- `docs:` – documentation changes
- `build:` – packaging, `pyproject.toml`, or dependency changes
- `ci:` – GitHub Actions workflow changes
- `chore:` – other maintenance, such as version bumps

Format: `<type>(<scope>): <description>`. The scope is optional and names the part of the
codebase the change is about. Prefer the area names used for issue and PR labels:

| Scope | Covers |
| --- | --- |
| `mcp-server` | The MCP server and its tools |
| `export-cli` | `siemens-docs-export`, its config, and the file writer |
| `converter` | HTML cleaning and HTML-to-Markdown conversion |
| `client` | Fluid Topics client, publication catalog, TOC parsing |

Examples:

- `feat(mcp-server): add a locale filter to list_publications`
- `fix(converter): keep code block indentation inside nested lists`
- `ci: group release notes by label`

## Opening a pull request

1. Fork the repository and push your branch.
2. Open a pull request against `main`, with a title in the commit message format above.
3. Fill in the pull request template: what changed and why, how it was verified, and whether it
   changes a tool's contract or the documentation.

Labels are added automatically. Area labels (`area: mcp-server`, `area: export-cli`,
`area: converter`, `area: client`) come from the paths the pull request changes. `enhancement` and
`bug` come from a `feat:` or `fix:` title prefix. Release notes are grouped by these labels, so a
correct title prefix puts your change under the right heading.

## Reporting bugs or requesting features

Open an issue with one of the [issue forms](https://github.com/Czarnak/siemens-docs-mcp/issues/new/choose):
bug report, feature request, or documentation issue.

## Reporting security vulnerabilities

Do not file security issues as public GitHub issues. Report them privately through a
[security advisory](https://github.com/Czarnak/siemens-docs-mcp/security/advisories/new).
