"""Packagings stay consistent with the single main spool read by Orca and Spoolman."""

import pytest
from pydantic import ValidationError

from app.schemas.filament import FilamentCreate


def _create(**fields):
    return FilamentCreate(brand_id=1, name="PLA", material_type="PLA", **fields)


def test_first_single_packaging_becomes_the_main_spool():
    created = _create(
        packagings=[
            {"net_weight_g": 1000, "package_type": "multipack", "units_per_package": 4},
            {"net_weight_g": 750, "empty_spool_weight_g": 150},
        ]
    )

    assert (created.spool_weight, created.empty_spool_weight_g) == (750, 150)


def test_main_spool_weight_outside_the_listed_sizes_is_rejected():
    # The form's default 1000 g must not survive next to a 500 g product.
    with pytest.raises(ValidationError):
        _create(spool_weight=1000, packagings=[{"net_weight_g": 500}])


@pytest.mark.parametrize(
    "packaging",
    [
        {"net_weight_g": 1000, "ean": "4006381333932"},
        {"net_weight_g": 750, "package_type": "refill", "spool_width_mm": 60},
        {"net_weight_g": 1000, "package_type": "multipack"},
        {"net_weight_g": 1000, "gross_weight_g": 900},
    ],
)
def test_impossible_packagings_are_rejected(packaging):
    with pytest.raises(ValidationError):
        _create(packagings=[packaging])
