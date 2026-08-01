"""File-backed, versioned legal documents and regional package selection."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request

from app.services.request_region_service import (
    AccessRegion,
    resolve_access_region,
    resolve_request_country_code,
)

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("ru", "en", "zh")
CONTENT_ROOT = Path(__file__).resolve().parents[2] / "legal_content"
_RELOAD_CHECK_INTERVAL_SECONDS = 1.0
_SAFE_EDITION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,31}$")
_MAX_DOCUMENT_BYTES = 512 * 1024

_EEA_COUNTRY_CODES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
)


class LegalContentError(RuntimeError):
    """The active legal content bundle is missing or invalid."""


class LegalPack(StrEnum):
    RU = "ru"
    EU = "eu"
    INTL = "intl"


class LegalDocumentType(StrEnum):
    TERMS = "terms"
    PERSONAL_DATA_CONSENT = "personal_data_consent"
    PRIVACY_POLICY = "privacy_policy"


DOCUMENT_ROUTES = {
    LegalDocumentType.TERMS: "/user-agreement",
    LegalDocumentType.PERSONAL_DATA_CONSENT: "/personal-data-consent",
    LegalDocumentType.PRIVACY_POLICY: "/privacy-policy",
}


@dataclass(frozen=True)
class LegalDocument:
    document_type: LegalDocumentType
    language: str
    title: str
    revision_label: str
    markdown: str


@dataclass(frozen=True)
class LegalEdition:
    edition_id: str
    effective_date: date
    update_note: str
    acceptance_versions: dict[LegalDocumentType, str]
    documents: dict[tuple[LegalDocumentType, str], LegalDocument]


@dataclass(frozen=True)
class LegalCatalog:
    packs: dict[LegalPack, LegalEdition]
    editions: dict[str, LegalEdition]


def resolve_legal_pack(request: Request) -> LegalPack:
    """Choose a coarse legal package without treating language as jurisdiction."""
    access_region = resolve_access_region(request)
    if access_region in {AccessRegion.RU, AccessRegion.UNKNOWN}:
        return LegalPack.RU

    country_code = resolve_request_country_code(request)
    if country_code and country_code.upper() in _EEA_COUNTRY_CODES:
        return LegalPack.EU
    return LegalPack.INTL


def normalize_legal_pack(value: str | LegalPack) -> LegalPack:
    try:
        return LegalPack(value)
    except ValueError as exc:
        raise LegalContentError(f"Unsupported legal pack: {value}") from exc


def normalize_legal_language(value: str | None) -> str:
    language = (value or "en").strip().lower().split("-", 1)[0]
    return language if language in SUPPORTED_LANGUAGES else "en"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegalContentError(f"Cannot read legal manifest: {path.name}") from exc
    if not isinstance(value, dict):
        raise LegalContentError(f"Legal manifest must be an object: {path.name}")
    return value


def _safe_child(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise LegalContentError("Legal document path must be relative")
    resolved_root = root.resolve()
    resolved = (root / relative_path).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise LegalContentError("Legal document path escapes its edition")
    return resolved


def _parse_document(
    *,
    path: Path,
    document_type: LegalDocumentType,
    language: str,
) -> LegalDocument:
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAX_DOCUMENT_BYTES:
            raise LegalContentError(f"Legal document has invalid size: {path.name}")
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise LegalContentError(f"Cannot read legal document: {path.name}") from exc

    lines = raw.splitlines()
    first_content = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_content is None or not lines[first_content].startswith("# "):
        raise LegalContentError(f"Legal document must start with an H1 title: {path.name}")

    title = lines[first_content][2:].strip()
    if not title:
        raise LegalContentError(f"Legal document title is empty: {path.name}")

    revision_index = next(
        (index for index in range(first_content + 1, len(lines)) if lines[index].strip()),
        None,
    )
    if revision_index is None:
        raise LegalContentError(f"Legal document has no revision label: {path.name}")
    revision_line = lines[revision_index].strip()
    if not (revision_line.startswith("_") and revision_line.endswith("_")):
        raise LegalContentError(
            f"Legal document revision label must be italic Markdown: {path.name}"
        )
    revision_label = revision_line[1:-1].strip()
    markdown = "\n".join(lines[revision_index + 1 :]).strip()
    if not markdown:
        raise LegalContentError(f"Legal document body is empty: {path.name}")
    if re.search(r"(?i)<\s*(script|iframe)|javascript\s*:", markdown):
        raise LegalContentError(f"Legal document contains unsafe markup: {path.name}")

    return LegalDocument(
        document_type=document_type,
        language=language,
        title=title,
        revision_label=revision_label,
        markdown=f"{markdown}\n",
    )


def _parse_acceptance_versions(value: Any) -> dict[LegalDocumentType, str]:
    if not isinstance(value, dict):
        raise LegalContentError("acceptance_versions must be an object")
    versions: dict[LegalDocumentType, str] = {}
    for document_type in LegalDocumentType:
        version = value.get(document_type.value)
        if not isinstance(version, str) or not _SAFE_VERSION.fullmatch(version):
            raise LegalContentError(
                f"Invalid acceptance version for {document_type.value}"
            )
        versions[document_type] = version
    return versions


def _load_edition(root: Path, edition_id: str) -> LegalEdition:
    if not _SAFE_EDITION_ID.fullmatch(edition_id):
        raise LegalContentError(f"Invalid legal edition id: {edition_id}")
    edition_root = _safe_child(root / "editions", edition_id)
    manifest = _read_json(edition_root / "edition.json")
    if manifest.get("schema_version") != 1 or manifest.get("edition_id") != edition_id:
        raise LegalContentError(f"Legal edition metadata mismatch: {edition_id}")

    try:
        effective_date = date.fromisoformat(str(manifest["effective_date"]))
    except (KeyError, ValueError) as exc:
        raise LegalContentError(f"Invalid effective date: {edition_id}") from exc

    update_note = manifest.get("update_note", "")
    if not isinstance(update_note, str) or len(update_note) > 500:
        raise LegalContentError(f"Invalid legal update note: {edition_id}")

    documents_manifest = manifest.get("documents")
    if not isinstance(documents_manifest, dict):
        raise LegalContentError(f"documents must be an object: {edition_id}")

    documents: dict[tuple[LegalDocumentType, str], LegalDocument] = {}
    for document_type in LegalDocumentType:
        translations = documents_manifest.get(document_type.value)
        if not isinstance(translations, dict):
            raise LegalContentError(
                f"Missing document mapping for {document_type.value}: {edition_id}"
            )
        for language in SUPPORTED_LANGUAGES:
            relative_path = translations.get(language)
            if not isinstance(relative_path, str) or not relative_path.endswith(".md"):
                raise LegalContentError(
                    f"Missing {language} document for {document_type.value}: {edition_id}"
                )
            document_path = _safe_child(edition_root, relative_path)
            documents[(document_type, language)] = _parse_document(
                path=document_path,
                document_type=document_type,
                language=language,
            )

    return LegalEdition(
        edition_id=edition_id,
        effective_date=effective_date,
        update_note=update_note,
        acceptance_versions=_parse_acceptance_versions(
            manifest.get("acceptance_versions")
        ),
        documents=documents,
    )


def load_legal_catalog(root: Path = CONTENT_ROOT) -> LegalCatalog:
    current = _read_json(root / "current.json")
    if current.get("schema_version") != 1:
        raise LegalContentError("Unsupported legal current-manifest schema")
    pack_map = current.get("packs")
    if not isinstance(pack_map, dict):
        raise LegalContentError("Legal pack map must be an object")

    editions: dict[str, LegalEdition] = {}
    published_editions = current.get("published_editions")
    if not isinstance(published_editions, list) or not all(
        isinstance(item, str) for item in published_editions
    ):
        raise LegalContentError("published_editions must be a list of edition ids")
    for edition_id in published_editions:
        if edition_id in editions:
            raise LegalContentError(f"Duplicate published legal edition: {edition_id}")
        editions[edition_id] = _load_edition(root, edition_id)

    packs: dict[LegalPack, LegalEdition] = {}
    for pack in LegalPack:
        edition_id = pack_map.get(pack.value)
        if not isinstance(edition_id, str):
            raise LegalContentError(f"Missing active edition for legal pack: {pack.value}")
        edition = editions.get(edition_id)
        if edition is None:
            raise LegalContentError(
                f"Active legal edition is not published: {edition_id}"
            )
        packs[pack] = edition

    return LegalCatalog(packs=packs, editions=editions)


def validate_legal_edition(
    edition_id: str,
    root: Path = CONTENT_ROOT,
) -> LegalEdition:
    """Validate a staged edition before it is added to current.json."""
    return _load_edition(root, edition_id)


class LegalCatalogStore:
    """Keep a last-known-good catalog and atomically replace it after validation."""

    def __init__(self, root: Path = CONTENT_ROOT) -> None:
        self.root = root
        self._catalog: LegalCatalog | None = None
        self._signature: tuple[int, int, int] | None = None
        self._failed_signature: tuple[int, int, int] | None = None
        self._next_check_at = 0.0
        self._lock = threading.Lock()

    def _manifest_signature(self) -> tuple[int, int, int]:
        stat = (self.root / "current.json").stat()
        return (stat.st_ino, stat.st_size, stat.st_mtime_ns)

    def get(self, *, force_reload: bool = False) -> LegalCatalog:
        now = time.monotonic()
        if not force_reload and self._catalog is not None and now < self._next_check_at:
            return self._catalog

        with self._lock:
            now = time.monotonic()
            if not force_reload and self._catalog is not None and now < self._next_check_at:
                return self._catalog
            self._next_check_at = now + _RELOAD_CHECK_INTERVAL_SECONDS

            try:
                signature = self._manifest_signature()
            except OSError as exc:
                if self._catalog is not None:
                    logger.error("Legal current manifest is unavailable; keeping cached edition")
                    return self._catalog
                raise LegalContentError("Legal current manifest is unavailable") from exc

            if not force_reload and self._catalog is not None and signature == self._signature:
                return self._catalog

            try:
                candidate = load_legal_catalog(self.root)
            except LegalContentError:
                if signature != self._failed_signature:
                    logger.exception(
                        "Legal content reload rejected; keeping the last-known-good edition"
                    )
                    self._failed_signature = signature
                if self._catalog is not None:
                    return self._catalog
                raise

            self._catalog = candidate
            self._signature = signature
            self._failed_signature = None
            return candidate


legal_catalog_store = LegalCatalogStore()


def get_legal_catalog() -> LegalCatalog:
    return legal_catalog_store.get()


def get_active_edition(pack: str | LegalPack) -> LegalEdition:
    return get_legal_catalog().packs[normalize_legal_pack(pack)]


def get_legal_document(
    *,
    pack: str | LegalPack,
    document_type: str | LegalDocumentType,
    language: str | None,
    edition_id: str | None = None,
) -> tuple[LegalPack, LegalEdition, LegalDocument]:
    normalized_pack = normalize_legal_pack(pack)
    try:
        normalized_type = LegalDocumentType(document_type)
    except ValueError as exc:
        raise LegalContentError(f"Unsupported legal document: {document_type}") from exc
    normalized_language = normalize_legal_language(language)
    catalog = get_legal_catalog()
    edition = (
        catalog.editions.get(edition_id)
        if edition_id is not None
        else catalog.packs[normalized_pack]
    )
    if edition is None:
        raise LegalContentError(f"Unknown legal edition: {edition_id}")
    return normalized_pack, edition, edition.documents[(normalized_type, normalized_language)]


def current_legal_requirements(pack: str | LegalPack) -> dict[str, object]:
    normalized_pack = normalize_legal_pack(pack)
    edition = get_active_edition(normalized_pack)
    pinned_query = urlencode(
        {"pack": normalized_pack.value, "edition": edition.edition_id}
    )
    return {
        "legal_pack": normalized_pack.value,
        "edition_id": edition.edition_id,
        "terms_version": edition.acceptance_versions[LegalDocumentType.TERMS],
        "personal_data_consent_version": edition.acceptance_versions[
            LegalDocumentType.PERSONAL_DATA_CONSENT
        ],
        "privacy_policy_version": edition.acceptance_versions[
            LegalDocumentType.PRIVACY_POLICY
        ],
        "terms_url": f"{DOCUMENT_ROUTES[LegalDocumentType.TERMS]}?{pinned_query}",
        "personal_data_consent_url": (
            f"{DOCUMENT_ROUTES[LegalDocumentType.PERSONAL_DATA_CONSENT]}?{pinned_query}"
        ),
        "privacy_policy_url": (
            f"{DOCUMENT_ROUTES[LegalDocumentType.PRIVACY_POLICY]}?{pinned_query}"
        ),
        "legal_update_effective_date": edition.effective_date,
        "legal_update_note": edition.update_note,
    }


def legacy_acceptance_versions() -> tuple[str, str, str]:
    """Versions shared by every pack, used by pre-pack acceptance records."""
    versions = {
        (
            edition.acceptance_versions[LegalDocumentType.TERMS],
            edition.acceptance_versions[LegalDocumentType.PERSONAL_DATA_CONSENT],
            edition.acceptance_versions[LegalDocumentType.PRIVACY_POLICY],
        )
        for edition in get_legal_catalog().packs.values()
    }
    if len(versions) != 1:
        raise LegalContentError("Active legal packs no longer share legacy versions")
    return next(iter(versions))
