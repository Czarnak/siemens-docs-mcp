<!--
PR title: use a conventional commit, for example `feat(mcp-server): add a locale filter`.
Types and scopes are listed in CONTRIBUTING.md.

Tick every box that is true. In "Tool contract and docs impact", delete the items
that do not apply instead of leaving them unticked.
-->

## Summary

<!-- What changed and why. Describe the design here. -->

## Related issue

<!-- `Closes #123` closes the issue when this PR merges; `Refs #123` only links it. -->

## Type of change

- [ ] `feat`: new feature
- [ ] `fix`: bug fix
- [ ] `refactor`: restructuring without behavior change
- [ ] `perf`: performance improvement
- [ ] `test`: test-only change
- [ ] `docs`: documentation only
- [ ] `build`: `pyproject.toml`, dependencies, or packaging
- [ ] `ci`: GitHub Actions workflows
- [ ] `chore`: other maintenance
- [ ] **Breaking change**: changes a tool's name, parameters, or output, an environment variable, or a config key (migration notes are in the Summary)

## Components touched

- [ ] MCP server and tools (`server.py`, `tools.py`)
- [ ] Export CLI (`cli.py`, `writer.py`, `configs/`)
- [ ] Converter (`converter.py`, `content.py`)
- [ ] Client and catalog (`client.py`, `catalog.py`, `toc.py`)
- [ ] Tests (`tests/`)
- [ ] Documentation (`README.md`, `docs/`)
- [ ] CI, packaging, or dependencies (`.github/`, `pyproject.toml`, `uv.lock`)

## Verification

- [ ] `ruff check .` passes
- [ ] `python -m pytest -q` passes locally
- [ ] New or changed behavior is covered by tests

Live check against the real documentation hosts (tick one):

- [ ] `python -m pytest -m live` passes. Hosts reached: <!-- e.g. docs.tia.siemens.cloud -->
- [ ] Not run; the change does not touch the client, catalog, or content handling
- [ ] Not run; the hosts were unreachable. Reviewer, please verify

## Tool contract and docs impact

<!-- Delete the items that do not apply. -->

- [ ] No change to any MCP tool's name, parameters, or output format
- [ ] Tool contract changed: migration notes are in the Summary and the README tool table is updated
- [ ] Environment variable or config key added or changed: documented in the README
- [ ] New runtime dependency: added to `pyproject.toml` and `uv.lock`, and `pip-audit` is clean
- [ ] Links added to `README.md` are absolute `https://github.com/Czarnak/siemens-docs-mcp/blob/main/...` URLs
- [ ] No exported Siemens documentation is committed beyond minimal test fixtures

## Notes for the reviewer

<!-- Risky parts, anything you are unsure about, and follow-ups deliberately left out of this PR. -->
