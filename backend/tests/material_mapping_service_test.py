"""The OrcaSlicer parent of an exported filament, chosen from its material.

A parent that is not an OrcaSlicer library preset either fails to resolve on a
receiver's machine or restricts the preset to a vendor's printers; both hide
the synchronized preset.
"""

import pytest

from app.services.material_mapping_service import (
    ORCA_LIBRARY_PARENTS,
    UNKNOWN_MATERIAL_PARENT,
    orca_parent_for_material,
)


@pytest.mark.parametrize(
    ("material", "parent"),
    [
        # Materials of the production catalogue keep their parent.
        ("PLA", "Generic PLA @System"),
        ("PLA+", "Generic PLA @System"),
        ("PETG", "Generic PETG @System"),
        ("PET-GF", "Generic PETG @System"),
        ("ABS", "Generic ABS @System"),
        ("ABS-CF", "Generic ABS @System"),
        ("ABS-GF", "Generic ABS @System"),
        ("PA", "Generic PA @System"),
        ("TPU", "Generic TPU @System"),
        # A variant the library knows gets that library preset.
        ("PLA-CF", "Generic PLA-CF @System"),
        ("CF PLA", "Generic PLA-CF @System"),
        ("Silk PLA", "Generic PLA Silk @System"),
        ("PLA Matte", "Generic PLA Matte @System"),
        ("PETG-HF", "Generic PETG HF @System"),
        ("PETG-CF", "Generic PETG-CF @System"),
        ("PA12-CF", "Generic PA-CF @System"),
        ("PPA-GF", "Generic PPA-GF @System"),
        ("PP+", "Generic PP @System"),
        ("HIPS", "Generic HIPS @System"),
        ("PCTG", "Generic PCTG @System"),
        # Names that used to fall through to no parent at all.
        ("CPE", "Generic CoPE @System"),
        ("CoPET", "Generic CoPE @System"),
        ("HTPLA", "Generic PLA @System"),
        ("TPU95A", "Generic TPU @System"),
        ("TPE", "Generic TPU @System"),
        ("PEBA", "Generic TPU @System"),
        # Blends follow one rule however they are written.
        ("PC-ABS", "Generic PC @System"),
        ("PC/ABS", "Generic PC @System"),
        ("PEI-9085", "Generic PC @System"),
        # Nothing to go on: an explicit PLA parent, never none.
        ("PMMA", UNKNOWN_MATERIAL_PARENT),
        ("", UNKNOWN_MATERIAL_PARENT),
        (None, UNKNOWN_MATERIAL_PARENT),
    ],
)
def test_material_selects_the_closest_library_parent(material, parent):
    assert orca_parent_for_material(material, log_unknown=False) == parent


def test_every_parent_is_an_orca_library_preset():
    materials = [
        "PLA", "PLA-CF", "PLA Silk", "PLA Matte", "PLA HS", "PETG", "PETG HF",
        "PETG-CF", "PET", "PCTG", "CPE", "ABS", "ASA", "HIPS", "PC", "PEEK", "PA",
        "PA6-GF", "PA-CF", "PPA", "PPA-CF", "PPA-GF", "PP", "PP-CF", "PP-GF", "PE",
        "PE-CF", "TPU", "EVA", "PVA", "PVB", "BVOH", "PHA", "SBS", "POM", "PVDF",
        "WOOD",
    ]
    parents = {orca_parent_for_material(m, log_unknown=False) for m in materials}
    assert parents <= ORCA_LIBRARY_PARENTS, parents - ORCA_LIBRARY_PARENTS
