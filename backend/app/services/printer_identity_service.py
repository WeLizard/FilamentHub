"""Privacy-preserving device evidence shared by all local execution surfaces."""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import decrypt_field, encrypt_field
from app.models.printer_identity import PrinterIdentity
from app.models.user import User
from app.schemas.printer_connection_observation import PrinterIdentityEvidence

DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "mqtt": 1883,
    "mqtts": 8883,
}


async def discovery_key(db: AsyncSession, user_id: int) -> str:
    """Stable across encryption-key rotation, app reinstall and local transports."""
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user.printer_discovery_key:
        user.printer_discovery_key = encrypt_field(secrets.token_hex(32))
        await db.flush()
    return decrypt_field(user.printer_discovery_key)


def normalize_endpoint(print_host: str | None, host_type: str | None) -> dict:
    provider = (host_type or "generic").strip().lower()
    raw = (print_host or "").strip()
    if raw and "://" not in raw:
        raw = "http://" + raw
    try:
        parts = urlsplit(raw)
        scheme = (parts.scheme or "http").lower()
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return {
            "provider": provider,
            "scheme": "",
            "host": "",
            "port": None,
            "path": "",
            "normalized": "",
        }
    path = (parts.path or "").rstrip("/")
    if port is None:
        port = DEFAULT_PORTS.get(scheme)
    normalized = "|".join([provider, scheme, host, str(port or ""), path]) if host else ""
    return {
        "provider": provider,
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": path,
        "normalized": normalized,
    }


def endpoint_token(key: str, host: str | None, provider: str | None) -> str | None:
    canonical = normalize_endpoint(host, provider)["normalized"]
    if not canonical:
        return None
    return hmac.new(
        bytes.fromhex(key),
        ("endpoint\0" + canonical).encode(),
        hashlib.sha256,
    ).hexdigest()


async def identity_printer(
    db: AsyncSession,
    user_id: int,
    evidence: PrinterIdentityEvidence,
) -> int | None:
    return await db.scalar(
        select(PrinterIdentity.physical_printer_id).where(
            PrinterIdentity.user_id == user_id,
            PrinterIdentity.kind == evidence.kind,
            PrinterIdentity.token == evidence.token,
        )
    )


async def remember_identity(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    evidence: PrinterIdentityEvidence,
    *,
    allow_replacement: bool = False,
) -> bool:
    """Caller holds the account lock. Never move an existing identity implicitly."""
    identity = await db.scalar(
        select(PrinterIdentity).where(
            PrinterIdentity.user_id == user_id,
            PrinterIdentity.kind == evidence.kind,
            PrinterIdentity.token == evidence.token,
        )
    )
    if identity is not None:
        if identity.physical_printer_id != physical_printer_id:
            return False
        identity.last_seen_at = datetime.now(timezone.utc)
    else:
        if not allow_replacement and await db.scalar(
            select(PrinterIdentity.id)
            .where(
                PrinterIdentity.user_id == user_id,
                PrinterIdentity.physical_printer_id == physical_printer_id,
                PrinterIdentity.kind == evidence.kind,
                PrinterIdentity.token != evidence.token,
            )
            .limit(1)
        ):
            return False
        db.add(
            PrinterIdentity(
                user_id=user_id,
                physical_printer_id=physical_printer_id,
                kind=evidence.kind,
                token=evidence.token,
            )
        )
        await db.flush()
    return True
