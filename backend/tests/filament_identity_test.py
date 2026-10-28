"""Probable-duplicate identity of two filaments of one brand."""

import pytest

from app.services.filament_identity import filament_identity, probable_duplicate


def _identity(brand: str, name: str, material: str, color: str | None, hex_: str | None):
    return filament_identity(
        brand_name=brand, name=name, material_type=material, color_name=color, color_hex=hex_
    )


# (brand, (name, material, colour, hex), (name, material, colour, hex), duplicate?)
CASES = [
    ("ELEGOO", ("PLA Matte Grey", "PLA", "Серый", "#A6A6A6"), ("PLA Matte", "PLA", "серый", "#A6A6A6"), True),
    ("ELEGOO", ("elegoo PLA+ rapid White", "PLA", "white", "#FFFFFF"), ("Pla Matte", "PLA", "Белый", "#FFFFFF"), False),
    ("ELEGOO", ("PLA Matte", "PLA", "Светло-серый", "#C8C8C8"), ("PLA Matte", "PLA", "Тёмно-серый", "#444444"), False),
    ("X", ("PLA", "PLA", "White", "#FFFFFF"), ("PLA+", "PLA", "White", "#FFFFFF"), False),
    ("ELEGOO", ("Elegoo PLA Matte Red", "PLA", None, "#FF0000"), ("PLA Matte", "PLA", "Красный", "#FF0000"), True),
    ("Hatchbox", ("Hatchbox PLA matte white", "PLA", "matte white", "#FFFFFF"), ("PLA Matte", "PLA", "White", "#FFFFFF"), True),
    ("eSUN", ("eSUN PLA+ red", "PLA", "red", "#B83E2C"), ("PLA+", "PLA+", "Красный", "#FF0000"), True),
    ("Bambu Lab", ("PLA Matte", "PLA", "Ivory White", "#FFFFFF"), ("PLA Matte", "PLA", "White", "#FFFFFF"), False),
    ("Sunlu", ("Sunlu PLA+ 2.0 (White)", "PLA", "White", "#FFFFFF"), ("PLA+ 2.0", "PLA", "Белый", "#FFFFFF"), True),
    ("Sunlu", ("PLA+ 2.0", "PLA", "White", "#FFFFFF"), ("PLA+", "PLA", "White", "#FFFFFF"), False),
    ("eSUN", ("PLA Basic", "PLA", None, "#FF0000"), ("PLA Basic", "PLA", None, "#0022FF"), False),
    ("eSUN", ("Translucent Light Blue", "PLA", "Light Blue", "#2600FF"), ("Translucent", "PLA", "Голубой", "#2600FF"), True),
    ("Bambu Lab", ("Matte", "PLA", "Dark Green", "#68724D"), ("PLA Matte", "PLA", "Тёмно-зелёный", "#68724D"), True),
    ("X", ("Matte PLA", "PLA", "Black", "#000000"), ("PLA Matte", "PLA", "Чёрный", "#111111"), True),
    ("X", ("PLA Silk", "PLA", "Gold", "#FFD700"), ("PLA Matte", "PLA", "Gold", "#FFD700"), False),
    ("X", ("PLA-CF", "PLA-CF", "Black", "#000000"), ("PLA", "PLA", "Black", "#000000"), False),
]


@pytest.mark.parametrize(("brand", "left", "right", "expected"), CASES)
def test_probable_duplicate_matches_reviewed_production_cases(brand, left, right, expected) -> None:
    assert probable_duplicate(_identity(brand, *left), _identity(brand, *right)) is expected
