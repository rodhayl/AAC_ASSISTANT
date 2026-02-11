from typing import Dict, List, Optional

import httpx
from loguru import logger

ARASAAC_API_BASE = "https://api.arasaac.org/api"
ARASAAC_IMAGE_BASE = "https://static.arasaac.org/pictograms"


class ArasaacService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def search_symbols(self, query: str, locale: str = "es") -> List[Dict]:
        """
        Search for symbols in ARASAAC.
        """
        try:
            # Use 'bestsearch' for better results
            url = f"{ARASAAC_API_BASE}/pictograms/{locale}/bestsearch/{query}"
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

    async def download_symbol_image(self, arasaac_id: int) -> Optional[bytes]:
        """
        Download a symbol image from ARASAAC.
        """
        try:
            url = f"{ARASAAC_IMAGE_BASE}/{arasaac_id}/{arasaac_id}_2500.png"  # Try high res first
            response = await self.client.get(url)
            if response.status_code != 200:
                # Fallback to 500px
                url = f"{ARASAAC_IMAGE_BASE}/{arasaac_id}/{arasaac_id}_500.png"
                response = await self.client.get(url)

            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to download ARASAAC image {arasaac_id}: {e}")
            return None

    async def close(self):
        await self.client.aclose()
