"""Server-backed OAuth handoff used by the OrcaSlicer plugin."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.api.v1.endpoints import auth as auth_endpoint
from app.core.security import decode_access_token, decode_refresh_token
from app.services import plugin_oauth_handoff_service as handoff_service


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        exat: int | None = None,
        nx: bool = False,
    ) -> bool:
        del ex, exat
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, key_count: int, key: str, token: str) -> int:
        del script, key_count
        if self.values.get(key) != token:
            return 0
        del self.values[key]
        return 1


@pytest.fixture
def plugin_oauth_store(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    store = FakeRedis()
    monkeypatch.setattr(handoff_service, "_redis_client", store)
    monkeypatch.setattr(auth_endpoint, "is_provider_configured", lambda provider: True)
    monkeypatch.setattr(auth_endpoint, "is_provider_allowed", lambda provider, region: True)
    monkeypatch.setattr(
        auth_endpoint,
        "get_google_auth_url",
        lambda state, public_origin: (
            f"https://accounts.google.test/authorize?state={state}&redirect={public_origin}"
        ),
    )
    return store


@pytest.mark.asyncio
async def test_plugin_oauth_handoff_delivers_fresh_session_once(
    client,
    auth_client,
    auth_user,
    plugin_oauth_store: FakeRedis,
) -> None:
    created = await client.post(
        "/api/v1/auth/plugin-oauth/flows",
        json={"provider": "google"},
    )
    assert created.status_code == 201, created.text
    flow = created.json()
    assert flow["expires_in"] <= 600
    assert flow["interval"] == 2
    assert flow["browser_url"].startswith("https://filamenthub.ru/oauth/plugin-start/google?")
    assert "localhost" not in flow["browser_url"]
    assert "127.0.0.1" not in flow["browser_url"]
    assert "access" not in flow["browser_url"]
    assert "refresh" not in flow["browser_url"]

    browser_query = parse_qs(urlparse(flow["browser_url"]).query)
    assert browser_query["flow"] == [flow["flow_id"]]
    stored = "\n".join(plugin_oauth_store.values.values())
    assert flow["poll_secret"] not in stored

    authorized_browser = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{flow['flow_id']}/authorize/google",
        json={},
    )
    assert authorized_browser.status_code == 200, authorized_browser.text
    oauth_state = authorized_browser.json()["state"]
    assert oauth_state in authorized_browser.json()["url"]

    pending = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{flow['flow_id']}/poll",
        json={"poll_secret": flow["poll_secret"]},
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert pending.json()["access_token"] is None

    completed_in_browser = await auth_client.post(
        f"/api/v1/auth/plugin-oauth/flows/{flow['flow_id']}/complete",
        json={"state": oauth_state},
    )
    assert completed_in_browser.status_code == 200, completed_in_browser.text
    assert completed_in_browser.json()["status"] == "authorized"

    delivered = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{flow['flow_id']}/poll",
        json={"poll_secret": flow["poll_secret"]},
        headers={"User-Agent": "FilamentHub-Orca/0.1.10"},
    )
    assert delivered.status_code == 200, delivered.text
    payload = delivered.json()
    assert payload["status"] == "complete"
    assert decode_access_token(payload["access_token"])["user_id"] == auth_user.id
    assert decode_refresh_token(payload["refresh_token"])["user_id"] == auth_user.id

    stored_after_delivery = "\n".join(plugin_oauth_store.values.values())
    assert payload["access_token"] not in stored_after_delivery
    assert payload["refresh_token"] not in stored_after_delivery

    replay = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{flow['flow_id']}/poll",
        json={"poll_secret": flow["poll_secret"]},
    )
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "ERR_PLUGIN_OAUTH_FLOW_CONFLICT"


@pytest.mark.asyncio
async def test_plugin_oauth_handoff_reports_provider_failure(
    client,
    plugin_oauth_store: FakeRedis,
) -> None:
    del plugin_oauth_store
    created = (
        await client.post(
            "/api/v1/auth/plugin-oauth/flows",
            json={"provider": "google"},
        )
    ).json()
    query = parse_qs(urlparse(created["browser_url"]).query)
    assert query == {"flow": [created["flow_id"]]}
    started = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{created['flow_id']}/authorize/google",
        json={},
    )
    oauth_state = started.json()["state"]
    failed = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{created['flow_id']}/fail",
        json={
            "state": oauth_state,
            "error": "provider_denied",
        },
    )
    assert failed.status_code == 200
    polled = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{created['flow_id']}/poll",
        json={"poll_secret": created["poll_secret"]},
    )
    assert polled.status_code == 400
    assert polled.json()["detail"] == {
        "code": "ERR_PLUGIN_OAUTH_FLOW_FAILED",
        "params": {"reason": "provider_denied"},
    }


@pytest.mark.asyncio
async def test_plugin_oauth_handoff_rejects_expired_and_wrong_poll_secrets(
    client,
    plugin_oauth_store: FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del plugin_oauth_store
    current_time = 1_800_000_000
    monkeypatch.setattr(handoff_service, "_now", lambda: current_time)
    created = (
        await client.post(
            "/api/v1/auth/plugin-oauth/flows",
            json={"provider": "google"},
        )
    ).json()
    wrong = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{created['flow_id']}/poll",
        json={"poll_secret": "z" * 43},
    )
    assert wrong.status_code == 404

    current_time += 601
    expired = await client.post(
        f"/api/v1/auth/plugin-oauth/flows/{created['flow_id']}/poll",
        json={"poll_secret": created["poll_secret"]},
    )
    assert expired.status_code == 410
    assert expired.json()["detail"]["code"] == "ERR_PLUGIN_OAUTH_FLOW_EXPIRED"
