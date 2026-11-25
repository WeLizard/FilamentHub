import logging

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_render_failure_reaches_the_log_on_one_header_line(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.api.v1.endpoints.client_errors"):
        response = await client.post(
            "/api/v1/client-errors",
            json={
                "message": "x is undefined\nINFO forged line",
                "stack": "at Profile (ProfilePage.js:1:2)",
                "path": "/profile?token=secret",
                "build": "index-AbCd1234.js",
            },
        )

    assert response.status_code == 204
    record = caplog.records[-1].getMessage()
    header = record.splitlines()[0]
    assert "build=index-AbCd1234.js path=/profile message=x is undefined INFO forged line" in header
    assert "secret" not in record
    assert "ProfilePage.js" in record


@pytest.mark.asyncio
async def test_oversized_report_is_refused(client: AsyncClient) -> None:
    response = await client.post("/api/v1/client-errors", json={"message": "m" * 501})

    assert response.status_code == 422
