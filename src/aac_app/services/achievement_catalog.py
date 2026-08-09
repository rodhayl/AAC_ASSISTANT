"""Canonical predefined achievement definitions."""

from __future__ import annotations

# Keep this data separate from the service so first-run seeding and runtime
# awarding cannot drift apart. Callers copy individual mappings before
# mutating them; the catalog itself is treated as read-only.
PREDEFINED_ACHIEVEMENTS: dict[str, dict[str, object]] = {
    "first_steps": {
        "name": "First Steps",
        "description": "Complete your first learning session",
        "category": "beginner",
        "criteria_type": "sessions_completed",
        "criteria_value": 1,
        "points": 10,
        "icon": "🎯",
    },
    "vocabulary_explorer": {
        "name": "Vocabulary Explorer",
        "description": "Learn 10 new words",
        "category": "vocabulary",
        "criteria_type": "vocabulary_size",
        "criteria_value": 10,
        "points": 25,
        "icon": "📚",
    },
    "quick_learner": {
        "name": "Quick Learner",
        "description": "Answer 5 questions correctly",
        "category": "performance",
        "criteria_type": "correct_answers",
        "criteria_value": 5,
        "points": 20,
        "icon": "⚡",
    },
    "comprehension_champion": {
        "name": "Comprehension Champion",
        "description": "Achieve 80% comprehension score",
        "category": "performance",
        "criteria_type": "comprehension_score",
        "criteria_value": 0.8,
        "points": 100,
        "icon": "🏆",
    },
    "streak_master": {
        "name": "Streak Master",
        "description": "Complete sessions for 3 consecutive days",
        "category": "consistency",
        "criteria_type": "consecutive_days",
        "criteria_value": 3,
        "points": 50,
        "icon": "🔥",
    },
    "dedicated_learner": {
        "name": "Dedicated Learner",
        "description": "Complete 10 learning sessions",
        "category": "consistency",
        "criteria_type": "sessions_completed",
        "criteria_value": 10,
        "points": 75,
        "icon": "📖",
    },
    "topic_expert": {
        "name": "Topic Expert",
        "description": "Complete sessions in 5 different topics",
        "category": "exploration",
        "criteria_type": "topics_completed",
        "criteria_value": 5,
        "points": 60,
        "icon": "🌟",
    },
    "voice_pioneer": {
        "name": "Voice Pioneer",
        "description": "Use voice input 10 times",
        "category": "interaction",
        "criteria_type": "voice_usage",
        "criteria_value": 10,
        "points": 30,
        "icon": "🎤",
    },
}

INITIAL_ACHIEVEMENT_KEYS = (
    "first_steps",
    "vocabulary_explorer",
    "quick_learner",
)
