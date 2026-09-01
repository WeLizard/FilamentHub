"""Personal and organization label presets keep exact ownership boundaries."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.organization import (
    Organization,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.organization_label_preset import OrganizationLabelPreset
from app.models.user import User
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)
from tests.conftest import accepted_legal


def _settings(width: float = 50) -> dict:
    return {
        "label": {
            "width_mm": width,
            "height_mm": 30,
            "kind": "full",
            "color_mode": "mono",
            "dpi": 203,
            "attribution": "full",
            "qr_mark": True,
            "brand_mode": "full",
            "border": False,
            "fields": ["nozzle", "bed"],
        },
        "format": "pdf",
        "media": "single",
        "page_margin_mm": 5,
        "gap_mm": 2,
        "crop_marks": False,
    }


async def test_default_label_preset_is_private_idempotent_and_revision_guarded(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    response = await auth_client.get("/api/v1/labels/presets/default")
    assert response.status_code == 200 and response.json() is None

    response = await auth_client.put(
        "/api/v1/labels/presets/default",
        json={"revision": None, "settings": _settings()},
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["revision"] == 1
    assert saved["settings"] == _settings()

    # Retrying an uncertain first response must not create a second row or
    # advance the revision when the intended settings already won.
    retry = await auth_client.put(
        "/api/v1/labels/presets/default",
        json={"revision": None, "settings": _settings()},
    )
    assert retry.status_code == 200
    assert retry.json()["id"] == saved["id"]
    assert retry.json()["revision"] == 1

    conflict = await auth_client.put(
        "/api/v1/labels/presets/default",
        json={"revision": 2, "settings": _settings(60)},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ERR_LABEL_PRESET_CONFLICT"

    updated = await auth_client.put(
        "/api/v1/labels/presets/default",
        json={"revision": 1, "settings": _settings(60)},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    stranger = User(
        email="label-preset-stranger@example.com",
        username="labelpresetstranger",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(stranger)
    await db_session.commit()
    stranger_token = create_access_token({"sub": stranger.email})
    private = await auth_client.get(
        "/api/v1/labels/presets/default",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert private.status_code == 200 and private.json() is None


async def test_default_label_preset_requires_an_account(client: AsyncClient) -> None:
    response = await client.get("/api/v1/labels/presets/default")
    assert response.status_code == 401


def _authorize(client: AsyncClient, user: User) -> None:
    token = create_access_token({"sub": user.email})
    client.headers["Authorization"] = f"Bearer {token}"


async def test_organization_label_preset_is_shared_only_in_exact_workspace(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    organization = Organization(name="Label Company", slug="label-company", active=True)
    representative = Organization(
        name="Label Representative", slug="label-representative", active=True
    )
    db_session.add_all([organization, representative])
    await db_session.flush()
    brand = Brand(
        name="Organization Label Brand",
        slug="organization-label-brand",
        organization_id=organization.id,
        verified=True,
        active=True,
    )
    editor = User(
        email="label-editor@example.com",
        username="labeleditor",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    representative_user = User(
        email="label-representative@example.com",
        username="labelrepresentative",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    outsider = User(
        email="label-outsider@example.com",
        username="labeloutsider",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db_session.add_all([brand, editor, representative_user, outsider])
    await db_session.flush()
    db_session.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=auth_user.id,
                role=OrganizationMemberRole.OWNER,
                all_brands=True,
                active=True,
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=editor.id,
                role=OrganizationMemberRole.EDITOR,
                all_brands=True,
                active=True,
            ),
            OrganizationMembership(
                organization_id=representative.id,
                user_id=representative_user.id,
                role=OrganizationMemberRole.OWNER,
                all_brands=True,
                active=True,
            ),
            BrandTerritorialGrant(
                organization_id=representative.id,
                brand_id=brand.id,
                country="TR",
                status=GrantStatus.active,
                source=GrantSource.application,
            ),
        ]
    )
    await db_session.commit()
    owner_path = (
        f"/api/v1/labels/organizations/{organization.id}/brands/{brand.id}" "/presets/default"
    )
    representative_path = (
        f"/api/v1/labels/organizations/{representative.id}/brands/{brand.id}" "/presets/default"
    )

    empty = await auth_client.get(owner_path)
    assert empty.status_code == 200 and empty.json() is None
    created = await auth_client.put(
        owner_path,
        json={"revision": None, "settings": _settings()},
    )
    assert created.status_code == 200
    assert created.json()["revision"] == 1

    _authorize(auth_client, editor)
    shared = await auth_client.get(owner_path)
    assert shared.status_code == 200
    assert shared.json()["id"] == created.json()["id"]
    conflict = await auth_client.put(
        owner_path,
        json={"revision": 2, "settings": _settings(60)},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ERR_LABEL_PRESET_CONFLICT"
    updated = await auth_client.put(
        owner_path,
        json={"revision": 1, "settings": _settings(60)},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    _authorize(auth_client, representative_user)
    separate = await auth_client.get(representative_path)
    assert separate.status_code == 200 and separate.json() is None
    representative_created = await auth_client.put(
        representative_path,
        json={"revision": None, "settings": _settings(40)},
    )
    assert representative_created.status_code == 200
    assert representative_created.json()["id"] != created.json()["id"]

    _authorize(auth_client, outsider)
    denied = await auth_client.get(owner_path)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ERR_ACCESS_DENIED"

    _authorize(auth_client, auth_user)
    unchanged = await auth_client.get(owner_path)
    assert unchanged.status_code == 200
    assert unchanged.json()["settings"] == _settings(60)
    preset = await db_session.scalar(
        select(OrganizationLabelPreset).where(OrganizationLabelPreset.id == created.json()["id"])
    )
    assert preset is not None
    assert preset.created_by_id == auth_user.id
    assert preset.updated_by_id == editor.id
