"""Tests for Spoolman integration endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_spoolman_sync_stub(client: AsyncClient):
    """Test Spoolman sync endpoint (stub for MVP)."""
    response = await client.get("/api/v1/spoolman/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "TODO"
    assert "message" in data
    assert "will be implemented" in data["message"].lower() or "spoolman" in data["message"].lower()

