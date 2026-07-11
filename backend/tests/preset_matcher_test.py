"""Unit tests for the deterministic preset↔printer scorer.

Pure-function coverage over in-memory model instances (no database).
"""

from __future__ import annotations

from app.models.preset import Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.services.preset_matcher import (
    BONUS_OFFICIAL,
    BONUS_RATING_MAX,
    BONUS_WEIGHTED,
    apply_bonuses,
    score_preset_for_printer,
)


def _printer(
    pid: int,
    manufacturer: str,
    model: str,
    *,
    family: str | None = None,
    nozzle: float | None = 0.4,
    build: tuple[float, float, float] | None = (220, 220, 250),
) -> Printer:
    bx, by, bz = build if build else (None, None, None)
    return Printer(
        id=pid,
        name=f"{manufacturer} {model}",
        manufacturer=manufacturer,
        model=model,
        slug=f"{manufacturer}-{model}".lower().replace(" ", "-"),
        family=family,
        nozzle_diameter=nozzle,
        build_volume_x=bx,
        build_volume_y=by,
        build_volume_z=bz,
    )


def _preset(*linked: Printer, is_official: bool = False, is_weighted: bool = False, rating: float | None = None) -> Preset:
    preset = Preset(
        id=100,
        name="Test preset",
        extruder_temp=210,
        bed_temp=60,
        is_official=is_official,
        is_weighted=is_weighted,
        rating=rating,
    )
    preset.printer_links = [PresetPrinter(preset_id=100, printer_id=p.id, printer=p) for p in linked]
    return preset


TARGET = _printer(1, "Creality", "Ender 3 Pro", family="Ender")


def test_exact_match() -> None:
    preset = _preset(_printer(1, "Creality", "Ender 3 Pro", family="Ender"))
    assert score_preset_for_printer(preset, TARGET) == (1.0, "exact_match")


def test_same_model_different_id() -> None:
    preset = _preset(_printer(2, "Creality", "Ender 3 Pro", family="Ender"))
    assert score_preset_for_printer(preset, TARGET) == (0.9, "same_model")


def test_same_model_is_case_insensitive() -> None:
    preset = _preset(_printer(2, "creality", "ender 3 pro"))
    assert score_preset_for_printer(preset, TARGET) == (0.9, "same_model")


def test_same_family() -> None:
    preset = _preset(_printer(3, "Creality", "Ender 5", family="Ender"))
    assert score_preset_for_printer(preset, TARGET) == (0.7, "same_family")


def test_same_manufacturer() -> None:
    preset = _preset(_printer(4, "Creality", "CR-10", family="CR"))
    assert score_preset_for_printer(preset, TARGET) == (0.5, "same_manufacturer")


def test_compatible_specs_cross_manufacturer() -> None:
    preset = _preset(_printer(5, "Prusa", "MK4", family="MK", nozzle=0.4, build=(230, 230, 250)))
    assert score_preset_for_printer(preset, TARGET) == (0.3, "compatible_specs")


def test_no_match_incompatible_specs() -> None:
    preset = _preset(_printer(6, "Prusa", "XL", family="XL", nozzle=0.6, build=(360, 360, 360)))
    assert score_preset_for_printer(preset, TARGET) == (0.0, "no_match")


def test_best_of_multiple_links_wins() -> None:
    preset = _preset(
        _printer(4, "Creality", "CR-10"),  # same_manufacturer 0.5
        _printer(2, "Creality", "Ender 3 Pro", family="Ender"),  # same_model 0.9
    )
    assert score_preset_for_printer(preset, TARGET) == (0.9, "same_model")


def test_exact_short_circuits_over_others() -> None:
    preset = _preset(
        _printer(4, "Creality", "CR-10"),
        _printer(1, "Creality", "Ender 3 Pro"),  # exact by id
    )
    assert score_preset_for_printer(preset, TARGET) == (1.0, "exact_match")


def test_link_without_printer_is_skipped() -> None:
    preset = _preset(_printer(2, "Creality", "Ender 3 Pro"))
    preset.printer_links.append(PresetPrinter(preset_id=100, printer_id=999, printer=None))
    assert score_preset_for_printer(preset, TARGET) == (0.9, "same_model")


def test_bonuses_official_weighted_rating() -> None:
    preset = _preset(is_official=True, is_weighted=True, rating=5.0)
    expected = 0.9 + BONUS_OFFICIAL + BONUS_WEIGHTED + BONUS_RATING_MAX
    assert apply_bonuses(0.9, preset) == expected


def test_rating_bonus_is_capped() -> None:
    high = _preset(rating=5.0)
    assert apply_bonuses(0.0, high) == BONUS_RATING_MAX


def test_no_bonuses_when_flags_absent() -> None:
    preset = _preset()
    assert apply_bonuses(0.5, preset) == 0.5
