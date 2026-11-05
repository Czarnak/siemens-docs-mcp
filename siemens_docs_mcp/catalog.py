"""Per-host catalog of publications (maps): listing, canonicalization, URL resolution, TOC cache."""
from __future__ import annotations

import difflib
import logging
import re
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import SplitResult, unquote, urlsplit

from siemens_docs_mcp.client import FluidtopicsClient
from siemens_docs_mcp.toc import TocPage, iter_pages, parse_toc

log = logging.getLogger(__name__)

HOST_ALIASES = {"tia": "docs.tia.siemens.cloud", "iox": "docs.industrial-operations-x.siemens.cloud"}
ReferenceFormat = Literal["compact", "url"]

TIA_VERSION_KEY = "tia:SoftwareVersionFilter"
SW_VERSION_KEY = "SoftwareVersion"
_VERSION_KEYS = (TIA_VERSION_KEY, SW_VERSION_KEY)
_CONTENT_ID = re.compile(r"[\w~.-]+")
# Image and download links in page bodies; their URLs are useless to an agent.
_ATTACHMENT_PATH = re.compile(r"/viewer/attachment/|/api/khub/maps/[^/]+/resources/")
_COMPACT_REF = re.compile(r"([\w.-]+):([\w~.-]+)(?:/([\w~.-]+))?")


class CatalogError(ValueError):
    """Raised for unknown hosts, unresolvable URLs, and unknown filter values."""


def validate_reference_format(value: str) -> ReferenceFormat:
    if value == "compact" or value == "url":
        return value
    raise ValueError(f"reference_format must be 'compact' or 'url', got {value!r}")


@dataclass(frozen=True)
class MapInfo:
    id: str
    title: str
    locale: str
    product: str
    version: str
    version_key: str
    pretty_url: str
    cluster_id: str
    last_publication: str


@dataclass(frozen=True)
class Resolved:
    host: str
    map_id: str
    content_id: str | None


def _meta(raw: dict) -> dict[str, list[str]]:
    return {m["key"]: m.get("values") or [] for m in raw.get("metadata", [])}


def _first(meta: dict[str, list[str]], key: str) -> str:
    values = meta.get(key) or []
    return values[0] if values else ""


def _map_info(raw: dict) -> MapInfo:
    meta = _meta(raw)
    version_key = next((k for k in _VERSION_KEYS if _first(meta, k)), "")
    return MapInfo(
        id=raw["id"],
        title=raw.get("title", ""),
        locale=_first(meta, "ft:locale"),
        product=_first(meta, "Product"),
        version=_first(meta, version_key) if version_key else "",
        version_key=version_key,
        pretty_url=_first(meta, "ft:prettyUrl").removeprefix("/r/"),
        cluster_id=_first(meta, "ft:clusterId"),
        last_publication=_first(meta, "ft:lastPublication"),
    )


def _split_body_url(url: str) -> SplitResult | None:
    """Parse a page-body href; None for malformed ones (e.g. "http://[IP address of the CPU]/")."""
    try:
        parts = urlsplit(url.strip())
        parts.hostname  # noqa: B018 - may raise for bracketed or invalid hosts
    except ValueError:
        return None
    return parts


class Catalog:
    def __init__(
        self,
        hosts: Sequence[str],
        client_factory: Callable[[str], FluidtopicsClient],
        ttl_seconds: float = 86400,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hosts: tuple[str, ...] = tuple(h.lower() for h in hosts)
        self._factory = client_factory
        self._ttl = ttl_seconds
        self._clock = clock
        # ponytail: global lock serializes cold catalog loads across hosts; per-host locks if that hurts
        self._lock = threading.RLock()  # re-entrant: maps()/toc() call client() while holding it
        self._clients: dict[str, FluidtopicsClient] = {}
        self._maps: dict[str, tuple[float, dict[str, MapInfo]]] = {}
        # Raw distinct version values per host per key (a map can carry both keys).
        self._versions: dict[str, dict[str, list[str]]] = {}
        # Raw version values per host per map id per key, for filter().
        self._map_versions: dict[str, dict[str, dict[str, str]]] = {}
        self._tocs: dict[tuple[str, str], tuple[float, TocPage]] = {}
        # Lower-cased pretty URLs carried by more than one map per host (ambiguous as reader URLs).
        self._shared: dict[str, set[str]] = {}

    def _check_host(self, host: str) -> str:
        host = host.lower()
        if host not in self.hosts:
            raise CatalogError(f"Host {host!r} is not allowed. Allowed hosts: {list(self.hosts)}")
        return host

    def client(self, host: str) -> FluidtopicsClient:
        host = self._check_host(host)
        with self._lock:
            if host not in self._clients:
                self._clients[host] = self._factory(host)
            return self._clients[host]

    def _fresh(self, stamp: float) -> bool:
        return self._clock() - stamp <= self._ttl

    def maps(self, host: str) -> dict[str, MapInfo]:
        host = self._check_host(host)
        with self._lock:
            cached = self._maps.get(host)
            if cached and self._fresh(cached[0]):
                return cached[1]
            raws = self.client(host).list_maps()
            infos = {m.id: m for m in map(_map_info, raws)}
            versions: dict[str, list[str]] = {k: [] for k in _VERSION_KEYS}
            per_map: dict[str, dict[str, str]] = {}
            for raw in raws:
                meta = _meta(raw)
                per_map[raw["id"]] = {}
                for key in _VERSION_KEYS:
                    v = _first(meta, key)
                    if v:
                        per_map[raw["id"]][key] = v
                        if v not in versions[key]:
                            versions[key].append(v)
            self._versions[host] = versions
            self._map_versions[host] = per_map
            counts = Counter(m.pretty_url.lower() for m in infos.values() if m.pretty_url)
            self._shared[host] = {p for p, n in counts.items() if n > 1}
            self._maps[host] = (self._clock(), infos)
            return infos

    @staticmethod
    def _unknown(host: str, label: str, value: str, known: list[str]) -> CatalogError:
        close = difflib.get_close_matches(value, known, n=5, cutoff=0.5)
        hint = f"Close matches: {close}" if close else f"Valid values include: {known[:10]}"
        return CatalogError(f"Unknown {label} {value!r} on {host}. {hint}")

    def canonical(self, host: str, field: Literal["product", "locale"], value: str) -> str:
        values = sorted({getattr(m, field) for m in self.maps(host).values()} - {""})
        for v in values:
            if v.lower() == value.lower():
                return v
        raise self._unknown(host, field, value, values)

    def canonical_version(self, host: str, value: str) -> tuple[str, str]:
        self.maps(host)
        versions = self._versions[host.lower()]
        for key in _VERSION_KEYS:
            for v in versions[key]:
                if v.lower() == value.lower():
                    return key, v
        known = sorted({v for vs in versions.values() for v in vs})
        raise self._unknown(host, "version", value, known)

    def filter(
        self,
        host: str,
        product: str | None = None,
        version: str | None = None,
        locale: str | None = None,
        title_contains: str | None = None,
    ) -> list[MapInfo]:
        result = list(self.maps(host).values())
        if product is not None:
            p = self.canonical(host, "product", product)
            result = [m for m in result if m.product == p]
        if locale is not None:
            loc = self.canonical(host, "locale", locale)
            result = [m for m in result if m.locale == loc]
        if version is not None:
            key, v = self.canonical_version(host, version)
            per_map = self._map_versions[host.lower()]
            result = [m for m in result if per_map[m.id].get(key) == v]
        if title_contains:
            needle = title_contains.lower()
            result = [m for m in result if needle in m.title.lower()]
        return sorted(result, key=lambda m: m.title)

    def toc(self, host: str, map_id: str) -> TocPage:
        key = (self._check_host(host), map_id)
        with self._lock:
            cached = self._tocs.get(key)
            if cached and self._fresh(cached[0]):
                return cached[1]
            root = parse_toc(self.client(host).get_pages(map_id))
            self._tocs[key] = (self._clock(), root)
            return root

    def resolve(self, url: str) -> Resolved:
        failure = CatalogError(
            f"Could not resolve {url}. Use search_docs or list_publications to find a valid reader URL."
        )
        value = url.strip()
        if "://" not in value and not value.startswith("//"):
            target = self._parse_compact_ref(value)
            if target.map_id not in self.maps(target.host):
                raise failure
            return target
        parts = urlsplit(url.strip())
        host = self._check_host(parts.hostname or "")
        path = unquote(parts.path).rstrip("/")
        if not path.startswith("/r/"):
            raise failure
        rel = path[3:]
        segs = rel.split("/")
        maps = self.maps(host)
        if segs[0] in maps:
            if len(segs) == 1:
                return Resolved(host, segs[0], None)
            if not _CONTENT_ID.fullmatch(segs[1]) or segs[1] in (".", ".."):
                raise failure
            return Resolved(host, segs[0], segs[1])
        low = rel.lower()
        # Several maps can share a pretty URL, and a longer prefix may lack the topic: try every
        # matching map, longest prefix first (stable on ties), until one's TOC holds the topic.
        matches = sorted(
            (
                m for m in maps.values()
                if m.pretty_url
                and (low == m.pretty_url.lower() or (low + "/").startswith(m.pretty_url.lower() + "/"))
            ),
            key=lambda m: len(m.pretty_url),
            reverse=True,
        )
        target = "/r/" + low
        for m in matches:
            if low == m.pretty_url.lower():
                return Resolved(host, m.id, None)
            for page in iter_pages(self.toc(host, m.id)):
                if page.pretty_url.lower() == target:
                    return Resolved(host, m.id, page.content_id)
        raise failure

    def _parse_compact_ref(self, value: str) -> Resolved:
        match = _COMPACT_REF.fullmatch(value)
        if not match or any(segment in (".", "..") for segment in match.groups()[1:]):
            raise CatalogError(
                f"Invalid compact reference {value!r}. Use <prefix>:<mapId>[/<contentId>]; "
                "find references with search_docs or list_publications."
            )
        prefix, map_id, content_id = match.groups()
        host = self._check_host(HOST_ALIASES.get(prefix.lower(), prefix))
        return Resolved(host, map_id, content_id)

    def _loaded_maps(self, host: str) -> dict[str, MapInfo] | None:
        """The host's publication list if it is already loaded and fresh; never fetches."""
        with self._lock:
            cached = self._maps.get(host)
            return cached[1] if cached and self._fresh(cached[0]) else None

    def compact_link(self, url: str, host: str | None = None) -> str | None:
        """Compact reference for a page-body link to ``/r/<mapId>[/<contentId>]``, or None to leave it alone.

        No network: the map id must be in an already-loaded publication list, because a short pretty URL
        (``/r/foo/bar``) looks exactly like an id URL. Links with a query or fragment are left alone so
        in-page anchors are not lost. With ``host``, only links to that host are rewritten.
        """
        parts = _split_body_url(url)
        if parts is None:
            return None
        link_host = (parts.hostname or "").lower()
        if (
            parts.scheme not in ("http", "https") or parts.query or parts.fragment or link_host not in self.hosts
            or (host is not None and link_host != host.lower())
        ):
            return None
        host = link_host
        segs = unquote(parts.path).rstrip("/").split("/")[1:]  # ["r", mapId, contentId?]
        maps = self._loaded_maps(host)
        if maps is None or len(segs) not in (2, 3) or segs[0] != "r":
            return None
        ids = segs[1:]
        if any(not _CONTENT_ID.fullmatch(i) or i in (".", "..") for i in ids) or ids[0] not in maps:
            return None
        return self.compact_ref(Resolved(host, ids[0], ids[1] if len(ids) == 2 else None))

    def is_attachment_link(self, url: str) -> bool:
        """True for image/attachment URLs on an allowed host."""
        parts = _split_body_url(url)
        return parts is not None and (parts.hostname or "").lower() in self.hosts and bool(
            _ATTACHMENT_PATH.match(parts.path)
        )

    def compact_ref(self, target: Resolved) -> str:
        host = self._check_host(target.host)
        prefix = next((alias for alias, value in HOST_ALIASES.items() if value == host), host)
        suffix = "" if target.content_id is None else f"/{target.content_id}"
        value = f"{prefix}:{target.map_id}{suffix}"
        if self._parse_compact_ref(value) != Resolved(host, target.map_id, target.content_id):
            raise CatalogError(f"Invalid compact target {target!r}")
        return value

    def id_url(self, target: Resolved) -> str:
        host = self._check_host(target.host)
        suffix = "" if target.content_id is None else f"/{target.content_id}"
        return f"https://{host}/r/{target.map_id}{suffix}"

    def fallback_reader_url(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        try:
            parts = urlsplit(value)
            if (
                parts.scheme != "https" or parts.hostname not in self.hosts
                or parts.username is not None or parts.password is not None
                or not parts.path.startswith("/r/") or not parts.path[3:].strip("/")
            ):
                return None
        except ValueError:
            return None
        return value

    def _pretty_ok(self, host: str, map_id: str) -> str:
        """The map's pretty URL if it identifies the map unambiguously, else ""."""
        info = self.maps(host).get(map_id)
        if not info or not info.pretty_url or info.pretty_url.lower() in self._shared[host.lower()]:
            return ""
        return info.pretty_url

    def map_url(self, host: str, map_id: str) -> str:
        """Reader URL of a publication: its pretty URL, or the id form when missing or shared."""
        host = self._check_host(host)
        pretty = self._pretty_ok(host, map_id)
        return f"https://{host}/r/{pretty}" if pretty else self.id_url(Resolved(host, map_id, None))

    def reader_url(self, host: str, map_id: str, page: TocPage) -> str:
        host = self._check_host(host)
        if not page.content_id:  # synthetic root of a multi-section TOC = the publication itself
            return self.map_url(host, map_id)
        if page.pretty_url and self._pretty_ok(host, map_id):
            return f"https://{host}{page.pretty_url}"
        return self.id_url(Resolved(host, map_id, page.content_id))
