"""Feature spellings in any interface language reach the catalog as one code."""

import pytest

from app.schemas.filament import FilamentAdditive, FilamentPropertyClaim, FilamentVisualSettings
from app.services.catalog_feature_search import resolve_catalog_feature_codes


@pytest.mark.parametrize("spelling", ["Стекловолокно", "glass fibre", "GF", "玻璃纤维"])
def test_additive_spellings_store_one_code(spelling):
    assert FilamentAdditive(code=spelling).code == "glass_fiber"


def test_ambiguous_words_stay_as_written():
    # "carbon" may be fibre or carbon black; "colour change" may be angle, UV or heat.
    assert FilamentAdditive(code="carbon").code == "carbon"
    assert FilamentVisualSettings(effects=["Color-Change"]).effects == ["color_change"]


def test_visual_spellings_map_to_codes_and_merge_duplicates():
    settings = FilamentVisualSettings(
        finish="Шёлковый",
        color_type="4-color",
        colors=["#000000"] * 4,
        effects=["Sparkle", "glitter", "Glow in the Dark", "хамелеон"],
    )

    assert settings.finish == "silk"
    assert settings.color_type == "four"
    assert settings.effects == ["glitter", "luminescent", "color_shift"]
    assert settings.filler == "glitter"


def test_claim_abbreviation_maps_to_code():
    assert FilamentPropertyClaim(code="FR").code == "flame_retardant"


def test_search_finds_codes_by_spelling_but_abbreviations_only_as_words():
    assert resolve_catalog_feature_codes("стекловолокно").additives == ("glass_fiber",)
    assert resolve_catalog_feature_codes("PETG GF").additives == ("glass_fiber",)
    assert resolve_catalog_feature_codes("fresh").claims == ()
    assert resolve_catalog_feature_codes("мрамор").effects == ("stone",)
