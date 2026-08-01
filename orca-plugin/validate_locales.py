from __future__ import annotations

import json
import string
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CATALOG_DIR = ROOT / "filamenthub_locales"
ORCA_UI_LOCALES = {
    "ca", "cs", "de", "en", "es", "eu", "fr", "hu", "it", "ja", "ko",
    "lt", "nl", "pl", "pt_BR", "ru", "sv", "th", "tr", "uk", "vi",
    "zh_CN", "zh_TW",
}


def placeholders(value: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(value)
        if field_name
    }


def validate_catalogs(catalog_dir: Path = CATALOG_DIR) -> list[str]:
    errors: list[str] = []
    catalogs: dict[str, dict[str, str]] = {}
    for path in sorted(catalog_dir.glob("*.json")):
        locale = path.stem
        if locale not in ORCA_UI_LOCALES:
            errors.append(f"{path.name}: locale is not supported by OrcaSlicer")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: invalid UTF-8 JSON: {exc}")
            continue
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value.strip()
            for key, value in data.items()
        ):
            errors.append(f"{path.name}: catalog must contain non-empty string values")
            continue
        catalogs[locale] = data

    english = catalogs.get("en")
    if not english:
        return errors + ["en.json: canonical English catalog is required"]

    english_keys = set(english)
    for locale, catalog in catalogs.items():
        unknown = sorted(set(catalog) - english_keys)
        if unknown:
            errors.append(f"{locale}.json: unknown keys: {', '.join(unknown)}")
        for key, value in catalog.items():
            if key not in english:
                continue
            try:
                actual = placeholders(value)
                expected = placeholders(english[key])
            except ValueError as exc:
                errors.append(f"{locale}.json:{key}: invalid placeholder syntax: {exc}")
                continue
            if actual != expected:
                errors.append(
                    f"{locale}.json:{key}: placeholders {sorted(actual)} != {sorted(expected)}"
                )
    return errors


def main() -> int:
    errors = validate_catalogs()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: {len(list(CATALOG_DIR.glob('*.json')))} locale catalogs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
