"""
Symbol Semantics Service
Analyzes AAC symbol sequences for semantic patterns and intent.
"""

from typing import Dict, List, Tuple


class SymbolSemantics:
    """Analyzes AAC symbol sequences for semantic patterns and intent."""

    # Category-based semantic roles
    SEMANTIC_ROLES = {
        "person": ["agent", "subject", "pronoun"],
        "action": ["verb", "activity"],
        "object": ["target", "theme", "object"],
        "feeling": ["state", "emotion"],
        "place": ["location", "destination"],
        "descriptor": ["adjective", "modifier"],
        "question": ["interrogative"],
    }

    def __init__(self):
        self.intent_patterns = self._load_intent_patterns()

    def _load_intent_patterns(self) -> Dict:
        """Common AAC intent patterns."""
        return {
            "request": {
                "patterns": [
                    ["pronoun", "verb", "object"],  # "I want cookie"
                    ["verb", "object"],  # "want cookie"
                    ["pronoun", "verb"],  # "I go"
                ],
                "keywords": ["want", "need", "help", "give", "more", "please"],
            },
            "question": {
                "patterns": [
                    ["interrogative", "verb", "object"],  # "what eat food"
                    ["interrogative", "subject", "verb"],  # "where mom go"
                ],
                "keywords": ["what", "where", "when", "who", "why", "how"],
            },
            "statement": {
                "patterns": [["subject", "verb", "object"], ["subject", "state"]],
                "keywords": [],
            },
            "greeting": {
                "patterns": [["greeting"]],
                "keywords": ["hello", "hi", "bye", "goodbye", "thanks", "thank"],
            },
            "feeling": {
                "patterns": [["state"], ["pronoun", "state"]],
                "keywords": [
                    "happy",
                    "sad",
                    "angry",
                    "tired",
                    "hungry",
                    "thirsty",
                    "feel",
                ],
            },
        }

    def analyze_sequence(self, symbols: List[Dict]) -> Dict:
        """
        Analyze symbol sequence for semantic intent.

        Args:
            symbols: List of symbol dicts with 'label', 'category', etc.

        Returns:
            {
                'intent': str,
                'confidence': float,
                'semantic_roles': List[str],
                'summary': str,
                'symbol_count': int,
                'unique_categories': List[str]
            }
        """
        if not symbols:
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "semantic_roles": [],
                "summary": "",
                "symbol_count": 0,
                "unique_categories": [],
            }

        # Extract categories and labels
        categories = [s.get("category", "general") for s in symbols]
        labels = [s.get("label", "").lower() for s in symbols]

        # Map categories to semantic roles
        semantic_roles = []
        for cat in categories:
            roles = self.SEMANTIC_ROLES.get(cat, ["general"])
            semantic_roles.append(roles[0])

        # Detect intent
        intent, confidence = self._detect_intent(labels, semantic_roles)

        # Build semantic summary
        summary = self._build_semantic_summary(symbols, semantic_roles, intent)

        return {
            "intent": intent,
            "confidence": confidence,
            "semantic_roles": semantic_roles,
            "summary": summary,
            "symbol_count": len(symbols),
            "unique_categories": list(set(categories)),
        }

    def _detect_intent(self, labels: List[str], roles: List[str]) -> Tuple[str, float]:
        """Detect intent from labels and semantic roles."""
        # Check for keyword matches (high confidence)
        for intent_name, intent_data in self.intent_patterns.items():
            for keyword in intent_data["keywords"]:
                if keyword in labels:
                    return intent_name, 0.85

        # Check pattern matches (medium confidence)
        for intent_name, intent_data in self.intent_patterns.items():
            for pattern in intent_data["patterns"]:
                if self._matches_pattern(roles, pattern):
                    return intent_name, 0.65

        # Fallback
        return "statement", 0.4

    def _matches_pattern(self, roles: List[str], pattern: List[str]) -> bool:
        """Check if semantic roles match intent pattern."""
        if len(roles) < len(pattern):
            return False

        # Allow partial matches (AAC often drops words)
        matches = sum(1 for r, p in zip(roles, pattern) if r == p)
        tolerance = max(1, len(pattern) - 1)  # Allow one mismatch
        return matches >= tolerance

    def _build_semantic_summary(
        self, symbols: List[Dict], roles: List[str], intent: str
    ) -> str:
        """Generate human-readable semantic summary."""
        parts = []
        for sym, role in zip(symbols, roles):
            parts.append(f"{sym.get('label')} ({role})")

        return f"{intent.upper()}: {' → '.join(parts)}"

    def generate_expansion_context(self, analysis: Dict, symbols: List[Dict]) -> str:
        """
        Generate context string for LLM to expand AAC utterance.

        Args:
            analysis: Result from analyze_sequence()
            symbols: Original symbol list

        Returns:
            Formatted context string for LLM prompt
        """
        intent = analysis["intent"]
        roles = analysis["semantic_roles"]
        labels = [s.get("label", "") for s in symbols]

        context_parts = [
            f"AAC Intent: {intent.upper()}",
            f"Symbol sequence: {' → '.join(labels)}",
            f"Semantic structure: {' → '.join(roles)}",
        ]

        # Add intent-specific guidance
        if intent == "request":
            context_parts.append(
                "Guidance: Interpret as a polite request. The student wants something."
            )
        elif intent == "question":
            context_parts.append(
                "Guidance: This is a question. Provide a clear, helpful answer."
            )
        elif intent == "greeting":
            context_parts.append(
                "Guidance: Respond warmly and encourage further interaction."
            )
        elif intent == "feeling":
            context_parts.append(
                "Guidance: Acknowledge the emotion with empathy and support."
            )

        return "\n".join(context_parts)
