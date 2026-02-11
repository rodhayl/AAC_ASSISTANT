import glob
import json
import os
import re


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_nested(data, key):
    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def scan_files():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    routers_dir = os.path.join(base_dir, "src", "api", "routers")

    # Load locales
    en_common_path = os.path.join(
        base_dir, "src", "frontend", "src", "locales", "en", "common.json"
    )
    es_common_path = os.path.join(
        base_dir, "src", "frontend", "src", "locales", "es", "common.json"
    )

    en_common = load_json(en_common_path)
    es_common = load_json(es_common_path)

    files = glob.glob(os.path.join(routers_dir, "*.py"))

    missing_en = []
    missing_es = []

    pattern = re.compile(r'get_text\(.*key=["\']([^"\']+)["\'].*\)')

    print(f"Scanning {len(files)} files in {routers_dir}...")

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            matches = pattern.findall(content)
            for key in matches:
                # Check EN
                if not get_nested(en_common, key):
                    # Try to check if it's in page specific files?
                    # For now, we assume backend uses common.json or we need to load others.
                    # The get_text implementation uses 'pages/learning' hardcoded in learning.py,
                    # but for others it seems we are adding to common.json?
                    # Wait, learning.py uses 'pages/learning'.
                    # Let's handle that exception or just check common.json for now.
                    if not key.startswith("errors."):
                        # Maybe it's a page key?
                        pass
                    else:
                        missing_en.append((os.path.basename(file_path), key))

                # Check ES
                if not get_nested(es_common, key):
                    if key.startswith("errors."):
                        missing_es.append((os.path.basename(file_path), key))

    if missing_en:
        print("\nMissing keys in EN common.json:")
        for file, key in missing_en:
            print(f"  - {file}: {key}")
    else:
        print("\nAll error keys found in EN common.json")

    if missing_es:
        print("\nMissing keys in ES common.json:")
        for file, key in missing_es:
            print(f"  - {file}: {key}")
    else:
        print("\nAll error keys found in ES common.json")


if __name__ == "__main__":
    scan_files()
