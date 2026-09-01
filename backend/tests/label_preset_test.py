"""Personal label presets stay private and reject conflicting updates."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)


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
