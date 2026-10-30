import sys
import os
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.aac_app.models.database import get_session, Symbol
from loguru import logger

def seed_core_vocabulary():
    """Seed the database with core vocabulary (pronouns, verbs, articles, etc.)"""
    
    core_vocab = [
        # Pronouns
        {"label": "I", "category": "pronouns", "keywords": "i, me, self"},
        {"label": "you", "category": "pronouns", "keywords": "you, your"},
        {"label": "he", "category": "pronouns", "keywords": "he, him, his"},
        {"label": "she", "category": "pronouns", "keywords": "she, her"},
        {"label": "it", "category": "pronouns", "keywords": "it, thing"},
        {"label": "we", "category": "pronouns", "keywords": "we, us, our"},
        {"label": "they", "category": "pronouns", "keywords": "they, them, their"},
        {"label": "me", "category": "pronouns", "keywords": "me, my"},
        {"label": "my", "category": "pronouns", "keywords": "my, mine"},
        
        # Verbs
        {"label": "want", "category": "verbs", "keywords": "want, desire, need"},
        {"label": "go", "category": "verbs", "keywords": "go, move, travel"},
        {"label": "like", "category": "verbs", "keywords": "like, enjoy, love"},
        {"label": "see", "category": "verbs", "keywords": "see, look, watch"},
        {"label": "have", "category": "verbs", "keywords": "have, possess, own"},
        {"label": "eat", "category": "verbs", "keywords": "eat, food, consume"},
        {"label": "drink", "category": "verbs", "keywords": "drink, thirsty"},
        {"label": "play", "category": "verbs", "keywords": "play, fun, game"},
        {"label": "sleep", "category": "verbs", "keywords": "sleep, rest, bed"},
        {"label": "stop", "category": "verbs", "keywords": "stop, end, finish"},
        {"label": "help", "category": "verbs", "keywords": "help, assist"},
        {"label": "is", "category": "verbs", "keywords": "is, be, exist"},
        {"label": "are", "category": "verbs", "keywords": "are, be"},
        {"label": "am", "category": "verbs", "keywords": "am, be"},
        {"label": "was", "category": "verbs", "keywords": "was, be"},
        {"label": "were", "category": "verbs", "keywords": "were, be"},
        
        # Articles & Prepositions
        {"label": "the", "category": "articles", "keywords": "the"},
        {"label": "a", "category": "articles", "keywords": "a, an"},
        {"label": "an", "category": "articles", "keywords": "an, a"},
        {"label": "in", "category": "prepositions", "keywords": "in, inside"},
        {"label": "on", "category": "prepositions", "keywords": "on, top"},
        {"label": "at", "category": "prepositions", "keywords": "at, location"},
        {"label": "to", "category": "prepositions", "keywords": "to, towards"},
        {"label": "for", "category": "prepositions", "keywords": "for, purpose"},
        {"label": "of", "category": "prepositions", "keywords": "of, belonging"},
        {"label": "with", "category": "prepositions", "keywords": "with, together"},
        
        # Social
        {"label": "yes", "category": "social", "keywords": "yes, agree, correct"},
        {"label": "no", "category": "social", "keywords": "no, disagree, incorrect"},
        {"label": "please", "category": "social", "keywords": "please, polite"},
        {"label": "thank you", "category": "social", "keywords": "thanks, gratitude"},
        {"label": "hello", "category": "social", "keywords": "hi, greetings"},
        {"label": "goodbye", "category": "social", "keywords": "bye, leave"},
    ]

    with get_session() as session:
        count = 0
        for item in core_vocab:
            # Check if exists (case insensitive)
            existing = session.query(Symbol).filter(Symbol.label.ilike(item["label"])).first()
            if not existing:
                new_symbol = Symbol(
                    label=item["label"],
                    category=item["category"],
                    keywords=item["keywords"],
                    is_builtin=True,
                    language="en"
                )
                session.add(new_symbol)
                count += 1
                logger.info(f"Added symbol: {item['label']}")
        
        session.commit()
        logger.success(f"Successfully added {count} core vocabulary symbols")

if __name__ == "__main__":
    seed_core_vocabulary()
