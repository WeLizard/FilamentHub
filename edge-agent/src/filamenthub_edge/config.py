"""Environment and Home Assistant option parsing."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .errors import ConfigurationError
from .http import normalize_origin

MAX_OPTIONS_BYTES = 64 * 1024
MAX_CONNECTIONS = 32
CONNECTION_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError("invalid boolean value")


def _as_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigurationError("invalid integer value")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("invalid integer value") from exc
    if parsed < minimum or parsed > maximum:
        raise ConfigurationError(f"integer value must be within {minimum}..{maximum}")
    return parsed


def _load_options(path: Path, *, required: bool = False) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_OPTIONS_BYTES + 1)
        if len(payload) > MAX_OPTIONS_BYTES:
            raise ConfigurationError("Edge options file is too large")
        decoded = json.loads(payload)
    except FileNotFoundError as exc:
        if not required:
            return {}
        raise ConfigurationError("Configured Edge options file was not found") from exc
    except (OSError, ValueError) as exc:
        raise ConfigurationError("Edge options file is invalid") from exc
    if not isinstance(decoded, dict):
        raise ConfigurationError("Edge options must be a JSON object")
    return decoded


def _text(value: Any, name: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ConfigurationError(f"invalid {name}")
    return value.strip()


@dataclass(frozen=True)
class EdgeConfig:
    """Configuration of one adapter connection within a node."""

    filamenthub_url: str
    pairing_code: str | None = field(repr=False)
    material_provider: str
    moonraker_url: str
    moonraker_api_key: str | None = field(repr=False)
    state_path: Path
    sync_interval: int
    request_timeout: int
    allow_insecure_cloud: bool
    run_once: bool
    connection_id: str = "printer"
    name: str = "Printer"
    enabled: bool = True
    adapter: str = "moonraker"
    node_instance_id: str | None = None


@dataclass(frozen=True)
class NodeConfig:
    filamenthub_url: str
    state_directory: Path
    connections: tuple[EdgeConfig, ...]
    run_once: bool = False

    @classmethod
    def load(cls) -> "NodeConfig":
        options_path = Path(os.getenv("FH_EDGE_OPTIONS_FILE", "/data/options.json"))
        options = _load_options(options_path, required="FH_EDGE_OPTIONS_FILE" in os.environ)
        unknown = options.keys() - {
            "filamenthub_url",
            "connections",
            "sync_interval",
            "request_timeout",
            "allow_insecure_cloud",
        }
        if unknown:
            raise ConfigurationError("Unknown Edge options; configure printers in connections")

        def setting(env_name: str, option_name: str, default: Any = None) -> Any:
            env_value = os.getenv(env_name)
            return env_value if env_value is not None else options.get(option_name, default)

        allow_http = _as_bool(setting("FH_EDGE_ALLOW_INSECURE_CLOUD", "allow_insecure_cloud"))
        origin = normalize_origin(
            _text(
                setting("FH_EDGE_FILAMENTHUB_URL", "filamenthub_url", "https://filamenthub.ru"),
                "FilamentHub URL",
            ),
            allow_http=allow_http,
        )
        directory = Path(os.getenv("FH_EDGE_STATE_DIRECTORY", "/data"))
        interval = _as_int(
            setting("FH_EDGE_SYNC_INTERVAL", "sync_interval"), default=30, minimum=15, maximum=3600
        )
        timeout = _as_int(
            setting("FH_EDGE_REQUEST_TIMEOUT", "request_timeout"), default=10, minimum=2, maximum=60
        )
        run_once = _as_bool(os.getenv("FH_EDGE_RUN_ONCE"))
        entries = options.get("connections", [])
        if not isinstance(entries, list) or len(entries) > MAX_CONNECTIONS:
            raise ConfigurationError(
                f"connections must be a list of at most {MAX_CONNECTIONS} items"
            )
        connections = []
        seen_ids: set[str] = set()
        seen_endpoints: set[tuple[str, str | None, int]] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ConfigurationError("each connection must be an object")
            if entry.keys() - {
                "id",
                "name",
                "enabled",
                "adapter",
                "material_provider",
                "moonraker_url",
                "moonraker_api_key",
                "pairing_code",
                "sync_interval",
            }:
                raise ConfigurationError("Unknown Edge connection options")
            identifier = _text(entry.get("id"), "connection id", maximum=64)
            if not CONNECTION_ID.fullmatch(identifier) or identifier in seen_ids:
                raise ConfigurationError("connection ids must be unique lowercase slugs")
            seen_ids.add(identifier)
            adapter = _text(entry.get("adapter", "moonraker"), "adapter", maximum=50)
            provider = _text(
                entry.get("material_provider", "happy_hare"), "material provider", maximum=50
            )
            endpoint = normalize_origin(
                _text(entry.get("moonraker_url"), "printer URL"), allow_http=True
            )
            parsed = urlsplit(endpoint)
            key = (
                parsed.scheme,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
            if key in seen_endpoints:
                raise ConfigurationError("a printer endpoint may appear only once in a node")
            seen_endpoints.add(key)
            connections.append(
                EdgeConfig(
                    connection_id=identifier,
                    name=_text(entry.get("name", identifier), "connection name", maximum=100)
                    or identifier,
                    enabled=_as_bool(entry.get("enabled"), default=True),
                    adapter=adapter,
                    filamenthub_url=origin,
                    pairing_code=_text(entry.get("pairing_code", ""), "pairing code", maximum=32)
                    or None,
                    material_provider=provider,
                    moonraker_url=endpoint,
                    moonraker_api_key=_text(
                        entry.get("moonraker_api_key", ""), "printer API key", maximum=4096
                    )
                    or None,
                    state_path=directory / "connections" / f"{identifier}.json",
                    sync_interval=_as_int(
                        entry.get("sync_interval"), default=interval, minimum=15, maximum=3600
                    ),
                    request_timeout=timeout,
                    allow_insecure_cloud=allow_http,
                    run_once=run_once,
                )
            )
        return cls(origin, directory, tuple(connections), run_once)
