"""Environment and Home Assistant option parsing."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

MAX_OPTIONS_BYTES = 64 * 1024


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
    raise ConfigurationError(f"invalid boolean value: {value!r}")


def _as_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"invalid integer value: {value!r}") from exc
    if parsed < minimum or parsed > maximum:
        raise ConfigurationError(f"integer value must be within {minimum}..{maximum}")
    return parsed


def _load_options(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        if path.stat().st_size > MAX_OPTIONS_BYTES:
            raise ConfigurationError("Home Assistant options file is too large")
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError("Home Assistant options file is invalid") from exc
    if not isinstance(decoded, dict):
        raise ConfigurationError("Home Assistant options must be a JSON object")
    return decoded


@dataclass(frozen=True)
class EdgeConfig:
    filamenthub_url: str
    pairing_code: str | None
    material_provider: str
    moonraker_url: str
    moonraker_api_key: str | None
    state_path: Path
    sync_interval: int
    request_timeout: int
    allow_insecure_cloud: bool
    run_once: bool

    @classmethod
    def load(cls) -> "EdgeConfig":
        options_path = Path(os.getenv("FH_EDGE_OPTIONS_FILE", "/data/options.json"))
        options = _load_options(options_path)

        def setting(env_name: str, option_name: str, default: Any = None) -> Any:
            env_value = os.getenv(env_name)
            return env_value if env_value is not None else options.get(option_name, default)

        material_provider = str(
            setting("FH_EDGE_MATERIAL_PROVIDER", "material_provider", "happy_hare")
        ).strip()
        if material_provider not in {"happy_hare", "legacy"}:
            raise ConfigurationError("material provider must be happy_hare or legacy")

        pairing_code = str(setting("FH_EDGE_PAIRING_CODE", "pairing_code", "")).strip()
        api_key = str(setting("FH_EDGE_MOONRAKER_API_KEY", "moonraker_api_key", "")).strip()
        state_path = Path(os.getenv("FH_EDGE_STATE_PATH", "/data/edge-state.json"))
        return cls(
            filamenthub_url=str(
                setting(
                    "FH_EDGE_FILAMENTHUB_URL",
                    "filamenthub_url",
                    "https://filamenthub.ru",
                )
            ).strip(),
            pairing_code=pairing_code or None,
            material_provider=material_provider,
            moonraker_url=str(
                setting(
                    "FH_EDGE_MOONRAKER_URL",
                    "moonraker_url",
                    "http://127.0.0.1:7125",
                )
            ).strip(),
            moonraker_api_key=api_key or None,
            state_path=state_path,
            sync_interval=_as_int(
                setting("FH_EDGE_SYNC_INTERVAL", "sync_interval"),
                default=30,
                minimum=15,
                maximum=3600,
            ),
            request_timeout=_as_int(
                setting("FH_EDGE_REQUEST_TIMEOUT", "request_timeout"),
                default=10,
                minimum=2,
                maximum=60,
            ),
            allow_insecure_cloud=_as_bool(
                setting("FH_EDGE_ALLOW_INSECURE_CLOUD", "allow_insecure_cloud"),
            ),
            run_once=_as_bool(os.getenv("FH_EDGE_RUN_ONCE"), default=False),
        )
