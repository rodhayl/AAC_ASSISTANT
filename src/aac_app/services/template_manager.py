"""
Companion Template Manager Service

Manages YAML-based personality templates for the Learning Companion.
Templates define default configurations that can be customized per-student.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from loguru import logger


class TemplateManager:
    """
    Manages companion profile templates stored as YAML files.

    Templates provide sensible defaults for different student needs:
    - default: Balanced, suitable for most students
    - autism_friendly: Calm, predictable, literal language
    - preschool: Playful, simple, lots of encouragement
    - teenager: Respectful, less patronizing
    - calm_gentle: Soothing, low-stimulation
    - high_energy: Enthusiastic, motivating
    """

    # Path to templates directory
    TEMPLATE_DIR = Path(__file__).parent.parent / "config" / "companion_templates"

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load all YAML templates from the templates directory."""
        if not self.TEMPLATE_DIR.exists():
            logger.warning(f"Template directory not found: {self.TEMPLATE_DIR}")
            self._cache = {"default": self._get_hardcoded_default()}
            return

        for yaml_file in self.TEMPLATE_DIR.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    template = yaml.safe_load(f)
                    if template:
                        template_name = yaml_file.stem
                        self._cache[template_name] = template
                        logger.debug(f"Loaded template: {template_name}")
            except Exception as e:
                logger.error(f"Failed to load template {yaml_file}: {e}")

        # Ensure default template exists
        if "default" not in self._cache:
            logger.warning("No default template found, using hardcoded default")
            self._cache["default"] = self._get_hardcoded_default()

        logger.info(f"TemplateManager initialized with {len(self._cache)} templates")

    def _get_hardcoded_default(self) -> Dict:
        """Fallback default template if YAML files are missing."""
        return {
            "name": "Default Companion",
            "description": "Balanced, friendly learning companion",
            "version": "1.0",
            "communication_style": {
                "tone": "encouraging",
                "complexity": "moderate",
                "sentence_length": "medium",
                "use_emojis": False,
                "avoid_idioms": False,
                "avoid_sarcasm": True,
            },
            "safety": {
                "content_filter_level": "standard",
                "forbidden_topics": [],
                "trigger_words": [],
                "max_response_length": 150,
            },
            "companion": {
                "name": None,
                "role": "learning companion",
                "personality": ["friendly", "patient", "encouraging"],
            },
            "custom_instructions": "Be warm, patient, and encouraging.",
        }

    def list_templates(self) -> List[Dict[str, str]]:
        """
        List all available templates with their metadata.

        Returns:
            List of dicts with 'name', 'display_name', 'description', 'version'
        """
        templates = []
        for name, template in self._cache.items():
            templates.append(
                {
                    "name": name,
                    "display_name": template.get(
                        "name", name.replace("_", " ").title()
                    ),
                    "description": template.get("description", ""),
                    "version": template.get("version", "1.0"),
                }
            )
        return sorted(templates, key=lambda x: x["name"])

    def get_template(self, name: str) -> Dict:
        """
        Get a template by name.

        Args:
            name: Template name (without .yaml extension)

        Returns:
            Template dict, or default if not found
        """
        template = self._cache.get(name)
        if template is None:
            logger.warning(f"Template '{name}' not found, using default")
            template = self._cache.get("default", self._get_hardcoded_default())
        return copy.deepcopy(template)

    def template_exists(self, name: str) -> bool:
        """Check if a template exists."""
        return name in self._cache

    def get_template_names(self) -> List[str]:
        """Get list of all template names."""
        return list(self._cache.keys())

    def resolve_profile(
        self,
        template_name: str,
        overrides: Optional[Dict[str, Any]] = None,
        demographics: Optional[Dict[str, Any]] = None,
        medical_context: Optional[Dict[str, Any]] = None,
        communication_style: Optional[Dict[str, Any]] = None,
        safety_constraints: Optional[Dict[str, Any]] = None,
        companion_persona: Optional[Dict[str, Any]] = None,
        custom_instructions: Optional[str] = None,
    ) -> Dict:
        """
        Resolve a complete profile by merging template with overrides.

        This is the main method for getting a student's effective profile.
        It starts with a template and applies any per-student customizations.

        Args:
            template_name: Base template to use
            overrides: Dict of dot-notation overrides (e.g., {"communication_style.tone": "calm"})
            demographics: Student demographics (age, gender)
            medical_context: Medical/accessibility information
            communication_style: Communication style overrides
            safety_constraints: Safety configuration overrides
            companion_persona: Companion persona overrides
            custom_instructions: Additional instructions to append

        Returns:
            Complete merged profile dict
        """
        # Start with template
        profile = self.get_template(template_name)

        # Apply structured overrides (deep merge)
        if communication_style:
            profile["communication_style"] = self._deep_merge(
                profile.get("communication_style", {}), communication_style
            )

        if safety_constraints:
            profile["safety"] = self._deep_merge(
                profile.get("safety", {}), safety_constraints
            )

        if companion_persona:
            profile["companion"] = self._deep_merge(
                profile.get("companion", {}), companion_persona
            )

        # Add demographics
        if demographics:
            profile["demographics"] = demographics

        # Add medical context
        if medical_context:
            profile["medical_context"] = medical_context

        # Apply dot-notation overrides (for fine-grained control)
        if overrides:
            self._apply_dot_overrides(profile, overrides)

        # Append custom instructions
        if custom_instructions:
            existing = profile.get("custom_instructions", "")
            profile["custom_instructions"] = (
                f"{existing}\n\n{custom_instructions}".strip()
            )

        return profile

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """
        Deep merge two dicts, with override taking precedence.

        Args:
            base: Base dictionary
            override: Override dictionary (values take precedence)

        Returns:
            Merged dictionary
        """
        result = copy.deepcopy(base)
        for key, value in override.items():
            if value is None:
                continue  # Don't override with None
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            elif (
                key in result
                and isinstance(result[key], list)
                and isinstance(value, list)
            ):
                # For lists, extend rather than replace
                result[key] = list(set(result[key] + value))
            else:
                result[key] = value
        return result

    def _apply_dot_overrides(self, profile: Dict, overrides: Dict[str, Any]) -> None:
        """
        Apply dot-notation overrides to a profile.

        Examples:
            {"communication_style.tone": "calm"} -> profile["communication_style"]["tone"] = "calm"
            {"safety.forbidden_topics": ["violence"]} -> profile["safety"]["forbidden_topics"] = ["violence"]
        """
        for key, value in overrides.items():
            if value is None:
                continue
            parts = key.split(".")
            target = profile
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value

    def build_system_prompt(self, profile: Dict) -> str:
        """
        Build an LLM system prompt from a resolved profile.

        This converts the structured profile into a natural language
        system prompt that the LLM can understand.

        Args:
            profile: Resolved profile dict

        Returns:
            Complete system prompt string
        """
        prompt_parts = []

        # Base AAC tutor identity
        prompt_parts.append(
            "You are an AAC-specialized tutor with expertise in Augmentative and Alternative Communication."
        )

        # Companion persona
        companion = profile.get("companion", {})
        if companion.get("name"):
            prompt_parts.append(f"Your name is {companion['name']}.")
        if companion.get("role"):
            prompt_parts.append(f"Your role is to be a {companion['role']}.")
        if companion.get("personality"):
            traits = companion["personality"]
            if isinstance(traits, list):
                prompt_parts.append(f"Your personality is: {', '.join(traits)}.")

        # Communication style
        style = profile.get("communication_style", {})
        style_instructions = []

        if style.get("tone"):
            style_instructions.append(f"Use a {style['tone']} tone")
        if style.get("complexity"):
            style_instructions.append(f"use {style['complexity']} language complexity")
        if style.get("sentence_length"):
            style_instructions.append(f"keep sentences {style['sentence_length']}")
        if style.get("avoid_idioms"):
            style_instructions.append("avoid idioms and figurative language")
        if style.get("avoid_sarcasm"):
            style_instructions.append("never use sarcasm")
        if style.get("avoid_metaphors"):
            style_instructions.append("avoid metaphors and abstract concepts")
        if style.get("explicit_transitions"):
            style_instructions.append("announce topic changes explicitly")
        if style.get("use_emojis"):
            style_instructions.append("include appropriate emojis")
        if style.get("use_repetition"):
            style_instructions.append("use repetition to reinforce concepts")

        if style_instructions:
            prompt_parts.append(
                "Communication style: " + ", ".join(style_instructions) + "."
            )

        # Demographics context
        demographics = profile.get("demographics", {})
        if demographics.get("age"):
            prompt_parts.append(f"The student is {demographics['age']} years old.")

        # Safety constraints
        safety = profile.get("safety", {})
        if safety.get("forbidden_topics"):
            topics = safety["forbidden_topics"]
            prompt_parts.append(f"NEVER discuss these topics: {', '.join(topics)}.")
        if safety.get("trigger_words"):
            words = safety["trigger_words"]
            prompt_parts.append(f"Avoid using these words: {', '.join(words)}.")
        if safety.get("content_filter_level") == "strict":
            prompt_parts.append(
                "Apply strict content filtering - keep everything G-rated and safe."
            )
        if safety.get("max_response_length"):
            max_len = safety["max_response_length"]
            prompt_parts.append(f"Keep responses under {max_len} words.")

        # Medical context awareness (generalized, not specific conditions)
        medical = profile.get("medical_context", {})
        if medical.get("sensitivities"):
            prompt_parts.append(
                f"Be sensitive to: {', '.join(medical['sensitivities'])}."
            )
        if medical.get("accessibility_needs"):
            prompt_parts.append(
                f"Accessibility considerations: {', '.join(medical['accessibility_needs'])}."
            )

        # Core AAC principles (always included)
        prompt_parts.append(
            """
Key AAC principles:
1. Students use symbol-based communication which may be telegraphic
2. Interpret intent from semantic roles rather than strict grammar
3. Expand telegraphic phrases while preserving meaning
4. Be encouraging and patient - communication takes effort
5. Ask ONE clarifying question if intent is ambiguous
6. Celebrate communication attempts and build on the student's message"""
        )

        # Custom instructions
        custom = profile.get("custom_instructions", "")
        if custom:
            prompt_parts.append(f"\nSpecial Instructions:\n{custom}")

        return "\n\n".join(prompt_parts)

    def reload_templates(self) -> int:
        """
        Reload all templates from disk.

        Useful for development or when templates are updated.

        Returns:
            Number of templates loaded
        """
        self._cache.clear()
        self._load_templates()
        return len(self._cache)


# Singleton instance
_template_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """Get the singleton TemplateManager instance."""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager
