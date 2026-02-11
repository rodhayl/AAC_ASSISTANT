import ast
import json
import re
from typing import Dict, List, Union

from loguru import logger

from ..providers.ollama_provider import OllamaProvider
from ..providers.openrouter_provider import OpenRouterProvider


def _normalize_label(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _dedupe_items_by_label(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[str] = set()
    deduped: List[Dict[str, str]] = []
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
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


class BoardGenerationService:
    """Service for generating communication board content using AI"""

    def __init__(self, llm_provider: Union[OllamaProvider, OpenRouterProvider]):
        self.llm = llm_provider
        self.provider_type = (
            "openrouter" if isinstance(llm_provider, OpenRouterProvider) else "ollama"
        )
        logger.info(
            f"Board Generation Service initialized with {self.provider_type} provider"
        )

    async def generate_board_items(
        self,
        topic: str,
        description: str = "",
        item_count: int = 12,
        fail_silently: bool = True,
        refine_prompt: str = "",
        regenerate: bool = False,
        language: str = "en",
        recursion_depth: int = 0,
    ) -> List[Dict[str, str]]:
        """
        Generate items for a communication board based on topic and description.
        Returns a list of dictionaries with 'label', 'symbol_key', and 'color'.
        """
        if recursion_depth > 2:  # Prevent infinite recursion
            logger.warning(f"Max recursion depth reached for topic {topic}")
            return []

        logger.info(f"Generating board items for topic: {topic} (lang={language}, count={item_count}, depth={recursion_depth})")

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

            # Clean up response if it contains markdown code blocks
            clean_response = response.strip()

            # Try to extract content within ```json ... ``` or ``` ... ```
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

            # Validate items
            valid_items = []
            for item in items or []:
                if isinstance(item, dict) and "label" in item and "symbol_key" in item:
                    # Ensure color is present
                    if "color" not in item:
                        item["color"] = "#FFFFFF"
                    valid_items.append(item)

            valid_items = _dedupe_items_by_label(valid_items)

            if valid_items:
                # Accept partial responses: avoid extra LLM calls during board creation.
                # The caller can request regeneration if they need more items.
                pass
            
            if not valid_items:
                logger.warning(f"AI response contained no valid items (fail_silently={fail_silently})")
                if fail_silently:
                    return []
                raise ValueError(
                    "AI returned no valid suggestions. Check AI provider output."
                )

            return valid_items[:item_count]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Raw response: {response}")

            extracted = _extract_first_json_array(clean_response)
            if extracted:
                try:
                    parsed = json.loads(extracted)
                    if isinstance(parsed, dict):
                        parsed = [parsed]
                    if isinstance(parsed, list):
                        parsed_valid: List[Dict[str, str]] = []
                        for item in parsed:
                            if isinstance(item, dict) and "label" in item:
                                if "symbol_key" not in item:
                                    item["symbol_key"] = item["label"].lower().replace(" ", "_")
                                if "color" not in item:
                                    item["color"] = "#FFFFFF"
                                parsed_valid.append(item)
                        parsed_valid = _dedupe_items_by_label(parsed_valid)
                        if parsed_valid:
                            logger.warning("Recovered valid JSON array from partial AI response.")
                            return parsed_valid[:item_count]
                except Exception:
                    pass

            # Fallback 1: try more permissive parsing (single quotes / Python-style)
            fallback_items: List[Dict[str, str]] = []
            try:
                fallback_items = ast.literal_eval(clean_response)
                if isinstance(fallback_items, dict):
                    fallback_items = [fallback_items]
            except Exception:
                fallback_items = []

            # Fallback 1b: try trimming incomplete JSON (missing closing ])
            if not fallback_items:

                def _try_load(txt: str):
                    try:
                        data = json.loads(txt)
                        if isinstance(data, dict):
                            return [data]
                        return data
                    except Exception:
                        return None

                candidate_texts = []
                if clean_response.startswith(
                    "["
                ) and not clean_response.rstrip().endswith("]"):
                    candidate_texts.append(clean_response.rstrip() + "]")
                # Trim to last complete object
                if "{" in clean_response and "}" in clean_response:
                    first = clean_response.find("[")
                    last = clean_response.rfind("}")
                    if first != -1 and last != -1 and last > first:
                        trimmed = clean_response[first : last + 1]
                        if not trimmed.endswith("]"):
                            trimmed = trimmed + "]"
                        candidate_texts.append(trimmed)

                for cand in candidate_texts:
                    loaded = _try_load(cand)
                    if loaded:
                        fallback_items = (
                            loaded if isinstance(loaded, list) else [loaded]
                        )
                        break

            # Fallback 1c: extract any object-like snippets and parse individually
            if not fallback_items:
                object_strings = re.findall(r"\{[^{}]*\}", clean_response)
                parsed_objects = []
                for obj_str in object_strings:
                    try:
                        parsed = json.loads(obj_str)
                        if isinstance(parsed, dict):
                            parsed_objects.append(parsed)
                    except Exception:
                        continue
                if parsed_objects:
                    fallback_items = parsed_objects

            # Fallback 2: extract bullet-like lines into label/color/key guesses
            if not fallback_items:
                fallback_items = []
                for line in clean_response.splitlines():
                    stripped = line.strip(" -*\t")
                    if not stripped:
                        continue
                    # Accept patterns like "Label - keyword" or "1. Label"
                    parts = stripped.split(" - ", 1)
                    label = parts[0]
                    symbol_key = (
                        parts[1] if len(parts) > 1 else label.lower().replace(" ", "_")
                    )
                    if label:
                        fallback_items.append(
                            {
                                "label": label.strip(),
                                "symbol_key": symbol_key.strip(),
                                "color": "#E8F5E9",
                            }
                        )

            valid_items = []
            for item in fallback_items:
                if isinstance(item, dict) and "label" in item:
                    if "symbol_key" not in item:
                        item["symbol_key"] = item["label"].lower().replace(" ", "_")
                    if "color" not in item:
                        item["color"] = "#FFFFFF"
                    valid_items.append(item)

            if valid_items:
                logger.warning("Used fallback parsing for AI response (non-JSON).")
                valid_items = _dedupe_items_by_label(valid_items)
                return valid_items[:item_count]

            if fail_silently:
                return []
            raise ValueError(
                "AI response was not valid JSON and no fallback could be parsed."
            )
        except Exception as e:
            logger.error(f"Error generating board items: {e}")
            if fail_silently:
                return []
            raise
