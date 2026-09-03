"""Shared prompt and response helpers for the learning service."""

import re

# Pedagogical policy shared by question-difficulty selection (questions.py)
# and next-action decisions (responses.py). Keep the thresholds in one place
# so the two modules cannot drift apart.
COMPREHENSION_REVIEW_BELOW = 0.4
COMPREHENSION_READY_AT = 0.8
COMPREHENSION_INTERMEDIATE_BELOW = 0.7
MIN_ANSWERS_FOR_READY = 5
MIN_ANSWERS_FOR_REVIEW = 3


def difficulty_for_score(score: float) -> str:
    """Map a comprehension score to a question difficulty band."""
    if score < COMPREHENSION_REVIEW_BELOW:
        return "basic"
    if score < COMPREHENSION_INTERMEDIATE_BELOW:
        return "intermediate"
    return "advanced"


def next_action_for(*, comprehension_score: float, questions_answered: int) -> str:
    """Map session progress to the frontend next-action hint."""
    if (
        comprehension_score >= COMPREHENSION_READY_AT
        and questions_answered >= MIN_ANSWERS_FOR_READY
    ):
        return "ready_for_activity"
    if (
        comprehension_score < COMPREHENSION_REVIEW_BELOW
        and questions_answered >= MIN_ANSWERS_FOR_REVIEW
    ):
        return "review_needed"
    return "continue_questions"


def _strip_reasoning(text: str) -> str:
    """
    Lightweight fallback to remove any thinking/reasoning tags from text.

    With JSON mode, this should rarely be needed. It's kept as a safety net
    for when JSON parsing fails or for legacy data.
    """
    if not text:
        return text

    cleaned = text

    # Remove explicit reasoning blocks
    cleaned = re.sub(r"```(?:thinking|reasoning)[\s\S]*?```", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)

    # If there's an explicit answer marker, extract that
    for marker in ["final answer:", "final response:", "answer:", "response:"]:
        idx = cleaned.lower().rfind(marker)
        if idx != -1:
            cleaned = cleaned[idx + len(marker) :].strip()
            break

    return cleaned.strip() or text


class AACPromptProfile:
    """
    Optimized prompt configuration specifically for AAC interactions.
    Provides tuned parameters for AAC-specific LLM interactions.

    Note: Response templates have been removed in favor of the
    Guardian Profile template system which provides more flexibility.
    """

    def __init__(self):
        self.max_tokens = 150  # Shorter, focused responses
        self.temperature = 0.6  # Balanced creativity/consistency

    def build_prompt(
        self,
        student_message: str,
        semantic_analysis: dict,
        expansion_result: dict,
        topic: str,
        recent_context: str = "",
    ) -> str:
        """
        Build AAC-optimized prompt with semantic and expansion context.

        Args:
            student_message: Original/enriched message from student
            semantic_analysis: Intent and semantic role information
            expansion_result: Grammar expansion result
            topic: Learning session topic
            recent_context: Recent conversation history

        Returns:
            Formatted prompt string for LLM
        """
        intent = semantic_analysis.get("intent", "statement")
        expanded = expansion_result.get("expanded_text", student_message)
        confidence = expansion_result.get("confidence", 0.5)
        transformations = expansion_result.get("transformations", [])

        prompt_parts = []

        # Context from recent conversation
        if recent_context:
            prompt_parts.append(f"Previous conversation:\n{recent_context}\n")

        # Student's communication with expansion details
        prompt_parts.append(f"Student's AAC message: {student_message}")

        if expanded != student_message and confidence > 0.6:
            prompt_parts.append(f"Expanded interpretation: {expanded}")
            if transformations:
                prompt_parts.append(f"Grammar improvements: {', '.join(transformations)}")

        # Semantic intent context
        prompt_parts.append(f"Detected intent: {intent.upper()}")

        # Intent-specific guidance
        intent_guidance = {
            "request": "The student is making a request. Acknowledge what they want and respond supportively.",
            "question": "The student is asking a question. Provide a clear, simple answer.",
            "greeting": "The student is greeting you. Respond warmly and encourage further interaction.",
            "feeling": "The student is expressing an emotion. Show empathy and provide validation.",
            "statement": "The student is making a statement. Acknowledge and build on their message.",
        }

        if intent in intent_guidance:
            prompt_parts.append(intent_guidance[intent])

        # Topic connection
        prompt_parts.append(f"Topic of discussion: {topic}")

        # Response instructions - simple and direct for JSON mode
        prompt_parts.append(
            "\nWrite a friendly, encouraging response to the student (1-2 sentences). "
            "Ask a follow-up question OR share a helpful fact about the topic."
        )

        return "\n".join(prompt_parts)

    def get_params(self) -> dict:
        """Get optimized LLM parameters for AAC."""
        return {"max_tokens": self.max_tokens, "temperature": self.temperature}


AAC_SYSTEM_PROMPT = """You are an AAC-specialized tutor with expertise in Augmentative and Alternative Communication.

Key principles:
1. Students use symbol-based communication which may be telegraphic (missing articles, conjunctions, etc.)
2. Interpret intent from semantic roles (subject, action, object) rather than strict grammar
3. Expand telegraphic phrases into grammatically complete sentences while preserving the student's meaning
4. Use simple, clear language in your responses (max 2-3 sentences)
5. Be encouraging and patient - communication takes effort
6. Ask ONE clarifying question if intent is ambiguous
7. Model proper grammar without correcting the student's AAC usage

Symbol categories guide semantic interpretation:
- Person symbols → subjects/agents (who)
- Action symbols → verbs (what doing)
- Object symbols → targets/themes (what)
- Feeling symbols → emotional states
- Place symbols → locations (where)
- Question symbols → interrogatives

Always celebrate communication attempts and build on the student's message.

When responding:
1. Understand the student's intent deeply
2. Provide a warm, encouraging response
3. Use simple, clear language
4. Ask follow-up questions to keep the conversation flowing"""
