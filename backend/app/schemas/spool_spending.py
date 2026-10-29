"""Responses for a person's own filament spending."""

from __future__ import annotations

from pydantic import BaseModel


class SpendingCurrency(BaseModel):
    currency: str | None
    bought_total: float
    bought_count: int
    bought_priced_count: int
    consumed_value: float
    consumed_grams_priced: float
    shelf_value: float
    shelf_grams: float


class SpendingUnpriced(BaseModel):
    spools_without_price: int
    spools_total: int
    consumed_grams_without_price: float
    unreconciled_grams: float
    shelf_grams_without_price: float


class SpendingMonthCurrency(BaseModel):
    currency: str | None
    bought_total: float
    consumed_value: float


class SpendingMonth(BaseModel):
    month: str
    currencies: list[SpendingMonthCurrency]


class SpendingGroup(BaseModel):
    key: str | None
    currency: str | None
    bought_total: float
    bought_count: int
    initial_weight_g: float
    price_per_kg: float | None
    catalog_price_per_kg: float | None


class SpoolSpendingResponse(BaseModel):
    months: int
    currencies: list[SpendingCurrency]
    unpriced: SpendingUnpriced
    by_month: list[SpendingMonth]
    by_brand: list[SpendingGroup]
    by_material: list[SpendingGroup]
