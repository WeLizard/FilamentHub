"""Versioned QR envelopes, personal spool bindings, and compact batch issuance."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, TypeVar, cast
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import delete, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_FILAMENT_NOT_FOUND,
    ERR_MANUFACTURER_QR_MATERIAL_LOCKED,
    ERR_QR_BATCH_LIMIT_EXCEEDED,
    ERR_QR_BATCH_NOT_FOUND,
    ERR_QR_BINDING_REVISION_CONFLICT,
    ERR_QR_BINDING_STATE_CONFLICT,
    ERR_QR_IDEMPOTENCY_CONFLICT,
    ERR_QR_IDEMPOTENCY_KEY_INVALID,
    ERR_QR_INSTANCE_UNAVAILABLE,
    ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE,
    ERR_QR_NOT_FOUND,
    ERR_QR_PAYLOAD_TOO_LONG,
    ERR_QR_RECOVERY_EXPIRED,
    ERR_QR_SPOOL_FILAMENT_REQUIRED,
    raise_error,
)
from app.core.field_encryption import blind_index, decrypt_field, encrypt_field
from app.models.filament import Filament
from app.models.qr_identity import (
    QrManufacturerBatch,
    QrManufacturerBatchItem,
    QrManufacturerBatchMode,
    QrManufacturerBatchStatus,
    QrManufacturerInstanceState,
    QrManufacturerInstanceStatus,
    QrOperationReceipt,
    QrUserBindingState,
    QrUserSpoolBinding,
)
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.qr_identity import (
    ManufacturerQrBatchCreateRequest,
    ManufacturerQrBatchItemResponse,
    ManufacturerQrBatchListResponse,
    ManufacturerQrBatchResponse,
    ManufacturerQrClaimResponse,
    ManufacturerQrExceptionResponse,
    ManufacturerQrPayloadPage,
    ManufacturerQrPayloadResponse,
    UserSpoolQrListResponse,
    UserSpoolQrResponse,
)
from app.services.qr_service import _qr_target_url, ensure_filament_qr_code
from app.services.territorial_access import active_grant_brand_ids_for, active_grants_for

logger = logging.getLogger(__name__)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

QR_ENVELOPE_PREFIX = "FHQ1_"
QR_ENVELOPE_VERSION = 1
QR_MAX_SHORT_CODE_LENGTH = 100
QR_USER_RECOVERY_DAYS = 7
QR_BINDING_SWEEP_INTERVAL_SECONDS = 60 * 60
QR_BINDING_CLEANUP_BATCH_SIZE = 500
QR_MANUFACTURER_MAX_BATCH_QUANTITY = 1_000_000
QR_MANUFACTURER_MAX_PAYLOAD_PAGE = 1_000

_BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PRODUCT_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


@dataclass(frozen=True)
class ParsedQrEnvelope:
    product_code: str
    namespace: str
    token: str


@dataclass(frozen=True)
class ManufacturerTokenReference:
    batch_ref: str
    ordinal: int


@dataclass
class QrResolution:
    """Product always resolves first; optional instance facts are actor-scoped."""

    filament: Filament
    envelope_version: int
    mode: str
    issuer: str | None
    resolution: str
    spool_id: int | None = None

    def public_identity(self) -> dict[str, int | str | None]:
        return {
            "version": self.envelope_version,
            "mode": self.mode,
            "issuer": self.issuer,
            "resolution": self.resolution,
            "spool_id": self.spool_id,
        }


@dataclass
class ResolvedManufacturerInstance:
    batch: QrManufacturerBatch
    item: QrManufacturerBatchItem
    ordinal: int
    state: QrManufacturerInstanceState | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _base36_pair(value: int) -> str:
    if not 0 <= value < 36 * 36:
        raise ValueError("value does not fit into two base36 digits")
    return _BASE36[value // 36] + _BASE36[value % 36]


def _decode_base36_pair(value: str) -> int:
    if len(value) != 2:
        raise ValueError("invalid product length")
    try:
        return _BASE36.index(value[0].upper()) * 36 + _BASE36.index(value[1].upper())
    except ValueError as exc:
        raise ValueError("invalid product length") from exc


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def encode_qr_envelope(product_code: str, namespace: str, token: str) -> str:
    """Encode an independently recoverable product code and opaque instance token."""
    if not _PRODUCT_CODE_RE.fullmatch(product_code):
        raise ValueError("invalid product QR code")
    if namespace not in {"U", "M"}:
        raise ValueError("invalid QR namespace")
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError("invalid instance token")

    encoded_product = _b64encode(product_code.encode("ascii"))
    short_code = (
        f"{QR_ENVELOPE_PREFIX}{_base36_pair(len(encoded_product))}_"
        f"{encoded_product}_{namespace}_{token}"
    )
    if len(short_code) > QR_MAX_SHORT_CODE_LENGTH:
        raise ValueError("QR envelope is too long")
    return short_code


def parse_qr_envelope(short_code: str) -> ParsedQrEnvelope | None:
    """Parse an FHQ1 envelope; legacy SKU-only codes return ``None``."""
    if not short_code.startswith(QR_ENVELOPE_PREFIX):
        return None
    if len(short_code) > QR_MAX_SHORT_CODE_LENGTH or len(short_code) < 30:
        raise ValueError("invalid QR envelope length")

    length_at = len(QR_ENVELOPE_PREFIX)
    if len(short_code) <= length_at + 3 or short_code[length_at + 2] != "_":
        raise ValueError("invalid QR envelope header")
    product_length = _decode_base36_pair(short_code[length_at : length_at + 2])
    product_at = length_at + 3
    product_end = product_at + product_length
    if product_end + 4 > len(short_code):
        raise ValueError("truncated QR envelope")

    encoded_product = short_code[product_at:product_end]
    suffix = short_code[product_end:]
    if len(suffix) < 4 or suffix[0] != "_" or suffix[2] != "_":
        raise ValueError("invalid QR envelope suffix")
    namespace = suffix[1]
    token = suffix[3:]
    if namespace not in {"U", "M"} or not _TOKEN_RE.fullmatch(token):
        raise ValueError("invalid QR instance reference")
    try:
        product_code = _b64decode(encoded_product).decode("ascii")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid encoded product QR code") from exc
    if not _PRODUCT_CODE_RE.fullmatch(product_code):
        raise ValueError("invalid product QR code")
    return ParsedQrEnvelope(
        product_code=product_code,
        namespace=namespace,
        token=token,
    )


def _new_user_token() -> str:
    return secrets.token_urlsafe(16)


def _user_token_digest(token: str) -> str:
    return blind_index(token, context="qr-user-token-v1")


def _operation_key_digest(value: str, *, context: str) -> str:
    return blind_index(value, context=context)


def _request_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _receipt_coordinates(
    *,
    scope: str,
    subject: str,
    idempotency_key: str,
) -> tuple[str, str]:
    normalized_key = idempotency_key.strip()
    if not 8 <= len(normalized_key) <= 128:
        raise_error(400, ERR_QR_IDEMPOTENCY_KEY_INVALID)
    return normalized_key, _operation_key_digest(
        normalized_key,
        context=f"qr-operation-receipt-v1:{scope}:{subject}",
    )


async def _read_operation_receipt(
    db: AsyncSession,
    *,
    scope: str,
    subject: str,
    key_digest: str,
    action: str,
    request_digest: str,
    response_model: type[ResponseModel],
) -> ResponseModel | None:
    receipt = await db.scalar(
        select(QrOperationReceipt).where(
            QrOperationReceipt.scope == scope,
            QrOperationReceipt.subject == subject,
            QrOperationReceipt.key_digest == key_digest,
        )
    )
    if receipt is None:
        return None
    if receipt.action != action or receipt.request_digest != request_digest:
        raise_error(409, ERR_QR_IDEMPOTENCY_CONFLICT)
    return response_model.model_validate_json(
        decrypt_field(receipt.response_snapshot_ciphertext)
    )


def _add_operation_receipt(
    db: AsyncSession,
    *,
    scope: str,
    subject: str,
    key_digest: str,
    action: str,
    request_digest: str,
    response: BaseModel,
) -> None:
    db.add(
        QrOperationReceipt(
            scope=scope,
            subject=subject,
            key_digest=key_digest,
            action=action,
            request_digest=request_digest,
            response_snapshot_ciphertext=encrypt_field(response.model_dump_json()),
        )
    )


def _binding_expired(binding: QrUserSpoolBinding, now: datetime) -> bool:
    return (
        binding.state == QrUserBindingState.PENDING_RETIREMENT
        and binding.purge_after is not None
        and _as_utc(binding.purge_after) <= now
    )


async def _owned_spool(
    db: AsyncSession,
    *,
    user_id: int,
    spool_id: int,
    for_update: bool = False,
) -> UserSpool:
    query = select(UserSpool).where(
        UserSpool.id == spool_id,
        UserSpool.user_id == user_id,
    )
    if for_update:
        query = query.with_for_update()
    spool = await db.scalar(query)
    if spool is None:
        raise_error(404, ERR_ACCESS_DENIED)
    return spool


async def _filament_with_qr(db: AsyncSession, filament_id: int) -> Filament:
    filament = await db.get(Filament, filament_id)
    if filament is None:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    await ensure_filament_qr_code(filament, db, render_images=False)
    await db.flush()
    if not filament.qr_code:
        raise_error(409, ERR_QR_NOT_FOUND)
    return filament


async def _user_binding_for_spool(
    db: AsyncSession,
    spool_id: int,
    *,
    for_update: bool = False,
) -> QrUserSpoolBinding | None:
    query = select(QrUserSpoolBinding).where(QrUserSpoolBinding.user_spool_id == spool_id)
    if for_update:
        query = query.with_for_update()
    return cast(QrUserSpoolBinding | None, await db.scalar(query))


def _user_binding_response(binding: QrUserSpoolBinding) -> UserSpoolQrResponse:
    token = decrypt_field(binding.token_ciphertext)
    product_code = binding.filament.qr_code if binding.filament is not None else None
    if product_code is None:
        raise_error(409, ERR_QR_NOT_FOUND)
    try:
        short_code = encode_qr_envelope(product_code, "U", token)
    except ValueError:
        raise_error(409, ERR_QR_PAYLOAD_TOO_LONG)
    return UserSpoolQrResponse(
        spool_id=binding.user_spool_id,
        filament_id=binding.filament_id,
        issuer="user",
        state=cast(Literal["active", "pending_retirement"], binding.state),
        revision=binding.revision,
        short_code=short_code,
        target_url=_qr_target_url(short_code),
        retirement_started_at=binding.retirement_started_at,
        purge_after=binding.purge_after,
    )


async def _manufacturer_binding_for_spool(
    db: AsyncSession,
    spool_id: int,
) -> QrManufacturerInstanceState | None:
    return cast(
        QrManufacturerInstanceState | None,
        await db.scalar(
            select(QrManufacturerInstanceState)
            .options(
                selectinload(QrManufacturerInstanceState.batch).selectinload(
                    QrManufacturerBatch.items
                )
            )
            .where(
                QrManufacturerInstanceState.user_spool_id == spool_id,
                QrManufacturerInstanceState.status == QrManufacturerInstanceStatus.CLAIMED,
            )
        ),
    )


def _item_for_ordinal(
    items: list[QrManufacturerBatchItem], ordinal: int
) -> QrManufacturerBatchItem | None:
    for item in items:
        if item.ordinal_start <= ordinal < item.ordinal_start + item.quantity:
            return item
    return None


def _manufacturer_token(
    batch: QrManufacturerBatch,
    *,
    ordinal: int,
    product_code: str,
) -> str:
    if not 0 <= ordinal <= 0xFFFFFFFF:
        raise ValueError("manufacturer ordinal is out of range")
    batch_ref = _b64decode(batch.token_ref)
    if len(batch_ref) != 10:
        raise ValueError("manufacturer batch reference is invalid")
    body = batch_ref + ordinal.to_bytes(4, "big")
    secret = decrypt_field(batch.secret_ciphertext).encode("utf-8")
    message = f"manufacturer-qr-v1\0{batch.public_id}\0{ordinal}\0{product_code}".encode("ascii")
    signature = hmac.new(secret, message, hashlib.sha256).digest()[:10]
    return _b64encode(body + signature)


def _manufacturer_token_reference(token: str) -> ManufacturerTokenReference:
    try:
        raw = _b64decode(token)
    except ValueError as exc:
        raise ValueError("invalid manufacturer token") from exc
    if len(raw) != 24:
        raise ValueError("invalid manufacturer token length")
    return ManufacturerTokenReference(
        batch_ref=_b64encode(raw[:10]),
        ordinal=int.from_bytes(raw[10:14], "big"),
    )


def _manufacturer_binding_response(
    state: QrManufacturerInstanceState,
) -> UserSpoolQrResponse:
    batch = state.batch
    item = _item_for_ordinal(batch.items, state.ordinal)
    if item is None or state.user_spool_id is None:
        raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)
    token = _manufacturer_token(
        batch,
        ordinal=state.ordinal,
        product_code=item.product_qr_code,
    )
    try:
        short_code = encode_qr_envelope(item.product_qr_code, "M", token)
    except ValueError:
        raise_error(409, ERR_QR_PAYLOAD_TOO_LONG)
    return UserSpoolQrResponse(
        spool_id=state.user_spool_id,
        filament_id=state.filament_id,
        issuer="manufacturer",
        state="linked",
        revision=batch.manifest_revision,
        short_code=short_code,
        target_url=_qr_target_url(short_code),
    )


async def issue_user_spool_qr(
    db: AsyncSession,
    *,
    user: User,
    spool_id: int,
    now: datetime | None = None,
) -> UserSpoolQrResponse:
    """Issue once and return the same identity for every ordinary reprint."""
    current_time = _as_utc(now or datetime.now(timezone.utc))
    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id, for_update=True)
    if spool.filament_id is None:
        raise_error(409, ERR_QR_SPOOL_FILAMENT_REQUIRED)

    manufacturer_state = await _manufacturer_binding_for_spool(db, spool.id)
    if (
        manufacturer_state is not None
        and manufacturer_state.batch.status == QrManufacturerBatchStatus.ACTIVE
    ):
        return _manufacturer_binding_response(manufacturer_state)

    binding = await _user_binding_for_spool(db, spool.id, for_update=True)
    if binding is not None and _binding_expired(binding, current_time):
        await db.delete(binding)
        await db.flush()
        binding = None

    if binding is not None:
        await db.refresh(binding, attribute_names=["filament"])
        return _user_binding_response(binding)
    if spool.state in {UserSpoolState.empty, UserSpoolState.archived}:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)

    filament = await _filament_with_qr(db, spool.filament_id)
    for _attempt in range(5):
        token = _new_user_token()
        digest = _user_token_digest(token)
        if not await db.scalar(
            select(QrUserSpoolBinding.id).where(QrUserSpoolBinding.token_digest == digest)
        ):
            break
    else:  # pragma: no cover - cryptographic collision backstop
        raise RuntimeError("could not allocate a unique QR token")

    binding = QrUserSpoolBinding(
        user_spool_id=spool.id,
        user_id=user.id,
        filament_id=filament.id,
        token_digest=digest,
        token_ciphertext=encrypt_field(token),
        state=QrUserBindingState.ACTIVE,
        revision=1,
    )
    binding.filament = filament
    db.add(binding)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed = await _user_binding_for_spool(db, spool.id)
        if replayed is None:
            raise
        await db.refresh(replayed, attribute_names=["filament"])
        return _user_binding_response(replayed)
    await db.refresh(binding)
    return _user_binding_response(binding)


async def get_user_spool_qr(
    db: AsyncSession,
    *,
    user: User,
    spool_id: int,
    now: datetime | None = None,
) -> UserSpoolQrResponse:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id)
    manufacturer_state = await _manufacturer_binding_for_spool(db, spool.id)
    if (
        manufacturer_state is not None
        and manufacturer_state.batch.status == QrManufacturerBatchStatus.ACTIVE
    ):
        return _manufacturer_binding_response(manufacturer_state)
    binding = await db.scalar(
        select(QrUserSpoolBinding)
        .options(selectinload(QrUserSpoolBinding.filament))
        .where(QrUserSpoolBinding.user_spool_id == spool.id)
    )
    if binding is None or _binding_expired(binding, current_time):
        raise_error(404, ERR_QR_NOT_FOUND)
    return _user_binding_response(binding)


async def list_user_spool_qr(
    db: AsyncSession,
    *,
    user: User,
    offset: int,
    limit: int,
    now: datetime | None = None,
) -> UserSpoolQrListResponse:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    user_rows = select(
        literal("user").label("issuer"),
        QrUserSpoolBinding.id.label("identity_id"),
        QrUserSpoolBinding.created_at.label("created_at"),
    ).where(
        QrUserSpoolBinding.user_id == user.id,
        or_(
            QrUserSpoolBinding.state != QrUserBindingState.PENDING_RETIREMENT,
            QrUserSpoolBinding.purge_after.is_(None),
            QrUserSpoolBinding.purge_after > current_time,
        ),
    )
    manufacturer_rows = (
        select(
            literal("manufacturer").label("issuer"),
            QrManufacturerInstanceState.id.label("identity_id"),
            QrManufacturerInstanceState.created_at.label("created_at"),
        )
        .join(
            QrManufacturerBatch,
            QrManufacturerBatch.id == QrManufacturerInstanceState.batch_id,
        )
        .where(
            QrManufacturerInstanceState.user_id == user.id,
            QrManufacturerInstanceState.user_spool_id.is_not(None),
            QrManufacturerInstanceState.status == QrManufacturerInstanceStatus.CLAIMED,
            QrManufacturerBatch.status == QrManufacturerBatchStatus.ACTIVE,
        )
    )
    identities = user_rows.union_all(manufacturer_rows).subquery()
    total = int(await db.scalar(select(func.count()).select_from(identities)) or 0)
    page_rows = (
        await db.execute(
            select(
                identities.c.issuer,
                identities.c.identity_id,
                identities.c.created_at,
            )
            .order_by(identities.c.created_at.desc(), identities.c.identity_id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    user_ids = [row.identity_id for row in page_rows if row.issuer == "user"]
    manufacturer_ids = [row.identity_id for row in page_rows if row.issuer == "manufacturer"]
    user_bindings = (
        list(
            (
                await db.scalars(
                    select(QrUserSpoolBinding)
                    .options(selectinload(QrUserSpoolBinding.filament))
                    .where(QrUserSpoolBinding.id.in_(user_ids))
                )
            ).all()
        )
        if user_ids
        else []
    )
    manufacturer_bindings = (
        list(
            (
                await db.scalars(
                    select(QrManufacturerInstanceState)
                    .options(
                        selectinload(QrManufacturerInstanceState.batch).selectinload(
                            QrManufacturerBatch.items
                        )
                    )
                    .where(QrManufacturerInstanceState.id.in_(manufacturer_ids))
                )
            ).all()
        )
        if manufacturer_ids
        else []
    )
    user_by_id = {binding.id: binding for binding in user_bindings}
    manufacturer_by_id = {state.id: state for state in manufacturer_bindings}
    responses: list[UserSpoolQrResponse] = []
    seen_spool_ids: set[int] = set()
    for row in page_rows:
        if row.issuer == "manufacturer":
            state = manufacturer_by_id.get(row.identity_id)
            if state is None:
                continue
            response = _manufacturer_binding_response(state)
        else:
            binding = user_by_id.get(row.identity_id)
            if binding is None or _binding_expired(binding, current_time):
                continue
            response = _user_binding_response(binding)
        if response.spool_id in seen_spool_ids:
            continue
        seen_spool_ids.add(response.spool_id)
        responses.append(response)
    return UserSpoolQrListResponse(
        items=responses,
        total=total,
        offset=offset,
        limit=limit,
    )


async def retire_user_spool_qr(
    db: AsyncSession,
    *,
    user: User,
    spool_id: int,
    revision: int,
    now: datetime | None = None,
) -> UserSpoolQrResponse:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id, for_update=True)
    if await _manufacturer_binding_for_spool(db, spool.id) is not None:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)
    binding = await _user_binding_for_spool(db, spool.id, for_update=True)
    if binding is None:
        raise_error(404, ERR_QR_NOT_FOUND)
    await db.refresh(binding, attribute_names=["filament"])
    if binding.state == QrUserBindingState.PENDING_RETIREMENT:
        if _binding_expired(binding, current_time):
            raise_error(409, ERR_QR_RECOVERY_EXPIRED)
        return _user_binding_response(binding)
    if binding.revision != revision:
        raise_error(409, ERR_QR_BINDING_REVISION_CONFLICT)
    binding.state = QrUserBindingState.PENDING_RETIREMENT
    binding.retirement_started_at = current_time
    binding.purge_after = current_time + timedelta(days=QR_USER_RECOVERY_DAYS)
    binding.revision += 1
    await db.flush()
    response = _user_binding_response(binding)
    await db.commit()
    return response


async def restore_user_spool_qr(
    db: AsyncSession,
    *,
    user: User,
    spool_id: int,
    revision: int,
    now: datetime | None = None,
) -> UserSpoolQrResponse:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id, for_update=True)
    binding = await _user_binding_for_spool(db, spool.id, for_update=True)
    if binding is None:
        raise_error(404, ERR_QR_NOT_FOUND)
    await db.refresh(binding, attribute_names=["filament"])
    if binding.state == QrUserBindingState.ACTIVE:
        return _user_binding_response(binding)
    if _binding_expired(binding, current_time):
        raise_error(409, ERR_QR_RECOVERY_EXPIRED)
    if binding.revision != revision:
        raise_error(409, ERR_QR_BINDING_REVISION_CONFLICT)
    binding.state = QrUserBindingState.ACTIVE
    binding.retirement_started_at = None
    binding.purge_after = None
    binding.revision += 1
    await db.flush()
    response = _user_binding_response(binding)
    await db.commit()
    return response


async def rotate_user_spool_qr(
    db: AsyncSession,
    *,
    user: User,
    spool_id: int,
    revision: int,
    idempotency_key: str,
    now: datetime | None = None,
) -> UserSpoolQrResponse:
    current_time = _as_utc(now or datetime.now(timezone.utc))
    scope = f"user:{user.id}"
    subject = f"spool:{spool_id}"
    normalized_key, key_digest = _receipt_coordinates(
        scope=scope,
        subject=subject,
        idempotency_key=idempotency_key,
    )
    request_digest = _request_digest({"revision": revision})
    replay = await _read_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=key_digest,
        action="rotate_user_spool_qr",
        request_digest=request_digest,
        response_model=UserSpoolQrResponse,
    )
    if replay is not None:
        return replay

    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id, for_update=True)
    replay = await _read_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=key_digest,
        action="rotate_user_spool_qr",
        request_digest=request_digest,
        response_model=UserSpoolQrResponse,
    )
    if replay is not None:
        return replay
    binding = await _user_binding_for_spool(db, spool.id, for_update=True)
    if binding is None:
        raise_error(404, ERR_QR_NOT_FOUND)
    await db.refresh(binding, attribute_names=["filament"])
    legacy_operation_digest = _operation_key_digest(
        normalized_key, context=f"qr-user-rotate-v1:{user.id}:{spool.id}"
    )
    if binding.last_rotation_key_digest == legacy_operation_digest:
        response = _user_binding_response(binding)
        _add_operation_receipt(
            db,
            scope=scope,
            subject=subject,
            key_digest=key_digest,
            action="rotate_user_spool_qr",
            request_digest=request_digest,
            response=response,
        )
        await db.commit()
        return response
    if binding.state != QrUserBindingState.ACTIVE or _binding_expired(binding, current_time):
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)
    if binding.revision != revision:
        raise_error(409, ERR_QR_BINDING_REVISION_CONFLICT)

    token = _new_user_token()
    binding.token_digest = _user_token_digest(token)
    binding.token_ciphertext = encrypt_field(token)
    binding.last_rotation_key_digest = legacy_operation_digest
    binding.revision += 1
    await db.flush()
    response = _user_binding_response(binding)
    _add_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=key_digest,
        action="rotate_user_spool_qr",
        request_digest=request_digest,
        response=response,
    )
    await db.commit()
    return response


async def replace_user_spool_qr_material(
    db: AsyncSession,
    *,
    user: User,
    spool_id: int,
    filament_id: int,
    revision: int,
    idempotency_key: str,
    confirm_reprint: bool,
) -> UserSpoolQrResponse:
    """Atomically change material and replace the linked user-issued token."""
    if not confirm_reprint:
        raise_error(409, ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE)
    scope = f"user:{user.id}"
    subject = f"spool:{spool_id}"
    _normalized_key, key_digest = _receipt_coordinates(
        scope=scope,
        subject=subject,
        idempotency_key=idempotency_key,
    )
    request_digest = _request_digest(
        {
            "confirm_reprint": True,
            "filament_id": filament_id,
            "revision": revision,
        }
    )
    replay = await _read_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=key_digest,
        action="replace_user_spool_qr_material",
        request_digest=request_digest,
        response_model=UserSpoolQrResponse,
    )
    if replay is not None:
        return replay

    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id, for_update=True)
    replay = await _read_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=key_digest,
        action="replace_user_spool_qr_material",
        request_digest=request_digest,
        response_model=UserSpoolQrResponse,
    )
    if replay is not None:
        return replay
    if await _manufacturer_binding_for_spool(db, spool.id) is not None:
        raise_error(409, ERR_MANUFACTURER_QR_MATERIAL_LOCKED)

    binding = await _user_binding_for_spool(db, spool.id, for_update=True)
    if binding is None:
        raise_error(404, ERR_QR_NOT_FOUND)
    if binding.state != QrUserBindingState.ACTIVE:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)
    if binding.revision != revision:
        raise_error(409, ERR_QR_BINDING_REVISION_CONFLICT)
    if spool.filament_id == filament_id:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)

    filament = await _filament_with_qr(db, filament_id)
    token = _new_user_token()
    spool.filament_id = filament.id
    binding.filament_id = filament.id
    binding.filament = filament
    binding.token_digest = _user_token_digest(token)
    binding.token_ciphertext = encrypt_field(token)
    binding.last_rotation_key_digest = None
    binding.revision += 1
    await db.flush()
    response = _user_binding_response(binding)
    _add_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=key_digest,
        action="replace_user_spool_qr_material",
        request_digest=request_digest,
        response=response,
    )
    await db.commit()
    return response


async def purge_expired_user_qr_bindings(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = QR_BINDING_CLEANUP_BATCH_SIZE,
) -> int:
    """Delete one bounded batch; the printed envelope still resolves its SKU."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    current_time = _as_utc(now or datetime.now(timezone.utc))
    expired_ids = (
        select(QrUserSpoolBinding.id)
        .where(
            QrUserSpoolBinding.state == QrUserBindingState.PENDING_RETIREMENT,
            QrUserSpoolBinding.purge_after.is_not(None),
            QrUserSpoolBinding.purge_after <= current_time,
        )
        .order_by(QrUserSpoolBinding.purge_after, QrUserSpoolBinding.id)
        .limit(batch_size)
    )
    result = await db.execute(
        delete(QrUserSpoolBinding).where(QrUserSpoolBinding.id.in_(expired_ids))
    )
    return max(int(getattr(result, "rowcount", 0) or 0), 0)


async def run_qr_binding_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: float = QR_BINDING_SWEEP_INTERVAL_SECONDS,
) -> None:
    """Periodically purge bounded expired user bindings without blocking startup."""
    while True:
        try:
            async with session_factory() as db:
                removed = await purge_expired_user_qr_bindings(db)
                await db.commit()
            if removed:
                logger.info("Removed %d expired user QR bindings", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to sweep expired user QR bindings", exc_info=True)
        await asyncio.sleep(interval_seconds)


async def _resolve_manufacturer_instance(
    db: AsyncSession,
    *,
    filament: Filament,
    token: str,
) -> ResolvedManufacturerInstance | None:
    try:
        reference = _manufacturer_token_reference(token)
    except ValueError:
        return None
    query = (
        select(QrManufacturerBatch)
        .options(selectinload(QrManufacturerBatch.items))
        .where(
            QrManufacturerBatch.token_ref == reference.batch_ref,
            QrManufacturerBatch.status == QrManufacturerBatchStatus.ACTIVE,
        )
    )
    batch = await db.scalar(query)
    if batch is None:
        return None
    item = _item_for_ordinal(batch.items, reference.ordinal)
    if item is None or item.filament_id != filament.id or item.product_qr_code != filament.qr_code:
        return None
    expected = _manufacturer_token(
        batch,
        ordinal=reference.ordinal,
        product_code=item.product_qr_code,
    )
    if not hmac.compare_digest(expected, token):
        return None
    state_query = select(QrManufacturerInstanceState).where(
        QrManufacturerInstanceState.batch_id == batch.id,
        QrManufacturerInstanceState.ordinal == reference.ordinal,
    )
    state = await db.scalar(state_query)
    return ResolvedManufacturerInstance(
        batch=batch,
        item=item,
        ordinal=reference.ordinal,
        state=state,
    )


async def resolve_qr_identity(
    db: AsyncSession,
    short_code: str,
    *,
    current_user: User | None = None,
) -> QrResolution:
    """Resolve legacy or FHQ1 codes without letting instance failure break SKU."""
    direct = await db.scalar(
        select(Filament).options(selectinload(Filament.brand)).where(Filament.qr_code == short_code)
    )
    if direct is not None:
        return QrResolution(
            filament=direct,
            envelope_version=0,
            mode="sku",
            issuer=None,
            resolution="product",
        )
    try:
        envelope = parse_qr_envelope(short_code)
    except ValueError:
        envelope = None
    if envelope is None:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    filament = await db.scalar(
        select(Filament)
        .options(selectinload(Filament.brand))
        .where(Filament.qr_code == envelope.product_code)
    )
    if filament is None:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    resolution = QrResolution(
        filament=filament,
        envelope_version=QR_ENVELOPE_VERSION,
        mode="instance",
        issuer="user" if envelope.namespace == "U" else "manufacturer",
        resolution="product_only",
    )
    if envelope.namespace == "U":
        binding = await db.scalar(
            select(QrUserSpoolBinding).where(
                QrUserSpoolBinding.token_digest == _user_token_digest(envelope.token),
                QrUserSpoolBinding.filament_id == filament.id,
            )
        )
        if (
            binding is not None
            and current_user is not None
            and binding.user_id == current_user.id
            and not _binding_expired(binding, datetime.now(timezone.utc))
        ):
            resolution.resolution = (
                "pending_retirement"
                if binding.state == QrUserBindingState.PENDING_RETIREMENT
                else "linked"
            )
            resolution.spool_id = binding.user_spool_id
        return resolution

    manufacturer = await _resolve_manufacturer_instance(db, filament=filament, token=envelope.token)
    if manufacturer is None:
        return resolution
    state = manufacturer.state
    if state is None:
        resolution.resolution = "unbound"
    elif (
        state.status == QrManufacturerInstanceStatus.CLAIMED
        and current_user is not None
        and state.user_id == current_user.id
        and state.user_spool_id is not None
    ):
        resolution.resolution = "linked"
        resolution.spool_id = state.user_spool_id
    return resolution


def _batch_request_digest(payload: ManufacturerQrBatchCreateRequest) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _batch_response(batch: QrManufacturerBatch) -> ManufacturerQrBatchResponse:
    return ManufacturerQrBatchResponse(
        public_id=batch.public_id,
        organization_id=batch.organization_id,
        brand_id=batch.brand_id,
        mode=cast(Literal["sku", "serialized"], batch.mode),
        status=cast(Literal["active", "cancelled"], batch.status),
        total_quantity=batch.total_quantity,
        manifest_revision=batch.manifest_revision,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        items=[
            ManufacturerQrBatchItemResponse(
                filament_id=item.filament_id,
                quantity=item.quantity,
                ordinal_start=item.ordinal_start,
                product_qr_code=item.product_qr_code,
            )
            for item in batch.items
        ],
    )


async def _authorized_organization_id(
    db: AsyncSession,
    *,
    user: User,
    brand_id: int,
) -> int:
    organization_id = user.active_organization_id
    if organization_id is None:
        raise_error(403, ERR_ACCESS_DENIED)
    grants = await active_grants_for(db, user, brand_id)
    if not any(grant.organization_id == organization_id for grant in grants):
        raise_error(403, ERR_ACCESS_DENIED)
    return organization_id


async def create_manufacturer_qr_batch(
    db: AsyncSession,
    *,
    user: User,
    payload: ManufacturerQrBatchCreateRequest,
    idempotency_key: str,
) -> ManufacturerQrBatchResponse:
    """Create a compact manifest; no per-label rows are materialized."""
    normalized_key = idempotency_key.strip()
    if not 8 <= len(normalized_key) <= 128:
        raise_error(400, ERR_QR_IDEMPOTENCY_KEY_INVALID)
    organization_id = await _authorized_organization_id(db, user=user, brand_id=payload.brand_id)
    key_digest = _operation_key_digest(
        normalized_key,
        context=f"qr-manufacturer-batch-v1:{organization_id}",
    )
    request_digest = _batch_request_digest(payload)
    existing = await db.scalar(
        select(QrManufacturerBatch)
        .options(selectinload(QrManufacturerBatch.items))
        .where(
            QrManufacturerBatch.organization_id == organization_id,
            QrManufacturerBatch.idempotency_key_digest == key_digest,
        )
    )
    if existing is not None:
        if existing.request_digest != request_digest:
            raise_error(409, ERR_QR_IDEMPOTENCY_CONFLICT)
        return _batch_response(existing)

    total_quantity = sum(item.quantity for item in payload.items)
    if total_quantity > QR_MANUFACTURER_MAX_BATCH_QUANTITY:
        raise_error(
            413,
            ERR_QR_BATCH_LIMIT_EXCEEDED,
            {"max": QR_MANUFACTURER_MAX_BATCH_QUANTITY},
        )
    filament_ids = [item.filament_id for item in payload.items]
    filaments = list(
        (
            await db.scalars(
                select(Filament).where(
                    Filament.id.in_(filament_ids),
                    Filament.brand_id == payload.brand_id,
                    Filament.active.is_(True),
                )
            )
        ).all()
    )
    by_id = {filament.id: filament for filament in filaments}
    if set(by_id) != set(filament_ids):
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    for filament in filaments:
        await ensure_filament_qr_code(filament, db, render_images=False)
    await db.flush()

    batch = QrManufacturerBatch(
        public_id=str(uuid4()),
        token_ref=secrets.token_urlsafe(10),
        organization_id=organization_id,
        brand_id=payload.brand_id,
        created_by_id=user.id,
        mode=payload.mode,
        status=QrManufacturerBatchStatus.ACTIVE,
        total_quantity=total_quantity,
        manifest_revision=1,
        secret_ciphertext=encrypt_field(secrets.token_urlsafe(32)),
        idempotency_key_digest=key_digest,
        request_digest=request_digest,
    )
    db.add(batch)
    await db.flush()
    ordinal = 0
    for requested in payload.items:
        filament = by_id[requested.filament_id]
        db.add(
            QrManufacturerBatchItem(
                batch_id=batch.id,
                filament_id=filament.id,
                quantity=requested.quantity,
                ordinal_start=ordinal,
                product_qr_code=filament.qr_code,
            )
        )
        ordinal += requested.quantity
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed = await db.scalar(
            select(QrManufacturerBatch)
            .options(selectinload(QrManufacturerBatch.items))
            .where(
                QrManufacturerBatch.organization_id == organization_id,
                QrManufacturerBatch.idempotency_key_digest == key_digest,
            )
        )
        if replayed is None or replayed.request_digest != request_digest:
            raise_error(409, ERR_QR_IDEMPOTENCY_CONFLICT)
        return _batch_response(replayed)
    reloaded_batch = await db.scalar(
        select(QrManufacturerBatch)
        .options(selectinload(QrManufacturerBatch.items))
        .where(QrManufacturerBatch.id == batch.id)
    )
    assert reloaded_batch is not None
    return _batch_response(reloaded_batch)


async def _authorized_batch(
    db: AsyncSession,
    *,
    user: User,
    public_id: str,
    for_update: bool = False,
) -> QrManufacturerBatch:
    organization_id = user.active_organization_id
    if organization_id is None:
        raise_error(404, ERR_QR_BATCH_NOT_FOUND)
    query = (
        select(QrManufacturerBatch)
        .options(selectinload(QrManufacturerBatch.items))
        .where(
            QrManufacturerBatch.public_id == public_id,
            QrManufacturerBatch.organization_id == organization_id,
        )
    )
    if for_update:
        query = query.with_for_update()
    batch = await db.scalar(query)
    if batch is None:
        raise_error(404, ERR_QR_BATCH_NOT_FOUND)
    grants = await active_grants_for(db, user, batch.brand_id)
    if not any(grant.organization_id == organization_id for grant in grants):
        raise_error(404, ERR_QR_BATCH_NOT_FOUND)
    return batch


async def get_manufacturer_qr_batch(
    db: AsyncSession,
    *,
    user: User,
    public_id: str,
) -> ManufacturerQrBatchResponse:
    return _batch_response(await _authorized_batch(db, user=user, public_id=public_id))


async def list_manufacturer_qr_batches(
    db: AsyncSession,
    *,
    user: User,
    offset: int,
    limit: int,
) -> ManufacturerQrBatchListResponse:
    organization_id = user.active_organization_id
    if organization_id is None:
        return ManufacturerQrBatchListResponse(items=[], total=0, offset=offset, limit=limit)
    authorized_brand_ids = active_grant_brand_ids_for(user)
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(QrManufacturerBatch)
            .where(
                QrManufacturerBatch.organization_id == organization_id,
                QrManufacturerBatch.brand_id.in_(authorized_brand_ids),
            )
        )
        or 0
    )
    if total == 0:
        return ManufacturerQrBatchListResponse(items=[], total=0, offset=offset, limit=limit)
    batches = list(
        (
            await db.scalars(
                select(QrManufacturerBatch)
                .options(selectinload(QrManufacturerBatch.items))
                .where(
                    QrManufacturerBatch.organization_id == organization_id,
                    QrManufacturerBatch.brand_id.in_(authorized_brand_ids),
                )
                .order_by(QrManufacturerBatch.created_at.desc(), QrManufacturerBatch.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return ManufacturerQrBatchListResponse(
        items=[_batch_response(batch) for batch in batches],
        total=total,
        offset=offset,
        limit=limit,
    )


async def manufacturer_qr_payload_page(
    db: AsyncSession,
    *,
    user: User,
    public_id: str,
    offset: int,
    limit: int,
) -> ManufacturerQrPayloadPage:
    if limit > QR_MANUFACTURER_MAX_PAYLOAD_PAGE:
        raise_error(
            413,
            ERR_QR_BATCH_LIMIT_EXCEEDED,
            {"max": QR_MANUFACTURER_MAX_PAYLOAD_PAGE},
        )
    batch = await _authorized_batch(db, user=user, public_id=public_id)
    end = min(batch.total_quantity, offset + limit)
    payloads: list[ManufacturerQrPayloadResponse] = []
    for ordinal in range(offset, end):
        item = _item_for_ordinal(batch.items, ordinal)
        if item is None:  # pragma: no cover - protected by manifest constraints
            raise RuntimeError("manufacturer batch ordinal is not covered")
        if batch.mode == QrManufacturerBatchMode.SERIALIZED:
            token = _manufacturer_token(
                batch,
                ordinal=ordinal,
                product_code=item.product_qr_code,
            )
            try:
                short_code = encode_qr_envelope(item.product_qr_code, "M", token)
            except ValueError:
                raise_error(409, ERR_QR_PAYLOAD_TOO_LONG)
        else:
            short_code = item.product_qr_code
        payloads.append(
            ManufacturerQrPayloadResponse(
                ordinal=ordinal,
                filament_id=item.filament_id,
                short_code=short_code,
                target_url=_qr_target_url(short_code),
            )
        )
    return ManufacturerQrPayloadPage(
        batch_id=batch.public_id,
        manifest_revision=batch.manifest_revision,
        offset=offset,
        limit=limit,
        total=batch.total_quantity,
        items=payloads,
        next_offset=end if end < batch.total_quantity else None,
    )


async def set_manufacturer_qr_exception(
    db: AsyncSession,
    *,
    user: User,
    public_id: str,
    ordinal: int,
    action: str,
    idempotency_key: str,
) -> ManufacturerQrExceptionResponse:
    batch = await _authorized_batch(db, user=user, public_id=public_id, for_update=True)
    if batch.mode != QrManufacturerBatchMode.SERIALIZED:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)
    item = _item_for_ordinal(batch.items, ordinal)
    if item is None:
        raise_error(404, ERR_QR_INSTANCE_UNAVAILABLE)
    scope = f"organization:{batch.organization_id}"
    subject = f"batch:{batch.public_id}:ordinal:{ordinal}"
    _normalized_key, operation_digest = _receipt_coordinates(
        scope=scope,
        subject=subject,
        idempotency_key=idempotency_key,
    )
    request_digest = _request_digest({"action": action, "ordinal": ordinal})
    replay = await _read_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=operation_digest,
        action="set_manufacturer_qr_exception",
        request_digest=request_digest,
        response_model=ManufacturerQrExceptionResponse,
    )
    if replay is not None:
        return replay
    state = await db.scalar(
        select(QrManufacturerInstanceState)
        .where(
            QrManufacturerInstanceState.batch_id == batch.id,
            QrManufacturerInstanceState.ordinal == ordinal,
        )
        .with_for_update()
    )
    next_status = {
        "revoke": QrManufacturerInstanceStatus.REVOKED,
        "scrap": QrManufacturerInstanceStatus.SCRAPPED,
        "restore": None,
    }[action]
    if state is not None and state.status == QrManufacturerInstanceStatus.CLAIMED:
        raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)

    if action == "restore":
        if state is not None:
            await db.delete(state)
            batch.manifest_revision += 1
        response = ManufacturerQrExceptionResponse(
            ordinal=ordinal,
            status=None,
            manifest_revision=batch.manifest_revision,
        )
        _add_operation_receipt(
            db,
            scope=scope,
            subject=subject,
            key_digest=operation_digest,
            action="set_manufacturer_qr_exception",
            request_digest=request_digest,
            response=response,
        )
        await db.commit()
        return response

    assert next_status is not None
    if state is None:
        state = QrManufacturerInstanceState(
            batch_id=batch.id,
            ordinal=ordinal,
            filament_id=item.filament_id,
            status=next_status,
        )
        db.add(state)
    else:
        state.status = next_status
    batch.manifest_revision += 1
    response = ManufacturerQrExceptionResponse(
        ordinal=ordinal,
        status=cast(Literal["revoked", "scrapped"], next_status),
        manifest_revision=batch.manifest_revision,
    )
    _add_operation_receipt(
        db,
        scope=scope,
        subject=subject,
        key_digest=operation_digest,
        action="set_manufacturer_qr_exception",
        request_digest=request_digest,
        response=response,
    )
    await db.commit()
    return response


async def claim_manufacturer_qr(
    db: AsyncSession,
    *,
    user: User,
    short_code: str,
    spool_id: int,
) -> ManufacturerQrClaimResponse:
    try:
        envelope = parse_qr_envelope(short_code)
    except ValueError:
        envelope = None
    if envelope is None or envelope.namespace != "M":
        raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)
    filament = await db.scalar(select(Filament).where(Filament.qr_code == envelope.product_code))
    if filament is None:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    resolved = await _resolve_manufacturer_instance(
        db,
        filament=filament,
        token=envelope.token,
    )
    if resolved is None:
        raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)
    spool = await _owned_spool(db, user_id=user.id, spool_id=spool_id, for_update=True)
    if spool.filament_id != filament.id:
        raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)
    if spool.state in {UserSpoolState.empty, UserSpoolState.archived}:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)
    batch_id = resolved.batch.id
    ordinal = resolved.ordinal
    state = await db.scalar(
        select(QrManufacturerInstanceState)
        .where(
            QrManufacturerInstanceState.batch_id == batch_id,
            QrManufacturerInstanceState.ordinal == ordinal,
        )
        .with_for_update()
    )
    if state is not None:
        if (
            state.status == QrManufacturerInstanceStatus.CLAIMED
            and state.user_id == user.id
            and state.user_spool_id == spool.id
        ):
            return ManufacturerQrClaimResponse(
                filament_id=filament.id,
                spool_id=spool.id,
            )
        raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)
    if await _user_binding_for_spool(db, spool.id) is not None:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)

    state = QrManufacturerInstanceState(
        batch_id=batch_id,
        ordinal=ordinal,
        filament_id=filament.id,
        status=QrManufacturerInstanceStatus.CLAIMED,
        user_id=user.id,
        user_spool_id=spool.id,
    )
    claimed_user_id = user.id
    claimed_filament_id = filament.id
    claimed_spool_id = spool.id
    db.add(state)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed = await db.scalar(
            select(QrManufacturerInstanceState).where(
                QrManufacturerInstanceState.batch_id == batch_id,
                QrManufacturerInstanceState.ordinal == ordinal,
            )
        )
        if (
            replayed is None
            or replayed.status != QrManufacturerInstanceStatus.CLAIMED
            or replayed.user_id != claimed_user_id
            or replayed.user_spool_id != claimed_spool_id
        ):
            raise_error(409, ERR_QR_INSTANCE_UNAVAILABLE)
    return ManufacturerQrClaimResponse(
        filament_id=claimed_filament_id,
        spool_id=claimed_spool_id,
    )
