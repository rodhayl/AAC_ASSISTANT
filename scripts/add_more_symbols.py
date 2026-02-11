import os
import sys

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aac_app.models.database import Symbol, get_session  # noqa: E402


def add_symbols():
    new_symbols = [
        # People / Pronouns
        {"label": "I", "category": "people", "keywords": "I, me, self, pronoun"},
        {"label": "you", "category": "people", "keywords": "you, your, pronoun"},
        {
            "label": "mom",
            "category": "people",
            "keywords": "mom, mother, mommy, parent",
        },
        {
            "label": "dad",
            "category": "people",
            "keywords": "dad, father, daddy, parent",
        },
        {
            "label": "teacher",
            "category": "people",
            "keywords": "teacher, school, learn",
        },
        {"label": "friend", "category": "people", "keywords": "friend, play, buddy"},
        # Actions (Verbs)
        {"label": "want", "category": "action", "keywords": "want, desire, need"},
        {"label": "go", "category": "action", "keywords": "go, move, leave"},
        {"label": "stop", "category": "action", "keywords": "stop, halt, end"},
        {"label": "eat", "category": "action", "keywords": "eat, food, hungry"},
        {"label": "drink", "category": "action", "keywords": "drink, water, thirsty"},
        {"label": "play", "category": "action", "keywords": "play, fun, game"},
        {"label": "help", "category": "action", "keywords": "help, assist, aid"},
        {"label": "like", "category": "action", "keywords": "like, love, enjoy, good"},
        {"label": "see", "category": "action", "keywords": "see, look, watch, eyes"},
        {"label": "sleep", "category": "action", "keywords": "sleep, bed, tired, nap"},
        {"label": "come", "category": "action", "keywords": "come, here, arrive"},
        {"label": "give", "category": "action", "keywords": "give, share, present"},
        # Feelings
        {
            "label": "happy",
            "category": "feeling",
            "keywords": "happy, good, smile, joy",
        },
        {"label": "sad", "category": "feeling", "keywords": "sad, cry, bad, unhappy"},
        {"label": "angry", "category": "feeling", "keywords": "angry, mad, upset"},
        {
            "label": "tired",
            "category": "feeling",
            "keywords": "tired, sleep, exhausted",
        },
        {"label": "excited", "category": "feeling", "keywords": "excited, yay, fun"},
        {"label": "scared", "category": "feeling", "keywords": "scared, afraid, fear"},
        {"label": "sick", "category": "feeling", "keywords": "sick, ill, hurt, pain"},
        # Objects / Food
        {
            "label": "banana",
            "category": "food",
            "keywords": "banana, fruit, yellow, food",
        },
        {"label": "milk", "category": "drinks", "keywords": "milk, drink, white, cow"},
        {"label": "juice", "category": "drinks", "keywords": "juice, drink, fruit"},
        {
            "label": "cookie",
            "category": "food",
            "keywords": "cookie, snack, sweet, food",
        },
        {"label": "book", "category": "object", "keywords": "book, read, story"},
        {
            "label": "tablet",
            "category": "object",
            "keywords": "tablet, ipad, screen, game",
        },
        {"label": "toy", "category": "object", "keywords": "toy, play, game"},
        {"label": "ball", "category": "object", "keywords": "ball, play, sport, round"},
        # Places
        {"label": "home", "category": "place", "keywords": "home, house, live"},
        {"label": "school", "category": "place", "keywords": "school, learn, class"},
        {"label": "park", "category": "place", "keywords": "park, play, outside"},
        {
            "label": "outside",
            "category": "place",
            "keywords": "outside, outdoors, nature",
        },
        # Social / Common
        {"label": "yes", "category": "social", "keywords": "yes, agree, okay, good"},
        {"label": "no", "category": "social", "keywords": "no, disagree, stop, bad"},
        {"label": "please", "category": "social", "keywords": "please, ask, polite"},
        {
            "label": "thank you",
            "category": "social",
            "keywords": "thank you, thanks, polite",
        },
        {"label": "hello", "category": "social", "keywords": "hello, hi, greet, wave"},
        {
            "label": "goodbye",
            "category": "social",
            "keywords": "goodbye, bye, leave, wave",
        },
        {"label": "more", "category": "social", "keywords": "more, again, extra"},
        {
            "label": "finished",
            "category": "social",
            "keywords": "finished, done, end, all done",
        },
    ]

    with get_session() as session:
        count = 0
        for s_data in new_symbols:
            existing = (
                session.query(Symbol).filter(Symbol.label == s_data["label"]).first()
            )
            if not existing:
                symbol = Symbol(
                    label=s_data["label"],
                    category=s_data["category"],
                    keywords=s_data["keywords"],
                    description=f"Symbol for {s_data['label']}",
                    is_builtin=True,
                )
                session.add(symbol)
                count += 1
                print(f"Added symbol: {s_data['label']}")
            else:
                # Update category if needed (optional, but good for fixing existing data)
                if existing.category != s_data["category"]:
                    existing.category = s_data["category"]
                    print(f"Updated category for: {s_data['label']}")

        session.commit()
        print(f"Successfully added {count} new symbols.")


if __name__ == "__main__":
    add_symbols()
