"""Unfinished provider sign-ins: kept for a while, then swept."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
    record_current_legal_acceptance,
)
from app.services.provisional_account_service import (
    PROVISIONAL_ACCOUNT_TTL_DAYS,
    sweep_abandoned_provisional_accounts,
)


async def _user(db: AsyncSession, email: str, **fields) -> User:
    user = User(
        email=email,
        username=email.split("@")[0],
        password_hash=None,
        active=True,
        **fields,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_sweep_removes_only_the_sign_in_nobody_finished(db_session: AsyncSession):
    """Someone distracted has time to come back; forever is a different thing."""
    now = datetime.now(timezone.utc)
    abandoned = await _user(
        db_session,
        "abandoned@example.com",
        provisional_since=now - timedelta(days=PROVISIONAL_ACCOUNT_TTL_DAYS + 1),
    )
    still_thinking = await _user(
        db_session, "thinking@example.com", provisional_since=now - timedelta(days=2)
    )
    # Accounts older than the legal gate carry no mark at all.
    legacy = await _user(db_session, "legacy@example.com")

    removed = await sweep_abandoned_provisional_accounts(db_session)
    assert removed == 1

    remaining = set(
        (await db_session.scalars(select(User.email))).all()
    )
    assert abandoned.email not in remaining
    assert still_thinking.email in remaining
    assert legacy.email in remaining


@pytest.mark.asyncio
async def test_accepting_the_documents_takes_the_account_out_of_the_sweep(
    db_session: AsyncSession,
):
    user = await _user(
        db_session,
        "accepts@example.com",
        provisional_since=datetime.now(timezone.utc)
        - timedelta(days=PROVISIONAL_ACCOUNT_TTL_DAYS + 5),
    )

    await record_current_legal_acceptance(
        db=db_session, user=user, language="ru", source="web"
    )
    await db_session.commit()

    assert user.provisional_since is None
    assert await sweep_abandoned_provisional_accounts(db_session) == 0


@pytest.mark.asyncio
async def test_summary_is_reachable_before_the_documents_are_accepted(
    client: AsyncClient, db_session: AsyncSession
):
    """Refusing has to show what the account holds, and refusal comes first."""
    user = await _user(
        db_session,
        "pending@example.com",
        provisional_since=datetime.now(timezone.utc),
    )
    client.headers["Authorization"] = f"Bearer {create_access_token({'sub': user.email})}"

    response = await client.get("/api/v1/auth/deletion-stats")

    assert response.status_code == 200
    body = response.json()
    for key in (
        "spools_count",
        "printers_count",
        "calculations_count",
        "quotes_count",
        "slice_reports_count",
    ):
        assert body[key] == 0


@pytest.mark.asyncio
async def test_summary_stays_open_to_a_settled_account(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _user(
        db_session,
        "settled@example.com",
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    client.headers["Authorization"] = f"Bearer {create_access_token({'sub': user.email})}"

    response = await client.get("/api/v1/auth/deletion-stats")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_deleting_an_account_removes_the_row_and_frees_the_address(
    db_session: AsyncSession,
):
    """"Delete" has to mean deleted, or the documents promise what we don't do."""
    from app.services.account_deletion import delete_user_account

    user = await _user(
        db_session,
        "goodbye@example.com",
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    user_id = user.id

    await delete_user_account(
        user=user, delete_reviews=False, release_brand_representation=False, db=db_session
    )

    assert await db_session.get(User, user_id) is None
    again = await _user(db_session, "goodbye@example.com")
    assert again.email == "goodbye@example.com"


@pytest.mark.asyncio
async def test_a_kept_review_stays_readable_without_its_author(
    db_session: AsyncSession,
):
    from app.models.brand import Brand
    from app.models.filament import Filament
    from app.models.filament_review import FilamentReview
    from app.services.account_deletion import delete_user_account

    user = await _user(
        db_session,
        "reviewer@example.com",
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    brand = Brand(name="Leaving Brand", slug="leaving-brand", active=True)
    filament = Filament(
        brand=brand, name="Leaving PLA", slug="leaving-pla", material_type="PLA", active=True
    )
    review = FilamentReview(
        user_id=user.id, filament=filament, rating=5, success=True, comment="Печатается отлично"
    )
    db_session.add_all([brand, filament, review])
    await db_session.commit()
    review_id = review.id

    await delete_user_account(
        user=user, delete_reviews=False, release_brand_representation=False, db=db_session
    )

    kept = await db_session.get(FilamentReview, review_id)
    assert kept is not None
    assert kept.user_id is None
    assert kept.active is True
    assert kept.comment == "Печатается отлично"
