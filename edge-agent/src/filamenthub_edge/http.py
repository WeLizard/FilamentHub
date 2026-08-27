"""Small bounded JSON HTTP client with redirect-safe credential handling."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from .errors import ConfigurationError, HttpRequestError

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def normalize_origin(value: str, *, allow_http: bool) -> str:
    raw = value.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("HTTP origin has an invalid port") from exc
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/", "/api/v1"}
    ):
        protocol = "HTTP(S)" if allow_http else "HTTPS"
        raise ConfigurationError(f"address must be a plain {protocol} origin")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}{f':{port}' if port is not None else ''}"


class JsonHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        allow_http: bool,
        timeout: float,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.base_url = normalize_origin(base_url, allow_http=allow_http)
        self.timeout = timeout
        self.default_headers = dict(default_headers or {})
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        expected_statuses: set[int] | None = None,
    ) -> tuple[int, Any, Mapping[str, str]]:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("request path must be origin-relative")
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "FilamentHub-Edge/0.1.0",
            **self.default_headers,
            **dict(headers or {}),
        }
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        expected = expected_statuses or {200}
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = response.getcode()
                body = self._read_limited(response)
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = self._read_limited(exc)
            response_headers = dict(exc.headers.items()) if exc.headers else {}
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise HttpRequestError("HTTP peer is unreachable") from exc
        if status not in expected:
            code = self._error_code(body)
            detail = f" ({code})" if code else ""
            raise HttpRequestError(
                f"HTTP peer returned {status}{detail}",
                status_code=status,
            )
        if not body:
            decoded: Any = None
        else:
            try:
                decoded = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise HttpRequestError("HTTP peer returned invalid JSON") from exc
        return status, decoded, response_headers

    @staticmethod
    def _read_limited(response) -> bytes:  # noqa: ANN001
        content_length = response.headers.get("Content-Length") if response.headers else None
        try:
            declared_length = int(content_length) if content_length is not None else None
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > MAX_RESPONSE_BYTES:
            raise HttpRequestError("HTTP response exceeds the size limit")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise HttpRequestError("HTTP response exceeds the size limit")
        return body

    @staticmethod
    def _error_code(body: bytes) -> str | None:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        if not isinstance(decoded, dict):
            return None
        detail = decoded.get("detail")
        if not isinstance(detail, dict):
            return None
        code = detail.get("code")
        return code if isinstance(code, str) and len(code) <= 100 else None
