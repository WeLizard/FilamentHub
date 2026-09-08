"""Lifecycle for private, short-lived Calculator G-code artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models.calculator_gcode_artifact import CalculatorGcodeArtifact
from app.models.user import User
from app.services.calculator_gcode_parser import GcodeParseCancelled, parse_gcode_payload
from app.services.file_service import get_upload_root_dir

logger = logging.getLogger(__name__)

ARTIFACT_TTL = timedelta(minutes=30)
UPLOAD_STALE_AFTER = timedelta(minutes=5)
ARTIFACT_SWEEP_INTERVAL_SECONDS = 300.0
ARTIFACT_SWEEP_BATCH_SIZE = 100
ORPHAN_FILE_GRACE = ARTIFACT_TTL
MAX_ARTIFACTS_PER_USER = 20
MAX_ARTIFACT_BYTES_PER_USER = 500 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_PLATES_PER_ARTIFACT = 256


class ArtifactNotFoundError(Exception):
    pass


class ArtifactConflictError(Exception):
    pass


class ArtifactQuotaError(Exception):
    pass


class ArtifactUploadError(Exception):
    pass


class ArtifactCancelledError(Exception):
    pass


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def artifact_storage_root() -> Path:
    """Private subtree of the persistent uploads volume."""
    return get_upload_root_dir() / "calculator_gcode_artifacts"


def _artifact_path(storage_key: str) -> Path:
    root = artifact_storage_root().resolve()
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root):
        raise ArtifactNotFoundError
    return path


def _cancel_path(artifact_id: str) -> Path:
    return _artifact_path(f"{artifact_id}.cancelled")


def normalize_artifact_file_name(file_name: str) -> str:
    """Keep the display name while refusing paths and control characters."""
    normalized = file_name.replace("\\", "/").split("/")[-1].strip()
    if not normalized or len(normalized) > 255 or any(ord(char) < 32 for char in normalized):
        raise ArtifactUploadError
    return normalized


def _old_artifact_files(root: Path, *, before: datetime, limit: int) -> list[Path]:
    candidates: list[Path] = []
    for path in root.iterdir():
        try:
            is_old_file = (
                path.is_file()
                and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) <= before
            )
        except FileNotFoundError:
            continue
        if is_old_file:
            candidates.append(path)
            if len(candidates) >= limit:
                break
    return candidates


async def reserve_artifact(
    db: AsyncSession,
    *,
    artifact_id: str,
    owner_user_id: int,
    file_name: str,
    expected_size_bytes: int,
    now: datetime | None = None,
) -> tuple[CalculatorGcodeArtifact, bool]:
    """Reserve quota for an upload and make retries idempotent by operation ID."""
    current_time = now or datetime.now(timezone.utc)
    safe_name = normalize_artifact_file_name(file_name)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if expected_size_bytes <= 0 or expected_size_bytes > max_bytes:
        raise ArtifactUploadError

    existing = await db.get(CalculatorGcodeArtifact, artifact_id)
    if existing is not None:
        if existing.owner_user_id != owner_user_id:
            raise ArtifactNotFoundError
        if (
            existing.original_name != safe_name
            or existing.expected_size_bytes != expected_size_bytes
        ):
            raise ArtifactConflictError
        if _utc(existing.expires_at) <= current_time:
            raise ArtifactNotFoundError
        if existing.state == "ready":
            return existing, False
        if existing.state == "uploading" and _utc(existing.updated_at) > current_time - UPLOAD_STALE_AFTER:
            raise ArtifactConflictError
        existing.state = "uploading"
        existing.size_bytes = None
        existing.sha256 = None
        existing.storage_key = None
        existing.generation += 1
        existing.expires_at = current_time + ARTIFACT_TTL
        await db.flush()
        return existing, True

    # Serializing reservations on the user row makes the per-owner byte budget
    # exact on PostgreSQL without holding a lock during network or file I/O.
    await db.execute(select(User.id).where(User.id == owner_user_id).with_for_update())
    usage = (
        await db.execute(
            select(
                func.count(CalculatorGcodeArtifact.id),
                func.coalesce(func.sum(CalculatorGcodeArtifact.expected_size_bytes), 0),
            ).where(
                CalculatorGcodeArtifact.owner_user_id == owner_user_id,
                CalculatorGcodeArtifact.state.in_(("uploading", "ready")),
                CalculatorGcodeArtifact.expires_at > current_time,
            )
        )
    ).one()
    if usage[0] >= MAX_ARTIFACTS_PER_USER or usage[1] + expected_size_bytes > MAX_ARTIFACT_BYTES_PER_USER:
        raise ArtifactQuotaError

    artifact = CalculatorGcodeArtifact(
        id=artifact_id,
        owner_user_id=owner_user_id,
        original_name=safe_name,
        expected_size_bytes=expected_size_bytes,
        state="uploading",
        expires_at=current_time + ARTIFACT_TTL,
        generation=1,
    )
    db.add(artifact)
    await db.flush()
    return artifact, True


async def write_artifact_stream(
    db: AsyncSession,
    *,
    artifact: CalculatorGcodeArtifact,
    chunks: AsyncIterator[bytes],
) -> CalculatorGcodeArtifact:
    """Stream one raw request body to disk and publish it atomically."""
    root = artifact_storage_root()
    await run_in_threadpool(root.mkdir, parents=True, exist_ok=True)
    storage_key = f"{artifact.id}.bin"
    destination = _artifact_path(storage_key)
    temporary = _artifact_path(f"{artifact.id}.{artifact.generation}.part")
    cancelled = _cancel_path(artifact.id)
    upload_generation = artifact.generation
    await run_in_threadpool(cancelled.unlink, missing_ok=True)

    digest = hashlib.sha256()
    bytes_written = 0
    handle = await run_in_threadpool(temporary.open, "wb")

    async def fail_upload() -> None:
        await run_in_threadpool(handle.close)
        await run_in_threadpool(temporary.unlink, missing_ok=True)
        await db.execute(
            update(CalculatorGcodeArtifact)
            .where(
                CalculatorGcodeArtifact.id == artifact.id,
                CalculatorGcodeArtifact.generation == upload_generation,
                CalculatorGcodeArtifact.state == "uploading",
            )
            .values(state="failed", size_bytes=bytes_written)
        )
        await db.commit()

    try:
        async for chunk in chunks:
            if cancelled.exists():
                raise ArtifactCancelledError
            if not chunk:
                continue
            bytes_written += len(chunk)
            if (
                bytes_written > artifact.expected_size_bytes
                or bytes_written > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            ):
                raise ArtifactUploadError
            digest.update(chunk)
            await run_in_threadpool(handle.write, chunk)
        await run_in_threadpool(handle.flush)
        await run_in_threadpool(os.fsync, handle.fileno())
    except asyncio.CancelledError:
        await fail_upload()
        raise
    except ArtifactCancelledError:
        await run_in_threadpool(handle.close)
        await run_in_threadpool(temporary.unlink, missing_ok=True)
        await db.rollback()
        raise
    except Exception:
        await fail_upload()
        raise
    else:
        await run_in_threadpool(handle.close)

    if bytes_written != artifact.expected_size_bytes:
        await fail_upload()
        raise ArtifactUploadError

    if cancelled.exists():
        await run_in_threadpool(temporary.unlink, missing_ok=True)
        await db.rollback()
        raise ArtifactCancelledError

    try:
        await run_in_threadpool(os.replace, temporary, destination)
    except Exception:
        await run_in_threadpool(temporary.unlink, missing_ok=True)
        await db.execute(
            update(CalculatorGcodeArtifact)
            .where(
                CalculatorGcodeArtifact.id == artifact.id,
                CalculatorGcodeArtifact.generation == upload_generation,
                CalculatorGcodeArtifact.state == "uploading",
            )
            .values(state="failed", size_bytes=bytes_written)
        )
        await db.commit()
        raise

    published = await db.execute(
        update(CalculatorGcodeArtifact)
        .where(
            CalculatorGcodeArtifact.id == artifact.id,
            CalculatorGcodeArtifact.generation == upload_generation,
            CalculatorGcodeArtifact.state == "uploading",
        )
        .values(
            storage_key=storage_key,
            size_bytes=bytes_written,
            sha256=digest.hexdigest(),
            state="ready",
        )
    )
    if published.rowcount != 1:
        await db.rollback()
        await run_in_threadpool(destination.unlink, missing_ok=True)
        raise ArtifactCancelledError
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def get_owned_artifact(
    db: AsyncSession,
    *,
    artifact_id: str,
    owner_user_id: int,
    ready_required: bool = False,
) -> CalculatorGcodeArtifact:
    artifact = await db.get(CalculatorGcodeArtifact, artifact_id)
    now = datetime.now(timezone.utc)
    if (
        artifact is None
        or artifact.owner_user_id != owner_user_id
        or _utc(artifact.expires_at) <= now
    ):
        raise ArtifactNotFoundError
    if artifact.state == "cancelled":
        raise ArtifactCancelledError
    if ready_required and artifact.state != "ready":
        raise ArtifactConflictError
    return artifact


def parse_artifact_payload(
    artifact: CalculatorGcodeArtifact,
) -> tuple[list[dict], int]:
    """Read and parse every plate, stopping when a shared cancel marker appears."""
    if artifact.storage_key is None or artifact.size_bytes is None or artifact.sha256 is None:
        raise ArtifactNotFoundError
    path = _artifact_path(artifact.storage_key)
    cancel_marker = _cancel_path(artifact.id)

    def should_cancel() -> bool:
        return cancel_marker.exists()

    payload = bytearray()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(UPLOAD_CHUNK_SIZE):
            if should_cancel():
                raise GcodeParseCancelled
            payload.extend(chunk)
            digest.update(chunk)
            if len(payload) > artifact.expected_size_bytes:
                raise ValueError("gcode_artifact_size_mismatch")
    if len(payload) != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
        raise ValueError("gcode_artifact_digest_mismatch")

    raw_bytes = bytes(payload)
    first = parse_gcode_payload(
        artifact.original_name,
        raw_bytes,
        should_cancel=should_cancel,
    )
    plate_indices = first.get("available_plate_indices") or []
    if len(plate_indices) > MAX_PLATES_PER_ARTIFACT:
        raise ValueError("gcode_artifact_too_many_plates")
    remaining = [index for index in plate_indices if index != first.get("plate_index")]
    jobs = [first]
    for plate_index in remaining:
        if should_cancel():
            raise GcodeParseCancelled
        jobs.append(
            parse_gcode_payload(
                artifact.original_name,
                raw_bytes,
                plate_index=plate_index,
                should_cancel=should_cancel,
            )
        )
    jobs.sort(key=lambda item: item.get("plate_index") or 0)
    return jobs, artifact.generation


async def cancel_artifact(
    db: AsyncSession,
    *,
    artifact_id: str,
    owner_user_id: int,
) -> None:
    """Cancel parsing and make future reads unavailable; deletion is idempotent."""
    artifact = await db.get(CalculatorGcodeArtifact, artifact_id)
    if artifact is None or artifact.owner_user_id != owner_user_id:
        return
    marker = _cancel_path(artifact.id)
    await run_in_threadpool(marker.parent.mkdir, parents=True, exist_ok=True)
    await run_in_threadpool(marker.touch, exist_ok=True)
    artifact.state = "cancelled"
    artifact.generation += 1
    await db.commit()
    if artifact.storage_key:
        try:
            await run_in_threadpool(_artifact_path(artifact.storage_key).unlink, missing_ok=True)
        except OSError:
            # An active parser can still hold the file on platforms that forbid
            # unlinking open files. The marker stops work and the sweeper retries.
            logger.debug("Deferred deletion of active G-code artifact %s", artifact.id)


async def verify_parse_generation(
    db: AsyncSession,
    *,
    artifact_id: str,
    owner_user_id: int,
    generation: int,
) -> None:
    artifact = await get_owned_artifact(
        db,
        artifact_id=artifact_id,
        owner_user_id=owner_user_id,
        ready_required=True,
    )
    if artifact.generation != generation:
        raise ArtifactCancelledError


async def cleanup_expired_artifacts(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = ARTIFACT_SWEEP_BATCH_SIZE,
) -> int:
    """Remove one bounded batch of expired or terminal artifact records and blobs."""
    current_time = now or datetime.now(timezone.utc)
    await run_in_threadpool(artifact_storage_root().mkdir, parents=True, exist_ok=True)
    rows = (
        await db.execute(
            select(CalculatorGcodeArtifact)
            .where(
                (CalculatorGcodeArtifact.expires_at <= current_time)
                | CalculatorGcodeArtifact.state.in_(("failed", "cancelled"))
            )
            .order_by(CalculatorGcodeArtifact.expires_at, CalculatorGcodeArtifact.id)
            .limit(batch_size)
        )
    ).scalars().all()
    for artifact in rows:
        await run_in_threadpool(_cancel_path(artifact.id).touch, exist_ok=True)
        if artifact.storage_key:
            await run_in_threadpool(_artifact_path(artifact.storage_key).unlink, missing_ok=True)
        for partial in artifact_storage_root().glob(f"{artifact.id}.*.part"):
            await run_in_threadpool(partial.unlink, missing_ok=True)
        await db.delete(artifact)
    await db.flush()

    # Rows can disappear through owner cascade deletion, and a process can stop
    # between writing a temporary file and committing its row. Reclaim those
    # files after a full artifact lifetime, in the same bounded sweep.
    root = artifact_storage_root()
    orphan_candidates = await run_in_threadpool(
        _old_artifact_files,
        root,
        before=current_time - ORPHAN_FILE_GRACE,
        limit=batch_size,
    )
    candidate_ids = {path.name[:36] for path in orphan_candidates}
    persisted_ids = set()
    if candidate_ids:
        persisted_ids = set(
            (
                await db.execute(
                    select(CalculatorGcodeArtifact.id).where(
                        CalculatorGcodeArtifact.id.in_(candidate_ids)
                    )
                )
            ).scalars()
        )
    for path in orphan_candidates:
        if path.name[:36] not in persisted_ids:
            await run_in_threadpool(path.unlink, missing_ok=True)
    return len(rows)


async def run_gcode_artifact_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: float = ARTIFACT_SWEEP_INTERVAL_SECONDS,
) -> None:
    while True:
        try:
            async with session_factory() as db:
                removed = await cleanup_expired_artifacts(db)
                await db.commit()
            if removed:
                logger.info("Removed %d expired Calculator G-code artifacts", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to sweep Calculator G-code artifacts", exc_info=True)
        await asyncio.sleep(interval_seconds)
