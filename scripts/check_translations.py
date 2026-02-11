import json
import os
from pathlib import Path


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return {}


def compare_keys(base_data, target_data, path=""):
    missing = []
    if isinstance(base_data, dict):
        for key, value in base_data.items():
            current_path = f"{path}.{key}" if path else key
            if key not in target_data:
                missing.append(current_path)
            else:
                missing.extend(compare_keys(value, target_data[key], current_path))
    return missing


def main():
    base_dir = Path(
        r"c:\Users\rulfe\GitHub\AAC_ASSISTANT_TRAE\src\frontend\src\locales"
    )
    en_dir = base_dir / "en"
    es_dir = base_dir / "es"

    print("Checking for missing keys in ES...")

    # Walk through EN directory
    for root, _, files in os.walk(en_dir):
        for file in files:
            if not file.endswith(".json"):
                continue

            rel_path = Path(root).relative_to(en_dir)
            en_file_path = Path(root) / file
            es_file_path = es_dir / rel_path / file

            if not es_file_path.exists():
                print(f"MISSING FILE: {rel_path / file}")
                continue

            en_data = load_json(en_file_path)
            es_data = load_json(es_file_path)

            missing_keys = compare_keys(en_data, es_data)
            if missing_keys:
                print(f"\nFile: {rel_path / file}")
                for key in missing_keys:
                    print(f"  - {key}")


if __name__ == "__main__":
    main()
