"""Versioned legal acceptance rules shared by auth and authorization."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_legal_acceptance import UserLegalAcceptance

CURRENT_TERMS_VERSION = "2026-07-25"
CURRENT_PERSONAL_DATA_CONSENT_VERSION = "2026-07-25"
CURRENT_PRIVACY_POLICY_VERSION = "2026-07-25"


def requires_current_legal_acceptance(user: User) -> bool:
    """Return whether the account still needs the current mandatory documents."""
    return (
        user.terms_version_accepted != CURRENT_TERMS_VERSION
        or user.personal_data_consent_version
        != CURRENT_PERSONAL_DATA_CONSENT_VERSION
    )


def current_legal_requirements() -> dict[str, str]:
    """Public current versions and stable document routes."""
    return {
        "terms_version": CURRENT_TERMS_VERSION,
        "personal_data_consent_version": CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        "privacy_policy_version": CURRENT_PRIVACY_POLICY_VERSION,
        "terms_url": "/user-agreement",
        "personal_data_consent_url": "/personal-data-consent",
        "privacy_policy_url": "/privacy-policy",
    }


async def record_current_legal_acceptance(
    *,
    db: AsyncSession,
    user: User,
    language: str,
    source: str,
) -> None:
    """Record both separately accepted documents without duplicating retries."""
    accepted_at = datetime.now(timezone.utc)
    documents = (
        ("terms", CURRENT_TERMS_VERSION),
        ("personal_data_consent", CURRENT_PERSONAL_DATA_CONSENT_VERSION),
    )

    existing_rows = await db.execute(
        select(
            UserLegalAcceptance.document_type,
            UserLegalAcceptance.document_version,
        ).where(
            UserLegalAcceptance.user_id == user.id,
            UserLegalAcceptance.document_type.in_([item[0] for item in documents]),
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
                    related_privacy_policy_version=CURRENT_PRIVACY_POLICY_VERSION,
                    acceptance_source=source,
                    language=language,
                    accepted_at=accepted_at,
                )
            )

    user.terms_version_accepted = CURRENT_TERMS_VERSION
    user.personal_data_consent_version = CURRENT_PERSONAL_DATA_CONSENT_VERSION
    user.privacy_policy_version_presented = CURRENT_PRIVACY_POLICY_VERSION
    user.legal_accepted_at = accepted_at
    user.legal_acceptance_language = language
    # The account has answered, so it is no longer waiting to be swept.
    user.provisional_since = None
