"""Idempotent creation of several identical physical spools in one transaction."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import (
    ERR_FILAMENT_NOT_FOUND,
    ERR_SPOOL_BATCH_KEY_CONFLICT,
    ERR_SPOOL_BATCH_LIMIT,
    ERR_SPOOL_BATCH_PRICE_PRECISION,
    raise_error,
)
from app.models.currency import Currency
from app.models.filament import Filament
from app.models.spool_batch_receipt import SpoolBatchReceipt
from app.models.user import User
from app.models.user_limit import UserLimit
from app.models.user_spool import UserSpool
from app.schemas.spool import SpoolBatchCreateRequest, SpoolBatchResponse, SpoolResponse
from app.services.spool_service import (
    _build_response,
    _load_filament_info,
    stage_new_spool,
    validate_new_spool_fields,
)

DEFAULT_CURRENCY_DECIMALS = 2
DEFAULT_SPOOL_BATCH_LIMIT = 20


async def effective_spool_batch_limit(db: AsyncSession, user_id: int) -> int:
    override = await db.scalar(
        select(UserLimit.spool_batch_limit).where(UserLimit.user_id == user_id)
    )
    return DEFAULT_SPOOL_BATCH_LIMIT if override is None else override


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_digest(payload: SpoolBatchCreateRequest) -> str:
    body = payload.model_dump(mode="json", exclude={"idempotency_key", "price"})
    body["price"] = None if payload.price is None else format(payload.price.normalize(), "f")
    return _digest(json.dumps(body, sort_keys=True, separators=(",", ":")))


async def _currency_decimals(db: AsyncSession, code: str | None) -> int:
    if code is None:
        return DEFAULT_CURRENCY_DECIMALS
    decimals = await db.scalar(select(Currency.decimals).where(Currency.code == code))
    return DEFAULT_CURRENCY_DECIMALS if decimals is None else decimals


def split_total(total: Decimal, quantity: int, decimals: int) -> list[Decimal]:
    """Split ``total`` into ``quantity`` shares in minor units; leftover units go first."""
    scale = Decimal(10) ** decimals
    base, remainder = divmod(int(total * scale), quantity)
    return [Decimal(base + (1 if index < remainder else 0)) / scale for index in range(quantity)]


async def _plan_prices(
    db: AsyncSession, payload: SpoolBatchCreateRequest
) -> tuple[list[Decimal | None], Decimal | None]:
    if payload.price is None:
        return [None] * payload.quantity, None
    if payload.price_mode == "per_spool":
        return [payload.price] * payload.quantity, payload.price * payload.quantity
    decimals = await _currency_decimals(db, payload.currency)
    if payload.price != payload.price.quantize(Decimal(1).scaleb(-decimals)):
        raise_error(422, ERR_SPOOL_BATCH_PRICE_PRECISION, params={"decimals": decimals})
    return split_total(payload.price, payload.quantity, decimals), payload.price


async def _load_responses(
    db: AsyncSession, user_id: int, spool_ids: list[int]
) -> list[SpoolResponse]:
    if not spool_ids:
        return []
    result = await db.execute(
        select(UserSpool)
        .where(UserSpool.id.in_(spool_ids), UserSpool.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    by_id = {spool.id: spool for spool in result.scalars().all()}
    spools = [by_id[spool_id] for spool_id in spool_ids if spool_id in by_id]
    filament_ids = {spool.filament_id for spool in spools if spool.filament_id}
    filaments: dict[int, Filament] = {}
    if filament_ids:
        fil_result = await db.execute(
            select(Filament)
            .options(joinedload(Filament.brand))
            .where(Filament.id.in_(filament_ids))
        )
        filaments = {item.id: item for item in fil_result.unique().scalars().all()}
    return [
        _build_response(spool, filaments.get(spool.filament_id) if spool.filament_id else None)
        for spool in spools
    ]


async def _replay(
    db: AsyncSession, user_id: int, receipt: SpoolBatchReceipt, digest: str
) -> SpoolBatchResponse:
    if receipt.payload_digest != digest:
        raise_error(409, ERR_SPOOL_BATCH_KEY_CONFLICT)
    return SpoolBatchResponse(
        spools=await _load_responses(db, user_id, list(receipt.spool_ids)),
        replayed=True,
        price_mode=receipt.price_mode,
        total_price=receipt.total_price,
        currency=receipt.currency,
    )


async def _find_receipt(
    db: AsyncSession, user_id: int, key_digest: str
) -> SpoolBatchReceipt | None:
    return await db.scalar(
        select(SpoolBatchReceipt)
        .where(
            SpoolBatchReceipt.user_id == user_id,
            SpoolBatchReceipt.key_digest == key_digest,
        )
        .execution_options(populate_existing=True)
    )


async def create_spool_batch(
    db: AsyncSession, user: User, payload: SpoolBatchCreateRequest
) -> SpoolBatchResponse:
    user_id = user.id
    key_digest = _digest(payload.idempotency_key)
    digest = payload_digest(payload)

    existing = await _find_receipt(db, user_id, key_digest)
    if existing is not None:
        return await _replay(db, user_id, existing, digest)

    limit = await effective_spool_batch_limit(db, user_id)
    if payload.quantity > limit:
        raise_error(422, ERR_SPOOL_BATCH_LIMIT, params={"limit": limit})
    validate_new_spool_fields(payload)
    if payload.filament_id is not None:
        if await _load_filament_info(db, payload.filament_id) is None:
            raise_error(404, ERR_FILAMENT_NOT_FOUND)
    prices, total_price = await _plan_prices(db, payload)

    receipt = SpoolBatchReceipt(
        user_id=user_id,
        key_digest=key_digest,
        payload_digest=digest,
        quantity=payload.quantity,
        price_mode=payload.price_mode,
        total_price=total_price,
        currency=payload.currency,
        spool_ids=[],
    )
    db.add(receipt)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        winner = await _find_receipt(db, user_id, key_digest)
        if winner is None:
            raise
        return await _replay(db, user_id, winner, digest)

    try:
        spools = [
            await stage_new_spool(db, user, payload, None if price is None else float(price))
            for price in prices
        ]
        await db.flush()
        receipt.spool_ids = [spool.id for spool in spools]
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return SpoolBatchResponse(
        spools=await _load_responses(db, user_id, list(receipt.spool_ids)),
        replayed=False,
        price_mode=payload.price_mode,
        total_price=total_price,
        currency=payload.currency,
    )
