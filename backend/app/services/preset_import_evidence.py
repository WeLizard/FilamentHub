"""Preserve exact Orca evidence separately from editable preset state."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def _capture(
    *,
    settings: dict[str, Any] | None,
    source: str | None,
    external_id: str | None,
    name: str,
    source_version: str | None,
    capture_mode: str | None,
) -> dict[str, Any]:
    captured_settings = deepcopy(settings or {})
    canonical = json.dumps(
        captured_settings,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": source or "orcaslicer",
        "source_version": source_version,
        "capture_mode": capture_mode,
        "settings_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "external_id": external_id,
        "name": name,
        "settings": captured_settings,
    }


def new_import_evidence(
    *,
    settings: dict[str, Any] | None,
    source: str | None,
    external_id: str | None,
    name: str,
    source_version: str | None = None,
    capture_mode: str | None = None,
) -> dict[str, Any]:
    """Create evidence whose original capture is never rewritten."""
    capture = _capture(
        settings=settings,
        source=source,
        external_id=external_id,
        name=name,
        source_version=source_version,
        capture_mode=capture_mode,
    )
    return {"version": 1, "original": capture, "latest": deepcopy(capture)}


def refresh_import_evidence(
    evidence: dict[str, Any] | None,
    *,
    settings: dict[str, Any] | None,
    source: str | None,
    external_id: str | None,
    name: str,
    source_version: str | None = None,
    capture_mode: str | None = None,
) -> dict[str, Any]:
    """Refresh the latest observation while retaining the first exact capture."""
    if not isinstance(evidence, dict) or evidence.get("version") != 1:
        return new_import_evidence(
            settings=settings,
            source=source,
            external_id=external_id,
            name=name,
            source_version=source_version,
            capture_mode=capture_mode,
        )

    result = deepcopy(evidence)
    if not isinstance(result.get("original"), dict):
        result["original"] = _capture(
            settings=settings,
            source=source,
            external_id=external_id,
            name=name,
            source_version=source_version,
            capture_mode=capture_mode,
        )
    result["latest"] = _capture(
        settings=settings,
        source=source,
        external_id=external_id,
        name=name,
        source_version=source_version,
        capture_mode=capture_mode,
    )
    return result


def latest_evidence_settings(
    evidence: dict[str, Any] | None,
    fallback: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    """Return exact latest evidence or the best stored import snapshot."""
    if isinstance(evidence, dict):
        latest = evidence.get("latest")
        if isinstance(latest, dict) and isinstance(latest.get("settings"), dict):
            return deepcopy(latest["settings"]), "orca_capture"
        original = evidence.get("original")
        if isinstance(original, dict) and isinstance(original.get("settings"), dict):
            return deepcopy(original["settings"]), "orca_capture"
    return deepcopy(fallback or {}), "stored_snapshot"
