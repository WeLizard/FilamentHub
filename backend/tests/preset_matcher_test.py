"""Unit tests for the deterministic preset↔printer scorer.

Pure-function coverage over in-memory model instances (no database).
"""

from __future__ import annotations

from app.models.filament import Filament
from app.models.preset import Preset
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.services.preset_matcher import (
    BONUS_OFFICIAL,
    BONUS_RATING_MAX,
    BONUS_WEIGHTED,
    apply_bonuses,
    evaluate_preset_compatibility,
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


def _preset(
    *linked: Printer,
    is_official: bool = False,
    is_weighted: bool = False,
    rating: float | None = None,
) -> Preset:
    preset = Preset(
        id=100,
        name="Test preset",
        extruder_temp=210,
        bed_temp=60,
        is_official=is_official,
        is_weighted=is_weighted,
        rating=rating,
    )
    preset.printer_links = [
        PresetPrinter(preset_id=100, printer_id=p.id, printer=p) for p in linked
    ]
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


def test_no_shared_catalog_specs_are_not_a_compatible_match() -> None:
    target = _printer(7, "Unknown", "A", nozzle=None, build=None)
    preset = _preset(_printer(8, "Other", "B", nozzle=None, build=None))

    assert score_preset_for_printer(preset, target) == (0.0, "no_match")


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


def test_known_hotend_conflict_is_hard_incompatibility() -> None:
    printer = _printer(20, "Voron", "2.4")
    printer.max_extruder_temp = 250
    printer.max_bed_temp = 120
    preset = _preset(printer)
    preset.extruder_temp = 280

    result = evaluate_preset_compatibility(
        preset,
        printer,
        None,
        None,
    )

    assert result.status == "incompatible"
    assert result.evidence_coverage == 1.0
    assert result.hard_conflicts == ["hotend_temperature"]
    temperature = next(check for check in result.checks if check.kind == "hotend_temperature")
    assert temperature.available_value == 250
    assert temperature.requirement_source == "preset"
    assert temperature.capability_source == "catalog_printer"


def test_known_bed_limit_conflict_is_hard_incompatibility() -> None:
    printer = _printer(26, "Voron", "2.4")
    printer.max_extruder_temp = 300
    printer.max_bed_temp = 50
    preset = _preset(printer)
    preset.bed_temp = 60

    result = evaluate_preset_compatibility(preset, printer, None, None)

    assert result.status == "incompatible"
    assert result.hard_conflicts == ["bed_temperature"]
    bed = next(check for check in result.checks if check.kind == "bed_temperature")
    assert bed.required_value == 60
    assert bed.available_value == 50
    assert bed.capability_source == "catalog_printer"


def test_missing_capability_is_unknown_not_compatible() -> None:
    printer = _printer(21, "Voron", "2.4", nozzle=None)
    printer.max_extruder_temp = None
    printer.max_bed_temp = None

    result = evaluate_preset_compatibility(
        _preset(printer),
        printer,
        None,
        None,
    )

    assert result.status == "unknown"
    assert result.technical_match is None
    assert result.evidence_coverage == 0.0
    assert all(check.status == "unknown" for check in result.checks)
    assert result.hard_conflicts == []


def test_partial_evidence_does_not_become_compatible() -> None:
    printer = _printer(22, "Voron", "2.4")
    printer.max_extruder_temp = None
    printer.max_bed_temp = None

    result = evaluate_preset_compatibility(_preset(printer), printer, None, None)

    assert result.status == "unknown"
    assert result.technical_match == 1.0
    assert result.evidence_count == 1
    assert result.evidence_total == 3
    assert result.evidence_coverage == 1 / 3


def test_exact_profile_nozzle_precedes_catalog_fallback() -> None:
    printer = _printer(23, "Voron", "2.4", nozzle=0.4)
    printer.max_extruder_temp = 300
    printer.max_bed_temp = 120
    preset = _preset(printer)

    fallback = evaluate_preset_compatibility(preset, printer, None, None)
    exact = evaluate_preset_compatibility(
        preset,
        printer,
        None,
        PrinterProfile(nozzle_diameters=[0.6], orcaslicer_settings={}),
    )

    fallback_nozzle = next(check for check in fallback.checks if check.kind == "nozzle_diameter")
    exact_nozzle = next(check for check in exact.checks if check.kind == "nozzle_diameter")
    assert fallback_nozzle.status == "compatible"
    assert fallback_nozzle.capability_source == "catalog_printer"
    assert exact_nozzle.status == "incompatible"
    assert exact_nozzle.available_values == (0.6,)
    assert exact_nozzle.capability_source == "printer_profile"
    assert exact.status == "incompatible"
    assert exact.hard_conflicts == ["nozzle_diameter"]


def test_material_nozzle_requirement_uses_exact_configuration() -> None:
    printer = _printer(24, "Voron", "2.4")
    printer.max_extruder_temp = 300
    printer.max_bed_temp = 120
    filament = Filament(required_nozzle_hrc=50)
    profile = PrinterProfile(orcaslicer_settings={"nozzle_type": ["brass"]})

    result = evaluate_preset_compatibility(
        _preset(printer),
        printer,
        filament,
        profile,
    )

    assert result.status == "incompatible"
    assert result.evidence_coverage == 1.0
    assert [check.kind for check in result.checks] == [
        "nozzle_diameter",
        "hotend_temperature",
        "bed_temperature",
        "nozzle_hrc",
    ]
    assert result.hard_conflicts == ["nozzle_hrc"]
    hrc = result.checks[-1]
    assert hrc.requirement_source == "filament_catalog"
    assert hrc.capability_source == "printer_profile"


def test_ranking_bonuses_do_not_change_technical_match() -> None:
    printer = _printer(25, "Voron", "2.4")
    printer.max_extruder_temp = 300
    printer.max_bed_temp = 120
    plain = _preset(printer)
    boosted = _preset(printer, is_official=True, is_weighted=True, rating=5.0)

    plain_match = evaluate_preset_compatibility(plain, printer, None, None)
    boosted_match = evaluate_preset_compatibility(boosted, printer, None, None)

    assert apply_bonuses(1.0, boosted) > apply_bonuses(1.0, plain)
    assert boosted_match.technical_match == plain_match.technical_match == 1.0
