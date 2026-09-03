
from urllib.parse import quote

import httpx
from loguru import logger

ARASAAC_API_BASE = "https://api.arasaac.org/api"
ARASAAC_IMAGE_BASE = "https://static.arasaac.org/pictograms"


class ArasaacService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def list_all_symbols(self, locale: str = "es") -> list[dict]:
        """
        List every pictogram available for a locale.

        The full catalog response is much larger than a search result, so it
        uses its own client with a longer timeout instead of the shared
        short-timeout client used for searches and single downloads.
        """
        url = f"{ARASAAC_API_BASE}/pictograms/all/{locale}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def search_symbols(self, query: str, locale: str = "es") -> list[dict]:
        """
        Search for symbols in ARASAAC.
        """
        try:
            # Use 'bestsearch' for better results. The query is a path segment
            # and must be percent-encoded: spaces, '/', '?' or '#' in a raw
            # query would otherwise corrupt the URL (extra path segments,
            # query-string parsing, or an early fragment).
            url = f"{ARASAAC_API_BASE}/pictograms/{locale}/bestsearch/{quote(query, safe='')}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

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
                        "image_url": f"{ARASAAC_IMAGE_BASE}/{item['_id']}/{item['_id']}_500.png",
                    }
                )
            return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            logger.error(f"ARASAAC API error: {e}")
            raise
        except Exception as e:
            logger.error(f"ARASAAC search failed: {e}")
            return []

    async def download_symbol_image(self, arasaac_id: int) -> bytes | None:
        """
        Download a symbol image from ARASAAC.
        """
        hi_res_url = f"{ARASAAC_IMAGE_BASE}/{arasaac_id}/{arasaac_id}_2500.png"  # Try high res first
        try:
            response = await self.client.get(hi_res_url)
        except Exception as e:
            logger.error(f"Failed to download ARASAAC image {arasaac_id}: {e}")
            return None
        if response.status_code != 200:
            # Fallback to 500px
            return await self.download_symbol_image_500(arasaac_id)
        return response.content

    async def download_symbol_image_500(self, arasaac_id: int) -> bytes | None:
        """
        Download the 500px pictogram used for card and board display.
        """
        url = f"{ARASAAC_IMAGE_BASE}/{arasaac_id}/{arasaac_id}_500.png"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to download ARASAAC image {arasaac_id}: {e}")
            return None

    async def close(self):
        await self.client.aclose()
