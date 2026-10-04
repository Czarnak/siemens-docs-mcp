import logging

import pytest

from siemens_docs_mcp import cli
from siemens_docs_mcp.catalog import Catalog
from tests.conftest import IOX_HOST, TIA_HOST

URL = f"https://{TIA_HOST}/r/en-us/v21/doc"


def test_validate_config_accepts_url_form():
    cli._validate_config({"url": URL, "output_dir": "o"})


def test_validate_config_accepts_legacy_form():
    cli._validate_config({"api_base": f"https://{TIA_HOST}", "map_id": "m", "output_dir": "o"})


def test_validate_config_rejects_neither():
    with pytest.raises(ValueError, match=r"url.*api_base \+ map_id"):
        cli._validate_config({"output_dir": "o"})


def test_validate_config_requires_output_dir():
    with pytest.raises(ValueError, match="output_dir"):
        cli._validate_config({"url": URL})


def _factory(fake_tia, fake_iox):
    clients = {TIA_HOST: fake_tia, IOX_HOST: fake_iox}
    seen: list[str] = []

    def factory(host: str) -> Catalog:
        seen.append(host)
        return Catalog([host], lambda h: clients[h])

    return factory, seen


def test_resolve_target_from_url(fake_tia, fake_iox):
    factory, seen = _factory(fake_tia, fake_iox)
    assert cli._resolve_target({"url": URL}, factory) == (TIA_HOST, "tia2")
    assert seen == [TIA_HOST]


def test_resolve_target_topic_url_warns(fake_tia, fake_iox, caplog):
    factory, _ = _factory(fake_tia, fake_iox)
    with caplog.at_level(logging.WARNING):
        host, map_id = cli._resolve_target({"url": f"{URL}/chapter-1/page-1"}, factory)
    assert (host, map_id) == (TIA_HOST, "tia2")
    assert "whole publication" in caplog.text


def test_resolve_target_legacy_builds_no_catalog():
    def boom(_host):
        raise AssertionError("no catalog expected")

    cfg = {"api_base": f"https://{TIA_HOST}", "map_id": "m1"}
    assert cli._resolve_target(cfg, boom) == (TIA_HOST, "m1")


def test_resolve_target_url_wins_over_legacy(fake_tia, fake_iox):
    factory, _ = _factory(fake_tia, fake_iox)
    cfg = {"url": URL, "api_base": f"https://{IOX_HOST}", "map_id": "zzz"}
    assert cli._resolve_target(cfg, factory) == (TIA_HOST, "tia2")
