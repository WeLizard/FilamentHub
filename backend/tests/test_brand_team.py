"""Regression tests for organization team and ownership lifecycle."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.notification import Notification, NotificationType
from app.models.organization import (
    Organization,
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.user import User, UserRole
from app.services.account_deletion import delete_user_account


async def _workspace(
    db: AsyncSession,
    owner: User,
    *,
    slug: str,
) -> tuple[Organization, Brand, OrganizationMembership]:
    organization = Organization(name=f"Organization {slug}", slug=f"org-{slug}", active=True)
    db.add(organization)
    await db.flush()
    brand = Brand(
        name=f"Brand {slug}",
        slug=f"brand-{slug}",
        organization_id=organization.id,
        verified=True,
        active=True,
    )
    db.add(brand)
    await db.flush()
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=owner.id,
        role=OrganizationMemberRole.OWNER,
        all_brands=True,
        active=True,
    )
    db.add(membership)
    owner.brand_id = brand.id
    owner.role = UserRole.BRAND
    await db.commit()
    return organization, brand, membership


def _auth(client: AsyncClient, user: User) -> None:
    client.headers["Authorization"] = f"Bearer {create_access_token({'sub': user.email})}"


@pytest.mark.asyncio
async def test_team_invite_is_bound_to_exact_email(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    organization, brand, _ = await _workspace(db_session, auth_user, slug="exact-email")
    invited = User(
        email="person@private.example",
        username="invited-person",
        password_hash="$2b$12$test",
        active=True,
    )
    wrong = User(
        email="other@private.example",
        username="wrong-person",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add_all([invited, wrong])
    await db_session.commit()

    created = await auth_client.post(
        f"/api/v1/brands/{brand.id}/team/invites",
        json={
            "email": invited.email,
            "role": "editor",
            "all_brands": False,
            "send_email": False,
        },
    )
    assert created.status_code == 201
    token = created.json()["invite_url"].rsplit("/", 1)[-1]

    _auth(auth_client, wrong)
    rejected = await auth_client.post(f"/api/v1/brand-invites/{token}/accept", json={})
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "ERR_BRAND_INVITE_EMAIL_MISMATCH"

    _auth(auth_client, invited)
    accepted = await auth_client.post(f"/api/v1/brand-invites/{token}/accept", json={})
    assert accepted.status_code == 200
    assert accepted.json()["member_role"] == "editor"
    retried = await auth_client.post(f"/api/v1/brand-invites/{token}/accept", json={})
    assert retried.status_code == 200
    assert retried.json()["organization_id"] == organization.id

    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == invited.id,
        )
    )
    assert membership is not None
    assert membership.role == OrganizationMemberRole.EDITOR
    assert membership.all_brands is False
    assert await db_session.scalar(
        select(OrganizationBrandAccess.id).where(
            OrganizationBrandAccess.membership_id == membership.id,
            OrganizationBrandAccess.brand_id == brand.id,
        )
    )


@pytest.mark.asyncio
async def test_removed_owner_reinvited_as_editor_does_not_regain_owner_role(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    organization, brand, _ = await _workspace(db_session, auth_user, slug="safe-reinvite")
    former_owner = User(
        email="former-owner@example.net",
        username="former-owner",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(former_owner)
    await db_session.flush()
    stale_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=former_owner.id,
        role=OrganizationMemberRole.OWNER,
        all_brands=True,
        active=False,
    )
    db_session.add(stale_membership)
    await db_session.commit()

    created = await auth_client.post(
        f"/api/v1/brands/{brand.id}/team/invites",
        json={
            "email": former_owner.email,
            "role": "editor",
            "all_brands": False,
            "send_email": False,
        },
    )
    assert created.status_code == 201
    token = created.json()["invite_url"].rsplit("/", 1)[-1]

    _auth(auth_client, former_owner)
    accepted = await auth_client.post(f"/api/v1/brand-invites/{token}/accept", json={})
    assert accepted.status_code == 200
    await db_session.refresh(stale_membership)
    assert stale_membership.active is True
    assert stale_membership.role == OrganizationMemberRole.EDITOR
    assert stale_membership.all_brands is False
    assert await db_session.scalar(
        select(OrganizationBrandAccess.id).where(
            OrganizationBrandAccess.membership_id == stale_membership.id,
            OrganizationBrandAccess.brand_id == brand.id,
        )
    )


@pytest.mark.asyncio
async def test_verified_brand_join_is_reviewed_by_owner_as_scoped_editor(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    organization, brand, _ = await _workspace(db_session, auth_user, slug="owner-review")
    requester = User(
        email="joiner@example.net",
        username="joiner",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(requester)
    await db_session.commit()
    _auth(auth_client, requester)
    created = await auth_client.post(
        "/api/v1/brand-requests/",
        json={"request_type": "join", "brand_id": brand.id, "message": "I work here"},
    )
    assert created.status_code == 201

    _auth(auth_client, auth_user)
    workspace = await auth_client.get(f"/api/v1/brands/{brand.id}/team")
    assert workspace.status_code == 200
    assert [request["id"] for request in workspace.json()["pending_join_requests"]] == [
        created.json()["id"]
    ]
    approved = await auth_client.patch(
        f"/api/v1/brands/{brand.id}/team/join-requests/{created.json()['id']}",
        json={"status": "approved"},
    )
    assert approved.status_code == 204
    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == requester.id,
        )
    )
    assert membership is not None
    assert membership.role == OrganizationMemberRole.EDITOR
    assert membership.all_brands is False
    await db_session.refresh(brand)
    assert brand.verified is True
    notification = await db_session.scalar(
        select(Notification).where(
            Notification.user_id == requester.id,
            Notification.type == NotificationType.BRAND_REQUEST_APPROVED,
        )
    )
    assert notification is not None
    assert notification.extra_data["brand_id"] == brand.id


@pytest.mark.asyncio
async def test_editor_sees_only_self_and_cannot_invite(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    organization, brand, _ = await _workspace(db_session, auth_user, slug="editor-privacy")
    editor = User(
        email="private-editor@example.net",
        username="private-editor",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.BRAND,
        brand_id=brand.id,
    )
    db_session.add(editor)
    await db_session.flush()
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=editor.id,
        role=OrganizationMemberRole.EDITOR,
        all_brands=False,
        active=True,
    )
    db_session.add(membership)
    await db_session.flush()
    db_session.add(OrganizationBrandAccess(membership_id=membership.id, brand_id=brand.id))
    await db_session.commit()

    _auth(auth_client, editor)
    workspace = await auth_client.get(f"/api/v1/brands/{brand.id}/team")
    assert workspace.status_code == 200
    assert [member["user_id"] for member in workspace.json()["members"]] == [editor.id]
    assert workspace.json()["pending_invites"] == []
    assert workspace.json()["pending_join_requests"] == []

    invite = await auth_client.post(
        f"/api/v1/brands/{brand.id}/team/invites",
        json={"email": "hidden@example.net", "send_email": False},
    )
    assert invite.status_code == 403


@pytest.mark.asyncio
async def test_owner_cannot_remove_member_from_another_organization(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    _, brand, _ = await _workspace(db_session, auth_user, slug="first-org")
    second_owner = User(
        email="second-owner@example.net",
        username="second-owner",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(second_owner)
    await db_session.flush()
    _, _, second_membership = await _workspace(db_session, second_owner, slug="second-org")

    _auth(auth_client, auth_user)
    response = await auth_client.delete(
        f"/api/v1/brands/{brand.id}/team/members/{second_membership.id}"
    )
    assert response.status_code == 404
    await db_session.refresh(second_membership)
    assert second_membership.active is True


@pytest.mark.asyncio
async def test_admin_approval_of_owned_brand_join_grants_scoped_editor(
    auth_client: AsyncClient,
    admin_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    organization, brand, _ = await _workspace(db_session, auth_user, slug="admin-team-review")
    requester = User(
        email="admin-reviewed-editor@example.net",
        username="admin-reviewed-editor",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(requester)
    await db_session.commit()

    _auth(auth_client, requester)
    created = await auth_client.post(
        "/api/v1/brand-requests/",
        json={"request_type": "join", "brand_id": brand.id, "message": "Team access"},
    )
    assert created.status_code == 201

    _auth(admin_client, admin_user)
    approved = await admin_client.patch(
        f"/api/v1/admin/brand-requests/{created.json()['id']}",
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == requester.id,
        )
    )
    assert membership is not None
    assert membership.role == OrganizationMemberRole.EDITOR
    assert membership.all_brands is False
    assert await db_session.scalar(
        select(OrganizationBrandAccess.id).where(
            OrganizationBrandAccess.membership_id == membership.id,
            OrganizationBrandAccess.brand_id == brand.id,
        )
    )


@pytest.mark.asyncio
async def test_last_owner_must_transfer_before_account_deletion(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    organization, brand, _ = await _workspace(db_session, auth_user, slug="transfer")
    editor = User(
        email="editor@example.net",
        username="brand-editor",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.BRAND,
        brand_id=brand.id,
    )
    db_session.add(editor)
    await db_session.flush()
    editor_membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=editor.id,
        role=OrganizationMemberRole.EDITOR,
        all_brands=False,
        active=True,
    )
    db_session.add(editor_membership)
    await db_session.flush()
    db_session.add(
        OrganizationBrandAccess(membership_id=editor_membership.id, brand_id=brand.id)
    )
    await db_session.commit()
    brand_id = brand.id
    editor_membership_id = editor_membership.id

    with pytest.raises(HTTPException) as exc:
        await delete_user_account(
            user=auth_user,
            delete_reviews=False,
            release_brand_representation=True,
            db=db_session,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ERR_OWNERSHIP_TRANSFER_REQUIRED"
    await db_session.rollback()

    transferred = await auth_client.post(
        f"/api/v1/brands/{brand_id}/team/transfer",
        json={"target_membership_id": editor_membership_id},
    )
    assert transferred.status_code == 204
    transferred_membership = await db_session.get(
        OrganizationMembership, editor_membership_id
    )
    assert transferred_membership is not None
    assert transferred_membership.role == OrganizationMemberRole.OWNER


@pytest.mark.asyncio
async def test_release_preserves_brand_catalog_and_existing_qr(
    auth_user: User,
    db_session: AsyncSession,
):
    _, brand, membership = await _workspace(db_session, auth_user, slug="release")
    filament = Filament(
        brand_id=brand.id,
        name="Release PLA",
        slug="release-pla",
        material_type="PLA",
        qr_code="stable-existing-qr",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()

    await delete_user_account(
        user=auth_user,
        delete_reviews=False,
        release_brand_representation=True,
        db=db_session,
    )
    preserved_brand = await db_session.get(Brand, brand.id)
    preserved_filament = await db_session.get(Filament, filament.id)
    await db_session.refresh(membership)
    assert preserved_brand is not None
    assert preserved_brand.verified is False
    assert preserved_filament is not None
    assert preserved_filament.qr_code == "stable-existing-qr"
    assert membership.active is False
