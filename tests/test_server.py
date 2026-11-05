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
    for tool in tools:
        properties = tool.input_schema["properties"]
        assert properties["reference_format"]["enum"] == ["compact", "url"]
        assert properties["reference_format"]["default"] == "compact"
        if tool.name in {"read_page", "get_toc"}:
            assert "url" in tool.input_schema["required"]
            assert "ref" not in properties


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


@pytest.mark.anyio
@pytest.mark.parametrize("name,args", [
    ("search_docs", {"query": "x"}), ("list_publications", {}),
    ("read_page", {"url": "tia:tia2/t-p1"}), ("get_toc", {"url": "tia:tia2"}),
])
async def test_mcp_reference_formats(server, fake_tia, name, args):
    from tests.conftest import make_hit, make_search_response

    fake_tia.search_response = make_search_response([make_hit()])
    async with Client(server) as client:
        compact = await client.call_tool(name, args)
        url = await client.call_tool(name, {**args, "reference_format": "url"})
    assert not compact.is_error, compact.content[0].text
    assert not url.is_error, url.content[0].text
    assert "tia:tia2" in compact.content[0].text
    assert "https://docs.tia.siemens.cloud/r/" in url.content[0].text


@pytest.mark.anyio
async def test_invalid_format_rejected_before_fetch(server, fake_tia, fake_iox):
    async with Client(server) as client:
        result = await client.call_tool("read_page", {"url": "tia:tia2", "reference_format": "json"})
    assert result.is_error
    assert "reference_format" in result.content[0].text
    for fake in (fake_tia, fake_iox):
        assert fake.list_maps_calls == 0
        assert fake.search_calls == fake.get_pages_calls == fake.get_content_calls == []


@pytest.mark.anyio
async def test_search_scope_selects_host_and_locale(server, fake_tia, fake_iox):
    """Without scope the default host (tia) would be searched; the scope must win."""
    from tests.conftest import make_hit, make_search_response

    fake_iox.search_response = make_search_response([make_hit(map_id="iox1", content_id="iox1-p1")])
    empty = {"host": "", "product": "", "version": "", "locale": ""}
    async with Client(server) as client:
        result = await client.call_tool("search_docs", {"query": "x", "scope": "iox:iox1", **empty})
    assert not result.is_error, result.content[0].text
    assert fake_tia.search_calls == []
    assert fake_iox.search_calls[0]["filters"] == [{"key": "ft:publicationId", "values": ["iox1"]}]
    assert fake_iox.search_calls[0]["locale"] == "en-US"
    assert "iox:iox1/iox1-p1" in result.content[0].text


@pytest.mark.anyio
async def test_search_scope_conflict_is_tool_error(server, fake_tia):
    async with Client(server) as client:
        result = await client.call_tool("search_docs", {"query": "x", "scope": "iox:iox1", "host": "docs.tia.siemens.cloud"})
    assert result.is_error
    assert "host" in result.content[0].text


@pytest.mark.anyio
async def test_search_scope_uses_publication_locale_not_server_default(server, fake_tia):
    """tia5 is de-DE while the server default is en-US: the scope's locale must win."""
    from tests.conftest import make_hit, make_search_response

    fake_tia.search_response = make_search_response([make_hit(map_id="tia5", content_id="x")])
    async with Client(server) as client:
        result = await client.call_tool("search_docs", {"query": "x", "scope": "tia:tia5"})
    assert not result.is_error, result.content[0].text
    assert fake_tia.search_calls[0]["locale"] == "de-DE"


@pytest.mark.anyio
async def test_read_page_reading_mode_schema(server, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = (
        '<p class="Blocktitle">A</p><p>a</p><p class="Blocktitle">B</p><pre>b()</pre>'
    )
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        properties = tools["read_page"].input_schema["properties"]
        assert properties["mode"]["enum"] == ["full", "outline", "code"]
        assert properties["mode"]["default"] == "full"
        assert {option.get("type") for option in properties["section"]["anyOf"]} >= {"integer", "string"}
        as_int = await client.call_tool("read_page", {"url": "tia:tia2/tia2-p1", "section": 2})
        as_str = await client.call_tool("read_page", {"url": "tia:tia2/tia2-p1", "section": "2"})
        outline = await client.call_tool("read_page", {"url": "tia:tia2/tia2-p1", "mode": "outline"})
    assert not as_int.is_error and as_int.content[0].text == as_str.content[0].text
    assert "## B" in as_int.content[0].text and "## A" not in as_int.content[0].text
    assert "Outline (2 sections" in outline.content[0].text
    assert "outline" in (tools["read_page"].description or "")
