
import json
import re
import time
from urllib.parse import quote

import httpx
from loguru import logger

ARASAAC_API_BASE = "https://api.arasaac.org/api"
ARASAAC_IMAGE_BASE = "https://static.arasaac.org/pictograms"

# ARASAAC language codes are two lowercase letters; pictogram ids are decimal
# numbers. Every value interpolated into a request URL below is checked
# against these whitelists first, so a malformed or hostile value can never
# steer the request to another host, path, or query. The percent-encoded
# search query may only contain unreserved characters plus '%'.
_LOCALE_RE = re.compile(r"^[a-z]{2}$")
_ARASAAC_ID_RE = re.compile(r"^[0-9]{1,10}$")
_ENCODED_QUERY_RE = re.compile(r"^[A-Za-z0-9_.~%-]{1,600}$")

# Downloaded pictograms are buffered in memory before they are written to the
# uploads directory, so the body size must be bounded: a compromised or
# misbehaving upstream must not be able to make one request allocate without
# limit. The upload policy (5 MB) is the same budget the multipart path uses,
# so a pictogram that would be rejected as a file upload is rejected here too.
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
# The full locale catalog is larger than a pictogram image, but it is still
# bounded before JSON parsing so an upstream failure cannot allocate without
# limit. Keep this separate from the per-image upload budget.
MAX_CATALOG_BYTES = 64 * 1024 * 1024

# Searches are typed ahead of the user (the picker re-queries on every
# keystroke), and each one is an upstream round trip. A tiny TTL cache absorbs
# the repeats without holding stale results for long enough to matter.
_SEARCH_CACHE_TTL_SECONDS = 60.0
_SEARCH_CACHE_MAX_ENTRIES = 256
_search_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def _cache_lookup(key: tuple[str, str]) -> list[dict] | None:
    entry = _search_cache.get(key)
    if entry is None:
        return None
    stored_at, results = entry
    if time.monotonic() - stored_at > _SEARCH_CACHE_TTL_SECONDS:
        _search_cache.pop(key, None)
        return None
    return [dict(item) for item in results]


def _cache_store(key: tuple[str, str], results: list[dict]) -> None:
    if len(_search_cache) >= _SEARCH_CACHE_MAX_ENTRIES:
        oldest = min(_search_cache, key=lambda k: _search_cache[k][0])
        _search_cache.pop(oldest, None)
    _search_cache[key] = (time.monotonic(), results)


def clear_search_cache() -> None:
    """Drop cached ARASAAC searches (tests and locale switches)."""
    _search_cache.clear()


def _validated_locale(locale: str | None) -> str:
    """Return a two-letter ARASAAC language code, defaulting to ``es``."""
    code = (locale or "es").strip().lower()
    return code if _LOCALE_RE.fullmatch(code) else "es"


def _validated_id_path(value: object) -> str:
    """Return ``value`` as a whitelisted decimal id for use in a URL path."""
    text = str(value).strip()
    if not _ARASAAC_ID_RE.fullmatch(text):
        raise ValueError(f"Invalid ARASAAC id: {value!r}")
    return text


class ArasaacService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def list_all_symbols(self, locale: str = "es") -> list[dict]:
        """
        List every pictogram available for a locale.

        The full catalog response is larger than a single image, so it uses a
        bounded streaming read rather than ``response.json()``. This preserves
        the bulk-import contract while preventing a compromised upstream from
        forcing an unbounded allocation before JSON parsing.
        """
        url = f"{ARASAAC_API_BASE}/pictograms/all/{_validated_locale(locale)}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_CATALOG_BYTES:
                        raise ValueError(
                            "ARASAAC catalog exceeds its configured byte limit"
                        )
            payload = json.loads(body)
            if not isinstance(payload, list):
                raise ValueError("ARASAAC catalog returned a non-list payload")
            return payload

    async def search_symbols(self, query: str, locale: str = "es") -> list[dict]:
        """
        Search for symbols in ARASAAC.

        Identical (query, locale) pairs within the TTL are served from the
        in-process cache, so the typo-ahead search loop does not turn into an
        upstream request per keystroke.
        """
        cache_key = (query, _validated_locale(locale))
        cached = _cache_lookup(cache_key)
        if cached is not None:
            return cached
        try:
            # Use 'bestsearch' for better results. The query is a path segment
            # and must be percent-encoded: spaces, '/', '?' or '#' in a raw
            # query would otherwise corrupt the URL (extra path segments,
            # query-string parsing, or an early fragment).
            encoded_query = quote(query, safe="")
            if not _ENCODED_QUERY_RE.fullmatch(encoded_query):
                raise ValueError("Unsupported ARASAAC search query")
            url = (
                f"{ARASAAC_API_BASE}/pictograms/{_validated_locale(locale)}/"
                f"bestsearch/{encoded_query}"
            )
            # Only network/transport failures are degrade-to-empty: an
            # upstream 404 means "no pictogram matches". A structural change
            # in the payload (missing _id, non-list body) is a real defect and
            # must surface instead of being reported as an empty result set.
            try:
                response = await self.client.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return []
                logger.error(f"ARASAAC API error: {e}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"ARASAAC search failed: {e}")
                return []
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(
                    f"ARASAAC search returned {type(data).__name__}, expected list"
                )

            # Format results
            results = []
            for item in data:
                # ARASAAC returns a list of objects.
                # Each object has _id, keywords, etc.
                # We want to return a simplified structure.

                # Get the first keyword as the main label
                keywords = [k["keyword"] for k in item.get("keywords", [])]
                label = keywords[0] if keywords else "Unknown"

                results.append(
                    {
                        "id": item["_id"],
                        "label": label,
                        "description": item.get("desc", ""),
                        "keywords": ", ".join(keywords),
                        "categories": item.get("categories", []),
                        "image_url": (
                            f"{ARASAAC_IMAGE_BASE}/{_validated_id_path(item['_id'])}/"
                            f"{_validated_id_path(item['_id'])}_500.png"
                        ),
                    }
                )
            _cache_store(cache_key, results)
            return results
        except (httpx.HTTPStatusError, ValueError):
            raise
        except (AttributeError, KeyError, IndexError, TypeError) as e:
            # A malformed upstream shape is actionable integration failure,
            # not an empty search result. Keep the original exception chained
            # so the route/logs identify the broken field without hiding it.
            logger.error("ARASAAC search returned malformed data: {}", e)
            raise ValueError("ARASAAC search returned malformed data") from e

    async def _download_bounded(self, url: str) -> bytes | None:
        """Stream ``url`` into memory, rejecting non-200 and oversize bodies.

        Streaming (instead of ``response.content``) is what makes the byte
        budget meaningful: the body is abandoned as soon as it exceeds
        ``MAX_DOWNLOAD_BYTES`` rather than after it has all been buffered.
        """
        async with self.client.stream("GET", url) as response:
            if response.status_code != 200:
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_DOWNLOAD_BYTES:
                    logger.warning(
                        "ARASAAC download exceeded {} bytes; rejected: {}",
                        MAX_DOWNLOAD_BYTES,
                        url,
                    )
                    return None
            return bytes(body) or None

    async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
        """
        Download a symbol image from ARASAAC.
        """
        hi_res_url = (  # Try high res first
            f"{ARASAAC_IMAGE_BASE}/{_validated_id_path(arasaac_id)}/"
            f"{_validated_id_path(arasaac_id)}_2500.png"
        )
        try:
            content = await self._download_bounded(hi_res_url)
        except Exception as e:
            logger.error(f"Failed to download ARASAAC image {arasaac_id}: {e}")
            return None
        if content is None:
            # Missing/unavailable/oversize high-res: fall back to 500px.
            return await self.download_symbol_image_500(arasaac_id)
        return content

    async def download_symbol_image_500(self, arasaac_id: int) -> bytes | None:
        """
        Download the 500px pictogram used for card and board display.
        """
        url = (
            f"{ARASAAC_IMAGE_BASE}/{_validated_id_path(arasaac_id)}/"
            f"{_validated_id_path(arasaac_id)}_500.png"
        )
        try:
            return await self._download_bounded(url)
        except Exception as e:
            logger.error(f"Failed to download ARASAAC image {arasaac_id}: {e}")
            return None

    async def close(self):
        await self.client.aclose()
