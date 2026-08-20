"""Admin brand-request pagination must not strand requests after page one."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_request import BrandRequest, BrandRequestStatus, BrandRequestType
from app.models.user import User


@pytest.mark.asyncio
async def test_admin_brand_requests_expose_complete_pagination_metadata(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    db_session.add_all(
        [
            BrandRequest(
                user_id=admin_user.id,
                request_type=BrandRequestType.CREATE,
                new_brand_name=f"Pending brand {index}",
                status=BrandRequestStatus.PENDING,
            )
            for index in range(21)
        ]
    )
    await db_session.commit()

    response = await admin_client.get(
        "/api/v1/admin/brand-requests",
        params={"page": 2, "size": 20, "status": "pending"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 21
    assert payload["page"] == 2
    assert payload["size"] == 20
    assert payload["pages"] == 2
    assert len(payload["items"]) == 1
