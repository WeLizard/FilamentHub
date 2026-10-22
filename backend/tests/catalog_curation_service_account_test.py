"""Scope and lifecycle tests for draft-only catalog service credentials."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import CatalogCurationProposal, CatalogCurationServiceAccount

pytestmark = pytest.mark.asyncio
ADMIN_ACCOUNTS = "/api/v1/admin/catalog/curation/service-accounts"
ADMIN_PROPOSALS = "/api/v1/admin/catalog/curation/proposals"
SERVICE_PROPOSALS = "/api/v1/service/catalog/curation/proposals"


def admin_headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


def service_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def proposal_payload():
    url = "https://maker.example/products/pla"
    fields = ("name", "material_type", "color_name", "diameter", "availability")
    return {
        "title": "Maker materials",
        "coverage_note": "Current catalog pages reviewed.",
        "draft": {
            "filename": "maker.json",
            "brands": [{"brand_key": "maker", "mode": "create", "name": "Maker"}],
            "filaments": [
                {
                    "filament_key": "maker:pla:black",
                    "brand_key": "maker",
                    "mode": "create",
                    "name": "PLA Black",
                    "material_type": "PLA",
                    "color_name": "Black",
                    "diameter": 1.75,
                    "availability": "available",
                }
            ],
        },
        "evidence": [
            {
                "sheet": "Brands",
                "key": "maker",
                "field": "name",
                "kind": "direct",
                "source_urls": [url],
            },
            *[
                {
                    "sheet": "Filaments",
                    "key": "maker:pla:black",
                    "field": field,
                    "kind": "direct",
                    "source_urls": [url],
                }
                for field in fields
            ],
        ],
        "unmapped_facts": [],
        "source_facts": [
            {
                "filament_key": "maker:pla:black",
                "property_name": field,
                "value_summary": f"Manufacturer states {field}.",
                "source_urls": [url],
                "disposition": "mapped",
                "mapped_fields": [field],
            }
            for field in fields
        ],
    }


async def issue_key(client: AsyncClient, admin_user, name: str) -> str:
    response = await client.post(
        ADMIN_ACCOUNTS,
        headers=admin_headers(admin_user),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["account"]["name"] == name
    assert body["account"]["created_by_user_id"] == admin_user.id
    assert body["account"]["expires_at"]
    return body["token"]


async def test_service_key_creates_and_edits_only_its_own_draft(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    token_a = await issue_key(client, admin_user, "curation-a")
    token_b = await issue_key(client, admin_user, "curation-b")
    account_list = (await client.get(ADMIN_ACCOUNTS, headers=admin_headers(admin_user))).json()
    assert account_list["total"] == 2
    assert all("token" not in item for item in account_list["items"])
    assert all("key_hash" not in item for item in account_list["items"])

    created = await client.post(
        SERVICE_PROPOSALS, headers=service_headers(token_a), json=proposal_payload()
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    proposal_id = proposal["id"]
    assert proposal["created_by_user_id"] is None
    assert proposal["created_by_service_account_id"] is not None
    assert proposal["updated_by_service_account_id"] == proposal["created_by_service_account_id"]
    saved = await db_session.get(CatalogCurationProposal, proposal_id)
    assert saved.created_by_service_account_id == proposal["created_by_service_account_id"]

    assert (await client.get(SERVICE_PROPOSALS, headers=service_headers(token_b))).json()["total"] == 0
    own_list = (await client.get(SERVICE_PROPOSALS, headers=service_headers(token_a))).json()
    assert own_list["total"] == 1
    assert own_list["items"][0]["filament_count"] == 1
    assert own_list["items"][0]["brand_name"] == "Maker"
    assert own_list["items"][0]["author_name"] == "curation-a"
    foreign_get = await client.get(
        f"{SERVICE_PROPOSALS}/{proposal_id}", headers=service_headers(token_b)
    )
    assert foreign_get.status_code == 404
    foreign_patch = await client.patch(
        f"{SERVICE_PROPOSALS}/{proposal_id}",
        headers=service_headers(token_b),
        json={"revision": 1, "title": "Take over"},
    )
    assert foreign_patch.status_code == 404

    edited = await client.patch(
        f"{SERVICE_PROPOSALS}/{proposal_id}",
        headers=service_headers(token_a),
        json={"revision": 1, "title": "Reviewed by service"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2
    assert edited.json()["updated_by_service_account_id"] == proposal["created_by_service_account_id"]
    assert edited.json()["updated_by_user_id"] is None

    admin_preview = await client.post(
        f"{ADMIN_PROPOSALS}/{proposal_id}/preview",
        headers=service_headers(token_a),
        json={"revision": 2},
    )
    assert admin_preview.status_code == 401
    admin_credential_create = await client.post(
        ADMIN_ACCOUNTS,
        headers=service_headers(token_a),
        json={"name": "escalated"},
    )
    assert admin_credential_create.status_code == 401


@pytest.mark.parametrize(
    "sheet,row_update",
    [
        ("Filaments", {"price_per_kg": 12.5}),
        ("Brands", {"verified": True}),
    ],
)
async def test_service_proposal_rejects_price_and_brand_verification(
    client: AsyncClient, admin_user, sheet: str, row_update: dict
):
    token = await issue_key(client, admin_user, f"invalid-{sheet.lower()}")
    payload = proposal_payload()
    target = payload["draft"]["filaments" if sheet == "Filaments" else "brands"][0]
    target.update(row_update)
    response = await client.post(
        SERVICE_PROPOSALS, headers=service_headers(token), json=payload
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "ERR_CATALOG_CURATION_INVALID"


async def test_service_keys_expire_and_revoke_without_exposing_secret(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    token = await issue_key(client, admin_user, "lifecycle")
    account = await db_session.scalar(
        select(CatalogCurationServiceAccount).where(
            CatalogCurationServiceAccount.name == "lifecycle"
        )
    )
    assert token.startswith("fhca_")
    assert account.key_hash != token
    assert len(account.key_hash) == 64

    valid = await client.get(SERVICE_PROPOSALS, headers=service_headers(token))
    assert valid.status_code == 200
    assert account.last_used_at is not None

    account.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client.get(SERVICE_PROPOSALS, headers=service_headers(token))
    assert expired.status_code == 401

    account.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.commit()
    revoked = await client.post(
        f"{ADMIN_ACCOUNTS}/{account.id}/revoke", headers=admin_headers(admin_user)
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"]
    after_revoke = await client.get(SERVICE_PROPOSALS, headers=service_headers(token))
    assert after_revoke.status_code == 401


async def test_service_key_is_not_an_admin_apply_credential(
    client: AsyncClient, admin_user
):
    token = await issue_key(client, admin_user, "no-publish")
    payload = proposal_payload()
    created = await client.post(
        SERVICE_PROPOSALS, headers=service_headers(token), json=payload
    )
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    apply = await client.post(
        f"{ADMIN_PROPOSALS}/{proposal_id}/apply",
        headers=service_headers(token),
        json={"revision": 1, "confirmation_token": "any"},
    )
    assert apply.status_code == 401
