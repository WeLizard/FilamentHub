"""Security boundaries for the brand-site ownership verifier."""

from __future__ import annotations

import httpx
import pytest

from app.services import site_ownership


class _NetworkStream:
    def __init__(self, address: str) -> None:
        self.address = address

    def get_extra_info(self, info: str):
        return (self.address, 443) if info == "server_addr" else None


class _StreamContext:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, *_args) -> None:
        await self.response.aclose()


class _Client:
    def __init__(self, response: httpx.Response | None, calls: list[str], **_kwargs) -> None:
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def stream(self, method: str, url: str) -> _StreamContext:
        self.calls.append(f"{method} {url}")
        assert self.response is not None
        return _StreamContext(self.response)


class _BodyStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def __aiter__(self):
        yield self.body


def _response(body: bytes, address: str = "93.184.216.34") -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/.well-known/filamenthub.txt")
    return httpx.Response(
        200,
        stream=_BodyStream(body),
        request=request,
        extensions={"network_stream": _NetworkStream(address)},
    )


@pytest.mark.asyncio
async def test_private_target_is_rejected_before_http(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def resolve(_domain: str):
        return set()

    monkeypatch.setattr(site_ownership, "_resolve_public_addresses", resolve)
    monkeypatch.setattr(
        site_ownership.httpx,
        "AsyncClient",
        lambda **kwargs: _Client(None, calls, **kwargs),
    )

    result = await site_ownership.confirm_site_ownership(
        "http://127.0.0.1/admin", "filamenthub-verify-secret"
    )

    assert result == (False, "127.0.0.1")
    assert calls == []


@pytest.mark.asyncio
async def test_connected_address_must_match_the_public_dns_result(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    async def resolve(_domain: str):
        return {"93.184.216.34"}

    monkeypatch.setattr(site_ownership, "_resolve_public_addresses", resolve)
    monkeypatch.setattr(
        site_ownership.httpx,
        "AsyncClient",
        lambda **kwargs: _Client(
            _response(b"filamenthub-verify-secret", address="127.0.0.1"),
            calls,
            **kwargs,
        ),
    )

    result = await site_ownership.confirm_site_ownership(
        "example.com", "filamenthub-verify-secret"
    )

    assert result == (False, "example.com")
    assert calls == ["GET https://example.com/.well-known/filamenthub.txt"]


@pytest.mark.asyncio
async def test_exact_token_is_accepted_from_expected_public_target(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []

    async def resolve(_domain: str):
        return {"93.184.216.34"}

    monkeypatch.setattr(site_ownership, "_resolve_public_addresses", resolve)
    monkeypatch.setattr(
        site_ownership.httpx,
        "AsyncClient",
        lambda **kwargs: _Client(
            _response(b"header\nfilamenthub-verify-secret\nfooter"), calls, **kwargs
        ),
    )

    result = await site_ownership.confirm_site_ownership(
        "https://www.example.com/about", "filamenthub-verify-secret"
    )

    assert result == (True, "example.com")
    assert calls == ["GET https://example.com/.well-known/filamenthub.txt"]


@pytest.mark.asyncio
async def test_oversized_body_is_rejected(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def resolve(_domain: str):
        return {"93.184.216.34"}

    monkeypatch.setattr(site_ownership, "_resolve_public_addresses", resolve)
    monkeypatch.setattr(
        site_ownership.httpx,
        "AsyncClient",
        lambda **kwargs: _Client(
            _response(b"filamenthub-verify-secret " + b"x" * 5000), calls, **kwargs
        ),
    )

    result = await site_ownership.confirm_site_ownership(
        "example.com", "filamenthub-verify-secret"
    )

    assert result == (False, "example.com")
