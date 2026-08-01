"""File-backed legal editions are complete, immutable and fail safely."""

from __future__ import annotations

import json
import shutil

import pytest
from starlette.requests import Request

from app.services import legal_document_service as legal_service
from app.services.legal_document_service import (
    CONTENT_ROOT,
    LegalCatalogStore,
    LegalContentError,
    LegalDocumentType,
    LegalPack,
    load_legal_catalog,
    resolve_legal_pack,
    validate_legal_edition,
)
from app.services.request_region_service import AccessRegion


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "client": ("203.0.113.5", 12345),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_active_catalog_has_three_complete_logical_packs() -> None:
    catalog = load_legal_catalog()

    assert set(catalog.packs) == {LegalPack.RU, LegalPack.EU, LegalPack.INTL}
    for edition in catalog.packs.values():
        assert len(edition.documents) == len(LegalDocumentType) * 3
        assert edition.acceptance_versions[LegalDocumentType.TERMS] == "2026-08-01"


def test_staged_edition_validation_reads_all_nine_documents() -> None:
    edition = validate_legal_edition("global-2026-08-01")

    assert len(edition.documents) == 9
    assert edition.documents[(LegalDocumentType.PRIVACY_POLICY, "en")].title == (
        "Privacy Policy"
    )


def test_store_keeps_last_known_good_catalog_during_partial_upload(tmp_path) -> None:
    root = tmp_path / "legal_content"
    shutil.copytree(CONTENT_ROOT, root)
    store = LegalCatalogStore(root)
    original = store.get(force_reload=True)

    (root / "current.json").write_text('{"schema_version":', encoding="utf-8")

    assert store.get(force_reload=True) is original


def test_invalid_catalog_without_a_cached_version_fails_closed(tmp_path) -> None:
    root = tmp_path / "legal_content"
    root.mkdir()
    (root / "current.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(LegalContentError):
        LegalCatalogStore(root).get(force_reload=True)


@pytest.mark.parametrize(
    ("access_region", "country_code", "expected"),
    [
        (AccessRegion.RU, "RU", LegalPack.RU),
        (AccessRegion.UNKNOWN, None, LegalPack.RU),
        (AccessRegion.INTL, "DE", LegalPack.EU),
        (AccessRegion.INTL, "US", LegalPack.INTL),
    ],
)
def test_legal_pack_is_independent_from_interface_language(
    monkeypatch,
    access_region: AccessRegion,
    country_code: str | None,
    expected: LegalPack,
) -> None:
    monkeypatch.setattr(legal_service, "resolve_access_region", lambda _request: access_region)
    monkeypatch.setattr(
        legal_service,
        "resolve_request_country_code",
        lambda _request: country_code,
    )

    assert resolve_legal_pack(_request()) == expected
