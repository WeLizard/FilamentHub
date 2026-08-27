"""FilamentHub cloud bridge client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import AuthenticationError, HttpRequestError
from .http import JsonHttpClient


@dataclass(frozen=True)
class PairingResult:
    bridge_token: str
    physical_printer_id: int
    material_system_id: int


@dataclass(frozen=True)
class DesiredResult:
    changed: bool
    etag: str | None
    snapshot: dict[str, Any] | None


class FilamentHubCloud:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        allow_insecure_http: bool,
    ) -> None:
        self.http = JsonHttpClient(
            base_url,
            allow_http=allow_insecure_http,
            timeout=timeout,
        )

    def pair(
        self,
        *,
        pairing_code: str,
        provider: str,
        instance_id: str,
        version: str,
        capabilities: list[str],
    ) -> PairingResult:
        _, decoded, _ = self.http.request(
            "POST",
            "/api/v1/printer-bridge/pair",
            payload={
                "pairing_code": pairing_code,
                "provider": provider,
                "transport": "edge_agent",
                "source_instance_id": instance_id,
                "plugin_version": version,
                "capabilities": capabilities,
            },
        )
        if not isinstance(decoded, dict):
            raise HttpRequestError("FilamentHub pairing response is invalid")
        token = decoded.get("bridge_token")
        printer_id = decoded.get("physical_printer_id")
        system_id = decoded.get("material_system_id")
        if (
            not isinstance(token, str)
            or not token.startswith("fhpb_")
            or not isinstance(printer_id, int)
            or printer_id < 1
            or not isinstance(system_id, int)
            or system_id < 1
        ):
            raise HttpRequestError("FilamentHub pairing response is invalid")
        return PairingResult(token, printer_id, system_id)

    def desired_snapshot(self, *, token: str, etag: str | None) -> DesiredResult:
        headers = self._headers(token)
        if etag:
            headers["If-None-Match"] = etag
        status, decoded, response_headers = self._authorized_request(
            "GET",
            "/api/v1/printer-bridge/snapshot",
            token=token,
            headers=headers,
            expected_statuses={200, 304},
        )
        response_etag = next(
            (value for key, value in response_headers.items() if key.lower() == "etag"),
            None,
        )
        if status == 304:
            return DesiredResult(False, response_etag or etag, None)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("slots"), list):
            raise HttpRequestError("FilamentHub desired snapshot is invalid")
        return DesiredResult(True, response_etag, decoded)

    def upload_observation(self, *, token: str, payload: dict[str, Any]) -> None:
        _, decoded, _ = self._authorized_request(
            "POST",
            "/api/v1/printer-bridge/snapshot",
            token=token,
            payload=payload,
        )
        if not isinstance(decoded, dict) or not isinstance(decoded.get("accepted"), bool):
            raise HttpRequestError("FilamentHub observation response is invalid")

    def heartbeat(self, *, token: str, payload: dict[str, Any]) -> None:
        _, decoded, _ = self._authorized_request(
            "POST",
            "/api/v1/printer-bridge/heartbeat",
            token=token,
            payload=payload,
        )
        if not isinstance(decoded, dict) or decoded.get("accepted") is not True:
            raise HttpRequestError("FilamentHub heartbeat response is invalid")

    def _authorized_request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: set[int] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        try:
            status, decoded, response_headers = self.http.request(
                method,
                path,
                payload=payload,
                headers=headers or self._headers(token),
                expected_statuses=expected_statuses,
            )
        except HttpRequestError as exc:
            if exc.status_code == 401:
                raise AuthenticationError(
                    "FilamentHub Edge connection is no longer authorized",
                    status_code=401,
                ) from exc
            raise
        return status, decoded, dict(response_headers)

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"X-FilamentHub-Bridge-Token": token}
