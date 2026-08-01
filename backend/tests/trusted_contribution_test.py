"""Only confirmed contributors move the community average."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.services.account_trust_service import TRUST_REQUIRED_FROM
from app.services.preset_recommender import get_recommended_preset_values


async def _filament(db: AsyncSession) -> Filament:
    brand = Brand(name="Trust Brand", slug="trust-brand", verified=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Trust PLA",
        slug="trust-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db.add(filament)
    await db.flush()
    return filament


async def _author(db: AsyncSession, *, name: str, verified: bool, created_at: datetime) -> User:
    # Accepted legal documents, so the legal gate does not answer before the one
    # under test.
    from app.services.legal_document_service import current_legal_requirements

    legal = current_legal_requirements("intl")
    user = User(
        terms_version_accepted=legal["terms_version"],
        personal_data_consent_version=legal["personal_data_consent_version"],
        privacy_policy_version_presented=legal["privacy_policy_version"],
        legal_accepted_at=datetime.now(timezone.utc),
        email=f"{name}@example.com",
        username=name,
        password_hash="x",
        active=True,
        email_verified=verified,
        created_at=created_at,
    )
    db.add(user)
    await db.flush()
    return user


async def _preset(db: AsyncSession, filament: Filament, user: User | None, temp: float) -> Preset:
    preset = Preset(
        name=f"preset-{temp}",
        filament_id=filament.id,
        user_id=user.id if user else None,
        extruder_temp=temp,
        bed_temp=60,
        active=True,
        is_weighted=False,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db.add(preset)
    await db.flush()
    return preset


@pytest.mark.asyncio
async def test_unconfirmed_newcomers_do_not_shift_the_average(db_session: AsyncSession):
    filament = await _filament(db_session)
    after = TRUST_REQUIRED_FROM + timedelta(days=1)
    confirmed = await _author(db_session, name="confirmed", verified=True, created_at=after)
    for temp in (200, 202, 204, 206):
        await _preset(db_session, filament, confirmed, temp)
    await db_session.commit()

    honest = await get_recommended_preset_values(filament.id, db_session)

    stranger = await _author(db_session, name="stranger", verified=False, created_at=after)
    for _ in range(4):
        await _preset(db_session, filament, stranger, 260)
    await db_session.commit()

    after_flood = await get_recommended_preset_values(filament.id, db_session)

    assert after_flood["extruder_temp"] == honest["extruder_temp"]


@pytest.mark.asyncio
async def test_accounts_that_predate_the_rule_keep_counting(db_session: AsyncSession):
    """Switching the rule on must not empty the averages of everyone who was never asked."""
    filament = await _filament(db_session)
    old_timer = await _author(
        db_session,
        name="oldtimer",
        verified=False,
        created_at=TRUST_REQUIRED_FROM - timedelta(days=30),
    )
    for temp in (210, 212, 214, 216):
        await _preset(db_session, filament, old_timer, temp)
    await db_session.commit()

    values = await get_recommended_preset_values(filament.id, db_session)

    assert 210 <= values["extruder_temp"] <= 216


@pytest.mark.asyncio
async def test_a_brand_preset_counts_whatever_the_author_looks_like(db_session: AsyncSession):
    filament = await _filament(db_session)
    stranger = await _author(
        db_session,
        name="brandrep",
        verified=False,
        created_at=datetime.now(timezone.utc),
    )
    for temp in (215, 216, 217, 218):
        preset = await _preset(db_session, filament, stranger, temp)
        preset.is_official = True
    await db_session.commit()

    values = await get_recommended_preset_values(filament.id, db_session)

    assert 215 <= values["extruder_temp"] <= 218


@pytest.mark.asyncio
async def test_a_fresh_unconfirmed_account_cannot_act_where_it_reaches_others(
    client, db_session: AsyncSession, monkeypatch
):
    """Reviews, brand claims and the trial need a confirmed address."""
    from app.api.v1.endpoints import auth as auth_module

    monkeypatch.setattr(auth_module, "send_email_verification_email", lambda **_: True)
    filament = await _filament(db_session)
    await db_session.commit()

    newcomer = await _author(
        db_session,
        name="fresh",
        verified=False,
        created_at=TRUST_REQUIRED_FROM + timedelta(days=1),
    )
    await db_session.commit()

    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token({'sub': newcomer.email})}"}
    blocked = await client.post(
        "/api/v1/filament-reviews/",
        headers=headers,
        json={"filament_id": filament.id, "success": True, "rating": 5.0},
    )

    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "ERR_EMAIL_NOT_VERIFIED"

    newcomer.email_verified = True
    await db_session.commit()

    allowed = await client.post(
        "/api/v1/filament-reviews/",
        headers=headers,
        json={"filament_id": filament.id, "success": True, "rating": 5.0},
    )
    assert allowed.status_code == 201
