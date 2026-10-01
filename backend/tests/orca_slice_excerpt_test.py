"""The plugin reads a slice from parts it cut out locally, never from the whole file."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.security import create_plugin_token
from app.models.user import User
from app.services import subscription_service

ROUTE = "/api/v1/orcaslicer/slices/excerpts/parse"
CALCULATOR_ROUTE = "/api/v1/calculator/gcode-excerpts/parse"
_FIXTURES = Path(__file__).parent / "fixtures" / "gcode_toolpath_parity"
_GCODE = (_FIXTURES / "toolpath.gcode").read_bytes()
_TOOLPATH = (_FIXTURES / "expected_evidence.json").read_text(encoding="utf-8")


def _request() -> dict:
    return {
        "data": {
            "file_name": "toolpath.gcode",
            "file_size_bytes": str(len(_GCODE)),
            "container": "plain_gcode",
            "toolpath": _TOOLPATH,
        },
        "files": [("head", ("head.gcode", _GCODE, "application/octet-stream"))],
    }


def _plugin_headers(user: User, scopes: list[str]) -> dict[str, str]:
    token = create_plugin_token({"sub": user.email, "user_id": user.id}, scopes)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_a_plugin_session_gets_the_answer_the_calculator_route_gives(
    client: AsyncClient,
    auth_client: AsyncClient,
    auth_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The calculator route refuses a plugin session, so the plugin needs its own door."""
    monkeypatch.setitem(subscription_service._settings_cache, "paywall_enforced", False)
    headers = _plugin_headers(auth_user, ["presets:write"])

    through_plugin = await client.post(ROUTE, headers=headers, **_request())
    refused = await client.post(CALCULATOR_ROUTE, headers=headers, **_request())
    through_calculator = await auth_client.post(CALCULATOR_ROUTE, **_request())

    assert through_plugin.status_code == 200
    assert refused.status_code in (401, 403)
    [job] = through_plugin.json()["jobs"]
    assert job["detail_level"] == "full"
    assert job["toolchange_count"] == 2
    assert through_plugin.json() == through_calculator.json()
    assert through_plugin.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_a_plugin_session_without_the_preset_scope_is_refused(
    client: AsyncClient,
    auth_user: User,
) -> None:
    unscoped = await client.post(
        ROUTE, headers=_plugin_headers(auth_user, ["presets:read"]), **_request()
    )
    anonymous = await client.post(ROUTE, **_request())

    assert unscoped.status_code == 403
    assert unscoped.json()["detail"]["code"] == "ERR_ACCESS_DENIED"
    assert anonymous.status_code == 401


@pytest.mark.asyncio
async def test_the_paid_gate_applies_before_the_body_is_read(
    client: AsyncClient,
    auth_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(subscription_service._settings_cache, "paywall_enforced", True)

    response = await client.post(
        ROUTE,
        headers=_plugin_headers(auth_user, ["presets:write"]),
        content=b"not multipart at all",
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_CALCULATOR_ACCESS_REQUIRED"


@pytest.mark.asyncio
async def test_a_body_that_breaks_the_excerpt_contract_is_refused_like_the_calculator_does(
    client: AsyncClient,
    auth_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(subscription_service._settings_cache, "paywall_enforced", False)
    headers = _plugin_headers(auth_user, ["presets:write"])
    request = _request()
    request["data"] = {**request["data"], "container": "gcode_3mf"}

    response = await client.post(ROUTE, headers=headers, **request)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_GCODE_EXCERPT_INVALID"
