"""Layered content safety: policy resolution + deterministic filters.

Protects children from unwanted content with settings configurable by admins
(global defaults) and teachers (per-student overrides). Enforcement is
layered:

* prompt guardrails (Layer 0) live in the companion prompt builder;
* this module is Layer 1: a zero-cost, deterministic term filter applied to
  student *input* (chat answers, topics, board-AI prompts) and to AI
  *output* (chat answers, topic words, pictogram labels) *before and after*
  generation;
* a strict-level LLM moderation sentinel (Layer 2, chat output only) lives
  in ``learning/service.py`` and calls back into :func:`check_text`.

Policy resolution order: built-in defaults < admin global policy
(``app_settings`` key ``content_safety_policy``) < teacher per-student
overrides (``GuardianProfile.safety_constraints``). Admin may lock fields so
teacher overrides are rejected for them.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

GLOBAL_POLICY_KEY = "content_safety_policy"

LEVELS = ("strict", "standard", "relaxed")
VALID_LEVELS = set(LEVELS)

# Feature gates a teacher/admin can lock per student. ``None`` in a per-student
# profile means "follow the global setting".
FEATURE_LOCKS = (
    "block_ai_chat",
    "block_board_ai",
    "block_custom_topics",
    "block_autogen_pictograms",
    "block_social_messaging",
)

SURFACES = ("chat", "topic", "words", "pictogram", "board", "social")


# --- built-in term families (normalized: folded accents, lowercase) --------
# Deliberately a *small* explicit set: the deterministic layer blocks the
# obvious cases cheaply; the strict sentinel catches nuance. Terms use word
# boundaries so everyday AAC vocabulary ("muerte de la célula", "coger") is
# never a false positive.
_FAMILIES: dict[str, list[str]] = {
    "weapons": [
        "pistola", "escopeta", "ametralladora", "fusil", "cuchillo", "navaja",
        "bomba", "granada", "explosivo", "hacha", "espada", "ballesta",
        "gun", "rifle", "knife", "bomb", "grenade", "explosive", "sword",
        "weapon", "arma",
    ],
    "violence": [
        "asesinar", "asesinato", "decapitar", "torturar", "apuñalar",
        "violencia", "violento", "kill", "murder", "torture", "behead",
        "stab", "shoot", "shooting", "slaughter",
    ],
    "adult": [
        "pornografía", "porno", "prostituta", "sexo", "sexual", "desnudo",
        "pene", "vagina", "violación", "violar", "culo", "puta", "puto",
        "porn", "sex", "sexual", "nude", "naked", "penis", "vagina", "rape",
        "fuck", "shit", "dick", "cock",
    ],
    "selfharm": [
        "suicidio", "suicidarse", "autolesión", "cortarse las venas",
        "ahorcarse", "matarme", "quiero morir", "no quiero vivir",
        "suicide", "kill myself", "self harm", "cut myself", "hang myself",
        "i want to die", "i don't want to live",
    ],
    "drugs": [
        "cocaína", "marihuana", "heroína", "metanfetamina", "éxtasis",
        "droga", "drogas", "inyectarse", "cocaine", "marijuana", "heroin",
        "methamphetamine", "ecstasy", "drug", "drugs",
    ],
    "profanity": [
        "mierda", "gilipollas", "cabrón", "hijo de puta", "estúpido",
        "idiota", "joder", "asshole", "bitch", "stupid", "idiot",
    ],
}

# Which families apply at each content-filter level. Relaxed keeps only the
# hard lines (adult + self-harm); standard adds violence, weapons and drugs;
# strict adds profanity.
_LEVEL_FAMILIES: dict[str, tuple[str, ...]] = {
    "strict": ("weapons", "violence", "adult", "selfharm", "drugs", "profanity"),
    "standard": ("weapons", "violence", "adult", "selfharm", "drugs"),
    "relaxed": ("adult", "selfharm"),
}

# Compiled matchers per level: family name -> regex over its normalized terms.
_MATCHERS: dict[str, dict[str, re.Pattern[str]]] = {}


def _variants(term: str) -> list[str]:
    """Term plus common plural forms, so word-boundary matching still catches
    "pistolas" while the dictionary lists "pistola". Spanish: vowel -> +s,
    consonant -> +es; English: +s. Multi-word phrases are matched verbatim."""
    if len(term) <= 3 or " " in term or term.endswith("s"):
        return [term]
    if term[-1] in "aeiouAEIOU":
        return [term, term + "s"]
    return [term, term + "s", term + "es"]


def _compile_matchers() -> None:
    for level, families in _LEVEL_FAMILIES.items():
        level_matchers: dict[str, re.Pattern[str]] = {}
        for family in families:
            variants = [v for t in _FAMILIES[family] for v in _variants(t)]
            pattern = r"\b(?:{})\b".format("|".join(re.escape(v) for v in variants))
            level_matchers[family] = re.compile(pattern)
        _MATCHERS[level] = level_matchers


_compile_matchers()


def normalize_text(text: str | None) -> str:
    """Case-fold, strip accents, and collapse whitespace for matching."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFD", text)
    folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", folded.casefold()).strip()


@dataclass(frozen=True)
class ContentPolicy:
    """The effective policy for one student (or the server default)."""

    level: str = "standard"
    forbidden_topics: tuple[str, ...] = ()
    trigger_words: tuple[str, ...] = ()
    feature_locks: dict[str, bool] = field(default_factory=dict)
    sentinel_moderation: bool = False
    max_response_length: int | None = None

    def feature_blocked(self, feature: str) -> bool:
        return bool(self.feature_locks.get(feature, False))


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    matched_families: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        return not self.allowed


def default_content_policy() -> ContentPolicy:
    """Built-in defaults (no admin configuration stored yet)."""
    return ContentPolicy(level="standard")


def default_level_for_age(age: int | None) -> str:
    """Age-based default filter level when neither admin nor teacher set one."""
    if age is None:
        return "standard"
    if age < 8:
        return "strict"
    if age < 13:
        return "standard"
    return "relaxed"


# --- global (admin) policy storage -----------------------------------------


def load_global_policy() -> ContentPolicy:
    """Read the admin-configured global policy from app_settings."""
    try:
        from src.api.deps.settings import get_setting_value

        raw = get_setting_value(GLOBAL_POLICY_KEY, "")
        if not raw:
            return default_content_policy()
        data = json.loads(raw)
        return _policy_from_dict(data)
    except Exception as exc:
        logger.warning("Could not read global content policy: {}", exc)
        return default_content_policy()


def load_global_policy_dict() -> dict[str, Any]:
    """Raw stored global policy dict (incl. ``locked_fields``), or {}."""
    try:
        from src.api.deps.settings import get_setting_value

        raw = get_setting_value(GLOBAL_POLICY_KEY, "")
        if not raw:
            return {}
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Could not read global content policy dict: {}", exc)
        return {}


def _policy_from_dict(data: dict[str, Any]) -> ContentPolicy:
    level = data.get("level", "standard")
    if level not in VALID_LEVELS:
        level = "standard"
    locks = {}
    for feature in FEATURE_LOCKS:
        value = data.get("feature_locks", {}).get(feature)
        locks[feature] = bool(value)
    return ContentPolicy(
        level=level,
        forbidden_topics=tuple(str(t).strip() for t in data.get("forbidden_topics", []) if str(t).strip()),
        trigger_words=tuple(str(t).strip() for t in data.get("trigger_words", []) if str(t).strip()),
        feature_locks=locks,
        sentinel_moderation=bool(data.get("sentinel_moderation", False)),
        max_response_length=_optional_int(data.get("max_response_length")),
    )


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def locked_fields() -> tuple[str, ...]:
    """Fields in the global policy that teachers may not override."""
    return tuple(
        str(f) for f in load_global_policy_dict().get("locked_fields", []) if str(f) in FEATURE_LOCKS
    )


def save_global_policy(data: dict[str, Any]) -> ContentPolicy:
    """Persist the admin global policy and return the normalized version."""
    from src.aac_app.db import get_session
    from src.aac_app.models import AppSettings

    level = data.get("level", "standard")
    if level not in VALID_LEVELS:
        raise ValueError(f"invalid content_filter_level: {level!r}")
    normalized = {
        "level": level,
        "forbidden_topics": [str(t).strip() for t in data.get("forbidden_topics", []) if str(t).strip()],
        "trigger_words": [str(t).strip() for t in data.get("trigger_words", []) if str(t).strip()],
        "feature_locks": {
            f: bool(data.get("feature_locks", {}).get(f, False)) for f in FEATURE_LOCKS
        },
        "sentinel_moderation": bool(data.get("sentinel_moderation", False)),
        "max_response_length": _optional_int(data.get("max_response_length")),
        "locked_fields": [
            str(f) for f in data.get("locked_fields", []) if str(f) in FEATURE_LOCKS
        ],
    }
    with get_session() as db:
        setting = (
            db.query(AppSettings)
            .filter(AppSettings.setting_key == GLOBAL_POLICY_KEY)
            .first()
        )
        if setting is None:
            setting = AppSettings(setting_key=GLOBAL_POLICY_KEY)
            db.add(setting)
        setting.setting_value = json.dumps(normalized, ensure_ascii=False)
        db.commit()
    return _policy_from_dict(normalized)


# --- per-student resolution -------------------------------------------------


def resolve_policy_for_user(user_id: int | None, db=None) -> ContentPolicy:
    """Effective policy: global defaults merged with the student's guardian
    profile overrides (teacher-configured)."""
    if user_id is None:
        return load_global_policy()
    global_policy = load_global_policy()
    try:
        from src.aac_app.db import get_session
        from src.aac_app.models import GuardianProfile

        if db is None:
            with get_session() as session:
                profile = session.query(GuardianProfile).filter_by(user_id=user_id).first()
        else:
            profile = db.query(GuardianProfile).filter_by(user_id=user_id).first()
        if profile is None or not profile.safety_constraints:
            return global_policy
        safety = profile.safety_constraints or {}
    except Exception as exc:
        logger.warning("Could not resolve per-student content policy: {}", exc)
        return global_policy

    level = safety.get("content_filter_level") or global_policy.level
    if level not in VALID_LEVELS:
        level = global_policy.level

    forbidden = list(global_policy.forbidden_topics) + [
        str(t).strip() for t in safety.get("forbidden_topics", []) if str(t).strip()
    ]
    triggers = list(global_policy.trigger_words) + [
        str(t).strip() for t in safety.get("trigger_words", []) if str(t).strip()
    ]
    locks = dict(global_policy.feature_locks)
    for feature in FEATURE_LOCKS:
        value = safety.get(feature)
        if isinstance(value, bool):
            locks[feature] = value
    sentinel = global_policy.sentinel_moderation
    if isinstance(safety.get("sentinel_moderation"), bool):
        sentinel = safety["sentinel_moderation"]
    max_len = global_policy.max_response_length
    if isinstance(safety.get("max_response_length"), int):
        max_len = safety["max_response_length"]

    return ContentPolicy(
        level=level,
        forbidden_topics=tuple(dict.fromkeys(forbidden)),
        trigger_words=tuple(dict.fromkeys(triggers)),
        feature_locks=locks,
        sentinel_moderation=sentinel,
        max_response_length=max_len,
    )


# --- deterministic checks ---------------------------------------------------


def _build_custom_matcher(terms: list[str]) -> re.Pattern[str] | None:
    cleaned = [normalize_text(t) for t in terms]
    cleaned = [v for t in cleaned if t for v in _variants(t)]
    if not cleaned:
        return None
    return re.compile(r"\b(?:{})\b".format("|".join(re.escape(t) for t in cleaned)))


def check_text(policy: ContentPolicy, text: str | None) -> Verdict:
    """Deterministic Layer-1 check over normalized text.

    Applies the built-in term families for the policy level plus the
    configured forbidden topics and trigger words. Returns matched families
    and the exact matched terms for auditing.
    """
    normalized = normalize_text(text)
    if not normalized:
        return Verdict(allowed=True)
    matched_families: list[str] = []
    matched_terms: list[str] = []
    for family in _LEVEL_FAMILIES.get(policy.level, _LEVEL_FAMILIES["standard"]):
        matcher = _MATCHERS[policy.level][family]
        if matcher.search(normalized):
            matched_families.append(family)
            exact = [
                t
                for t in _FAMILIES[family]
                if re.search(rf"\b{re.escape(t)}\b", normalized)
            ]
            if exact:
                matched_terms.extend(exact)
            else:
                # Only a plural/derived form matched — record the family label
                # so the audit log still shows which block fired.
                matched_terms.append(f"{family}*")
    custom_terms = list(policy.forbidden_topics) + list(policy.trigger_words)
    custom = _build_custom_matcher(custom_terms)
    if custom is not None and custom.search(normalized):
        matched_families.append("configured")
        matched_terms.extend(
            t
            for t in custom_terms
            if re.search(rf"\b{re.escape(normalize_text(t))}\b", normalized)
        )
    if not matched_families:
        return Verdict(allowed=True)
    # dedupe preserving order
    seen: set[str] = set()
    unique_terms = [t for t in matched_terms if not (t in seen or seen.add(t))]
    return Verdict(
        allowed=False,
        matched_families=tuple(matched_families),
        matched_terms=tuple(unique_terms),
    )


def log_event(
    *,
    user_id: int | None,
    surface: str,
    direction: str = "output",
    verdict: str = "blocked",
    matched: list[str] | None = None,
    detail: str | None = None,
    db=None,
) -> None:
    """Persist one content-safety event. Best-effort: never raises."""
    if surface not in SURFACES:
        surface = "chat"
    try:
        from src.aac_app.db import get_session
        from src.aac_app.models import ContentSafetyEvent

        event = ContentSafetyEvent(
            user_id=user_id,
            surface=surface,
            direction=direction,
            verdict=verdict,
            matched=matched or [],
            detail=detail,
        )
        if db is not None:
            db.add(event)
            db.commit()
        else:
            with get_session() as session:
                session.add(event)
                session.commit()
    except Exception as exc:
        logger.warning("Failed to log content-safety event: {}", exc)


def purge_ai_symbols(db=None) -> int:
    """Delete every auto-generated pictogram symbol row and its image file."""
    from src.aac_app.db import get_session
    from src.aac_app.models import Symbol
    from src.aac_app.services.symbol_svg_autogen import _AUTOGEN_DESC_PREFIX

    def _purge(session) -> int:
        rows = (
            session.query(Symbol)
            .filter(Symbol.description.like(f"{_AUTOGEN_DESC_PREFIX}%"))
            .all()
        )
        count = 0
        for symbol in rows:
            if symbol.image_path:
                with suppress(OSError):
                    path = os.path.join("uploads", symbol.image_path.lstrip("/"))
                    if os.path.exists(path):
                        os.remove(path)
            session.delete(symbol)
            count += 1
        session.commit()
        return count

    if db is not None:
        return _purge(db)
    with get_session() as session:
        return _purge(session)
