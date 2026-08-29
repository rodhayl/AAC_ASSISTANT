import json
import re

from loguru import logger

from ..providers.base_provider import BaseLLMProvider
from ..providers.groq_provider import GroqProvider
from ..providers.lmstudio_provider import LMStudioProvider
from ..providers.openrouter_provider import OpenRouterProvider


def _normalize_label(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _dedupe_items_by_label(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in items:
        label = _normalize_label(str(item.get("label", "")))
        if not label or label in seen:
            continue
        seen.add(label)
        deduped.append(item)
    return deduped


def _extract_first_json_array(text: str) -> str | None:
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class BoardGenerationService:
    """Service for generating communication board content using AI"""

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
    ):
        self.llm = llm_provider
        if isinstance(llm_provider, GroqProvider):
            self.provider_type = "groq"
        elif isinstance(llm_provider, LMStudioProvider):
            self.provider_type = "lmstudio"
        elif isinstance(llm_provider, OpenRouterProvider):
            self.provider_type = "openrouter"
        else:
            self.provider_type = "ollama"
        logger.info(
            f"Board Generation Service initialized with {self.provider_type} provider"
        )

    async def generate_board_items(
        self,
        topic: str,
        description: str = "",
        item_count: int = 12,
        refine_prompt: str = "",
        regenerate: bool = False,
        language: str = "en",
    ) -> list[dict[str, str]]:
        """
        Generate items for a communication board based on topic and description.
        Returns a list of dictionaries with 'label', 'symbol_key', and 'color'.
        """
        logger.info(f"Generating board items for topic: {topic} (lang={language}, count={item_count})")

        refine_text = (refine_prompt or "").strip()
        refinement_instructions = ""
        if refine_text:
            refinement_instructions = (
                f"\nAdditional guidance from user: {refine_text}\n"
            )

        generation_goal = (
            "Regenerate a fresh full set of diverse items (avoid repeating earlier ideas)."
            if regenerate
            else "Provide extra symbols that complement the current board without duplicating existing items."
        )

        prompt = f"""
        {generation_goal}

        Generate a list of {item_count} items for an AAC communication board about "{topic}".
        Board description: {description}
        Target Language: {language}
        {refinement_instructions}
        For each item, provide:
        1. A short label (1-3 words) in {language}
        2. A keyword to find a symbol/icon (e.g., "apple" for an apple icon).
           Prefer English keywords for symbol lookup.
        3. A suggested background color hex code (soft pastel colors).

        Return ONLY a JSON array of objects with keys: "label", "symbol_key", "color".
        Do not include any other text or markdown formatting.
        Example:
        [
            {{"label": "Yes", "symbol_key": "check_mark", "color": "#E8F5E9"}},
            {{"label": "No", "symbol_key": "cross_mark", "color": "#FFEBEE"}}
        ]
        """

        system_prompt = (
            "You are an expert in AAC (Augmentative and Alternative Communication). "
            "You help create communication boards for people with speech difficulties. "
            "Output valid JSON only."
        )

        response = ""
        try:
            response = await self.llm.generate(
                prompt=prompt, system=system_prompt, max_tokens=1000, temperature=0.7
            )

            # Normalize harmless presentation wrappers before strict validation.
            clean_response = response.strip()
            code_block_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")
            match = code_block_pattern.search(clean_response)
            if match:
                clean_response = match.group(1).strip()
            else:
                extracted = _extract_first_json_array(clean_response)
                if extracted:
                    clean_response = extracted

            items = json.loads(clean_response)
            if isinstance(items, dict):
                items = [items]

            # Validate the complete response contract. Partial or malformed
            # provider output is an explicit failure, never a guessed board.
            if not isinstance(items, list):
                raise ValueError("AI response must be a JSON array")
            valid_items = [
                item for item in items
                if isinstance(item, dict)
                and isinstance(item.get("label"), str)
                and item["label"].strip()
                and isinstance(item.get("symbol_key"), str)
                and item["symbol_key"].strip()
                and isinstance(item.get("color"), str)
            ]
            valid_items = _dedupe_items_by_label(valid_items)
            if len(valid_items) != item_count:
                raise ValueError(
                    f"AI returned {len(valid_items)} valid items; expected {item_count}"
                )
            return valid_items

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise ValueError("AI response was not valid JSON") from e
        except Exception as e:
            logger.error(f"Error generating board items: {e}")
            raise
