from importlib.metadata import entry_points


def test_console_scripts_point_into_package():
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts["siemens-docs-mcp"] == "siemens_docs_mcp.server:main"
    assert scripts["siemens-docs-export"] == "siemens_docs_mcp.cli:main"
