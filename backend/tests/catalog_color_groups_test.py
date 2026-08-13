"""Core examples for the catalogue colour-group classifier."""

import pytest

from app.services.catalog_color_groups import classify_color_group, resolve_color_group


@pytest.mark.parametrize(
    ("color_hex", "visual_settings", "expected"),
    [
        ("#111111", None, "black"),
        ("#F5F5F5", None, "white"),
        ("#808080", None, "gray"),
        ("#FF0000", None, "red"),
        ("#FF7A00", None, "orange"),
        ("#FFD900", None, "yellow"),
        ("#00A651", None, "green"),
        ("#0066FF", None, "blue"),
        ("#7C3AED", None, "purple"),
        ("#FF69B4", None, "pink"),
        ("#8B4513", None, "brown"),
        ("#D4AF37", {"effects": ["metallic"]}, "gold"),
        ("#C0C0C0", {"effects": ["metallic"]}, "silver"),
        ("#00FFFF", None, "blue"),
        ("#008080", None, "green"),
        ("#800080", None, "purple"),
        ("#A52A2A", None, "brown"),
        ("#FFB6C1", None, "pink"),
        ("#C98C86", {"effects": ["metallic"]}, "pink"),
        ("#52664A", None, "green"),
        ("#C5A77B", {"filler": "wood"}, "brown"),
        ("#34383D", {"filler": "carbon"}, "gray"),
        ("#C9E8B4", {"filler": "luminescent"}, "green"),
        ("#7E9CAB", None, "blue"),
        ("#F05A28", None, "orange"),
    ],
)
def test_classifies_representative_catalogue_colours(
    color_hex: str,
    visual_settings: dict | None,
    expected: str,
):
    assert classify_color_group(color_hex, visual_settings) == expected


def test_manual_empty_group_preserves_multicolor_without_a_dominant_color():
    assert resolve_color_group(
        color_hex="#FF0000",
        visual_settings={"color_type": "gradient", "colors": ["#FF0000", "#0000FF"]},
        requested_group=None,
        requested_source="manual",
    ) == (None, "manual")
