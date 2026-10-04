import pytest
from mcp import Client

from siemens_docs_mcp.server import DEFAULT_HOSTS, Settings, build_server, load_settings

TOOLS = {"search_docs", "read_page", "get_toc", "list_publications"}


def test_load_settings_defaults():
    s = load_settings({})
    assert s == Settings(DEFAULT_HOSTS, "en-US", 0.3)


def test_load_settings_extra_hosts():
    s = load_settings({"SIEMENS_DOCS_HOSTS": " Docs.Example.com ,docs.tia.siemens.cloud,"})
    assert s.hosts == DEFAULT_HOSTS + ("docs.example.com",)


@pytest.mark.parametrize("bad", ["-1", "abc", "inf", "nan"])
def test_load_settings_bad_interval(bad):
    with pytest.raises(ValueError):
        load_settings({"SIEMENS_DOCS_MIN_INTERVAL": bad})


@pytest.fixture
def server(catalog):
    return build_server(catalog, Settings(DEFAULT_HOSTS, "en-US", 0.0))


@pytest.mark.anyio
async def test_tools_registered(server):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    assert all("docs.tia.siemens.cloud" in (t.description or "") for t in tools)


@pytest.mark.anyio
async def test_unknown_host_is_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool("read_page", {"url": "https://evil.example/r/x"})
    assert result.is_error
    assert "docs.tia.siemens.cloud" in result.content[0].text


@pytest.mark.anyio
async def test_search_defaults_host_and_locale(server, fake_tia):
    async with Client(server) as client:
        result = await client.call_tool("search_docs", {"query": "x"})
    assert not result.is_error
    assert fake_tia.search_calls[0]["locale"] == "en-US"


@pytest.mark.anyio
async def test_descriptions_list_configured_hosts(catalog):
    settings = Settings((*DEFAULT_HOSTS, "docs.example.com"), "en-US", 0.0)
    async with Client(build_server(catalog, settings)) as client:
        tools = (await client.list_tools()).tools
    assert all("docs.example.com" in (t.description or "") for t in tools)


@pytest.mark.anyio
async def test_unexpected_error_names_exception_type(server):
    """tia1 has no TOC in the fake, so get_pages raises a bare KeyError (stand-in for API shape drift)."""
    async with Client(server) as client:
        result = await client.call_tool("get_toc", {"url": "https://docs.tia.siemens.cloud/r/tia1"})
    assert result.is_error
    assert "KeyError" in result.content[0].text


@pytest.mark.anyio
async def test_empty_string_optional_params_are_ignored(server, fake_tia):
    empty = {"host": "", "product": "", "version": "", "locale": ""}
    async with Client(server) as client:
        pubs = await client.call_tool("list_publications", {**empty, "title_contains": ""})
        hits = await client.call_tool("search_docs", {"query": "x", **empty})
    assert not pubs.is_error, pubs.content[0].text
    assert "STEP 7 Basic" in pubs.content[0].text
    assert not hits.is_error, hits.content[0].text
    assert fake_tia.search_calls[0]["locale"] == "en-US"
