"""Bridge rate limits are isolated by credential, not by shared NAT address."""

from starlette.requests import Request

from app.core.limiter import adapter_token_key


def _request(token: str | None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"x-filamenthub-bridge-token", token.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/printer-bridge/heartbeat",
            "headers": headers,
            "client": ("203.0.113.7", 4242),
        }
    )


def test_adapter_rate_limit_key_is_private_and_per_credential() -> None:
    first = adapter_token_key(_request("fhpb_first"))
    same = adapter_token_key(_request("fhpb_first"))
    second = adapter_token_key(_request("fhpb_second"))

    assert first == same
    assert first != second
    assert "fhpb_first" not in first
    assert adapter_token_key(_request(None)) == "203.0.113.7"
