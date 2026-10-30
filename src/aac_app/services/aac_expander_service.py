"""
AAC Grammar Expander Service
Transforms telegraphic AAC symbol sequences into grammatically rich text.
Uses rule-based patterns for deterministic, fast expansion.
"""

import re
from typing import Dict, List, Optional, Tuple

from loguru import logger


class AACExpanderService:
    """
    Expands AAC symbol sequences into grammatically complete sentences.
    Combines rule-based templates with pattern caching for performance.
    """

    def __init__(self):
        self.grammar_rules = self._load_grammar_rules()
        self.expansion_cache: Dict[str, Dict] = {}  # Cache common patterns
        logger.info("AACExpanderService initialized with grammar rules")

    def _load_grammar_rules(self) -> Dict:
        """Load grammar expansion rules."""
        return {
            # Article insertion rules
            "article": {
                "patterns": [
                    # "want cookie" -> "want a cookie"
                    (r"\b(want|need|have|see|like)\s+([a-z]+)\b", self._insert_article),
                    # "go store" -> "go to the store" (but not if temporal marker present)
                    (
                        r"\b(go|went)(?!\s+to)\s+(?!yesterday|tomorrow|before|later|soon)([a-z]+)\b",
                        self._insert_to_the,
                    ),
                ]
            },
            # Pronoun normalization rules
            "pronoun": {
                "patterns": [
                    # "me want" -> "I want" (subject position)
                    (r"\b(me|my)\s+(want|need|go|like|have|see)\b", r"I \2"),
                    # "him go" -> "he goes"
                    (r"\bhim\s+(go|want|need)\b", r"he \1"),
                    # "her go" -> "she goes"
                    (r"\bher\s+(go|want|need)\b", r"she \1"),
                ]
            },
            # Verb conjugation rules
            "verb": {
                "patterns": [
                    # "I goes" -> "I go" (remove incorrect -s)
                    (r"\b(I|you|we|they)\s+([a-z]+)s\b", r"\1 \2"),
                    # "he go" -> "he goes" (add -s for third person)
                    (
                        r"\b(he|she|it)\s+(go|want|need|like|have|eat|drink|play)\b",
                        self._conjugate_third_person,
                    ),
                ]
            },
            # Tense markers and temporal expressions
            "tense": {
                "past_markers": ["yesterday", "before", "was", "did", "last"],
                "future_markers": ["tomorrow", "will", "later", "soon", "next"],
                "present_markers": ["now", "today", "currently"],
                "patterns": [
                    # "yesterday eat" -> "I ate yesterday"
                    (r"\b(yesterday|before)\s+(\w+)", self._apply_past_tense),
                    # "tomorrow go" -> "I will go tomorrow"
                    (
                        r"\b(tomorrow|later|soon|next\s+\w+)\s+(\w+)",
                        self._apply_future_tense,
                    ),
                ],
            },
            # Question formation rules
            "question": {
                "markers": ["what", "where", "when", "who", "why", "how"],
                "patterns": [
                    # "what time lunch" -> "What time is lunch?"
                    (r"\b(what|where|when)\s+(.+)", self._form_question),
                ],
            },
            # Common AAC expansions
            "common_expansions": {
                # Feelings
                "happy": "I feel happy",
                "sad": "I feel sad",
                "angry": "I feel angry",
                "tired": "I feel tired",
                "hungry": "I feel hungry",
                "thirsty": "I feel thirsty",
                # Basic requests (single word)
                "help": "I need help",
                "more": "I want more",
                "please": "please",
                # Greetings
                "hello": "Hello",
                "hi": "Hi",
                "bye": "Goodbye",
                "thanks": "Thank you",
            },
        }

    def expand(
        self,
        symbols: List[Dict],
        raw_gloss: str,
        semantic_analysis: Optional[Dict] = None,
    ) -> Dict:
        """
        Main expansion method.

        Args:
            symbols: List of symbol dicts with label, category, etc.
            raw_gloss: Simple concatenation of symbol labels
            semantic_analysis: Optional semantic analysis from SymbolSemantics

        Returns:
            {
                'expanded_text': str,        # Fully expanded sentence
                'confidence': float,         # 0.0-1.0
                'transformations': List[str], # Rules applied
                'method': 'rules'            # Always rules for now
            }
        """
        # Check cache first
        cache_key = self._make_cache_key(symbols)
        if cache_key in self.expansion_cache:
            logger.debug(f"Cache hit for: {cache_key}")
            return self.expansion_cache[cache_key]

        # Start with raw gloss
        text = raw_gloss.strip().lower()
        transformations = []

        if not text:
            return {
                "expanded_text": "",
                "confidence": 0.0,
                "transformations": [],
                "method": "rules",
            }

        # Check for single-word common expansions first
        if len(symbols) == 1:
            single_word = text.lower()
            if single_word in self.grammar_rules["common_expansions"]:
                expanded = self.grammar_rules["common_expansions"][single_word]
                result = {
                    "expanded_text": self._polish_output(expanded),
                    "confidence": 0.95,
                    "transformations": ["common_expansion"],
                    "method": "rules",
                }
                self.expansion_cache[cache_key] = result
                return result

        # Apply grammar rules in sequence
        text, rules_applied = self._apply_grammar_rules(
            text, symbols, semantic_analysis
        )
        transformations.extend(rules_applied)

        # Final polish
        text = self._polish_output(text)

        result = {
            "expanded_text": text,
            "confidence": self._calculate_confidence(transformations),
            "transformations": transformations,
            "method": "rules",
        }

        # Cache result
        self.expansion_cache[cache_key] = result
        logger.debug(f"Expanded '{raw_gloss}' -> '{text}' (rules: {transformations})")

        return result

    def _apply_past_tense(self, match: re.Match) -> Optional[str]:
        """Apply past tense conjugation: 'yesterday eat' -> 'I ate yesterday'."""
        temporal = match.group(1)
        verb = match.group(2)

        # Simple past tense conjugation
        past_verb = self._conjugate_past(verb)
        return f"I {past_verb} {temporal}"

    def _apply_future_tense(self, match: re.Match) -> Optional[str]:
        """Apply future tense: 'tomorrow go' -> 'I will go tomorrow'."""
        temporal = match.group(1)
        verb = match.group(2)

        return f"I will {verb} {temporal}"

    def _conjugate_past(self, verb: str) -> str:
        """Convert verb to simple past tense."""
        # Irregular verbs (common AAC verbs)
        irregular = {
            "go": "went",
            "eat": "ate",
            "drink": "drank",
            "have": "had",
            "do": "did",
            "see": "saw",
            "come": "came",
            "make": "made",
            "take": "took",
            "get": "got",
            "give": "gave",
            "say": "said",
            "tell": "told",
            "think": "thought",
            "know": "knew",
            "feel": "felt",
            "find": "found",
            "leave": "left",
            "put": "put",
            "run": "ran",
            "sit": "sat",
            "stand": "stood",
            "write": "wrote",
            "read": "read",
            "hear": "heard",
            "buy": "bought",
            "sleep": "slept",
            "speak": "spoke",
            "teach": "taught",
            "learn": "learned",
            "play": "played",
            "want": "wanted",
            "need": "needed",
            "like": "liked",
            "love": "loved",
            "help": "helped",
            "work": "worked",
            "try": "tried",
            "ask": "asked",
            "use": "used",
            "show": "showed",
            "move": "moved",
            "live": "lived",
            "believe": "believed",
            "bring": "brought",
            "begin": "began",
            "keep": "kept",
            "hold": "held",
            "write": "wrote",
            "meet": "met",
            "cut": "cut",
            "let": "let",
            "set": "set",
            "win": "won",
            "lose": "lost",
            "pay": "paid",
            "send": "sent",
            "fall": "fell",
            "sell": "sold",
            "build": "built",
            "spend": "spent",
            "wear": "wore",
            "catch": "caught",
            "choose": "chose",
            "fight": "fought",
            "draw": "drew",
            "drive": "drove",
            "ride": "rode",
            "fly": "flew",
            "sing": "sang",
            "swim": "swam",
            "throw": "threw",
            "wake": "woke",
            "break": "broke",
            "steal": "stole",
            "tear": "tore",
            "freeze": "froze",
        }

        if verb in irregular:
            return irregular[verb]

        # Regular verbs: add -ed
        if verb.endswith("e"):
            return verb + "d"
        elif verb.endswith("y") and len(verb) > 1 and verb[-2] not in "aeiou":
            return verb[:-1] + "ied"
        elif (
            len(verb) >= 3
            and verb[-1] not in "aeiou"
            and verb[-2] in "aeiou"
            and verb[-3] not in "aeiou"
        ):
            # Double final consonant (e.g., 'stop' -> 'stopped')
            return verb + verb[-1] + "ed"
        else:
            return verb + "ed"

    def _apply_grammar_rules(
        self, text: str, symbols: List[Dict], semantic_analysis: Optional[Dict]
    ) -> Tuple[str, List[str]]:
        """Apply rule-based grammar transformations in priority order."""
        applied = []

        # 0. Tense markers (handle temporal expressions first)
        text, rule_applied = self._apply_tense_rules(text)
        if rule_applied:
            applied.append(rule_applied)

        # 1. Pronoun normalization (must come before verb conjugation)
        text, rule_applied = self._apply_pronoun_rules(text)
        if rule_applied:
            applied.append(rule_applied)

        # 2. Article insertion
        text, rule_applied = self._apply_article_rules(text)
        if rule_applied:
            applied.append(rule_applied)

        # 3. Verb conjugation (after pronoun fixes)
        text, rule_applied = self._apply_verb_rules(text)
        if rule_applied:
            applied.append(rule_applied)

        # 4. Question formation (use semantic intent if available)
        text, rule_applied = self._apply_question_rules(text, semantic_analysis)
        if rule_applied:
            applied.append(rule_applied)

        return text, applied

    def _apply_tense_rules(self, text: str) -> Tuple[str, Optional[str]]:
        """Apply tense marker rules."""
        for pattern, replacement_func in self.grammar_rules["tense"].get(
            "patterns", []
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if callable(replacement_func):
                    new_text = replacement_func(match)
                    if new_text:
                        text = text[: match.start()] + new_text + text[match.end() :]
                        return text, "tense_conjugation"
        return text, None

    def _apply_pronoun_rules(self, text: str) -> Tuple[str, Optional[str]]:
        """Apply pronoun normalization rules."""
        for pattern, replacement in self.grammar_rules["pronoun"]["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                if callable(replacement):
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                else:
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                return text, "pronoun_fix"
        return text, None

    def _apply_article_rules(self, text: str) -> Tuple[str, Optional[str]]:
        """Apply article insertion rules."""
        for pattern, replacement_func in self.grammar_rules["article"]["patterns"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if callable(replacement_func):
                    new_text = replacement_func(match)
                    if new_text:
                        text = text[: match.start()] + new_text + text[match.end() :]
                        return text, "article_insertion"
        return text, None

    def _apply_verb_rules(self, text: str) -> Tuple[str, Optional[str]]:
        """Apply verb conjugation rules."""
        for pattern, replacement in self.grammar_rules["verb"]["patterns"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if callable(replacement):
                    new_text = replacement(match)
                    if new_text:
                        text = text[: match.start()] + new_text + text[match.end() :]
                        return text, "verb_conjugation"
                else:
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                    return text, "verb_conjugation"
        return text, None

    def _apply_question_rules(
        self, text: str, semantic_analysis: Optional[Dict]
    ) -> Tuple[str, Optional[str]]:
        """Apply question formation rules."""
        if semantic_analysis and semantic_analysis.get("intent") == "question":
            # Already a question, ensure question mark at end
            if not text.rstrip().endswith("?"):
                text = text.rstrip(".!") + "?"
                return text, "question_mark"
        else:
            # Check for question words
            for pattern, replacement_func in self.grammar_rules["question"]["patterns"]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    if callable(replacement_func):
                        new_text = replacement_func(match)
                        if new_text:
                            return new_text, "question_formation"
        return text, None

    def _insert_article(self, match: re.Match) -> Optional[str]:
        """Insert appropriate article (a/an) before noun."""
        verb = match.group(1)
        noun = match.group(2)

        # Determine article
        article = self._get_article(noun)
        return f"{verb} {article} {noun}"

    def _insert_to_the(self, match: re.Match) -> Optional[str]:
        """Insert 'to the' for location verbs."""
        verb = match.group(1)
        location = match.group(2)
        return f"{verb} to the {location}"

    def _get_article(self, word: str) -> str:
        """Determine appropriate article (a/an) for word."""
        vowels = "aeiou"
        if word and word[0].lower() in vowels:
            return "an"
        return "a"

    def _conjugate_third_person(self, match: re.Match) -> Optional[str]:
        """Add -s/-es to verb for third-person singular."""
        subject = match.group(1)
        verb = match.group(2)

        conjugated = self._add_s(verb)
        return f"{subject} {conjugated}"

    def _add_s(self, verb: str) -> str:
        """Add appropriate -s/-es ending to verb."""
        if verb == "go":
            return "goes"
        elif verb == "have":
            return "has"
        elif verb.endswith("y") and len(verb) > 1 and verb[-2] not in "aeiou":
            return verb[:-1] + "ies"
        elif verb.endswith(("s", "sh", "ch", "x", "z", "o")):
            return verb + "es"
        else:
            return verb + "s"

    def _form_question(self, match: re.Match) -> Optional[str]:
        """Form a proper question from question word + phrase."""
        question_word = match.group(1).capitalize()
        rest = match.group(2).strip()

        # Simple question formation
        # "what time lunch" -> "What time is lunch?"
        # "where mom" -> "Where is mom?"

        # Check if there's a verb already
        has_verb = re.search(r"\b(is|are|was|were|do|does|did|can|will|should)\b", rest)

        if not has_verb:
            # Insert "is" as helper
            return f"{question_word} is {rest}?"
        else:
            return f"{question_word} {rest}?"

    def _polish_output(self, text: str) -> str:
        """Final cleanup and formatting."""
        if not text:
            return text

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        # Ensure terminal punctuation
        if text and not text[-1] in ".!?":
            text = text + "."

        return text

    def _calculate_confidence(self, transformations: List[str]) -> float:
        """Calculate confidence based on transformations applied."""
        if not transformations:
            return 0.6  # No changes = moderate confidence (might not need expansion)

        # More transformations = more confident we improved it
        base_confidence = 0.7
        bonus = min(len(transformations) * 0.05, 0.2)
        return min(base_confidence + bonus, 0.95)

    def _make_cache_key(self, symbols: List[Dict]) -> str:
        """Create cache key from symbol sequence."""
        labels = [s.get("label", "").lower() for s in symbols]
        return "|".join(labels)

    def clear_cache(self):
        """Clear the expansion cache (useful for testing)."""
        self.expansion_cache.clear()
        logger.debug("Expansion cache cleared")
