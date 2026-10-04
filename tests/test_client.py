import json

import httpx
import pytest

from scraper.client import FluidtopicsClient, FluidtopicsError

SESSION = "/internal/api/webapp/authentication/session"


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def make(handler, interval=0.3):
    fc = FakeClock()
    client = FluidtopicsClient(
        "docs.example.com", interval,
        transport=httpx.MockTransport(handler), clock=fc.clock, sleep=fc.sleep,
    )
    return client, fc


def test_throttle_spaces_requests():
    client, fc = make(lambda r: httpx.Response(200, json={}))
    client.get_pages("m1")
    client.get_pages("m1")
    assert fc.sleeps == pytest.approx([0.3, 0.3])


def test_host_and_https():
    seen = []
    client, _ = make(lambda r: seen.append(str(r.url)) or httpx.Response(200, json=[]))
    assert client.host == "docs.example.com"
    client.list_maps()
    assert seen[-1] == "https://docs.example.com/api/khub/maps"


def test_search_body_shape():
    bodies = []

    def handler(r):
        if r.url.path.endswith("clustered-search"):
            bodies.append(json.loads(r.content))
        return httpx.Response(200, json={})

    client, _ = make(handler)
    client.search("q", "en-US")
    client.search("q", "en-US", filters=[{"key": "k", "values": ["v"]}])
    assert bodies[0] == {"query": "q", "contentLocale": "en-US", "paging": {"page": 1, "perPage": 10}}
    assert bodies[1]["filters"] == [{"key": "k", "values": ["v"]}]


def test_401_reestablishes_session_once():
    calls = {"session": 0, "content": 0}

    def handler(r):
        if r.url.path == SESSION:
            calls["session"] += 1
            return httpx.Response(200)
        calls["content"] += 1
        return httpx.Response(401 if calls["content"] == 1 else 200, text="<p>x</p>")

    client, _ = make(handler)
    assert client.get_content("m", "c") == "<p>x</p>"
    assert calls["session"] == 2


def test_403_twice_raises():
    client, _ = make(lambda r: httpx.Response(200 if r.url.path == SESSION else 403))
    with pytest.raises(FluidtopicsError) as e:
        client.get_pages("m")
    assert e.value.status == 403


def _flaky(retry_after, statuses):
    it = iter(statuses)

    def handler(r):
        if r.url.path == SESSION:
            return httpx.Response(200)
        h = {"Retry-After": retry_after} if retry_after else {}
        return httpx.Response(next(it), headers=h, json={})

    return handler


def test_429_honours_retry_after():
    client, fc = make(_flaky("5", [429, 200]))
    client.get_pages("m")
    assert 5.0 in fc.sleeps


def test_retry_after_capped_at_30():
    client, fc = make(_flaky("120", [429, 200]))
    client.get_pages("m")
    assert 30.0 in fc.sleeps


def test_http_date_retry_after_falls_back():
    client, fc = make(_flaky("Wed, 21 Oct 2026 07:28:00 GMT", [503, 200]))
    client.get_pages("m")
    assert 2.0 in fc.sleeps


def test_503_then_fail_raises():
    client, fc = make(_flaky(None, [503, 503]))
    with pytest.raises(FluidtopicsError) as e:
        client.get_pages("m")
    assert e.value.status == 503
    assert 2.0 in fc.sleeps


def test_session_failure_raises():
    client, _ = make(lambda r: httpx.Response(500))
    with pytest.raises(FluidtopicsError) as e:
        client.get_pages("m")
    assert e.value.status == 500


def test_network_error_wrapped():
    def handler(r):
        raise httpx.ConnectError("boom")

    client, _ = make(handler)
    with pytest.raises(FluidtopicsError) as e:
        client.list_maps()
    assert e.value.status is None
    assert "docs.example.com" in str(e.value)
