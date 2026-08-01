"""An erasure request must be executable from the panel, and only where it is safe."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User, UserRole


async def _account(db: AsyncSession, *, name: str, role: UserRole = UserRole.USER) -> User:
    from datetime import datetime, timezone

    from app.services.legal_document_service import current_legal_requirements

    legal = current_legal_requirements("intl")
    user = User(
        email=f"{name}@example.com",
        username=name,
        password_hash="x",
        role=role,
        active=True,
        email_verified=True,
        terms_version_accepted=legal["terms_version"],
        personal_data_consent_version=legal["personal_data_consent_version"],
        privacy_policy_version_presented=legal["privacy_policy_version"],
        legal_accepted_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


def _as(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


@pytest.mark.asyncio
async def test_admin_can_carry_out_an_erasure_request(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _account(db_session, name="erasure_admin", role=UserRole.ADMIN)
    person = await _account(db_session, name="asked_to_be_erased")
    await db_session.commit()
    person_id = person.id

    preview = await client.get(
        f"/api/v1/admin/users/{person_id}/deletion-preview", headers=_as(admin)
    )
    assert preview.status_code == 200

    erased = await client.request(
        "DELETE",
        f"/api/v1/admin/users/{person_id}",
        headers=_as(admin),
        json={"delete_reviews": True},
    )

    assert erased.status_code == 200
    assert await db_session.scalar(select(User).where(User.id == person_id)) is None


@pytest.mark.asyncio
async def test_an_admin_cannot_erase_themselves_or_another_admin(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await _account(db_session, name="careful_admin", role=UserRole.ADMIN)
    colleague = await _account(db_session, name="other_admin", role=UserRole.ADMIN)
    await db_session.commit()

    itself = await client.request(
        "DELETE", f"/api/v1/admin/users/{admin.id}", headers=_as(admin), json={}
    )
    colleague_attempt = await client.request(
        "DELETE", f"/api/v1/admin/users/{colleague.id}", headers=_as(admin), json={}
    )

    assert itself.status_code == 400
    assert colleague_attempt.status_code == 400
    assert await db_session.scalar(select(User).where(User.id == admin.id)) is not None
    assert await db_session.scalar(select(User).where(User.id == colleague.id)) is not None


@pytest.mark.asyncio
async def test_an_ordinary_account_cannot_erase_anyone(
    client: AsyncClient, db_session: AsyncSession
):
    person = await _account(db_session, name="just_a_user")
    victim = await _account(db_session, name="someone_else")
    await db_session.commit()

    refused = await client.request(
        "DELETE", f"/api/v1/admin/users/{victim.id}", headers=_as(person), json={}
    )

    assert refused.status_code in (401, 403)
    assert await db_session.scalar(select(User).where(User.id == victim.id)) is not None


@pytest.mark.asyncio
async def test_erasure_removes_private_drafts_and_keeps_what_others_rely_on(
    client: AsyncClient, db_session: AsyncSession
):
    """A draft nobody could reach is deleted; a published preset survives without its author."""
    from app.models.brand import Brand
    from app.models.filament import Filament
    from app.models.preset import Preset, PresetModerationStatus

    admin = await _account(db_session, name="erasing_admin", role=UserRole.ADMIN)
    person = await _account(db_session, name="leaving_person")
    brand = Brand(name="Erasure Brand", slug="erasure-brand", verified=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Erasure PLA",
        slug="erasure-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()

    draft = Preset(
        name="Мой личный черновик",
        filament_id=None,
        user_id=person.id,
        extruder_temp=210,
        bed_temp=60,
        active=False,
        moderation_status=PresetModerationStatus.PENDING,
    )
    published = Preset(
        name="Общий пресет",
        filament_id=filament.id,
        user_id=person.id,
        extruder_temp=205,
        bed_temp=60,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db_session.add_all([draft, published])
    await db_session.commit()
    draft_id, published_id = draft.id, published.id

    erased = await client.request(
        "DELETE",
        f"/api/v1/admin/users/{person.id}",
        headers=_as(admin),
        json={"delete_reviews": True},
    )
    assert erased.status_code == 200

    db_session.expire_all()
    assert await db_session.scalar(select(Preset).where(Preset.id == draft_id)) is None
    survivor = await db_session.scalar(select(Preset).where(Preset.id == published_id))
    assert survivor is not None
    assert survivor.user_id is None
    assert survivor.active is True
