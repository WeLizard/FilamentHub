"""Versioned legal acceptance rules shared by auth and authorization."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_legal_acceptance import UserLegalAcceptance
from app.services.legal_document_service import (
    LegalContentError,
    LegalDocumentType,
    LegalPack,
    get_active_edition,
    legacy_acceptance_versions,
    normalize_legal_pack,
)
from app.services.legal_document_service import (
    current_legal_requirements as _current_legal_requirements,
)

# Compatibility exports for fixtures and older internal imports. Runtime checks
# below always read the active manifest, so a manifest switch does not require a
# code edit or process restart.
_DEFAULT_REQUIREMENTS = _current_legal_requirements(LegalPack.INTL)
CURRENT_TERMS_VERSION = str(_DEFAULT_REQUIREMENTS["terms_version"])
CURRENT_PERSONAL_DATA_CONSENT_VERSION = str(
    _DEFAULT_REQUIREMENTS["personal_data_consent_version"]
)
CURRENT_PRIVACY_POLICY_VERSION = str(
    _DEFAULT_REQUIREMENTS["privacy_policy_version"]
)
LEGAL_UPDATE_EFFECTIVE_DATE = _DEFAULT_REQUIREMENTS["legal_update_effective_date"]
LEGAL_UPDATE_NOTE = str(_DEFAULT_REQUIREMENTS["legal_update_note"])


def requires_current_legal_acceptance(user: User) -> bool:
    """Return whether the account still needs the current mandatory documents."""
    if user.legal_document_pack:
        try:
            edition = get_active_edition(user.legal_document_pack)
            terms_version = edition.acceptance_versions[LegalDocumentType.TERMS]
            consent_version = edition.acceptance_versions[
                LegalDocumentType.PERSONAL_DATA_CONSENT
            ]
        except LegalContentError:
            return True
    else:
        # Rows created before regional packs are valid while every active pack
        # shares the same mandatory versions. The first regional divergence
        # safely asks these legacy accounts to accept their resolved pack.
        try:
            terms_version, consent_version, _privacy_version = (
                legacy_acceptance_versions()
            )
        except LegalContentError:
            return True

    return (
        user.terms_version_accepted != terms_version
        or user.personal_data_consent_version != consent_version
    )


def current_legal_requirements(
    pack: str | LegalPack = LegalPack.INTL,
) -> dict[str, object]:
    """Public current versions and stable document routes."""
    return _current_legal_requirements(pack)


async def record_current_legal_acceptance(
    *,
    db: AsyncSession,
    user: User,
    language: str,
    source: str,
    legal_pack: str | LegalPack = LegalPack.INTL,
) -> None:
    """Record both separately accepted documents without duplicating retries."""
    normalized_pack = normalize_legal_pack(legal_pack)
    edition = get_active_edition(normalized_pack)
    accepted_at = datetime.now(timezone.utc)
    documents = (
        (
            LegalDocumentType.TERMS.value,
            edition.acceptance_versions[LegalDocumentType.TERMS],
        ),
        (
            LegalDocumentType.PERSONAL_DATA_CONSENT.value,
            edition.acceptance_versions[LegalDocumentType.PERSONAL_DATA_CONSENT],
        ),
    )

    existing_rows = await db.execute(
        select(
            UserLegalAcceptance.document_type,
            UserLegalAcceptance.document_version,
        ).where(
            UserLegalAcceptance.user_id == user.id,
            UserLegalAcceptance.document_type.in_([item[0] for item in documents]),
            UserLegalAcceptance.legal_document_pack == normalized_pack.value,
        )
    )
    existing = set(existing_rows.all())

    for document_type, document_version in documents:
        if (document_type, document_version) not in existing:
            db.add(
                UserLegalAcceptance(
                    user_id=user.id,
                    document_type=document_type,
                    document_version=document_version,
                    related_privacy_policy_version=edition.acceptance_versions[
                        LegalDocumentType.PRIVACY_POLICY
                    ],
                    legal_document_pack=normalized_pack.value,
                    acceptance_source=source,
                    language=language,
                    accepted_at=accepted_at,
                )
            )

    user.terms_version_accepted = edition.acceptance_versions[LegalDocumentType.TERMS]
    user.personal_data_consent_version = edition.acceptance_versions[
        LegalDocumentType.PERSONAL_DATA_CONSENT
    ]
    user.privacy_policy_version_presented = edition.acceptance_versions[
        LegalDocumentType.PRIVACY_POLICY
    ]
    user.legal_document_pack = normalized_pack.value
    user.legal_accepted_at = accepted_at
    user.legal_acceptance_language = language
    # The account has answered, so it is no longer waiting to be swept.
    user.provisional_since = None
