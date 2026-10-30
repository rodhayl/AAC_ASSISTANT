import os
import sys

# Add the project root to the python path
sys.path.append(os.getcwd())

from src.aac_app.models.database import Symbol, get_session  # noqa: E402


def check_and_migrate_arasaac_symbols():
    print("Checking for ARASAAC symbols...")
    with get_session() as session:
        # Find symbols that have 'arasaac' in their image path or are from arasaac import
        # We'll look for 'arasaac' in the image_path as a heuristic,
        # or if we can identify them another way.
        # The user said "imported symbols currently default to 'general'".

        # Let's look for symbols with image_path containing 'arasaac'
        symbols = (
            session.query(Symbol).filter(Symbol.image_path.like("%arasaac%")).all()
        )

        print(f"Found {len(symbols)} symbols with 'arasaac' in image_path.")

        migrated_count = 0
        for symbol in symbols:
            print(
                f"Symbol: {symbol.label}, Category: {symbol.category}, Path: {symbol.image_path}"
            )
            if symbol.category == "general":
                print(f"  -> Migrating '{symbol.label}' to category 'ARASAAC'")
                symbol.category = "ARASAAC"
                migrated_count += 1

        if migrated_count > 0:
            session.commit()
            print(
                f"Successfully migrated {migrated_count} symbols to 'ARASAAC' category."
            )
        else:
            print("No symbols needed migration.")


if __name__ == "__main__":
    check_and_migrate_arasaac_symbols()
