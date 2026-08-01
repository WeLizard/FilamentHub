"""Passwords move to Argon2id without anyone being asked to do anything."""

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    get_password_hash,
    password_hash_is_outdated,
    verify_password,
)
from app.models.user import User
from tests.conftest import registration_payload


def _bcrypt_hash(password: str) -> str:
    """A password stored the way it was before the move."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(4)).decode("utf-8")


def test_new_passwords_are_written_with_argon2id():
    hashed = get_password_hash("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong horse", hashed)
    assert not password_hash_is_outdated(hashed)


def test_passwords_stored_before_the_move_still_open_the_door():
    hashed = _bcrypt_hash("old faithful")

    assert verify_password("old faithful", hashed)
    assert not verify_password("not it", hashed)
    assert password_hash_is_outdated(hashed)


def test_an_unreadable_hash_refuses_rather_than_raises():
    assert not verify_password("anything", "not a hash at all")
    assert not verify_password("anything", "")
    assert not password_hash_is_outdated("")


@pytest.mark.asyncio
async def test_signing_in_quietly_rewrites_an_old_hash(
    client: AsyncClient, db_session: AsyncSession
):
    from datetime import datetime, timezone

    from app.services.legal_document_service import current_legal_requirements

    legal = current_legal_requirements("intl")
    password = "testpassword123"
    person = User(
        email="legacy@example.com",
        username="legacy_person",
        password_hash=_bcrypt_hash(password),
        active=True,
        email_verified=True,
        terms_version_accepted=legal["terms_version"],
        personal_data_consent_version=legal["personal_data_consent_version"],
        privacy_policy_version_presented=legal["privacy_policy_version"],
        legal_accepted_at=datetime.now(timezone.utc),
    )
    db_session.add(person)
    await db_session.commit()

    signed_in = await client.post(
        "/api/v1/auth/login", json={"email": "legacy@example.com", "password": password}
    )
    assert signed_in.status_code == 200

    db_session.expire_all()
    stored = await db_session.scalar(select(User).where(User.email == "legacy@example.com"))
    assert stored.password_hash.startswith("$argon2id$")

    # And the new hash still opens the same door.
    again = await client.post(
        "/api/v1/auth/login", json={"email": "legacy@example.com", "password": password}
    )
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_a_wrong_password_never_rewrites_anything(
    client: AsyncClient, db_session: AsyncSession
):
    from datetime import datetime, timezone

    from app.services.legal_document_service import current_legal_requirements

    legal = current_legal_requirements("intl")
    original = _bcrypt_hash("the real one")
    person = User(
        email="guarded@example.com",
        username="guarded_person",
        password_hash=original,
        active=True,
        email_verified=True,
        terms_version_accepted=legal["terms_version"],
        personal_data_consent_version=legal["personal_data_consent_version"],
        privacy_policy_version_presented=legal["privacy_policy_version"],
        legal_accepted_at=datetime.now(timezone.utc),
    )
    db_session.add(person)
    await db_session.commit()

    refused = await client.post(
        "/api/v1/auth/login", json={"email": "guarded@example.com", "password": "a guess"}
    )

    assert refused.status_code == 401
    db_session.expire_all()
    stored = await db_session.scalar(select(User).where(User.email == "guarded@example.com"))
    assert stored.password_hash == original


@pytest.mark.asyncio
async def test_a_newcomer_is_stored_with_the_current_algorithm(
    client: AsyncClient, db_session: AsyncSession
):
    registered = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email="fresh@example.com", username="fresh_person", password="testpassword123"
        ),
    )
    assert registered.status_code == 201

    stored = await db_session.scalar(select(User).where(User.email == "fresh@example.com"))
    assert stored.password_hash.startswith("$argon2id$")
